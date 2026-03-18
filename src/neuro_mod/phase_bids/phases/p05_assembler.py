import os
import json
import yaml
import shutil
import logging
import pandas as pd
from pathlib import Path
from neuro_mod.phase_bids.core.schema import AuditSchema  # Step 1: 引入 Schema

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Phase5_Assembler")

class Assembler:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_yaml(config_path)
        self.schema = AuditSchema(self.config)  # Step 1: 实例化 schema 对象
        
        # 路径定义
        self.bids_root = Path(self.config['paths']['bids_output_dir'])
        self.excel_path = Path(self.config['paths']['work_dir'])/self.config['paths']['audit_final_filename']
        self.events_source = Path(self.config['paths'].get('events_source', ''))
        
        # 必须存在的文件
        self.intended_for_json_path = Path(self.config['paths']['work_dir'])/self.config['paths']['intended_for_filename']
        
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Audit Excel not found: {self.excel_path}")

    def _load_yaml(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def load_resources(self):
        """加载 Phase 3 的所有产出物"""
        logger.info("Loading Phase 3 execution plan...")
        
        # 1. 加载 Excel 执行表
        self.df = pd.read_excel(self.excel_path)
        # 确保关键列存在 (根据你提供的 Phase 3 表头)
        # Step 2: 替换列名
        required_cols = [
            self.schema.col.source_path_abs,
            self.schema.col.source_json_abs,
            self.schema.col.bids_path,
            self.schema.col.task_name_audit,
            self.schema.col.datatype
        ]
        if not all(col in self.df.columns for col in required_cols):
            raise ValueError(f"Excel 缺少必要列: {required_cols}")

        # 2. 加载 IntendedFor 映射表
        # 格式: {"sub-01/.../fmap/xxx.nii.gz": ["ses-01/func/xxx.nii.gz", ...]}
        self.fmap_map = {}
        if self.intended_for_json_path.exists():
            with open(self.intended_for_json_path, 'r', encoding='utf-8') as f:
                self.fmap_map = json.load(f)
        else:
            logger.warning(f"IntendedFor map not found at {self.intended_for_json_path}. Fmaps will not be linked.")

    def transfer_file(self, src: Path, dst: Path):
        """通用的文件复制函数"""
        try:
            if not src.exists():
                logger.warning(f"Source file missing: {src}")
                return False
            
            # 确保父目录存在 (虽然 Phase 4 建过，但防呆)
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            shutil.copy2(src, dst)
            return True
        except Exception as e:
            logger.error(f"Copy failed: {src} -> {dst}: {e}")
            return False

    def patch_json_sidecar(self, json_path: Path, row: pd.Series, rel_bids_path: str):
        """
        修补 JSON 元数据
        包含: IntendedFor, TaskName
        """
        if not json_path.exists():
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            is_modified = False

            # === A. 注入 IntendedFor (查表法) ===
            # 使用 BIDS 相对路径作为 Key 去 Map 里找
            if rel_bids_path in self.fmap_map:
                data['IntendedFor'] = self.fmap_map[rel_bids_path]
                is_modified = True
                logger.info(f"  -> Injected IntendedFor targets for {json_path.name}")

            # === B. 注入 TaskName (如果是 Func) ===
            # BIDS 要求 func 必须有 TaskName。如果 dcm2niix 没生成，我们补上。
            # Step 2 & 3: 替换列名和状态值
            if row[self.schema.col.datatype] == self.schema.dtype.func and pd.notna(row[self.schema.col.task_name_audit]):
                if 'TaskName' not in data:
                    data['TaskName'] = str(row[self.schema.col.task_name_audit])
                    is_modified = True

            # === C. 保存修改 ===
            if is_modified:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)

        except Exception as e:
            logger.error(f"Failed to patch JSON {json_path}: {e}")

    def process_events(self, bold_dst_path: Path):
        """
        处理 Events 文件
        逻辑: 已知 BOLD 路径 -> 替换后缀 -> 检查 Source -> 复制
        """
        if not self.events_source.exists():
            return

        # 1. 构造目标文件名: ..._bold.nii.gz -> ..._events.tsv
        # BIDS 规则: 除了后缀，前缀必须完全一致
        events_name = bold_dst_path.name.replace('_bold.nii.gz', '_events.tsv')
        
        # 2. 构造源文件路径
        # 假设源文件都在 self.events_source 这个扁平文件夹里，且已经命好名了
        src_event = self.events_source / events_name
        
        # 3. 构造目标路径 (和 bold 在同一个文件夹)
        dst_event = bold_dst_path.parent / events_name

        if src_event.exists():
            shutil.copy2(src_event, dst_event)
            logger.info(f"  -> Linked Event file: {events_name}")
        else:
            # 这是一个常见的警告，未必是错误（有的 run 可能没有行为数据）
            logger.debug(f"  -> No event file found for {bold_dst_path.name}")

    def run(self):
        logger.info("Starting Phase 5: Assembly (The Executioner)")
        self.load_resources()

        success_count = 0
        
        # === 核心循环: 遍历 Excel 每一行 ===
        # 不需要 GroupBy，不需要 Sort，直接线性执行
        for idx, row in self.df.iterrows():
            
            # 0. 检查是否跳过 ( NaN path or Excluded )
            bids_path_raw = row.get(self.schema.col.bids_path)
            status = str(row.get(self.schema.col.inclusion_status, "")).lower()
            if pd.isna(bids_path_raw) or status != self.schema.status.include.lower():
                continue

            # 1. 准备路径
            src_nii_raw = row.get(self.schema.col.source_path_abs)
            if pd.isna(src_nii_raw):
                continue
                
            src_nii = Path(str(src_nii_raw))
            
            src_json_raw = row.get(self.schema.col.source_json_abs)
            src_json = Path(str(src_json_raw)) if pd.notna(src_json_raw) else None
            
            rel_path = str(bids_path_raw)
            dst_nii = self.bids_root / rel_path
            dst_json = dst_nii.with_suffix('').with_suffix('.json') # 确保 json 和 nii 同名

            # 2. 复制 NIfTI
            if self.transfer_file(src_nii, dst_nii):
                success_count += 1
                
                # 3. 复制并修补 JSON
                if src_json and src_json.exists():
                    self.transfer_file(src_json, dst_json)
                    self.patch_json_sidecar(dst_json, row, rel_path)
                
                # 4. 如果是 BOLD，顺手查一下 Events
                # Step 2 & 3: 替换列名和状态值
                if row[self.schema.col.datatype] == self.schema.dtype.func:
                    self.process_events(dst_nii)

        logger.info(f"Phase 5 Completed. Processed {success_count} files.")

if __name__ == "__main__":
    assembler = Assembler()
    assembler.run()