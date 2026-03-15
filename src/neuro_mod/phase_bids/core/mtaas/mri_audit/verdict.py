# src/mri_audit/verdict.py
from dataclasses import dataclass
from typing import List, Optional
from ..temporal_matcher.models import MatchResult

@dataclass
class VerdictResult:
    status: str          # PASS, FIXABLE, REVIEW, REVIEW_EMPTY
    flags: List[str]     # ["HIGH_GAP", "LOW_COVERAGE", "MRI_ONLY", etc.]
    description: str     # 人类可读的简述

class VerdictJudge:
    def __init__(self, gap_threshold: float = 0.5, offset_drift_threshold: float = 0.2):
        """
        :param gap_threshold: 允许的最大中位数间隔误差 (秒)
        :param offset_drift_threshold: 允许的 offset 抖动范围 (res_max)
        """
        self.gap_th = gap_threshold
        self.drift_th = offset_drift_threshold

    def judge(self, result: MatchResult, n_mri: int, n_resp: int) -> VerdictResult:
        """
        根据 H1-H4 规则生成判决
        """
        flags = []
        
        # E4: 某侧为空
        if n_mri == 0 or n_resp == 0:
            return VerdictResult("REVIEW_EMPTY", ["EMPTY_SIDE"], "One side has no data")

        # 检查核心匹配质量
        metrics = result.metrics
        matched_count = len(result.pairs)
        
        # 1. 结构一致性检查 (V1, V2)
        is_timing_good = True
        if metrics.gap_med > self.gap_th:
            flags.append(f"HIGH_GAP_MED({metrics.gap_med:.3f}s)")
            is_timing_good = False
        
        if metrics.res_max > self.drift_th:
            flags.append(f"UNSTABLE_OFFSET(max_res={metrics.res_max:.3f}s)")
            # 严格来说，Offset 不稳可能是 drift，也可能是 match 错了
            is_timing_good = False

        if matched_count == 0:
            return VerdictResult("REVIEW", ["NO_MATCH_FOUND"], "Algorithm found no valid alignment")

        # 2. 覆盖率检查 (V3)
        # 理想情况: matched_count == min(n_mri, n_resp)
        min_len = min(n_mri, n_resp)
        is_coverage_full = (matched_count >= min_len)
        
        if len(result.unmatched_source) > 0:
            flags.append(f"MRI_ONLY({len(result.unmatched_source)})")
        if len(result.unmatched_target) > 0:
            flags.append(f"RESP_ONLY({len(result.unmatched_target)})")

        # 3. 综合判定 (H2, H3, H4)
        if not is_timing_good:
            # 时间结构对不上，必须人工复核
            return VerdictResult("REVIEW", flags, "Timing structure mismatch or unstable")
        
        if is_coverage_full:
            # 结构好且覆盖全 -> PASS
            # 注意：如果 n_mri != n_resp，但我们匹配了 min 个，这算 FIXABLE 还是 PASS？
            # 根据 H3 定义，存在 MRI-only/RESP-only 算 FIXABLE
            if n_mri == n_resp:
                return VerdictResult("PASS", flags, "Perfect match")
            else:
                return VerdictResult("FIXABLE", flags, "Good match but count mismatch (extra files)")
        else:
            # 结构好，但覆盖率不满 (中间断了，或者掐头去尾丢了) -> FIXABLE
            # 前提是“结构一致的主链”存在。如果 match count 极低（例如 < 50% min_len），可能还是 Review
            if matched_count < min_len * 0.5:
                flags.append("LOW_MATCH_RATIO")
                return VerdictResult("REVIEW", flags, "Good timing but too few matches")
            
            return VerdictResult("FIXABLE", flags, "Valid match with missing events")