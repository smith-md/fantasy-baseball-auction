"""
Competition analyzer for league-wide resource tracking.

Provides visibility into remaining budgets and roster spots across all teams,
helping users identify which teams can still compete for specific players.
"""

import logging
from typing import Dict, List

from .league_schema import LeagueState

logger = logging.getLogger(__name__)


def calculate_competition_metrics(league_state: LeagueState, user_team_id: str = None) -> Dict:
    """
    Calculate league-wide resource availability and competition metrics.

    Algorithm:
    1. Extract budget_remaining and open_slots from each TeamState
    2. Calculate competition_score = (budget_share + slots_share) / 2
    3. Sort teams by budget_remaining descending
    4. Calculate league-wide totals

    Args:
        league_state: Current league state
        user_team_id: Optional team ID to mark as user's team

    Returns:
        Dict with:
        - teams: List of team resource dicts sorted by budget
        - league_totals: Summary of league-wide resources
    """
    logger.info(f"Calculating competition metrics for {len(league_state.teams)} teams")

    teams = []

    # Calculate league totals first (for competition scores)
    total_budget = sum(t.budget_remaining for t in league_state.teams.values())
    total_slots = sum(t.total_open_slots for t in league_state.teams.values())

    # Process each team
    for team_id, team in league_state.teams.items():
        # Competition score: team's share of remaining league resources
        budget_share = team.budget_remaining / total_budget if total_budget > 0 else 0
        slots_share = team.total_open_slots / total_slots if total_slots > 0 else 0
        competition_score = (budget_share + slots_share) / 2

        # Identify positions with multiple open slots (strong competition)
        high_need_positions = [
            pos for pos, count in team.open_slots.items()
            if count >= 2  # 2+ open slots = high need
        ]

        teams.append({
            'team_id': team_id,
            'team_name': team.team_name,
            'budget_remaining': round(team.budget_remaining, 2),
            'total_open_slots': team.total_open_slots,
            'open_slots_by_position': team.open_slots,
            'competition_score': round(competition_score, 3),
            'high_need_positions': high_need_positions,
            'is_user_team': (user_team_id is not None and team_id == user_team_id)
        })

    # Sort by budget descending (richest teams first)
    teams.sort(key=lambda t: t['budget_remaining'], reverse=True)

    # Calculate league totals
    league_totals = {
        'total_budget_remaining': round(total_budget, 2),
        'total_open_slots': total_slots,
        'avg_budget_per_team': round(total_budget / len(teams), 2) if teams else 0,
        'avg_slots_per_team': round(total_slots / len(teams), 1) if teams else 0,
        'avg_budget_per_slot': round(total_budget / total_slots, 2) if total_slots > 0 else 0
    }

    logger.info(
        f"Competition metrics: ${league_totals['total_budget_remaining']} total budget, "
        f"{league_totals['total_open_slots']} total slots"
    )

    return {
        'teams': teams,
        'league_totals': league_totals
    }


def get_positional_competition(league_state: LeagueState, position: str) -> Dict:
    """
    Get competition for a specific position.

    Args:
        league_state: Current league state
        position: Position to analyze (e.g., 'SS', 'P')

    Returns:
        Dict with:
        - position: Position name
        - teams_with_need: List of teams with open slots
        - total_slots_available: Total open slots across all teams
        - avg_budget_per_team_with_need: Average budget for teams needing this position
    """
    teams_with_need = []

    for team_id, team in league_state.teams.items():
        open_slots = team.open_slots.get(position, 0)
        if open_slots > 0:
            teams_with_need.append({
                'team_id': team_id,
                'team_name': team.team_name,
                'open_slots': open_slots,
                'budget_remaining': team.budget_remaining
            })

    # Sort by budget (richest first)
    teams_with_need.sort(key=lambda t: t['budget_remaining'], reverse=True)

    total_slots = sum(t['open_slots'] for t in teams_with_need)
    avg_budget = (
        sum(t['budget_remaining'] for t in teams_with_need) / len(teams_with_need)
        if teams_with_need else 0
    )

    return {
        'position': position,
        'teams_with_need': teams_with_need,
        'total_slots_available': total_slots,
        'avg_budget_per_team_with_need': round(avg_budget, 2)
    }
