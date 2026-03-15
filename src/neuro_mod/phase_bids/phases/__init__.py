# 这样您可以直接从 phases 包导入主要的类
from .p01_raw_ingest import StandardZipStrategy, IngestStrategy
from .p02_raw_conversion import RawConverter

# 待后续添加
# from .p03_mapping import MappingGenerator
# from .p04_skeleton import SkeletonBuilder
# from .p05_assembler import BidsAssembler