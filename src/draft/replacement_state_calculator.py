"""
Replacement state calculation and storage.

Converts replacement baseline calculations from the SGP pipeline
into the ReplacementState schema for storage in LeagueState.
"""

import pandas as pd
from typing import Dict
import logging

from .league_schema import ReplacementState, ReplacementProfile
from ..sgp.replacement_baseline import ReplacementBaseline
from .. import config

logger = logging.getLogger(__name__)


class ReplacementStateCalculator:
    """Calculates and formats replacement-level profiles."""

    @staticmethod
    def calculate_replacement_state(
        hitter_baseline: ReplacementBaseline,
        pitcher_baseline: ReplacementBaseline,
        available_hitters_df: pd.DataFrame = None,
        available_pitchers_df: pd.DataFrame = None
    ) -> ReplacementState:
        """
        Create ReplacementState from replacement baselines.

        Args:
            hitter_baseline: Replacement baseline for hitters
            pitcher_baseline: Replacement baseline for pitchers
            available_hitters_df: Optional DataFrame of available hitters
                                 (for position-specific profiles)
            available_pitchers_df: Optional DataFrame of available pitchers
                                  (for position-specific profiles)

        Returns:
            ReplacementState with profiles by position
        """
        profiles = {}

        # Hitter positions - use league average baseline for now
        # (could be enhanced to calculate position-specific baselines)
        hitter_profile = ReplacementStateCalculator._create_hitter_profile(
            hitter_baseline
        )

        for pos in ['C', '1B', '2B', '3B', 'SS', 'OF', 'UTIL', 'BN_H']:
            profiles[pos] = hitter_profile

        # Pitcher positions
        pitcher_profile = ReplacementStateCalculator._create_pitcher_profile(
            pitcher_baseline
        )

        for pos in ['P', 'BN_P']:
            profiles[pos] = pitcher_profile

        logger.debug(
            f"Created ReplacementState with {len(profiles)} position profiles"
        )

        return ReplacementState(by_position=profiles)

    @staticmethod
    def _create_hitter_profile(baseline: ReplacementBaseline) -> ReplacementProfile:
        """
        Create replacement profile for hitters.

        Uses the replacement-level stats from the baseline for VAR calculation.

        Args:
            baseline: ReplacementBaseline with hitter stats

        Returns:
            ReplacementProfile for hitters
        """
        # Use replacement-level stats (not league average)
        # These represent the "zero value" baseline
        obp = baseline.replacement_obp or 0.300
        slg = baseline.replacement_slg or 0.380
        pa = baseline.pa or config.REPLACEMENT_HITTER_PA
        ab = baseline.ab or (pa * 0.90)  # Approximate AB from PA

        # Calculate counting stats (placeholder - could use actual data)
        # For now, use simple estimates based on replacement-level performance
        r = pa * 0.10  # ~10% of PA become runs
        rbi = pa * 0.095  # ~9.5% of PA become RBI
        sb = pa * 0.015  # ~1.5% of PA become SB

        # Calculate rate stat components
        # OBP numerator = H + BB + HBP
        # For replacement level: H ≈ AB × BA, BB ≈ PA × 0.08, HBP ≈ PA × 0.01
        ba = (slg / 1.4) if slg > 0 else 0.270  # Rough estimate: SLG ≈ 1.4 × BA
        h = ab * ba
        bb = pa * 0.08
        hbp = pa * 0.01
        obp_num = h + bb + hbp

        # SLG numerator = Total Bases
        tb = ab * slg

        return ReplacementProfile(
            counting={
                'R': r,
                'RBI': rbi,
                'SB': sb,
            },
            rate_numerators={
                'OBP_num': obp_num,
                'SLG_num': tb,
            },
            rate_denominators={
                'PA': pa,
                'AB': ab,
            }
        )

    @staticmethod
    def _create_pitcher_profile(baseline: ReplacementBaseline) -> ReplacementProfile:
        """
        Create replacement profile for pitchers.

        Uses the replacement-level stats from the baseline for VAR calculation.

        Args:
            baseline: ReplacementBaseline with pitcher stats

        Returns:
            ReplacementProfile for pitchers
        """
        # Use replacement-level stats
        era = baseline.replacement_era or 4.50
        whip = baseline.replacement_whip or 1.35
        ip = baseline.ip or config.REPLACEMENT_PITCHER_IP

        # Calculate counting stats (placeholder - could use actual data)
        # For now, use simple estimates based on replacement-level performance
        # Typical replacement pitcher: ~8 K/9, ~5 W+QS per 150 IP, ~2 SV+HLD per 150 IP
        k = ip * (8.0 / 9.0)  # 8 K/9
        w_qs = ip / 30.0  # ~5 W+QS per 150 IP
        sv_hld = ip / 75.0  # ~2 SV+HLD per 150 IP

        # Calculate rate stat components
        # ERA = (ER / IP) × 9, so ER = (ERA × IP) / 9
        er = (era * ip) / 9.0

        # WHIP = (H + BB) / IP, so H + BB = WHIP × IP
        # Estimate: H ≈ 70% of (H+BB), BB ≈ 30% of (H+BB)
        whip_total = whip * ip
        h = whip_total * 0.70
        bb = whip_total * 0.30
        whip_num = h + bb

        return ReplacementProfile(
            counting={
                'W_QS': w_qs,
                'SV_HLD': sv_hld,
                'K': k,
            },
            rate_numerators={
                'ERA_num': er,
                'WHIP_num': whip_num,
            },
            rate_denominators={
                'IP': ip,
            }
        )

    @staticmethod
    def update_replacement_state(
        league_state: 'LeagueState',
        hitter_baseline: ReplacementBaseline,
        pitcher_baseline: ReplacementBaseline
    ) -> None:
        """
        Update replacement state in an existing LeagueState.

        Args:
            league_state: LeagueState to update
            hitter_baseline: Replacement baseline for hitters
            pitcher_baseline: Replacement baseline for pitchers
        """
        league_state.replacement = ReplacementStateCalculator.calculate_replacement_state(
            hitter_baseline,
            pitcher_baseline
        )

        # Update metadata
        from datetime import datetime
        league_state.metadata.last_updated = datetime.now()
        league_state.metadata.notes = (
            f"{league_state.metadata.notes or ''} | "
            f"ReplacementState updated at {datetime.now().isoformat()}"
        ).strip()

        logger.debug("Updated ReplacementState in LeagueState")

    @staticmethod
    def get_replacement_stats(
        replacement_state: ReplacementState,
        position: str
    ) -> Dict[str, float]:
        """
        Get replacement-level stats for a position.

        Args:
            replacement_state: ReplacementState object
            position: Position to look up

        Returns:
            Dict with replacement stats (counting + calculated rates)

        Raises:
            ValueError: If position not found
        """
        if position not in replacement_state.by_position:
            raise ValueError(f"Position {position} not found in ReplacementState")

        profile = replacement_state.by_position[position]

        # Combine counting stats and calculated rate stats
        stats = profile.counting.copy()

        # Calculate rate stats
        if profile.rate_denominators.get('PA', 0) > 0:
            stats['OBP'] = (
                profile.rate_numerators.get('OBP_num', 0) /
                profile.rate_denominators['PA']
            )
        else:
            stats['OBP'] = 0.0

        if profile.rate_denominators.get('AB', 0) > 0:
            stats['SLG'] = (
                profile.rate_numerators.get('SLG_num', 0) /
                profile.rate_denominators['AB']
            )
        else:
            stats['SLG'] = 0.0

        if profile.rate_denominators.get('IP', 0) > 0:
            stats['ERA'] = (
                (profile.rate_numerators.get('ERA_num', 0) /
                 profile.rate_denominators['IP']) * 9.0
            )
            stats['WHIP'] = (
                profile.rate_numerators.get('WHIP_num', 0) /
                profile.rate_denominators['IP']
            )
        else:
            stats['ERA'] = 0.0
            stats['WHIP'] = 0.0

        return stats
