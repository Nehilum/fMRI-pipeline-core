import argparse
import yaml
import logging
import sys
import pickle
from pathlib import Path

# 引入各个阶段的模块
from bids_converter.phases.p01_raw_ingest import get_ingestor
from bids_converter.phases.p02_raw_conversion import RawConverter
from bids_converter.phases.p03_1_preaudit import MappingGenerator
from bids_converter.phases.p03_2_compilation import BidsCompilationStep
from bids_converter.phases.p04_skeleton import SkeletonCreator
from bids_converter.phases.p05_assembler import Assembler
# 引入 Status 枚举以便检查状态
from bids_converter.core.models import ProcessStatus 

def setup_logging(log_dir: Path, level=logging.INFO):
    """配置全局日志"""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pipeline_execution.log"

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    fh = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    root_logger.addHandler(fh)
    root_logger.addHandler(ch)
    return root_logger

def load_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

class BidsPipeline:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = load_config(config_path)
        
        # 初始化路径
        self.work_dir = Path(self.config['paths']['work_dir'])
        self.log_dir = self.work_dir / "logs"
        self.logger = setup_logging(self.log_dir)
        
        # === 新增：定义缓存文件路径 ===
        # 这个文件将存储 Phase 1 解析出来的 entries 对象列表
        self.ckpt_p1 = self.work_dir / "checkpoint_01_ingest.pkl"
        self.ckpt_p2 = self.work_dir / "checkpoint_02_converted.pkl"
        self.entries = []

    # ==========================================
    # 通用缓存读写工具
    # ==========================================
    def _save_checkpoint(self, path: Path, data):
        """通用保存函数"""
        try:
            with open(path, 'wb') as f:
                pickle.dump(data, f)
            self.logger.info(f"💾 Checkpoint saved: {path.name}")
        except Exception as e:
            self.logger.warning(f"Failed to save checkpoint {path.name}: {e}")

    def _load_checkpoint(self, path: Path) -> bool:
        """通用加载函数：成功返回 True，失败返回 False"""
        if not path.exists():
            return False
        try:
            with open(path, 'rb') as f:
                self.entries = pickle.load(f)
            self.logger.info(f"📂 Loaded checkpoint: {path.name} ({len(self.entries)} entries)")
            return True
        except Exception as e:
            self.logger.warning(f"Checkpoint corrupted {path.name}: {e}")
            return False

    # ==========================================
    # 阶段控制逻辑 (核心修改)
    # ==========================================

    def ensure_p1_done(self) -> bool:
        """
        保证 P1 完成。
        策略：内存有 -> 用内存；没内存 -> 读P1缓存；没缓存 -> 跑P1。
        """
        # 1. 如果内存里已经有数据（可能是P1的，也可能是P2的），暂且认为满足
        if self.entries:
            return True
            
        # 2. 尝试加载 P1 检查点
        if self._load_checkpoint(self.ckpt_p1):
            return True
            
        # 3. 实在没有，运行 Phase 1
        return self.run_p1_ingest()

    def ensure_p2_done(self, force_rerun: bool = False) -> bool:
        """
        保证 P2 完成。
        参数 force_rerun: 如果为 True，强制忽略 P2 缓存，重新基于 P1 结果运行。
        """
        # 1. 如果不强制重跑，且 P2 缓存存在，直接加载 P2 结果 -> 完成
        if not force_rerun and self.ckpt_p2.exists():
            if self._load_checkpoint(self.ckpt_p2):
                # 这里可以加个校验：检查是否真的有 sidecar (防止脏缓存)
                if self.entries and hasattr(self.entries[0], 'nifti_pool'):
                    return True
                self.logger.warning("P2 checkpoint loaded but seems empty/invalid. Rerunning.")

        # =========================================================
        # 2. 需要运行 P2 (因为没有缓存，或者被强制重跑)
        # 关键点：必须先加载 P1 的干净数据！
        # =========================================================
        self.logger.info("🔄 Preparing to run Phase 2...")
        
        # 显式加载 P1 缓存 (这会重置 self.entries 为 P1 结束时的状态)
        if not self._load_checkpoint(self.ckpt_p1):
            # 如果连 P1 缓存都没了，那就得从头跑
            if not self.run_p1_ingest():
                return False
        
        # 此时 self.entries 是纯净的 P1 状态，开始运行 P2
        return self.run_p2_conversion()

    # ==========================================
    # 阶段执行函数
    # ==========================================

    def run_p1_ingest(self) -> bool:
        self.logger.info(">>> [Phase 1] Raw Ingest Started (Slow Operation)")
        try:
            # 模拟：运行 ingestor
            ingestor = get_ingestor(self.config)
            self.entries = ingestor.run()
            
            if not self.entries: return False
            
            # 存盘：P1 检查点
            self._save_checkpoint(self.ckpt_p1, self.entries) 
            return True
        except Exception as e:
            self.logger.error(f"Phase 1 Failed: {e}", exc_info=True)
            return False

    def run_p2_conversion(self) -> bool:
        # ====================================================
        # [核心修复] 如果内存为空，先加载 Phase 1 的存档
        # ====================================================
        if not self.entries:
            self.logger.info("⚠️ Memory is empty. Loading Phase 1 checkpoint...")
            if not self._load_checkpoint(self.ckpt_p1):
                self.logger.error("❌ Cannot run Phase 2: Phase 1 checkpoint not found!")
                return False
        # ====================================================

        self.logger.info(">>> [Phase 2] Raw Conversion Started")
        
        try:
            converter = RawConverter(self.config)
            # 此时 self.entries 已经被填满了，可以正常跑了
            converter.execute(self.entries)
            
            # 存盘：P2 检查点
            self._save_checkpoint(self.ckpt_p2, self.entries)
            return True
        except Exception as e:
            self.logger.error(f"Phase 2 Failed: {e}", exc_info=True)
            return False

    def run_p3a_mapping(self):
        # 运行 P3 前，确保 P2 已完成
        # 你可以在这里手动控制是否要 force_rerun P2
        if not self.ensure_p2_done(force_rerun=False): 
            return False
            
        mapper = MappingGenerator(self.config)
        mapper.execute(self.entries)

    def run_p3b_mapping(self):
        # 

        compiler = BidsCompilationStep(self.config)
        compiler.execute()

    def run_p4_skeleton(self) -> bool:
        # P4 只需要 Excel 文件，不需要 entries 对象
        try:
            self.logger.info("Starting Phase 4: Skeleton & Metadata...")
            
            # 实例化并运行
            creator = SkeletonCreator(self.config_path) # 假设传入路径
            creator.run()
            return True

        except FileNotFoundError as e:
            # 捕获 Phase 4 抛出的具体错误（文件没找到）
            self.logger.error(f"❌ Phase 4 Failed: Missing Input File - {str(e)}")
            return False
            
        except Exception as e:
            # 捕获其他未知错误
            self.logger.error(f"❌ Phase 4 Failed: Unexpected error - {str(e)}")
            return False

    def run_p5_assembly(self) -> bool:
        try:
            self.logger.info("Starting Phase 5: Final Assembly...")
            
            assembler = Assembler(self.config_path)
            assembler.run()
            return True

        except FileNotFoundError as e:
            # 捕获 Phase 5 抛出的具体错误（文件没找到）
            self.logger.error(f"❌ Phase 5 Failed: Missing Input File - {str(e)}")
            return False
            
        except Exception as e:
            # 捕获其他未知错误
            self.logger.error(f"❌ Phase 5 Failed: Unexpected error - {str(e)}")
            return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', default="config/config.yaml")
    modes = ['all', 'prep', 'build', 'p1', 'p2', 'p3a','p3b', 'p4', 'p5']
    parser.add_argument('-m', '--mode', choices=modes, default='all')
    parser.add_argument('--force-p1', action='store_true', help="Clear cache and re-run P1")
    
    args = parser.parse_args()
    pipeline = BidsPipeline(args.config)

    if args.force_p1 and pipeline.cache_file.exists():
        pipeline.cache_file.unlink()
        pipeline.logger.info("🧹 Cache cleared by user.")

    success = True
    mode = args.mode

    # 调度逻辑
    # 核心思想：只需要调用用户指定的那个 Phase，
    # 依赖检查由每个 Phase 内部的 ensure_xx_done 自动处理。

    if mode == 'p1':
        success = pipeline.run_p1_ingest()
    
    elif mode == 'p2':
        success = pipeline.run_p2_conversion()
        
    elif mode == 'p3a':
        success = pipeline.run_p3a_mapping()
    
    elif mode == 'p3b':
        success = pipeline.run_p3b_mapping()

    elif mode == 'prep': # P1 -> P2 -> P3
        # 这里为了效率，直接顺序跑，如果断了会报错
        if pipeline.run_p1_ingest():
            if pipeline.run_p2_conversion():
                success = pipeline.run_p3a_mapping()
            else: success = False
        else: success = False

    elif mode == 'p4':
        success = pipeline.run_p4_skeleton()

    elif mode == 'p5':
        success = pipeline.run_p5_assembly()

    elif mode == 'build': # P4 -> P5
        if pipeline.run_p4_skeleton():
            success = pipeline.run_p5_assembly()
        else: success = False

    elif mode == 'all': # Prep + Build
        # 依次运行 P1(check) -> P2(check) -> P3 -> P4 -> P5
        # 利用 ensure 机制，我们可以简化调用：
        if pipeline.run_p3a_mapping(): # 这会自动确保 P1/P2 完成
             if pipeline.run_p4_skeleton():
                 success = pipeline.run_p5_assembly()
             else: success = False
        else: success = False

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()