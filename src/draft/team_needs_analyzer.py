"""
Team needs analyzer for strategic player recommendations.

Identifies which categories are easiest to improve and recommends specific players
to help the user's team gain roto points efficiently.
"""

import logging
from typing import Dict, List
import pandas as pd

from .league_schema import LeagueState
from .. import config

logger = logging.getLogger(__name__)


def find_team_at_rank(standings: List[Dict], category: str, target_rank: int) -> Dict:
    """
    Find the team at a specific rank for a given category.

    Args:
        standings: List of team standings
        category: Category to check
        target_rank: Rank to find (1-12)

    Returns:
        Team dict at that rank, or None if not found
    """
    for team in standings:
        if team['category_ranks'][category] == target_rank:
            return team
    return None


def find_next_better_team(standings: List[Dict], category: str, current_rank: float, team_id: str) -> Dict:
    """
    Find nearest team ranked strictly better (lower rank number) than us.

    Handles tied ranks (e.g., rank 6.5) where exact rank-1 lookup would fail.

    Args:
        standings: List of team standings
        category: Category to check
        current_rank: Our current rank (may be fractional due to ties)
        team_id: Our team ID (to exclude from results)

    Returns:
        Team dict of the closest better-ranked team, or None if no one is better
    """
    better_teams = [
        s for s in standings
        if s['category_ranks'][category] < current_rank and s['team_id'] != team_id
    ]
    if not better_teams:
        return None
    # Return closest better team (highest rank among those better than us)
    return max(better_teams, key=lambda s: s['category_ranks'][category])


def calculate_ease_score(
    points_to_next: float,
    stats_gap: float,
    available_sgp: float,
    budget_remaining: float
) -> float:
    """
    Calculate how easy it is to improve in a category.

    Higher score = easier to gain points.

    Args:
        points_to_next: Roto points gap to next rank
        stats_gap: Statistical gap to overtake next team
        available_sgp: Total SGP available from top players in this category
        budget_remaining: User team's remaining budget

    Returns:
        Ease score (0-1, higher is easier)
    """
    # No available SGP means we can't improve
    if available_sgp <= 0:
        return 0.0

    # No room to gain points and no stats gap — truly nothing to improve
    if points_to_next <= 0 and stats_gap <= 0:
        return 0.0

    # Tied scenario: stats_gap == 0 but points_to_next > 0 means any improvement breaks the tie
    if stats_gap == 0:
        sgp_ratio = 3.0  # Max ratio — any stat improvement helps
        gap_factor = 1.0  # No gap to close
    else:
        # More available SGP relative to the gap = easier
        sgp_ratio = min(available_sgp / stats_gap, 3.0)
        # Smaller gaps = easier to close
        gap_factor = 1.0 / (1.0 + stats_gap / 10.0)  # Normalize around 10 stat units

    # More budget = easier to acquire players
    budget_factor = min(budget_remaining / 100.0, 3.0)  # Normalize around $100

    # Combined score (weighted average)
    ease = (sgp_ratio * 0.4 + budget_factor * 0.3 + gap_factor * 0.3) / 3.0

    return min(ease, 1.0)  # Cap at 1.0


def find_top_players_for_category(
    available_players_df: pd.DataFrame,
    category: str,
    limit: int = 5
) -> List[Dict]:
    """
    Find top available players for a specific category.

    Args:
        available_players_df: DataFrame of available players with SGP columns
        category: Category name (e.g., 'R', 'SB', 'ERA')
        limit: Max number of players to return

    Returns:
        List of player recommendation dicts
    """
    # Category SGP column name
    sgp_col = f'{category}_sgp'

    # Check if column exists
    if sgp_col not in available_players_df.columns:
        logger.warning(f"SGP column {sgp_col} not found in available players")
        return []

    # Filter to players with positive SGP in this category
    df = available_players_df[available_players_df[sgp_col] > 0].copy()

    if df.empty:
        return []

    # Sort by category SGP descending
    df = df.sort_values(sgp_col, ascending=False).head(limit)

    # Build recommendations
    recommendations = []
    for _, player in df.iterrows():
        recommendations.append({
            'player_name': player['player_name'],
            'positions': player['positions'] if isinstance(player['positions'], list) else [player['positions']],
            'auction_value': round(player['auction_value'], 1),
            'raw_value': round(player.get('raw_value', 0), 2),
            'category_sgp': round(player[sgp_col], 2),
            'total_sgp': round(player.get('raw_value', 0), 2)
        })

    return recommendations


