import os
import json
import yaml
import shutil
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from neuro_mod.phase_bids.core.schema import AuditSchema  # [Added] 引入 Schema 类

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SkeletonCreator:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = self._load_config(config_path)
        
        # [Added] 初始化 Schema
        self.schema = AuditSchema(self.config)
        
        self.bids_root = Path(self.config['paths']['bids_output_dir'])
        self.excel_path = Path(self.config['paths']['work_dir'])/self.config['paths']['audit_final_filename']
        
        # 确保输出根目录存在
        self.bids_root.mkdir(parents=True, exist_ok=True)

    def _load_config(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def load_audit_excel(self) -> pd.DataFrame:
        if not self.excel_path.exists():
            raise FileNotFoundError(f"Audit Excel not found at {self.excel_path}. Please run Phase 3 first.")
        
        df = pd.read_excel(self.excel_path)
        # 过滤：只保留状态为 'Include' 的行
        # [Modified] 使用 schema.col.inclusion_status 和 schema.status.include
        if self.schema.col.inclusion_status in df.columns:
            original_count = len(df)
            df = df[df[self.schema.col.inclusion_status] == self.schema.status.include].copy()
            logger.info(f"Loaded Excel. Filtered from {original_count} to {len(df)} rows based on {self.schema.col.inclusion_status}.")
        else:
            logger.warning(f"'{self.schema.col.inclusion_status}' column not found in Excel. Processing ALL rows.")
        return df

    def create_directory_structure(self, df: pd.DataFrame):
        """
        根据 Excel 中的 'BIDS_Path' 列创建目录树
        """
        logger.info("Building directory skeleton...")
        
        # --- [修改开始] ---
        # 检查列是否存在
        # [Modified] 使用 schema.col.bids_path
        if self.schema.col.bids_path not in df.columns:
            logger.error(f"Column '{self.schema.col.bids_path}' missing. Cannot build structure.")
            return

        # 提取唯一的父目录路径
        # Excel中的 BIDS_Path 包含文件名 (e.g., sub-01/func/sub-01_task-rest_bold.nii.gz)
        # 我们需要去掉文件名，只保留目录部分
        # [Modified] 使用 schema.col.bids_path
        unique_dirs = df[self.schema.col.bids_path].dropna().apply(lambda x: os.path.dirname(x)).unique()
        # --- [修改结束] ---

        count = 0
        for rel_path in unique_dirs:
            # 拼接完整路径
            full_path = self.bids_root / rel_path
            if not full_path.exists():
                full_path.mkdir(parents=True, exist_ok=True)
                count += 1
        
        logger.info(f"Created {count} new directories.")

    def generate_dataset_description(self):
        """
        生成 dataset_description.json
        """
        logger.info("Generating dataset_description.json...")
        
        meta = self.config['bids_metadata']['description']
        output_file = self.bids_root / "dataset_description.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=4)

    def generate_participants_tsv(self, df: pd.DataFrame):
        """
        从 Excel 中提取被试信息生成 participants.tsv
        """
        logger.info("Generating participants.tsv...")
        
        # [Modified] 使用 schema 获取列名
        bids_col = self.schema.col.subject_bids
        raw_col = self.schema.col.subject_raw

        # 1. 检查 Excel 中是否有必要的列
        if bids_col not in df.columns or raw_col not in df.columns:
            logger.warning(f"Columns '{bids_col}' or '{raw_col}' missing. Skipping participants.tsv.")
            return

        # 2. 提取唯一被试 (基于 BIDS ID 去重，同时保留 Raw ID 用于查 Config)
        # 注意：这里假设同一个 BIDS ID 对应的 Raw ID 是一样的
        subjects_df = df[[bids_col, raw_col]].drop_duplicates(subset=[bids_col]).copy()
        
        # 3. 准备存储列表
        participants_data = []
        
        # 加载 config 中的 mapping 字典
        mapping_dict = self.config.get('mapping', {}).get('subject_mapping', {})

        for _, row in subjects_df.iterrows():
            b_id = row[bids_col]
            r_id = row[raw_col]
            
            # 确保 BIDS ID 格式正确 (sub-前缀)
            p_id = b_id if str(b_id).startswith('sub-') else f"sub-{b_id}"
            
            # 初始化数据行
            entry = {
                'participant_id': p_id,
                'age': 'n/a',
                'sex': 'n/a'
            }
            
            # 4. 从 Config 中查找信息
            if r_id in mapping_dict:
                user_info = mapping_dict[r_id]
                # 获取 age, 默认为 'n/a'
                entry['age'] = user_info.get('age', 'n/a')
                # 获取 sex, 默认为 'n/a'
                entry['sex'] = user_info.get('sex', 'n/a')
            else:
                logger.warning(f"Raw ID {r_id} (for {p_id}) not found in Config mapping.")
            
            participants_data.append(entry)
            
        # 5. 生成 DataFrame
        final_df = pd.DataFrame(participants_data)
        
        # 6. 保存 TSV
        output_file = self.bids_root / "participants.tsv"
        # 指定列顺序，符合 BIDS 习惯
        final_df = final_df[['participant_id', 'age', 'sex']] 
        final_df.to_csv(output_file, sep='\t', index=False)
        
        # 7. 生成对应的 JSON Sidecar (更新元数据描述)
        json_file = self.bids_root / "participants.json"
        json_content = {
            "participant_id": {
                "Description": "Unique participant identifier"
            },
            "age": {
                "Description": "Age of the participant at the time of scanning",
                "Units": "years"
            },
            "sex": {
                "Description": "Sex of the participant",
                "Levels": {
                    "M": "male",
                    "F": "female",
                    "O": "other"
                }
            }
        }
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, indent=4)
            
        logger.info(f"participants.tsv created with {len(final_df)} entries.")

    def generate_task_json(self):
        """
        根据 Config 生成根目录下的 task-<name>_bold.json
        """
        logger.info("Generating task json sidecars...")
        
        tasks = self.config['bids_metadata']['tasks']
        
        for task_key, task_meta in tasks.items():
            # 文件名例如: task-per_bold.json
            filename = f"task-{task_key}_bold.json"
            output_file = self.bids_root / filename
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(task_meta, f, indent=4)
                
            logger.info(f"Generated {filename}")

    def run(self):
        df = self.load_audit_excel()
        
        # 1. 创建文件夹
        self.create_directory_structure(df)
        
        # 2. 生成 BIDS 全局文件
        self.generate_dataset_description()
        self.generate_participants_tsv(df)
        self.generate_task_json()
        
        logger.info("Phase 4 (Skeleton & Metadata) completed successfully.")

if __name__ == "__main__":
    creator = SkeletonCreator()
    creator.run()