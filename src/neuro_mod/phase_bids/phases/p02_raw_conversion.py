import shutil
import subprocess
import logging
from pathlib import Path
from typing import List, Optional
import json

# 引入核心模型
# 假设 SeriesRecord 和 NiftiPoolArtifacts 已经按你的描述更新到了 models.py
from neuro_mod.phase_bids.core.models import (
    ConversionEntry, 
    ProcessStatus, 
    NiftiPoolArtifacts
)

logger = logging.getLogger(__name__)

class RawConverter:
    """
    Phase 2: Raw Conversion (DICOM -> NIfTI Pool)
    
    职责：
    1. 读取 ConversionEntry 中的 DICOM 路径。
    2. 调用 dcm2niix 进行格式转换。
    3. 将生成的所有文件（nii, json, bval, bvec）收集到 NIfTI Pool。
    4. 更新 ConversionEntry 的中间产物信息 (NiftiPoolArtifacts)。
    
    注意：此阶段不进行 BIDS 重命名，文件名保持 dcm2niix 的输出格式（通常是 Series Description）。
    """

    def __init__(self, config: dict):
        self.config = config
        
        # 基础路径配置
        self.work_dir = Path(config['paths']['work_dir'])
        self.nifti_pool_root = self.work_dir / "nifti_pool"
        
        # # dcm2niix 工具配置
        # self.dcm2niix_bin = config['tools'].get('dcm2niix', 'dcm2niix')
        # self.dcm2niix_flags = config['dcm2niix'].get('flags', ["-z", "y", "-f", "%p_%s"])
        
        tool_config = config['tools'].get('dcm2niix', {})
        self.dcm2niix_bin = tool_config.get('executable', 'dcm2niix')
        # flags 也在 tools -> dcm2niix 下面
        self.dcm2niix_flags = tool_config.get('flags', ["-z", "y", "-f", "%p_%s"])
        # 确保 Pool 根目录存在
        self.nifti_pool_root.mkdir(parents=True, exist_ok=True)

    def execute(self, entries: List[ConversionEntry]) -> List[ConversionEntry]:
        """
        批处理执行入口
        """
        logger.info(f"Phase 2: Starting Raw Conversion for {len(entries)} entries...")
        
        for entry in entries:
            # 只有当状态为 PENDING 时才处理 (或者你可以增加 force 标志)
            if entry.status != ProcessStatus.PENDING:
                continue

            try:
                self._process_single_entry(entry)
                entry.status = ProcessStatus.SUCCESS
            except Exception as e:
                logger.error(f"Failed to convert entry {entry.id}: {str(e)}")
                entry.set_error(f"Raw Conversion Failed: {str(e)}")
        
        logger.info("Phase 2: Completed.")
        return entries

    def _process_single_entry(self, entry: ConversionEntry):
        """
        处理单个 Entry 的核心原子逻辑
        """
        # 1. 准备输入输出路径
        # 兼容逻辑：根据 models.py 的定义，获取 DICOM 路径
        # [修改前] dicom_path = entry.source.dicom_path 
        # [修改后] 需要多深入一层，并且建议做个简单的非空检查
        if entry.source.dicom is None:
             raise ValueError(f"Entry {entry.id} source has no DICOM artifacts.")
        dicom_path = entry.source.dicom.dicom_path 
        
        if not dicom_path or not dicom_path.exists():
            raise FileNotFoundError(f"DICOM path does not exist: {dicom_path}")

        # 为每个 Entry 创建专属的 Pool 子目录 (Isolation)
        # 例如: work/nifti_pool/<Hash_ID>/
        entry_pool_dir = self.nifti_pool_root / entry.id
        
        # 2. 清理环境 (幂等性保证)
        if entry_pool_dir.exists():
            shutil.rmtree(entry_pool_dir)
        entry_pool_dir.mkdir(parents=True)

        # 3. 执行 dcm2niix
        success = self._run_dcm2niix(dicom_path, entry_pool_dir)
        if not success:
            raise RuntimeError(f"dcm2niix execution failed for {dicom_path}")

        # 4. 收集产物 (Artifact Discovery)
        # 扫描该目录下的所有文件，不只是 nii.gz，还包含 json, bval, bvec 等
        generated_files = sorted(list(entry_pool_dir.glob("*")))
        
        # === [新增逻辑 START] ===
        # 读取 Sidecar JSON 以获取精确的 AcquisitionTime
        sidecar_data = {}
        json_file = next((f for f in generated_files if f.name.endswith('.json')), None)
        
        if json_file:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    sidecar_data = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load sidecar for {entry.id}: {e}")

        # 填充 nifti_pool
        pool_artifacts = NiftiPoolArtifacts(
            output_dir=entry_pool_dir,
            files=generated_files,
            sidecar_content=sidecar_data # <--- 存入内容
        )
        entry.nifti_pool = pool_artifacts
        
        # 立即提取机器时间到 TimeMetadata
        if "AcquisitionTime" in sidecar_data:
            entry.time_meta.sidecar_acq_time = sidecar_data["AcquisitionTime"]
        
        # === [新增逻辑 END] ===
        logger.info(f"Converted {entry.id}. AcqTime: {entry.time_meta.sidecar_acq_time}")

        if not generated_files:
            raise RuntimeError("dcm2niix finished but no files were generated.")

        # 5. 更新模型 (Data Model Update)
        # 将结果封装进 NiftiPoolArtifacts
        pool_artifacts = NiftiPoolArtifacts(
            output_dir=entry_pool_dir,
            files=generated_files
        )
        
        # 关键点：将 Artifacts 挂载回 Entry
        # 假设 ConversionEntry 被修改以支持 nifti_pool 字段，或者我们将数据回填到 source 中
        # 这里建议修改 models.py 中的 ConversionEntry 增加 nifti_pool 字段
        if hasattr(entry, 'nifti_pool'):
            entry.nifti_pool = pool_artifacts
        elif hasattr(entry.source, 'raw_nifti_path'):
            # 兼容旧字段：尝试找到主要的 nii 文件填入 (不推荐，建议升级 Model)
            nii_files = [f for f in generated_files if f.name.endswith('.nii.gz')]
            json_files = [f for f in generated_files if f.name.endswith('.json')]
            if nii_files:
                entry.source.raw_nifti_path = nii_files[0]
            if json_files:
                entry.source.raw_json_path = json_files[0]
            
            # 临时保存完整 artifacts 以备后用（如果 Model 不支持存对象，这一步可省略）
            entry.source.temp_pool_artifacts = pool_artifacts

        logger.info(f"Converted {entry.id}: {len(generated_files)} files generated.")

    def _run_dcm2niix(self, input_dir: Path, output_dir: Path) -> bool:
        """
        封装 subprocess 调用，处理 dcm2niix 的特定行为
        """
        cmd = [str(self.dcm2niix_bin)] + self.dcm2niix_flags + [
            "-o", str(output_dir),
            str(input_dir)
        ]
        
        try:
            # capture_output=True 可以避免日志刷屏，只在报错时打印
            result = subprocess.run(
                cmd, 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            # 可以在这里检查 stdout 中是否有 "No valid DICOM files found" 等软错误
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"dcm2niix Stdout: {e.stdout}")
            logger.error(f"dcm2niix Stderr: {e.stderr}")
            return False