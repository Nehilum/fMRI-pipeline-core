# src/temporal_matcher/solver.py
import numpy as np
from typing import List
from collections import defaultdict
from .models import MatchCandidate, MatchResult
from .metrics import calculate_metrics

class TemporalAligner:
    def __init__(self, tolerance_sec: float = 2.0):
        """
        :param tolerance_sec: 用于初步筛选“是否属于同一Offset组”的宽容度。
                              这只是为了生成候选，最终评判由 Gap Metrics 决定。
        """
        self.tolerance = tolerance_sec

    def align(self, source_times: List[float], target_times: List[float]) -> MatchResult:
        """
        执行匹配主入口
        """
        N = len(source_times)
        K = len(target_times)
        
        # 边界条件处理
        if N == 0 or K == 0:
            return self._build_empty_result(N, K)

        # 1. 生成候选方案
        candidates = self._generate_candidates(source_times, target_times)
        
        # 2. 决策排序 (Tie-Breaker Logic)
        best_candidate = self._pick_best_candidate(candidates)
        
        # 3. 包装结果
        return self._finalize_result(best_candidate, N, K)

    def _generate_candidates(self, src: List[float], tgt: List[float]) -> List[MatchCandidate]:
        """
        核心生成逻辑：
        不使用复杂的 DP，而是基于“Offset 聚类”的启发式搜索。
        因为物理事实是：正确的匹配必然共享一个近似的 global offset。
        """
        candidates = []
        
        # 步骤 A: 计算所有可能的 offset (diff table)
        # 记录所有 (i, j) 对应的 offset
        raw_offsets = []
        for i, t_s in enumerate(src):
            for j, t_t in enumerate(tgt):
                diff = t_s - t_t
                raw_offsets.append((diff, i, j))
        
        # 步骤 B: 寻找“主流 Offset”
        # 我们将 offset 四舍五入到 tolerance 的精度，进行分组
        # 例如 tolerance=2.0s, offset=101.5 -> key=50 (100/2)
        offset_bins = defaultdict(list)
        for diff, i, j in raw_offsets:
            bin_key = int(diff / self.tolerance)
            offset_bins[bin_key].append((i, j))
            # 为了防止边界效应（比如 diff 在 1.99 和 2.01），同时也加入相邻 bin
            # 但为了简化，我们这里假设后续的长链构建会处理微小抖动
            
        # 步骤 C: 对每个 Offset Bin 构建最长单调链
        # 这里的逻辑是：如果一堆点都落在同一个 Offset Bin 里，它们很可能属于同一个对齐方案
        unique_strategies = []
        
        # 提取所有 bin 中包含点数较多的 (作为 Seed)
        # 也可以直接遍历所有 bin，反正数量不多
        sorted_bins = sorted(offset_bins.items(), key=lambda x: len(x[1]), reverse=True)
        
        # 限制处理的 bin 数量以优化性能 (比如只看 Top 10 密集的 offset 区域)
        top_bins = sorted_bins[:15] 

        for _, pairs in top_bins:
            # pairs 是一组 (i, j)，它们具有相近的 offset
            # 从这些 pairs 中构建符合 i 递增且 j 递增的最长链
            chain = self._build_longest_monotonic_chain(pairs)
            if chain:
                unique_strategies.append(chain)

        # 步骤 D: 将这些链转化为 Candidate 对象并计算指标
        for chain in unique_strategies:
            cand = calculate_metrics(src, tgt, chain)
            candidates.append(cand)
            
        return candidates

    def _build_longest_monotonic_chain(self, pairs: List[tuple]) -> List[tuple]:
        """
        给定一组散点，找最长递增子序列 (LIS) 的变体 (2D LIS)。
        pairs: List[(i, j)]
        """
        # 先按 i 排序，如果 i 相同按 j 排序
        pairs.sort(key=lambda x: (x[0], x[1]))
        
        if not pairs:
            return []

        # 简单的贪心或者 DP LIS。
        # 由于我们已经筛选了 Offset 相近的点，这里的 conflict 应该很少。
        # 简单贪心：取第一个，然后取之后第一个满足 i2>i1 且 j2>j1 的点...
        # 但为了更稳健（防止中间插了一个噪音点导致断链），我们用简单的 DP LIS。
        
        # dp[k] = 以 pairs[k] 结尾的最长链长度
        # prev[k] = 前驱索引
        n = len(pairs)
        dp = [1] * n
        prev = [-1] * n
        
        for k in range(n):
            curr_i, curr_j = pairs[k]
            for p in range(k):
                prev_i, prev_j = pairs[p]
                if curr_i > prev_i and curr_j > prev_j:
                    if dp[p] + 1 > dp[k]:
                        dp[k] = dp[p] + 1
                        prev[k] = p
        
        # 回溯找最长链
        max_len = 0
        end_idx = -1
        for k in range(n):
            if dp[k] > max_len:
                max_len = dp[k]
                end_idx = k
        
        path = []
        curr = end_idx
        while curr != -1:
            path.append(pairs[curr])
            curr = prev[curr]
        
        return path[::-1] # 反转回正序

    def _pick_best_candidate(self, candidates: List[MatchCandidate]) -> MatchCandidate:
        """
        实现你的 M1-M5 级联决策逻辑
        """
        if not candidates:
            return None

        # 过滤掉 match_count 极低的 (比如 < 1)，除非全是 < 1
        valid_cands = [c for c in candidates if c.match_count > 0]
        if not valid_cands:
            return candidates[0] # Fallback

        # 排序 Key 的设计是核心：
        # Python 的 sort 是稳定的，且 tuple 比较是按顺序的
        # 我们希望 metrics 越小越好，count 越大越好
        
        # 优先级:
        # 1. Match Count (覆盖率优先? 不，你说过间隔优先。但如果只匹配 2 个点间隔完美， vs 匹配 20 个点间隔微小误差？通常我们希望覆盖率接近 max)
        #    修正：你的逻辑中 M6 是允许缺失，M2 是间隔为主。
        #    但是在多解的情况下，通常覆盖率高的是真解。
        #    *重要策略*: 我们先按“匹配数量”分层。只有数量相当（比如差值在 1-2 之内）的方案，才比较 Gap。
        #    或者，直接把 Match Count 作为一个硬性指标，太短的直接扔掉？
        #    让我们遵循你的 Hierarchy：
        #    你并没有把 Match Count 放在 M2。但是如果匹配点太少，Gap 毫无意义。
        #    我们将 Match Count 取负数作为第一排序键（越大越好），但允许微小差异？
        #    为了严格遵守你的 M2 (E_gap_med 最小)，我们直接用 Gap。
        #    *但在实际工程中*，匹配 2 个点的 gap 往往是 0，这会打败匹配 100 个点的方案。
        #    *调整*: 只比较 match_count >= max_match_count - 2 的方案（假设最多丢 2 个包）。
        
        max_matches = max(c.match_count for c in valid_cands)
        # 只考虑那些“足够长”的候选者
        top_tier = [c for c in valid_cands if c.match_count >= max_matches * 0.8] # 至少匹配了 80% 的最大可能数
        
        # 排序规则 (Tuple 比较，越小越优):
        # 1. E_gap_med (间隔一致性)
        # 2. E_gap_max (是否有爆点)
        # 3. E_res_med (Offset 稳定性)
        # 4. E_res_max
        # 5. E_abs_med (绝对时间 Tie-break)
        # 6. -match_count (数量越多越好)
        
        top_tier.sort(key=lambda c: (
            c.gap_med,
            c.gap_max,
            c.res_med,
            c.res_max,
            c.abs_med,
            -c.match_count
        ))
        
        return top_tier[0]

    def _finalize_result(self, candidate: MatchCandidate, N: int, K: int) -> MatchResult:
        if not candidate:
            return self._build_empty_result(N, K)
            
        matched_src = {i for i, j in candidate.matched_indices}
        matched_tgt = {j for i, j in candidate.matched_indices}
        
        return MatchResult(
            source_indices=list(range(N)),
            target_indices=list(range(K)),
            pairs=candidate.matched_indices,
            unmatched_source=sorted(list(set(range(N)) - matched_src)),
            unmatched_target=sorted(list(set(range(K)) - matched_tgt)),
            metrics=candidate
        )

    def _build_empty_result(self, N, K):
        return MatchResult(
            source_indices=list(range(N)),
            target_indices=list(range(K)),
            pairs=[],
            unmatched_source=list(range(N)),
            unmatched_target=list(range(K)),
            metrics=MatchCandidate([], np.inf, np.inf, np.inf, np.inf, np.inf, 0)
        )