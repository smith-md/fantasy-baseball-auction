"""
Standings calculator for projected rotisserie standings.

Calculates what the final league standings would be if the draft ended now,
with remaining roster spots filled by replacement-level players.
"""

import logging
from typing import Dict, List, Optional, Set, Tuple
from copy import deepcopy

from .league_schema import LeagueState, TeamStats, ReplacementProfile
from .. import config

logger = logging.getLogger(__name__)

BENCH_SLOTS = {'BN_H', 'BN_P'}


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


def select_optimal_lineup(
    team,
    player_pool: dict,
    player_stats_lookup: dict
) -> Tuple[Set[str], Dict[str, int]]:
    """
    Select the optimal active lineup for a team.

    Picks the best players for active slots by priority (PA for hitters,
    IP*10 for pitchers), filling most-scarce specific slots first so that
    UTIL is only used when no specific slot is available.

    Args:
        team: TeamState whose roster to evaluate
        player_pool: Full league player pool (player_id -> PlayerState)
        player_stats_lookup: Mapping of player_id -> raw stats dict

    Returns:
        Tuple of:
          - active_player_ids: set of player IDs placed in active slots
          - open_active_slots: dict of position -> remaining unfilled active slots
    """
    from .position_assigner import determine_player_type

    # Total active slot capacity (reassign everyone fresh, ignore current assignment)
    remaining = {
        pos: count
        for pos, count in config.ROSTER_SLOTS_PER_TEAM.items()
        if pos not in BENCH_SLOTS
    }

    # Collect all drafted players across all roster positions
    all_players = []
    seen_ids: Set[str] = set()
    for player_ids in team.roster.values():
        for pid in player_ids:
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            if pid not in player_pool:
                continue
            player = player_pool[pid]
            stats = player_stats_lookup.get(pid, {})
            try:
                ptype = determine_player_type(player)
            except ValueError:
                ptype = 'hitter'
            # Use raw SGP value as priority — directly measures standings contribution.
            # Fall back to volume proxy if raw_value not present.
            raw_value = stats.get('raw_value')
            if raw_value is not None and raw_value == raw_value:  # not NaN
                priority = float(raw_value)
            elif ptype == 'hitter':
                priority = float(stats.get('PA') or 0)
            else:
                priority = float(stats.get('IP') or 0) * 10
            all_players.append((pid, priority, player, ptype))

    # Best players first
    all_players.sort(key=lambda x: x[1], reverse=True)

    active_ids: Set[str] = set()
    for pid, priority, player, ptype in all_players:
        # Build set of eligible active slots this player could fill
        eligible: Set[str] = set()
        if ptype == 'hitter':
            for p in player.eligible_positions:
                if p in remaining:
                    eligible.add(p)
                # OF consolidates LF/CF/RF
                if p in {'LF', 'CF', 'RF', 'OF'}:
                    eligible.add('OF')
            eligible.add('UTIL')
        else:
            eligible.add('P')

        # Keep only slots that still have capacity
        eligible = {p for p in eligible if remaining.get(p, 0) > 0}
        if not eligible:
            continue  # This player goes to bench

        # Prefer specific slots over UTIL; among specific slots pick most-scarce
        specific = {p for p in eligible if p != 'UTIL'}
        if specific:
            chosen = min(specific, key=lambda p: remaining[p])
        else:
            chosen = 'UTIL'

        remaining[chosen] -= 1
        active_ids.add(pid)

    return active_ids, remaining


def rank_teams_by_category(teams_data: List[Dict], categories: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Rank teams by each category. Tied teams share the average rank.

    Args:
        teams_data: List of team dicts with projected_stats
        categories: List of category names to rank

    Returns:
        Dict mapping team_id -> {category -> rank} (ties get averaged rank, e.g. 6.5)
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

        # Assign ranks with tie handling (tied teams share avg rank)
        i = 0
        while i < len(team_values):
            # Find all teams tied at this value
            j = i + 1
            while j < len(team_values) and team_values[j][1] == team_values[i][1]:
                j += 1

            # Average rank for tied positions (1-indexed)
            avg_rank = (i + 1 + j) / 2.0
            for k in range(i, j):
                ranks[team_values[k][0]][category] = avg_rank

            i = j

    return ranks


def calculate_projected_standings(
    league_state: LeagueState,
    user_team_id: str = None,
    stats_aggregator=None
) -> List[Dict]:
    """
    Calculate projected final standings based on current rosters + replacement fills.

    Algorithm:
    1. For each team, determine active lineup (optimal if stats_aggregator provided,
       otherwise use existing team.stats)
    2. Add replacement-level stats for each remaining open active slot
    3. Calculate rate stats from accumulated numerators/denominators
    4. Rank teams 1-12 for each category
    5. Convert ranks to roto points (1st = 12 pts, 12th = 1 pt)
    6. Sum category points to total points
    7. Sort by total points descending
    8. Calculate gaps between consecutive teams

    Args:
        league_state: Current league state
        user_team_id: Optional team ID to mark as user's team
        stats_aggregator: Optional TeamStatsAggregator; when provided, optimal
            lineup selection is used instead of the pre-aggregated team.stats

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
        if stats_aggregator is not None:
            # Optimal lineup: pick best players for active slots regardless of
            # which slot they happen to be assigned to in the roster dict
            active_ids, open_active_slots = select_optimal_lineup(
                team, league_state.players, stats_aggregator.player_stats
            )
            projected_stats = stats_aggregator.aggregate_for_player_ids(
                active_ids, league_state.players
            )
        else:
            # Fallback: use pre-aggregated stats and open_slots (bench excluded)
            projected_stats = deepcopy(team.stats)
            open_active_slots = {
                pos: count
                for pos, count in team.open_slots.items()
                if pos not in BENCH_SLOTS
            }

        # Add replacement-level stats for each unfilled active slot
        for position, open_count in open_active_slots.items():
            if open_count > 0:
                replacement_profile = league_state.replacement.by_position.get(position)
                if replacement_profile:
                    for _ in range(open_count):
                        projected_stats = add_replacement_stats(projected_stats, replacement_profile)
                else:
                    logger.warning(f"No replacement profile for position {position}")

        # Calculate rate stats from components
        rate_stats = projected_stats.calculate_rate_stats()

        # Combine counting and rate stats
        # Round counting stats to whole numbers (can't have fractional RBIs, Ks, etc.)
        rounded_counting = {cat: round(val) for cat, val in projected_stats.counting.items()}
        all_stats = {**rounded_counting, **rate_stats}

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
