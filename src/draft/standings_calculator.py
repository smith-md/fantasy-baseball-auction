"""
Standings calculator for projected rotisserie standings.

Calculates what the final league standings would be if the draft ended now,
with remaining roster spots filled by replacement-level players.
"""

import logging
from typing import Dict, List
from copy import deepcopy

from .league_schema import LeagueState, TeamStats, ReplacementProfile
from .. import config

logger = logging.getLogger(__name__)


def add_replacement_stats(team_stats: TeamStats, replacement: ReplacementProfile) -> TeamStats:
    """
    Add replacement-level player stats to team stats.

    Args:
        team_stats: Current team stats
        replacement: Replacement-level profile to add

    Returns:
        New TeamStats with replacement stats added
    """
    new_stats = TeamStats(
        counting=team_stats.counting.copy(),
        rate_numerators=team_stats.rate_numerators.copy(),
        rate_denominators=team_stats.rate_denominators.copy()
    )

    # Add counting stats
    for cat, value in replacement.counting.items():
        new_stats.counting[cat] = new_stats.counting.get(cat, 0) + value

    # Add rate numerators
    for key, value in replacement.rate_numerators.items():
        new_stats.rate_numerators[key] = new_stats.rate_numerators.get(key, 0) + value

    # Add rate denominators
    for key, value in replacement.rate_denominators.items():
        new_stats.rate_denominators[key] = new_stats.rate_denominators.get(key, 0) + value

    return new_stats


def rank_teams_by_category(teams_data: List[Dict], categories: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Rank teams by each category.

    Args:
        teams_data: List of team dicts with projected_stats
        categories: List of category names to rank

    Returns:
        Dict mapping team_id -> {category -> rank (1-12)}
    """
    ranks = {team['team_id']: {} for team in teams_data}

    for category in categories:
        # Get category values for all teams
        team_values = []
        for team in teams_data:
            value = team['projected_stats'].get(category, 0)
            team_values.append((team['team_id'], value))

        # Sort by value (descending for most cats, ascending for ERA/WHIP)
        reverse = category not in ['ERA', 'WHIP']
        team_values.sort(key=lambda x: x[1], reverse=reverse)

        # Assign ranks (1 = best)
        for rank_idx, (team_id, value) in enumerate(team_values, start=1):
            ranks[team_id][category] = rank_idx

    return ranks


def calculate_projected_standings(league_state: LeagueState, user_team_id: str = None) -> List[Dict]:
    """
    Calculate projected final standings based on current rosters + replacement fills.

    Algorithm:
    1. For each team, start with current TeamStats
    2. Add replacement-level stats for each open slot
    3. Calculate rate stats from accumulated numerators/denominators
    4. Rank teams 1-12 for each category
    5. Convert ranks to roto points (1st = 12 pts, 12th = 1 pt)
    6. Sum category points to total points
    7. Sort by total points descending
    8. Calculate gaps between consecutive teams

    Args:
        league_state: Current league state
        user_team_id: Optional team ID to mark as user's team

    Returns:
        List of team standing dicts sorted by total_points, each containing:
        - team_id, team_name
        - total_points (sum of category points)
        - category_points (dict of category -> roto points)
        - category_ranks (dict of category -> rank 1-12)
        - projected_stats (dict of category -> stat value)
        - gaps_to_next (dict of category -> points gap to next team)
        - is_user_team (bool)
    """
    logger.info(f"Calculating projected standings for {len(league_state.teams)} teams")

    standings = []

    # Step 1-3: Calculate projected stats for each team
    for team_id, team in league_state.teams.items():
        # Start with current roster stats
        projected_stats = deepcopy(team.stats)

        # Add replacement-level stats for each open slot
        for position, open_count in team.open_slots.items():
            if open_count > 0:
                replacement_profile = league_state.replacement.by_position.get(position)
                if replacement_profile:
                    # Add replacement stats for each open slot
                    for _ in range(open_count):
                        projected_stats = add_replacement_stats(projected_stats, replacement_profile)
                else:
                    logger.warning(f"No replacement profile for position {position}")

        # Calculate rate stats from components
        rate_stats = projected_stats.calculate_rate_stats()

        # Combine counting and rate stats
        all_stats = {**projected_stats.counting, **rate_stats}

        standings.append({
            'team_id': team_id,
            'team_name': team.team_name,
            'projected_stats': all_stats
        })

    # Step 4: Rank teams by each category
    all_categories = config.HITTER_CATEGORIES + config.PITCHER_CATEGORIES
    category_ranks = rank_teams_by_category(standings, all_categories)

    # Step 5: Convert ranks to rotisserie points
    num_teams = len(standings)
    for team in standings:
        team_id = team['team_id']
        team['category_ranks'] = category_ranks[team_id]

        # Roto points: 1st place = num_teams points, last place = 1 point
        category_points = {}
        for category in all_categories:
            rank = category_ranks[team_id][category]
            points = num_teams - rank + 1
            category_points[category] = points

        team['category_points'] = category_points
        team['total_points'] = sum(category_points.values())

    # Step 6: Sort by total points descending
    standings.sort(key=lambda x: x['total_points'], reverse=True)

    # Step 7: Calculate gaps to next team
    for i, team in enumerate(standings):
        gaps = {}

        if i > 0:
            # Compare to team ahead
            team_ahead = standings[i - 1]

            for category in all_categories:
                # Points gap
                points_gap = team_ahead['category_points'][category] - team['category_points'][category]

                # Stats gap (how much stat difference caused the rank gap)
                stat_gap = abs(
                    team_ahead['projected_stats'][category] - team['projected_stats'][category]
                )

                gaps[category] = {
                    'points': points_gap,
                    'stats': round(stat_gap, 2)
                }

        team['gaps_to_next'] = gaps
        team['is_user_team'] = (user_team_id is not None and team['team_id'] == user_team_id)

    logger.info(f"Calculated standings: leader has {standings[0]['total_points']} total points")

    return standings


def get_standings_summary(standings: List[Dict]) -> Dict:
    """
    Generate a summary of the standings for API response.

    Args:
        standings: Output from calculate_projected_standings

    Returns:
        Summary dict with key metrics
    """
    if not standings:
        return {'num_teams': 0, 'point_spread': 0}

    leader = standings[0]
    last_place = standings[-1]

    return {
        'num_teams': len(standings),
        'leader_team': leader['team_name'],
        'leader_points': leader['total_points'],
        'last_place_points': last_place['total_points'],
        'point_spread': leader['total_points'] - last_place['total_points']
    }
