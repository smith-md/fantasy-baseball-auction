"""
Generate diagnostic files for SGP calculations.

Provides transparency and validation by documenting:
1. Category rank distances
2. Gap distributions
3. Denominator calculations
4. Multi-year smoothing
5. Ratio marginal impacts
"""

import os
import logging
from typing import Dict
import pandas as pd

from .. import config
from .league_data_loader import SeasonStandings, rank_teams_by_category, get_categories_for_player_type
from .category_analyzer import analyze_category_gaps, get_gap_distribution_stats
from .replacement_baseline import ReplacementBaseline
from .sgp_calculator import SGPDenominators

logger = logging.getLogger(__name__)


def write_all_diagnostics(
    standings_data: Dict[int, SeasonStandings],
    denominators: Dict[str, SGPDenominators],
    baseline: ReplacementBaseline,
    player_sample: pd.DataFrame,
    player_type: str
):
    """
    Write all 5 diagnostic files.

    Args:
        standings_data: Historical standings data
        denominators: SGP denominators for all categories
        baseline: Replacement baseline
        player_sample: Sample of players for ratio impact examples
        player_type: 'hitters' or 'pitchers'
    """
    output_dir = config.DIAGNOSTICS_DIR

    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    logger.info(f"Writing diagnostic files to {output_dir}")

    # Select representative player sample for diagnostic #5
    sample = _select_diagnostic_player_sample(player_sample)

    # Write each diagnostic file
    write_category_rank_distance(standings_data, output_dir)
    write_gap_distribution(standings_data, output_dir)
    write_sgp_denominators(denominators, output_dir)
    write_multi_year_smoothing(denominators, output_dir)
    write_ratio_marginal_impact(baseline, sample, denominators, player_type, output_dir)

    logger.info("All diagnostic files written successfully")


def write_category_rank_distance(
    standings_data: Dict[int, SeasonStandings],
    output_dir: str
):
    """
    Diagnostic #1: Category Rank Distance File.

    Shows team ranks and gaps for each category/season.
    """
    logger.info("Writing diagnostic #1: Category rank distance")

    rows = []

    for season, standings in standings_data.items():
        for category in standings.categories:
            # Rank teams
            ranked = rank_teams_by_category(standings, category)

            # Record each rank and gap to next
            for i in range(len(ranked)):
                team = ranked.iloc[i]
                rank = i + 1
                value = team[category]

                # Calculate gap to next rank (if not last)
                if i < len(ranked) - 1:
                    next_team = ranked.iloc[i + 1]
                    next_value = next_team[category]
                    gap = abs(value - next_value)
                else:
                    gap = None

                rows.append({
                    'season': season,
                    'category': category,
                    'rank': rank,
                    'team': team['Team'],
                    'value': value,
                    'gap_to_next': gap
                })

    df = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, '01_category_rank_distance.csv')
    df.to_csv(output_path, index=False)
    logger.info(f"Wrote {len(df)} rows to {output_path}")


def write_gap_distribution(
    standings_data: Dict[int, SeasonStandings],
    output_dir: str
):
    """
    Diagnostic #2: Category Gap Distribution File.

    Shows raw gap distributions for identifying outliers.
    """
    logger.info("Writing diagnostic #2: Gap distribution")

    rows = []

    for season, standings in standings_data.items():
        for category in standings.categories:
            # Analyze gaps
            gap_analysis = analyze_category_gaps(standings, category)

            # Calculate distribution stats
            stats = get_gap_distribution_stats(gap_analysis.gaps)

            rows.append({
                'season': season,
                'category': category,
                'min_gap': stats['min'],
                'p25_gap': stats['p25'],
                'median_gap': stats['median'],
                'p75_gap': stats['p75'],
                'max_gap': stats['max'],
                'mean_gap': stats['mean'],
                'std_gap': stats['std'],
                'num_gaps': len(gap_analysis.gaps)
            })

    df = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, '02_category_gap_distribution.csv')
    df.to_csv(output_path, index=False)
    logger.info(f"Wrote {len(df)} rows to {output_path}")


def write_sgp_denominators(
    denominators: Dict[str, SGPDenominators],
    output_dir: str
):
    """
    Diagnostic #3: SGP Denominator Calculation File.

    Shows per-season denominators and aggregation method.
    """
    logger.info("Writing diagnostic #3: SGP denominators")

    rows = []

    for category, denom in denominators.items():
        for season, value in denom.per_season.items():
            rows.append({
                'category': category,
                'season': season,
                'denominator': value,
                'method': config.SGP_METHOD
            })

    df = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, '03_sgp_denominator_calculation.csv')
    df.to_csv(output_path, index=False)
    logger.info(f"Wrote {len(df)} rows to {output_path}")


