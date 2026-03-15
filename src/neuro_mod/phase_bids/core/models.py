"""
bids_converter/core/models.py
核心数据模型定义。
该模块定义了在 Pipeline 中流转的标准数据对象，
替代了原脚本中散落在 dict、DataFrame 和 hardcoded 变量中的状态。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum
from pathlib import Path
from datetime import datetime

class ProcessStatus(Enum):
    """用于跟踪处理状态"""
    PENDING = "pending"
    SKIPPED = "skipped"
    SUCCESS = "success"
    FAILED = "failed"

@dataclass
class SeriesIdentity:
    subject_id_raw: str
    date_folder: str
    scan_folder: str
    scan_time: Optional[datetime] = None
    time_str_raw: str = ""

@dataclass
class DicomArtifacts:
    dicom_path: Path

@dataclass
class NiftiPoolArtifacts:
    output_dir: Path
    files: list[Path]  # 全部产物（不筛选）
    # [新增] 缓存 Sidecar 内容，避免重复读取
    sidecar_content: Dict = field(default_factory=dict)

@dataclass
class SeriesRecord:
    identity: SeriesIdentity
    dicom: Optional[DicomArtifacts] = None
    nifti_pool: Optional[NiftiPoolArtifacts] = None

@dataclass
class TimeMetadata:
    """
    [新增] 专门用于时间审计的元数据
    """
    # 来源 1: Phase 1 从 Zip 文件名提取的粗略时间 (HHMMSS)
    zip_time_raw: str = "" 
    
    # 来源 2: Phase 2 从 JSON Sidecar 读取的精确机器时间
    # dcm2niix 输出可能是 float (143022.500) 或 str ("14:30:22.500")
    sidecar_acq_time: Any = None 
    
    # 结果: Phase 3 计算出的权威时间
    canonical_timestamp: Optional[datetime] = None
    time_source: str = "unknown"
    time_diff: float = 0.0          # 与 Zip 时间的偏差(秒)
    quality_flag: str = "OK"        # OK / WARN

@dataclass
class BidsTargetInfo:
    """
    Phase 2 (Mapping) 目标信息
    对应原脚本 write_mapping_excel.py 生成的 BIDS 字段
    """
    sub_id: str                 # sub-01
    ses_id: str                 # ses-01
    datatype: str               # func, anat, fmap
    suffix: str                 # bold, T1w, phasediff
    
    # 任务相关 (对应 task_mapping)
    task: Optional[str] = None  # per, mod, ecog
    run: Optional[str] = None   # run-01
    
    # 输出路径规划
    # 对应原脚本 "BIDS_Folder" 列，例如: sub-01/ses-01/func/sub-01_..._bold
    bids_folder_relative: str = "" 
    
    # 用于 Fieldmap 关联逻辑 (IntendedFor)
    # 存储需要写入 JSON 的 "bids::sub-xx/..." URI 列表
    intended_for: List[str] = field(default_factory=list)

@dataclass
class ConversionEntry:
    """
    核心转换条目
    贯穿 Phase 1 -> Phase 4 的完整记录。
    一个 Entry 代表一次扫描 (One Scan/Sequence)。
    """
    # 唯一标识 (通常用 dicom_path 的 hash 或 相对路径字符串)
    id: str
    
    source: SeriesRecord   
    target: Optional[BidsTargetInfo] = None
    
    # 状态追踪
    status: ProcessStatus = ProcessStatus.PENDING
    error_message: Optional[str] = None
    
    # [新增] Phase 2 产物
    # 使用 Optional 是因为在 Phase 1 阶段它还是 None
    nifti_pool: Optional[NiftiPoolArtifacts] = None
    # 最终产物 (Phase 4 填充)
    # 对应 move_and_rename_nifti_json 的返回值
    result_nifti_path: Optional[Path] = None
    result_json_path: Optional[Path] = None
    
    # 特殊产物: Fieldmap 可能产生多个文件 (phasediff, mag1, mag2)
    # 对应 rename_fieldmap_files 的返回值字典
    result_extra_files: Dict[str, Path] = field(default_factory=dict)

    @property
    def is_bold(self) -> bool:
        return self.target and self.target.datatype == 'func'

    @property
    def is_fmap(self) -> bool:
        return self.target and self.target.datatype == 'fmap'

    def set_error(self, msg: str):
        self.status = ProcessStatus.FAILED
        self.error_message = msg

# -----------------------------------------------------------------------------
# 辅助配置类 (可选，用于类型提示)
# -----------------------------------------------------------------------------
@dataclass
class MappingRule:
    """对应 config 中的 mapping section"""
    subject_map: Dict[str, Dict[str, str]]  # H875574 -> {bids_id: sub-01}
    task_map: Dict[str, str]                # 478 -> per
    valid_prefixes: List[str]               # ["BOLD", "Fieldmap", "T1"]