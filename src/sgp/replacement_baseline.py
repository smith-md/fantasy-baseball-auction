"""
Calculate replacement-level baselines for ratio categories.

Replacement level represents "zero value" in auction context - the stats
you get from the worst rosterable player at a position.
"""

import logging
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np

from .. import config

logger = logging.getLogger(__name__)


@dataclass
class ReplacementBaseline:
    """Replacement-level baseline stats for ratio categories."""
    player_type: str  # 'hitters' or 'pitchers'

    # Playing time
    pa: Optional[float] = None   # For hitters
    ab: Optional[float] = None   # For hitters
    ip: Optional[float] = None   # For pitchers

    # Rate stats
    obp: Optional[float] = None
    slg: Optional[float] = None
    era: Optional[float] = None
    whip: Optional[float] = None


def calculate_replacement_baseline(
    player_pool: pd.DataFrame,
    player_type: str
) -> ReplacementBaseline:
    """
    Calculate replacement-level baseline from player pool.

    Strategy: Use players just below the roster threshold (replacement tier)
    as the baseline for "zero value".

    Args:
        player_pool: DataFrame of all players (with projections)
        player_type: 'hitters' or 'pitchers'

    Returns:
        ReplacementBaseline object
    """
    if player_type == 'hitters':
        return _calculate_hitter_replacement_baseline(player_pool)
    elif player_type == 'pitchers':
        return _calculate_pitcher_replacement_baseline(player_pool)
    else:
        raise ValueError(f"Invalid player_type: {player_type}")


def _calculate_hitter_replacement_baseline(
    player_pool: pd.DataFrame
) -> ReplacementBaseline:
    """
    Calculate replacement baseline for hitters.

    Uses players ranked just below roster threshold (156 hitters rostered).

    Args:
        player_pool: Hitter projections DataFrame

    Returns:
        ReplacementBaseline for hitters
    """
    # Sort by playing time as proxy for initial ranking
    # (raw_value will be calculated later)
    sorted_pool = player_pool.sort_values('PA', ascending=False).copy()

    # Replacement tier: players ranked 157-220 (below 156 roster spots)
    # Use larger range for more stable estimates
    replacement_start = config.TOTAL_HITTERS  # 156
    replacement_end = replacement_start + 64   # ~220

    if len(sorted_pool) < replacement_end:
        logger.warning(
            f"Player pool only has {len(sorted_pool)} hitters, "
            f"using bottom 20% as replacement tier"
        )
        replacement_start = int(len(sorted_pool) * 0.65)
        replacement_end = len(sorted_pool)

    replacement_tier = sorted_pool.iloc[replacement_start:replacement_end]

    # Calculate median stats from replacement tier
    baseline_obp = replacement_tier['OBP'].median()
    baseline_slg = replacement_tier['SLG'].median()

    # Use config values if provided, otherwise auto-calculate
    if config.REPLACEMENT_OBP is not None:
        baseline_obp = config.REPLACEMENT_OBP
    if config.REPLACEMENT_SLG is not None:
        baseline_slg = config.REPLACEMENT_SLG

    logger.info(
        f"Hitter replacement baseline: "
        f"OBP={baseline_obp:.3f}, SLG={baseline_slg:.3f}, "
        f"PA={config.REPLACEMENT_HITTER_PA}"
    )

    return ReplacementBaseline(
        player_type='hitters',
        pa=config.REPLACEMENT_HITTER_PA,
        ab=config.REPLACEMENT_HITTER_PA * 0.85,  # Approximate AB from PA
        obp=baseline_obp,
        slg=baseline_slg
    )


