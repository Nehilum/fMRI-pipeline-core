import pandas as pd
import json
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import re
from itertools import groupby

# 引入核心模型
from neuro_mod.phase_bids.core.models import (
    ConversionEntry, 
    BidsTargetInfo, 
    ProcessStatus
)
# 引入新的 Adapter
from neuro_mod.phase_bids.core.mtaas.adapter import MtaasAdapter
# [Step 1] 引入 Schema
from neuro_mod.phase_bids.core.schema import AuditSchema

logger = logging.getLogger(__name__)

class MappingGenerator:
    """
    Phase 3: Mapping Logic (Simplified)
    职责：
    1. 强制加载 JSON Sidecar（如果 Phase 2 遗漏）。
    2. 时间解析：仅解析 Sidecar JSON 中的 AcquisitionTime，作为 Canonical Time。
    3. 基础结构映射：确定 Subject, Session, Experiment。
    4. 报告：生成用于后续步骤（Phase 3.5）的干净 Excel 清单。
    """

    def __init__(self, config: Dict):
        self.config = config
        
        # [Step 1] 实例化 Schema
        self.schema = AuditSchema(config)

        self.subject_map = config['mapping']['subject_mapping']
        self.resp_log_path = config['paths'].get('behavior_logs_summary', '')
        # 时间配置 (仅保留日期格式配置)
        self.time_cfg = config.get('time_config', {})
        self.date_fmt = self.time_cfg.get('folder_date_format', '%Y%m%d')

    def execute(self, entries: List[ConversionEntry]) -> Path:
        logger.info(f"Phase 3: Starting simplified mapping for {len(entries)} entries...")
        
        # ==============================================================================
        # 1. [强制补课逻辑] 确保 Sidecar Content 被加载
        # ==============================================================================
        self._ensure_sidecar_loaded(entries)
        
        # ==============================================================================
        # 2. [时间解析] 解析 Sidecar Time 作为 Canonical Time
        # ==============================================================================
        for entry in entries:
            self._resolve_canonical_time(entry)
            self._initial_guess_datatype(entry) # 新增：猜测 datatype
        # =========================================================
        # 2. MTAAS (只读模式)
        # =========================================================
        mtaas_results = {} # 默认为空字典
        if self.config.get('enable_mtaas', True):
            mtaas = MtaasAdapter(self.config)
            # 获取结果字典 {scan_id: MtaasResult}
            mtaas_results = mtaas.run_audit(entries) 
            
            # 生成 CSV 报告 (Adapter 内部状态)
            csv_path = Path(self.config['paths']['work_dir']) / "audit_truth_table_scans.csv"
            mtaas.generate_csv_report(csv_path)

        # ==============================================================================
        # 3. [排序] 基于 Subject 和 准确的 Sidecar 时间排序
        # ==============================================================================
        sorted_entries = sorted(entries, key=lambda e: (
            e.source.identity.subject_id_raw,
            e.time_meta.canonical_timestamp or datetime.max
        ))

        # ==============================================================================
        # 4. [生成 Excel] 计算 Session 并写入基础信息
        # ==============================================================================
        excel_rows = []
        
        # 按原始 Subject 分组处理
        for subj_raw, subj_group in groupby(sorted_entries, key=lambda x: x.source.identity.subject_id_raw):
            subj_entries = list(subj_group)
            
            if subj_raw not in self.subject_map:
                logger.warning(f"Subject {subj_raw} not in mapping config. Skipping.")
                continue

            # 获取映射配置信息
            bids_subj_info = self.subject_map[subj_raw]
            bids_id = bids_subj_info['bids_id']          # 对应 Excel: Subject_ID_BIDS
            exp_id = bids_subj_info['experiment_id']     # 对应 Excel: Experiment_ID

            # 计算 Session：基于 date_folder 的唯一值排序
            dates = sorted(list(set(e.source.identity.date_folder for e in subj_entries)))
            
            for entry in subj_entries:
                # 跳过处理失败的条目
                if entry.status == ProcessStatus.FAILED:
                    continue

                # --- Session 确定 ---
                date_str = entry.source.identity.date_folder
                try:
                    ses_num = dates.index(date_str) + 1
                    ses_label = f"ses-{ses_num:02d}"     # 对应 Excel: BIDS_Session
                except ValueError:
                    ses_label = "ses-unknown"

                # --- 提取 Protocol Name (不做任何猜测，仅提取) ---
                sidecar = entry.nifti_pool.sidecar_content if entry.nifti_pool else {}
                protocol_name = sidecar.get("ProtocolName", "")
                # 如果 ProtocolName 为空，尝试用 SeriesDescription 兜底，方便人工查看
                if not protocol_name:
                    protocol_name = sidecar.get("SeriesDescription", "")

                # --- 写入 Excel 行 ---
                self._append_excel_row(excel_rows, entry, bids_id, exp_id, ses_label, protocol_name, mtaas_results)

        # 5. 导出 Excel
        df = pd.DataFrame(excel_rows)
        draft_filename = self.config['paths'].get('audit_draft_filename', "audit_sheet_auto.xlsx")
        output_xlsx = Path(self.config['paths']['work_dir']) / draft_filename
        
        # [Step 2] 调整列顺序，使用 Schema 定义的列名
        cols = [
            self.schema.col.subject_bids, 
            self.schema.col.session_bids, 
            self.schema.col.scan_id, 
            self.schema.col.behavior_filename,
            self.schema.col.inclusion_status, 
            self.schema.col.decision_source, 
            self.schema.col.decision_rationale,
            self.schema.col.discard_prefix
        ]
        
        # 确保剩余列也在
        all_cols = cols + [c for c in df.columns if c not in cols]
        df = df[all_cols]
        
        df.to_excel(output_xlsx, index=False)
        logger.info(f"Generated Audit Draft: {output_xlsx}")
        return output_xlsx
    
    def _ensure_sidecar_loaded(self, entries: List[ConversionEntry]):
        """辅助函数：检查并从硬盘重新加载 JSON 内容"""
        fixed_count = 0
        for entry in entries:
            if not entry.nifti_pool or not entry.nifti_pool.files:
                continue
            
            # 如果内容为空，尝试寻找 json 文件读取
            if not entry.nifti_pool.sidecar_content:
                json_files = [f for f in entry.nifti_pool.files if str(f).lower().endswith('.json')]
                if json_files:
                    try:
                        with open(json_files[0], 'r', encoding='utf-8') as jf:
                            entry.nifti_pool.sidecar_content = json.load(jf)
                            fixed_count += 1
                    except Exception as e:
                        logger.error(f"Failed to reload JSON for {entry.id}: {e}")
        
        if fixed_count > 0:
            logger.info(f"Reloaded JSON content for {fixed_count} entries.")

    def _resolve_canonical_time(self, entry: ConversionEntry):
        """
        [核心逻辑] 仅解析 Sidecar 中的时间。
        策略：无论格式是 HH:MM:SS.ffffff 还是 HHMMSS.fff，都统一解析为 datetime 对象。
        """
        meta = entry.time_meta
        date_folder = entry.source.identity.date_folder
        
        # 1. 提取日期部分 (YYYYMMDD)
        clean_date = None
        date_match = re.search(r"(20\d{2})[-]?(\d{2})[-]?(\d{2})", date_folder)
        if date_match:
            clean_date = "".join(date_match.groups())
        else:
            clean_date = date_folder # 假设本来就是纯数字

        # 2. 获取并清洗时间字符串
        acq_time = meta.sidecar_acq_time # 来源可能是 float 或 str
        sidecar_dt = None

        if acq_time is not None and clean_date:
            try:
                acq_str = str(acq_time).strip()
                
                hh, mm, ss, ms = "00", "00", "00", "000000"
                
                # --- 分支 A: 带冒号 (10:57:02.500) ---
                if ":" in acq_str:
                    parts = acq_str.split(":")
                    if len(parts) >= 3:
                        hh = parts[0]
                        mm = parts[1]
                        ss_part = parts[2]
                        if "." in ss_part:
                            ss, ms_raw = ss_part.split(".")
                            ms = ms_raw
                        else:
                            ss = ss_part
                
                # --- 分支 B: 纯数字 (105702.500) ---
                else:
                    if "." in acq_str:
                        time_part, ms_raw = acq_str.split(".")
                        ms = ms_raw
                    else:
                        time_part, ms = acq_str, "0"
                    
                    # 补全左侧 0 (930 -> 000930, 93005 -> 093005)
                    # dcm2niix 有时会去除前导零
                    time_part = time_part.zfill(6)
                    hh = time_part[0:2]
                    mm = time_part[2:4]
                    ss = time_part[4:6]

                # --- 统一标准化 ---
                hh = hh.zfill(2)
                mm = mm.zfill(2)
                ss = ss.zfill(2)
                
                # 微秒必须是 6 位
                # 277 -> 277000 (左对齐)
                # 27750055 -> 277500 (截断)
                ms = (ms + "000000")[:6]

                # --- 组合 ---
                dt_str = f"{clean_date}{hh}{mm}{ss}{ms}"
                sidecar_dt = datetime.strptime(dt_str, "%Y%m%d%H%M%S%f")
                
                # 成功解析
                meta.canonical_timestamp = sidecar_dt
                meta.time_source = "sidecar"
                meta.quality_flag = "OK"

            except Exception as e:
                logger.warning(f"Time Parse Error for {entry.id} (Val: {acq_time}): {e}")
                meta.canonical_timestamp = None
                meta.quality_flag = "BAD_PARSE"
        else:
            meta.canonical_timestamp = None
            meta.quality_flag = "MISSING_TIME"

    def _append_excel_row(self, rows, entry, bids_id, exp_id, ses_label, protocol_name, mtaas_results):
        """
        构建 Excel 行，仅包含基础信息和时间，不包含猜测结果。
        """
        ts = entry.time_meta.canonical_timestamp
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.%f") if ts else "N/A"
        
        # === [关键] 从字典查结果，而不是从 entry 读属性 ===
        # 如果查不到（比如非 func），就给个默认空结果
        res = mtaas_results.get(entry.id)

        # 逻辑：MTAAS 是否成功匹配
        mtaas_status = getattr(res, 'status', "")
        offset = getattr(res, 'offset', "")
        comments = getattr(res, 'comments', "")
        is_matched = getattr(res, 'is_matched', False)
        
        # 修复 Task_Name 空值问题：不要读 entry.target.task，要读 res.task_name
        auto_task = getattr(res, 'task_name', "") 
        beh_filename = getattr(res, 'filename', "")

        # 1. 安全获取 datatype (防止 entry.target.datatype 为 None)
        current_dtype = entry.target.datatype if entry.target.datatype else None
        
        # 2. 初始化变量
        # [Step 3] 替换 Status 值
        final_status = self.schema.status.exclude      # 默认 Exclude，以此为基准修改
        final_rationale = ""
        
        # 3. 分支判断逻辑
        if not current_dtype:
            # --- 情况 A: Discard 或 空值 ---
            final_status = self.schema.status.exclude
            final_rationale = "Datatype is unknown"
        elif current_dtype == self.schema.dtype.discard or current_dtype == self.schema.dtype.derived:
            # --- 情况 A: Discard ---
            final_status = self.schema.status.exclude
            final_rationale = f"Marked as '{current_dtype}' by dcm2niix"
        elif current_dtype == self.schema.dtype.func:
            # --- 情况 B: 功能像 (func) ---
            # 逻辑：必须依赖 MTAAS 的匹配结果
            final_status = self.schema.status.include if is_matched else self.schema.status.exclude
            # 逻辑：直接使用 MTAAS 返回的 comments (例如: "Matched successfully", "No behavior file")
            final_rationale = comments 
        else:
            # --- 情况 C: 其他类型 (anat, fmap, dwi, etc.) ---
            # 逻辑：默认纳入，不需要行为文件
            final_status = self.schema.status.include
            final_rationale = f"{current_dtype} scan, no behavior file needed"

        rows.append({
            # [Step 2] 替换 Excel 列名 Keys
            # --- ID & BIDS Info (User Requested) ---
            self.schema.col.scan_id: entry.id,
            self.schema.col.experiment_id: exp_id,          # [Requested]
            
            # --- Source Data ---
            self.schema.col.protocol_name: protocol_name,
            self.schema.col.subject_raw: entry.source.identity.subject_id_raw,
            self.schema.col.date_folder: entry.source.identity.date_folder,
            
            # --- Time Info ---
            self.schema.col.canonical_timestamp: ts_str,
            self.schema.col.sidecar_time_raw: str(entry.time_meta.sidecar_acq_time),
            
            self.schema.col.subject_bids: bids_id,       # [Requested]
            self.schema.col.session_bids: ses_label,        # [Requested]

            # --- Phase 3.5 Placeholders (Optional but helpful) ---
            
            # --- Target (Auto-filled by MTAAS) ---
            self.schema.col.task_name_audit: auto_task,  # 如果匹配了，这里会有值
            self.schema.col.behavior_filename: beh_filename,
            self.schema.col.inclusion_status: final_status,
            self.schema.col.decision_source: "Auto",
            self.schema.col.decision_rationale: final_rationale,

            # # --- Debug Info ---
            self.schema.col.mtaas_status: mtaas_status,
            self.schema.col.mtaas_offset: offset,
            self.schema.col.discard_prefix: ""
        })

    def _initial_guess_datatype(self, entry: ConversionEntry):
        """
        利用 dcm2niix 生成的 BidsGuess 字段直接推断 datatype。
        
        Example BidsGuess in JSON:
          ["func", "_acq-epfid2m6_dir-AP_run-11_bold"] -> datatype="func"
          ["fmap", "_acq-fm2_magnitude1"]              -> datatype="fmap"
          ["discard", "..."]                           -> datatype="discard"
        """
        # 1. 安全检查：确保 Sidecar 内容存在
        if not entry.nifti_pool or not entry.nifti_pool.sidecar_content:
            return
        # =======================================================
        # [Fix] 确保 target 对象已初始化
        # =======================================================
        if entry.target is None:
            entry.target = BidsTargetInfo(
                sub_id="",      # 必填：先给空字符串，Phase 3b 会填充
                ses_id="",      # 必填
                datatype="",    # 必填：马上就会被覆盖
                suffix=""       # 必填
            )
        # 2. 获取 BidsGuess 字段
        bids_guess = entry.nifti_pool.sidecar_content.get("BidsGuess")

        # 3. 解析并赋值
        # BidsGuess 通常是一个列表: [datatype, suffix_string]
        if bids_guess and isinstance(bids_guess, list) and len(bids_guess) > 0:
            dtype = bids_guess[0]  # 提取第一个元素 (e.g., "func", "anat")
            
            # 直接赋值给 entry.target
            entry.target.datatype = dtype
            
            # 日志记录 (可选，方便调试)
            # logger.debug(f"Scan {entry.id}: inferred datatype '{dtype}' from BidsGuess")
        else:
            # 如果没有 BidsGuess，保持默认为 None，或者在此处做 fallback
            # 通常 dcm2niix 较新版本都会生成此字段
            pass