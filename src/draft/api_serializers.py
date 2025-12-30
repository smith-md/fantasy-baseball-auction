"""
API serializers for stable contract endpoints.

Transforms internal data structures to contract-compliant response formats
as defined in the API Contract PRD.
"""

from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ========== Available Players Endpoint ==========

class AvailablePlayerResponse(BaseModel):
    """Individual player response for /players/available endpoint."""
    player_id: str
    name: str
    positions: List[str]
    market_value: float = Field(description="Market value in dollars")
    personal_value: float = Field(description="Personal value in dollars (auction_value)")
    sgp_total: float = Field(description="Total SGP across all categories")
    sgp_by_category: Dict[str, float] = Field(description="SGP breakdown by category")


class AvailablePlayersListResponse(BaseModel):
    """Response for GET /players/available endpoint."""
    updated_at: str = Field(description="ISO-8601 timestamp of last update")
    players: List[AvailablePlayerResponse]


# ========== Standings Endpoint ==========

class TeamStandingResponse(BaseModel):
    """Individual team standing for /standings endpoint."""
    team_id: str
    team_name: str
    total_roto_points: float
    categories: Dict[str, int] = Field(description="Category roto points (integers)")


class StandingsResponse(BaseModel):
    """Response for GET /standings endpoint."""
    updated_at: str = Field(description="ISO-8601 timestamp")
    teams: List[TeamStandingResponse] = Field(description="Teams sorted by total_roto_points descending")


# ========== League Resources Endpoint ==========

class TeamResourcesResponse(BaseModel):
    """Individual team resources for /league/resources endpoint."""
    team_id: str
    team_name: str
    remaining_budget: float
    open_roster_spots: Dict[str, int] = Field(description="Open slots by position")


class LeagueResourcesResponse(BaseModel):
    """Response for GET /league/resources endpoint."""
    updated_at: str = Field(description="ISO-8601 timestamp")
    teams: List[TeamResourcesResponse]


# ========== Recommendations Endpoint ==========

class PlayerRecommendation(BaseModel):
    """Player recommendation nested in category needs."""
    player_id: str
    name: str
    positions: List[str]
    expected_sgp_gain: float
    category_contributions: Dict[str, float]


class CategoryNeed(BaseModel):
    """Category gap and improvement recommendations."""
    category: str
    gap_to_next_rank: float = Field(description="Statistical units to next rank")
    sgp_per_unit: float


class TeamRecommendationsResponse(BaseModel):
    """Response for GET /recommendations endpoint."""
    team_id: str
    updated_at: str = Field(description="ISO-8601 timestamp")
    category_gaps: List[CategoryNeed] = Field(description="Sorted by ease of gain")
    recommended_players: List[PlayerRecommendation] = Field(description="Sorted by expected SGP gain")


# ========== Serializer Functions ==========

def serialize_available_players(
    cache_data: Dict,
    limit: Optional[int] = None,
    min_value: Optional[float] = None,
    position_filter: Optional[str] = None
) -> AvailablePlayersListResponse:
    """
    Transform ResultCache data to contract format.

    Args:
        cache_data: Cache dict from ResultCache.get_latest()
        limit: Optional limit on number of players
        min_value: Optional minimum auction_value filter
        position_filter: Optional position filter (e.g., 'OF', 'P')

    Returns:
        AvailablePlayersListResponse with filtered players
    """
    players_data = cache_data.get('players', [])
    timestamp = cache_data.get('timestamp', datetime.now().isoformat())

    # Filter players
    filtered_players = []
    for player in players_data:
        # Apply min_value filter
        auction_value = player.get('auction_value', 0)
        if min_value is not None and auction_value < min_value:
            continue

        # Apply position filter
        if position_filter:
            positions = player.get('positions', [])
            if isinstance(positions, str):
                positions = [positions]
            if position_filter not in positions:
                continue

        # Extract SGP by category
        sgp_by_category = {}
        sgp_total = 0.0

        # Hitter categories
        for cat in ['R', 'RBI', 'SB', 'OBP', 'SLG']:
            sgp_col = f'{cat}_sgp'
            if sgp_col in player:
                sgp_value = player[sgp_col] or 0
                sgp_by_category[cat] = round(sgp_value, 2)
                sgp_total += sgp_value

        # Pitcher categories
        for cat in ['W_QS', 'SV_HLD', 'K', 'ERA', 'WHIP']:
            sgp_col = f'{cat}_sgp'
            if sgp_col in player:
                sgp_value = player[sgp_col] or 0
                sgp_by_category[cat] = round(sgp_value, 2)
                sgp_total += sgp_value

        # Build player response
        filtered_players.append(AvailablePlayerResponse(
            player_id=player.get('player_id', player.get('player_name', '')),
            name=player.get('player_name', ''),
            positions=player.get('positions', []) if isinstance(player.get('positions'), list) else [player.get('positions', '')],
            market_value=round(auction_value, 1),  # MVP: market = personal
            personal_value=round(auction_value, 1),
            sgp_total=round(sgp_total, 2),
            sgp_by_category=sgp_by_category
        ))

    # Sort by personal_value descending (contract requirement)
    filtered_players.sort(key=lambda p: p.personal_value, reverse=True)

    # Apply limit
    if limit is not None:
        filtered_players = filtered_players[:limit]

    return AvailablePlayersListResponse(
        updated_at=timestamp,
        players=filtered_players
    )


