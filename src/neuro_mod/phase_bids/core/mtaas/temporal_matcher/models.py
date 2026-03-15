# src/temporal_matcher/models.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class MatchCandidate:
    """
    表示一个潜在的匹配方案（即一条对齐路径）
    """
    matched_indices: List[tuple]  # List of (mri_idx, resp_idx)
    
    # 评分指标 (对应审计表 E 部分)
    gap_med: float       # 间隔误差中位数 (越小越好)
    gap_max: float       # 间隔误差最大值 (越小越好)
    res_med: float       # 残差(Offset)中位数稳定性 (越小越好)
    res_max: float       # 残差最大偏离度
    abs_med: float       # 绝对时间差中位数 (Tie-breaker)
    match_count: int     # 匹配到的数量 (越大越好)

@dataclass
class MatchResult:
    """
    最终返回给业务层的解
    """
    source_indices: List[int]      # 原始 MRI 索引序列
    target_indices: List[int]      # 原始 Response 索引序列
    
    # 对齐结果
    pairs: List[tuple]             # [(m_idx, r_idx), ...]
    unmatched_source: List[int]    # MRI-only indices
    unmatched_target: List[int]    # RESP-only indices
    
    # 最终指标
    metrics: MatchCandidate        # 包含用于生成 Verdict 的所有数值