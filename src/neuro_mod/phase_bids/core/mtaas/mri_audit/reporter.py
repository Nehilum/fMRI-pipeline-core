# src/mri_audit/reporter.py
import pandas as pd
from typing import List, Dict
from datetime import date
from .models import AuditBucket
from .verdict import VerdictResult, VerdictJudge
from ..temporal_matcher.models import MatchResult

class AuditReporter:
    def __init__(self):
        self.scan_records = []
        self.bucket_records = []

    def add_result(self, bucket: AuditBucket, result: MatchResult, verdict: VerdictResult):
        # ... (Bucket Summary 部分代码略，逻辑中计算 global offset 也要用 end_timestamp)
        
        # Scan Level Logic
        match_map = {i: j for i, j in result.pairs}
        
        for i, m_evt in enumerate(bucket.mri_events):
            rec = {
                "Subject_Key": bucket.subject_key,
                "Date": bucket.date_key,
                "Scan_ID": m_evt.scan_id,
                "Machine_Timestamp": m_evt.datetime_obj, # 依然显示开始时间，方便人类核对
                "Duration_Sec": m_evt.duration,          # 新增列：显示解析出的时长
                "Calculated_End_Time": m_evt.datetime_obj.timestamp() + m_evt.duration, # 方便Debug
                "Verdict": verdict.status,
                "Note": ""
            }
            
            if i in match_map:
                j = match_map[i]
                r_evt = bucket.resp_events[j]
                
                # --- 关键修改 ---
                # Offset 计算基于 End Time vs End Time
                # 这样 Offset_Sec 应该是一个稳定的常数
                offset = m_evt.end_timestamp - r_evt.timestamp
                
                rec.update({
                    "Matched_Selected_File": r_evt.filename,
                    "Response_Timestamp": r_evt.datetime_obj,
                    "Offset_Sec": offset, # (MRI_End - Resp_End)
                    "Match_Type": "MATCHED"
                })
            else:
                # MRI Only
                rec.update({
                    "Matched_Selected_File": None,
                    "Response_Timestamp": None,
                    "Offset_Sec": None,
                    "Match_Type": "MRI_ONLY"
                })
                rec["Note"] = "MRI without response"
            
            self.scan_records.append(rec)
            
        # B. 处理 RESP Only (没有匹配到任何 MRI 的)
        # 这些行 Scan_ID 为空，提醒用户有额外文件
        for j in result.unmatched_target:
            r_evt = bucket.resp_events[j]
            rec = {
                "Subject_Key": bucket.subject_key,
                "Date": bucket.date_key,
                "Scan_ID": None, # No MRI
                "Machine_Timestamp": None,
                "Matched_Selected_File": r_evt.filename,
                "Response_Timestamp": r_evt.datetime_obj,
                "Verdict": verdict.status,
                "Match_Type": "RESP_ONLY",
                "Note": "Response file unused"
            }
            self.scan_records.append(rec)

    def save_reports(self, output_dir: str):
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        df_scan = pd.DataFrame(self.scan_records)
        df_bucket = pd.DataFrame(self.bucket_records)
        
        # 调整列顺序
        scan_cols = ["Subject_Key", "Date", "Scan_ID", "Machine_Timestamp", 
                     "Matched_Selected_File", "Response_Timestamp", 
                     "Offset_Sec", "Verdict", "Match_Type", "Note"]
        # 仅保留存在的列
        final_scan_cols = [c for c in scan_cols if c in df_scan.columns]
        df_scan = df_scan[final_scan_cols]

        df_scan.to_csv(os.path.join(output_dir, "audit_truth_table_scans.csv"), index=False)
        df_bucket.to_csv(os.path.join(output_dir, "audit_summary_buckets.csv"), index=False)
        
        print(f"Reports saved to {output_dir}")

    # --- 新增方法开始 ---
    def export_updated_excel(self, source_excel_path: str, output_excel_path: str):
        """
        读取原始 Excel，将审计匹配到的行为文件回填到 Matched_Behavior 列。
        """
        try:
            df = pd.read_excel(source_excel_path)
        except Exception as e:
            print(f"[Error] Failed to read source Excel: {e}")
            return

        # 1. 构建映射字典: Scan_ID -> Matched_Selected_File
        # 仅提取 Match_Type 为 MATCHED 的记录
        scan_map = {}
        for rec in self.scan_records:
            if rec.get("Match_Type") == "MATCHED" and rec.get("Scan_ID"):
                # 确保 Scan_ID 转为字符串，防止 Excel 中是数字格式导致匹配失败
                scan_map[str(rec["Scan_ID"])] = rec["Matched_Selected_File"]
        
        print(f"Preparing to backfill {len(scan_map)} matched records into Excel...")

        # 2. 准备列
        if "Matched_Behavior" not in df.columns:
            df["Matched_Behavior"] = None
            
        # --- 🔴 新增这行代码来修复警告 ---
        # 强制将该列转换为 object 类型 (支持字符串)，防止 float64 冲突
        df["Matched_Behavior"] = df["Matched_Behavior"].astype("object")
        # --------------------------------

        # 3. 执行回填
        # 将 Excel 中的 Scan_ID 转为字符串用于查找
        source_scan_ids = df["Scan_ID"].astype(str)
        
        # map返回一个 Series，包含匹配到的文件名（未匹配到的为 NaN）
        mapped_values = source_scan_ids.map(scan_map)
        
        # 仅更新那些在审计中找到了匹配文件的行
        # (mapped_values.notna() 确保我们不会把原本可能有手动填写的行误覆盖为空，
        #  虽然按理说原本是空的，但这样写更安全)
        df.loc[mapped_values.notna(), "Matched_Behavior"] = mapped_values[mapped_values.notna()]

        # 4. 保存结果
        try:
            df.to_excel(output_excel_path, index=False)
            print(f"✅ Updated Excel with Matched_Behavior saved to:\n   {output_excel_path}")
        except Exception as e:
            print(f"[Error] Failed to save updated Excel: {e}")
    # --- 新增方法结束 ---