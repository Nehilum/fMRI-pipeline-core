"""
bids_converter/phases/p01_raw_ingest.py
Phase 1: Raw Ingest
负责将各种各样的原始物理介质（ZIP, 乱序文件夹等）标准化为统一的 DICOM 目录结构。
"""

import zipfile
import shutil
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Generator
import re

# 引入核心模型
from neuro_mod.phase_bids.core.models import ConversionEntry, SeriesIdentity, DicomArtifacts, SeriesRecord, ProcessStatus

logger = logging.getLogger(__name__)

class IngestStrategy(ABC):
    """
    [扩展接口] 所有的解压/整理逻辑必须继承此类。
    """
    def __init__(self, source_root: Path, target_dicom_root: Path):
        self.source_root = source_root
        self.target_root = target_dicom_root

    @abstractmethod
    def run(self) -> List[ConversionEntry]:
        """
        执行整理逻辑，返回生成的 ConversionEntry 列表（仅填充 Source 部分）。
        """
        pass

class StandardZipStrategy(IngestStrategy):
    """
    [当前实现] 对应原 unzip_dicom.py 逻辑。
    适用结构: raw/{Subject}/{Session}/{Scan}/*.zip
    目标结构: dicom/{Subject}/{Session}/{Scan}/*.dcm
    """
    
    def run(self) -> List[ConversionEntry]:
        entries = []
        
        if not self.source_root.exists():
            logger.error(f"Source root not found: {self.source_root}")
            return []

        # 遍历 Subject
        for subject_dir in [d for d in self.source_root.iterdir() if d.is_dir()]:
            # 遍历 Session (Date Folder)
            for session_dir in [d for d in subject_dir.iterdir() if d.is_dir()]:
                # 遍历 Scan
                for scan_dir in [d for d in session_dir.iterdir() if d.is_dir()]:
                    
                    # 寻找 ZIP 文件
                    zip_files = list(scan_dir.glob("*.zip"))
                    if not zip_files:
                        continue
                    
                    # 假设一个 Scan 目录下只有一个 ZIP，或者处理所有 ZIP
                    for zip_path in zip_files:
                        try:
                            # 1. 计算标准化的目标路径
                            # 结构保持: Subject/Session/Scan
                            target_scan_dir = self.target_root / subject_dir.name / session_dir.name / scan_dir.name
                            
                            # 如果目标非空，可能是已处理过，可以选择跳过或覆盖
                            # 这里演示覆盖逻辑，先清理
                            if target_scan_dir.exists():
                                shutil.rmtree(target_scan_dir)
                            target_scan_dir.mkdir(parents=True, exist_ok=True)
                            
                            # 2. 解压处理
                            self._extract_and_flatten(zip_path, target_scan_dir)
                            
                            # 3. 创建 Source Info 
                            # 从 ZIP 文件名提取粗略时间 (用于 Phase 3 的双重验证)
                            # 假设文件名类似: BOLD_...20240306155138855...
                            # 使用 config 中的正则或默认正则
                            time_pattern = r"(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})"
                            match = re.search(time_pattern, zip_path.name)
                            
                            zip_time_extracted = ""
                            if match:
                                # 提取 HHMMSS (Group 4, 5, 6)
                                # match.groups() -> ('2024', '03', '06', '15', '51', '38')
                                zip_time_extracted = "".join(match.groups()[3:6]) # -> "155138"
                            else:
                                logger.warning(f"Could not extract time from zip name: {zip_path.name}")

                            # 创建 Identity
                            identity = SeriesIdentity(
                                subject_id_raw=subject_dir.name,
                                date_folder=session_dir.name,
                                scan_folder=scan_dir.name,
                                time_str_raw=zip_time_extracted # <--- 将提取的时间放入 identity (可选)
                            )

                            dicom = DicomArtifacts(
                                dicom_path=target_scan_dir
                            )

                            source_info = SeriesRecord(
                                identity=identity,
                                dicom=dicom,
                                nifti_pool=None   # Phase 1 还没做 NIfTI
                            )

                            # 4. 创建 Entry
                            entry_id = f"{subject_dir.name}_{session_dir.name}_{scan_dir.name}"
                            # entries.append(ConversionEntry(id=entry_id, source=source_info))
                            
                            # logger.info(f"Ingested: {entry_id}")
                            # === [新增/修改 START] ===
                            entry = ConversionEntry(id=entry_id, source=source_info)
                            
                            # 显式填入 TimeMetadata
                            entry.time_meta.zip_time_raw = zip_time_extracted
                            
                            entries.append(entry)
                            # === [新增/修改 END] ===
                            
                            logger.info(f"Ingested: {entry_id} (Time: {zip_time_extracted})")

                        except Exception as e:
                            logger.error(f"Failed to ingest {zip_path}: {e}")
                            # 即使失败也不中断整个循环
        return entries

    def _extract_and_flatten(self, zip_path: Path, target_dir: Path):
        """
        解压 ZIP 并将内部深层嵌套的 DICOM 文件移动到 target_dir 根部 (Flatten)。
        对应原脚本中的 os.walk + shutil.move 逻辑。
        """
        temp_extract_path = target_dir / "temp_unzip"
        temp_extract_path.mkdir(exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_path)
            
            # 遍历解压后的目录，将文件移动到上一级
            for file_path in temp_extract_path.rglob("*"):
                if file_path.is_file() and not file_path.name.startswith("."):
                    # 可以在此增加 .dcm 后缀检查，原脚本似乎没有强校验后缀，只校验了 ZIP
                    shutil.move(str(file_path), str(target_dir / file_path.name))
                    
        finally:
            # 清理临时目录
            if temp_extract_path.exists():
                shutil.rmtree(temp_extract_path)

def get_ingestor(config: dict) -> IngestStrategy:
    """工厂方法：根据配置返回对应的策略"""
    source = Path(config['paths']['raw_data_dir'])
    target = Path(config['paths']['dicom_dir'])
    
    # 将来可以在 config 中增加 'ingest_strategy' 字段来切换
    # 目前默认返回 StandardZipStrategy
    return StandardZipStrategy(source, target)