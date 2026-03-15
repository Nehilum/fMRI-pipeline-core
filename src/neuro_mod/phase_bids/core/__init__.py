# bids_converter/core/__init__.py

# 这样你就可以直接从 core 导入，而不用写 core.models
from .models import ConversionEntry, SeriesIdentity, DicomArtifacts, NiftiPoolArtifacts, SeriesRecord, BidsTargetInfo, ProcessStatus
# from .errors import BidsConverterError  # 假设你以后写了 errors.py