def write_multi_year_smoothing(
    denominators: Dict[str, SGPDenominators],
    output_dir: str
):
    """
    Diagnostic #4: Multi-Year SGP Smoothing File.

    Shows how seasons are weighted and combined.
    """
    logger.info("Writing diagnostic #4: Multi-year smoothing")

    rows = []

    for category, denom in denominators.items():
        # Create one row per category showing all seasons
        row = {
            'category': category,
            'smoothed_denominator': denom.smoothed,
            'seasons_used': ','.join(map(str, denom.seasons_used))
        }

        # Add per-season columns
        for season, value in denom.per_season.items():
            weight = config.SGP_SEASON_WEIGHTS.get(season, 1.0)
            row[f'season_{season}_denom'] = value
            row[f'season_{season}_weight'] = weight

        rows.append(row)

    df = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, '04_multi_year_smoothing.csv')
    df.to_csv(output_path, index=False)
    logger.info(f"Wrote {len(df)} rows to {output_path}")


def write_ratio_marginal_impact(
    baseline: ReplacementBaseline,
    player_sample: pd.DataFrame,
    denominators: Dict[str, SGPDenominators],
    player_type: str,
    output_dir: str
):
    """
    Diagnostic #5: Ratio Category Marginal Impact File.

    Shows example calculations for ratio categories.
    """
    logger.info("Writing diagnostic #5: Ratio marginal impact")

    rows = []

    # Get ratio categories for this player type
    if player_type == 'hitters':
        ratio_categories = ['OBP', 'SLG']
    else:
        ratio_categories = ['ERA', 'WHIP']

    for category in ratio_categories:
        if category not in denominators:
            continue

        for _, player in player_sample.iterrows():
            # Get player name (use player_name if available)
            player_name = player.get('player_name', f"Player_{player.get('player_id', 'Unknown')}")

            # Get values
            player_value = player.get(category, 0)
            marginal = player.get(f'{category}_marginal', 0)
            sgp = player.get(f'{category}_sgp', 0)

            # Get baseline and playing time
            if player_type == 'hitters':
                baseline_value = baseline.obp if category == 'OBP' else baseline.slg
                playing_time = player.get('PA' if category == 'OBP' else 'AB', 0)
                time_stat = 'PA' if category == 'OBP' else 'AB'
            else:
                baseline_value = baseline.era if category == 'ERA' else baseline.whip
                playing_time = player.get('IP', 0)
                time_stat = 'IP'

            rows.append({
                'player': player_name,
                'category': category,
                'player_value': player_value,
                'replacement_value': baseline_value,
                'playing_time': playing_time,
                'time_stat': time_stat,
                'marginal_impact': marginal,
                'sgp_denominator': denominators[category].smoothed,
                'sgp': sgp
            })

    df = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, '05_ratio_marginal_impact.csv')
    df.to_csv(output_path, index=False)
    logger.info(f"Wrote {len(df)} rows to {output_path}")


def _select_diagnostic_player_sample(player_df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """
    Select representative players for ratio marginal impact diagnostic.

    Strategy:
    - Top 5 players by raw_value (if available)
    - 5 mid-tier players
    - 5 replacement-level players
    - 5 random selections

    Args:
        player_df: Player DataFrame
        n: Number of players to select

    Returns:
        Sample DataFrame
    """
    samples = []

    # Sort by raw_value if available, otherwise by first available stat
    if 'raw_value' in player_df.columns:
        sorted_df = player_df.sort_values('raw_value', ascending=False)
    elif 'PA' in player_df.columns:
        sorted_df = player_df.sort_values('PA', ascending=False)
    elif 'IP' in player_df.columns:
        sorted_df = player_df.sort_values('IP', ascending=False)
    else:
        sorted_df = player_df

    # Top 5
    if len(sorted_df) >= 5:
        samples.append(sorted_df.iloc[:5])

    # Mid-tier (around rank 50-55)
    if len(sorted_df) >= 55:
        samples.append(sorted_df.iloc[49:54])
    elif len(sorted_df) >= 25:
        mid = len(sorted_df) // 2
        samples.append(sorted_df.iloc[mid:mid+5])

    # Replacement tier (around rank 150-155 for hitters, 130-135 for pitchers)
    if len(sorted_df) >= 155:
        samples.append(sorted_df.iloc[149:154])
    elif len(sorted_df) >= 100:
        samples.append(sorted_df.iloc[-10:-5])

    # Random
    if len(sorted_df) >= 10:
        random_sample = sorted_df.sample(min(5, len(sorted_df) // 10))
        samples.append(random_sample)

    # Combine
    if samples:
        result = pd.concat(samples)
        # Drop duplicates based on player_id if available, otherwise use index
        if 'player_id' in result.columns:
            result = result.drop_duplicates(subset='player_id')
        else:
            result = result.drop_duplicates(subset=result.select_dtypes(exclude=['object', 'list']).columns.tolist())
        return result.iloc[:n]  # Limit to n players
    else:
        # Fallback: just take first n players
        return sorted_df.iloc[:n]