def _calculate_pitcher_replacement_baseline(
    player_pool: pd.DataFrame
) -> ReplacementBaseline:
    """
    Calculate replacement baseline for pitchers.

    Uses pitchers ranked just below roster threshold (132 pitchers rostered).

    Args:
        player_pool: Pitcher projections DataFrame

    Returns:
        ReplacementBaseline for pitchers
    """
    # Sort by IP as proxy for initial ranking
    sorted_pool = player_pool.sort_values('IP', ascending=False).copy()

    # Replacement tier: pitchers ranked 133-200 (below 132 roster spots)
    replacement_start = config.TOTAL_PITCHERS  # 132
    replacement_end = replacement_start + 48    # ~180

    if len(sorted_pool) < replacement_end:
        logger.warning(
            f"Player pool only has {len(sorted_pool)} pitchers, "
            f"using bottom 20% as replacement tier"
        )
        replacement_start = int(len(sorted_pool) * 0.65)
        replacement_end = len(sorted_pool)

    replacement_tier = sorted_pool.iloc[replacement_start:replacement_end]

    # Calculate median stats from replacement tier
    baseline_era = replacement_tier['ERA'].median()
    baseline_whip = replacement_tier['WHIP'].median()

    # Use config values if provided, otherwise auto-calculate
    if config.REPLACEMENT_ERA is not None:
        baseline_era = config.REPLACEMENT_ERA
    if config.REPLACEMENT_WHIP is not None:
        baseline_whip = config.REPLACEMENT_WHIP

    logger.info(
        f"Pitcher replacement baseline: "
        f"ERA={baseline_era:.2f}, WHIP={baseline_whip:.3f}, "
        f"IP={config.REPLACEMENT_PITCHER_IP}"
    )

    return ReplacementBaseline(
        player_type='pitchers',
        ip=config.REPLACEMENT_PITCHER_IP,
        era=baseline_era,
        whip=baseline_whip
    )


def calculate_ratio_marginal_impact(
    player_df: pd.DataFrame,
    baseline: ReplacementBaseline,
    player_type: str
) -> pd.DataFrame:
    """
    Calculate marginal impact over replacement for ratio categories.

    This is similar to stat_converter.py but uses replacement baseline
    instead of league average.

    Args:
        player_df: Player projections DataFrame
        baseline: ReplacementBaseline object
        player_type: 'hitters' or 'pitchers'

    Returns:
        DataFrame with marginal impact columns added
    """
    df = player_df.copy()

    if player_type == 'hitters':
        # OBP marginal impact
        if 'OBP' in df.columns and 'PA' in df.columns:
            df['OBP_marginal'] = (df['OBP'] - baseline.obp) * df['PA']
            logger.debug(
                f"OBP marginal range: [{df['OBP_marginal'].min():.1f}, "
                f"{df['OBP_marginal'].max():.1f}]"
            )
        else:
            logger.warning("Missing OBP or PA columns for hitters")

        # SLG marginal impact
        if 'SLG' in df.columns and 'AB' in df.columns:
            df['SLG_marginal'] = (df['SLG'] - baseline.slg) * df['AB']
            logger.debug(
                f"SLG marginal range: [{df['SLG_marginal'].min():.1f}, "
                f"{df['SLG_marginal'].max():.1f}]"
            )
        else:
            logger.warning("Missing SLG or AB columns for hitters")

    elif player_type == 'pitchers':
        # ERA marginal impact (inverted: lower ERA is better)
        if 'ERA' in df.columns and 'IP' in df.columns:
            df['ERA_marginal'] = (baseline.era - df['ERA']) * df['IP']
            logger.debug(
                f"ERA marginal range: [{df['ERA_marginal'].min():.1f}, "
                f"{df['ERA_marginal'].max():.1f}]"
            )
        else:
            logger.warning("Missing ERA or IP columns for pitchers")

        # WHIP marginal impact (inverted: lower WHIP is better)
        if 'WHIP' in df.columns and 'IP' in df.columns:
            df['WHIP_marginal'] = (baseline.whip - df['WHIP']) * df['IP']
            logger.debug(
                f"WHIP marginal range: [{df['WHIP_marginal'].min():.1f}, "
                f"{df['WHIP_marginal'].max():.1f}]"
            )
        else:
            logger.warning("Missing WHIP or IP columns for pitchers")

    return df