def serialize_standings(
    standings: List[Dict],
    user_team_id: Optional[str] = None
) -> StandingsResponse:
    """
    Transform standings_calculator output to contract format.

    Args:
        standings: Output from calculate_projected_standings()
        user_team_id: Optional user team ID (not used in MVP contract)

    Returns:
        StandingsResponse with teams sorted by total_roto_points
    """
    teams = []

    for standing in standings:
        # Convert category_points to integers per contract
        category_points_int = {
            cat: int(points)
            for cat, points in standing['category_points'].items()
        }

        teams.append(TeamStandingResponse(
            team_id=standing['team_id'],
            team_name=standing['team_name'],
            total_roto_points=round(standing['total_points'], 1),
            categories=category_points_int
        ))

    # Already sorted by total_points in standings_calculator, but ensure
    teams.sort(key=lambda t: t.total_roto_points, reverse=True)

    return StandingsResponse(
        updated_at=datetime.now().isoformat(),
        teams=teams
    )


def serialize_league_resources(
    competition_metrics: Dict,
    user_team_id: Optional[str] = None
) -> LeagueResourcesResponse:
    """
    Transform competition_analyzer output to contract format.

    Args:
        competition_metrics: Output from calculate_competition_metrics()
        user_team_id: Optional user team ID (not used in MVP contract)

    Returns:
        LeagueResourcesResponse with team resources
    """
    teams_data = competition_metrics.get('teams', [])

    teams = []
    for team_data in teams_data:
        teams.append(TeamResourcesResponse(
            team_id=team_data['team_id'],
            team_name=team_data['team_name'],
            remaining_budget=round(team_data['budget_remaining'], 1),
            open_roster_spots=team_data['open_slots_by_position']
        ))

    # Already sorted by budget in competition_analyzer
    return LeagueResourcesResponse(
        updated_at=datetime.now().isoformat(),
        teams=teams
    )


def serialize_recommendations(
    team_needs_data: Dict,
    user_team_id: Optional[str] = None
) -> TeamRecommendationsResponse:
    """
    Transform team_needs_analyzer output to contract format.

    Args:
        team_needs_data: Dict containing:
            - team_id: Team ID
            - team_name: Team name
            - needs: Output from calculate_team_needs()
            - best_targets: Output from get_best_overall_targets()
        user_team_id: Optional user team ID (not used in MVP contract)

    Returns:
        TeamRecommendationsResponse with category gaps and recommendations
    """
    needs = team_needs_data.get('needs', [])
    best_targets = team_needs_data.get('best_targets', [])

    # Transform category needs
    category_gaps = []
    for need in needs:
        # Calculate SGP per unit
        stats_needed = need['stats_needed']
        sgp_per_unit = 0.0
        if stats_needed > 0 and need['top_recommendations']:
            # Use first recommended player's SGP as proxy
            first_player_sgp = need['top_recommendations'][0].get('category_sgp', 0)
            # Estimate SGP per stat unit
            sgp_per_unit = first_player_sgp / max(stats_needed, 1)

        category_gaps.append(CategoryNeed(
            category=need['category'],
            gap_to_next_rank=need['stats_needed'],
            sgp_per_unit=round(sgp_per_unit, 3)
        ))

    # Transform recommended players (from best_targets)
    recommended_players = []
    for player in best_targets[:10]:  # Limit to top 10
        # Build category contributions dict
        category_contributions = {}
        # Extract SGP contributions from player data
        # Note: best_targets includes 'need_sgp' and 'addresses_categories'
        # We need to look up individual category SGP values
        # For MVP, we'll use a simplified approach

        recommended_players.append(PlayerRecommendation(
            player_id=player.get('player_id', player.get('player_name', '')),
            name=player['player_name'],
            positions=player['positions'] if isinstance(player['positions'], list) else [player['positions']],
            expected_sgp_gain=player.get('need_sgp', player.get('raw_value', 0)),
            category_contributions=category_contributions  # Simplified for MVP
        ))

    # Sort recommended_players by expected_sgp_gain descending (contract requirement)
    recommended_players.sort(key=lambda p: p.expected_sgp_gain, reverse=True)

    return TeamRecommendationsResponse(
        team_id=team_needs_data.get('team_id', ''),
        updated_at=datetime.now().isoformat(),
        category_gaps=category_gaps,
        recommended_players=recommended_players
    )