def calculate_team_needs(
    team_id: str,
    league_state: LeagueState,
    available_players_df: pd.DataFrame,
    standings: List[Dict]
) -> List[Dict]:
    """
    Calculate strategic needs for a specific team.

    Identifies which categories are easiest to improve and recommends
    specific players to target.

    Args:
        team_id: Team ID to analyze
        league_state: Current league state
        available_players_df: DataFrame of available players
        standings: Projected standings from standings_calculator

    Returns:
        List of category need dicts sorted by ease_score, each containing:
        - category: Category name
        - current_rank: Current rank (1-12)
        - points_to_next_rank: Roto points gap to next rank
        - stats_needed: Statistical units needed to improve one rank
        - ease_score: How easy it is to improve (0-1)
        - top_recommendations: List of recommended players
    """
    logger.info(f"Calculating team needs for {team_id}")

    # Find user team in standings
    user_standing = next((s for s in standings if s['team_id'] == team_id), None)
    if not user_standing:
        logger.error(f"Team {team_id} not found in standings")
        return []

    user_team = league_state.teams.get(team_id)
    if not user_team:
        logger.error(f"Team {team_id} not found in league state")
        return []

    needs = []
    all_categories = config.HITTER_CATEGORIES + config.PITCHER_CATEGORIES

    for category in all_categories:
        current_rank = user_standing['category_ranks'][category]

        # Skip if already sole first place
        if current_rank == 1:
            continue

        # Find nearest team ranked better than us (handles ties)
        next_team = find_next_better_team(standings, category, current_rank, team_id)

        if next_team:
            # Normal case: someone is ranked better
            user_stat = user_standing['projected_stats'][category]
            next_stat = next_team['projected_stats'][category]

            # For ERA/WHIP, lower is better (we want to reduce our stat)
            if category in ['ERA', 'WHIP']:
                stats_gap = user_stat - next_stat
            else:
                stats_gap = next_stat - user_stat

            # Points gap (how many roto points separate the ranks)
            points_gap = next_team['category_points'][category] - user_standing['category_points'][category]
        else:
            # Tied at top but not sole first (e.g., all teams rank 6.5)
            # Any improvement breaks the tie and moves us toward sole 1st
            stats_gap = 0
            points_gap = current_rank - 1  # Roto points gained by reaching sole 1st

        # Find top available players for this category
        top_players = find_top_players_for_category(available_players_df, category, limit=5)

        # Calculate total available SGP from top 5 players
        available_sgp = sum(p['category_sgp'] for p in top_players)

        # Calculate ease score
        ease = calculate_ease_score(
            points_to_next=points_gap,
            stats_gap=abs(stats_gap),
            available_sgp=available_sgp,
            budget_remaining=user_team.budget_remaining
        )

        needs.append({
            'category': category,
            'current_rank': current_rank,
            'next_rank': current_rank - 1 if next_team else 1,
            'points_to_next_rank': points_gap,
            'stats_needed': round(abs(stats_gap), 2),
            'stats_gap_type': 'reduce' if category in ['ERA', 'WHIP'] else 'increase',
            'ease_score': round(ease, 3),
            'top_recommendations': top_players[:3]  # Return top 3
        })

    # Sort by ease_score descending (easiest improvements first)
    needs.sort(key=lambda n: n['ease_score'], reverse=True)

    logger.info(f"Found {len(needs)} improvement opportunities for team {team_id}")

    return needs


def get_best_overall_targets(
    team_id: str,
    team_needs: List[Dict],
    available_players_df: pd.DataFrame,
    limit: int = 10
) -> List[Dict]:
    """
    Get best overall player targets considering all team needs.

    Args:
        team_id: Team ID
        team_needs: Output from calculate_team_needs
        available_players_df: Available players DataFrame
        limit: Max players to return

    Returns:
        List of top player targets with multi-category value
    """
    if available_players_df.empty:
        return []

    # Get top categories by ease score
    top_categories = [need['category'] for need in team_needs[:3]]  # Focus on top 3 needs

    # Score each player by SGP in top need categories
    players_scored = []

    for _, player in available_players_df.iterrows():
        # Sum SGP from top need categories
        need_sgp = 0
        for category in top_categories:
            sgp_col = f'{category}_sgp'
            if sgp_col in player.index:
                need_sgp += player[sgp_col]

        if need_sgp > 0:
            players_scored.append({
                'player_name': player['player_name'],
                'positions': player['positions'] if isinstance(player['positions'], list) else [player['positions']],
                'auction_value': round(player['auction_value'], 1),
                'raw_value': round(player.get('raw_value', 0), 2),
                'need_sgp': round(need_sgp, 2),
                'addresses_categories': top_categories
            })

    # Sort by need_sgp descending
    players_scored.sort(key=lambda p: p['need_sgp'], reverse=True)

    return players_scored[:limit]
