"""
API contract endpoints - stable interface for draft day frontend.

Implements the 4 core endpoints defined in the API Contract PRD:
- GET /players/available
- GET /standings
- GET /league/resources
- GET /recommendations

These endpoints provide a stable contract independent of backend implementation.
"""

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from .. import config
from .result_cache import ResultCache
from .standings_calculator import calculate_projected_standings
from .competition_analyzer import calculate_competition_metrics
from .team_needs_analyzer import calculate_team_needs, get_best_overall_targets
from .api_serializers import (
    serialize_available_players,
    serialize_standings,
    serialize_league_resources,
    serialize_recommendations,
    AvailablePlayersListResponse,
    StandingsResponse,
    LeagueResourcesResponse,
    TeamRecommendationsResponse
)

logger = logging.getLogger(__name__)

# Create contract router
contract_router = APIRouter(tags=["Contract API"])


def get_session_manager():
    """Get session manager from api_server module."""
    from .api_server import session_manager
    return session_manager


@contract_router.get("/players/available", response_model=AvailablePlayersListResponse)
def get_available_players(
    limit: Optional[int] = Query(None, ge=1, le=500, description="Limit number of players returned"),
    min_value: Optional[float] = Query(None, ge=0, description="Minimum auction value filter"),
    position: Optional[str] = Query(None, description="Position filter (e.g., 'OF', 'P')")
):
    """
    Get available players sorted by personal value.

    Contract guarantees:
    - Sorted by personal_value descending
    - Only undrafted players returned
    - All categories included in sgp_by_category

    Args:
        limit: Optional limit on number of players (default: all)
        min_value: Optional minimum auction_value filter
        position: Optional position filter

    Returns:
        AvailablePlayersListResponse with filtered players

    Raises:
        404: No cached results available
        500: Backend error
    """
    try:
        # Get latest cache
        result_cache = ResultCache(Path(config.DRAFT_CACHE_DIR))
        cache_data = result_cache.get_latest()

        if not cache_data:
            raise HTTPException(
                status_code=404,
                detail="No cached results available"
            )

        # Serialize to contract format with filters
        response = serialize_available_players(
            cache_data,
            limit=limit,
            min_value=min_value,
            position_filter=position
        )

        logger.info(
            f"Returned {len(response.players)} available players "
            f"(limit={limit}, min_value={min_value}, position={position})"
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to get available players: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backend error: {e}")


@contract_router.get("/standings", response_model=StandingsResponse)
def get_standings():
    """
    Get projected final standings with roto points.

    Contract guarantees:
    - Teams sorted by total_roto_points descending
    - Category values are integers (roto points)

    Returns:
        StandingsResponse with projected standings

    Raises:
        404: No active draft session
        500: Backend error
    """
    try:
        session_manager = get_session_manager()

        # Check for active engine
        if not session_manager._engine:
            raise HTTPException(
                status_code=404,
                detail="No active draft session"
            )

        # Get league state
        league_state = session_manager._engine.draft_state_manager.league_state

        # Calculate projected standings
        standings = calculate_projected_standings(
            league_state,
            user_team_id=config.USER_TEAM_ID
        )

        # Serialize to contract format
        response = serialize_standings(standings, user_team_id=config.USER_TEAM_ID)

        logger.info(f"Returned standings for {len(response.teams)} teams")

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to get standings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backend error: {e}")


@contract_router.get("/league/resources", response_model=LeagueResourcesResponse)
def get_league_resources():
    """
    Get league-wide budget and roster availability.

    Contract guarantees:
    - Budget values reflect remaining dollars only
    - Open roster spots reflect remaining eligible slots

    Returns:
        LeagueResourcesResponse with team resources

    Raises:
        404: No active draft session
        500: Backend error
    """
    try:
        session_manager = get_session_manager()

        # Check for active engine
        if not session_manager._engine:
            raise HTTPException(
                status_code=404,
                detail="No active draft session"
            )

        # Get league state
        league_state = session_manager._engine.draft_state_manager.league_state

        # Calculate competition metrics
        metrics = calculate_competition_metrics(
            league_state,
            user_team_id=config.USER_TEAM_ID
        )

        # Serialize to contract format
        response = serialize_league_resources(metrics, user_team_id=config.USER_TEAM_ID)

        logger.info(f"Returned league resources for {len(response.teams)} teams")

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to get league resources: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backend error: {e}")


@contract_router.get("/recommendations", response_model=TeamRecommendationsResponse)
def get_recommendations(
    team_id: Optional[str] = Query(None, description="Team ID (defaults to user team)")
):
    """
    Get strategic recommendations for a team.

    Contract guarantees:
    - Categories sorted by ease of gain (highest marginal impact first)
    - Players sorted by expected SGP gain

    Args:
        team_id: Optional team ID (defaults to USER_TEAM_ID)

    Returns:
        TeamRecommendationsResponse with category gaps and player recommendations

    Raises:
        404: No active session or team not found
        500: Backend error
    """
    try:
        session_manager = get_session_manager()

        # Check for active engine
        if not session_manager._engine:
            raise HTTPException(
                status_code=404,
                detail="No active draft session"
            )

        # Use provided team_id or default to USER_TEAM_ID
        target_team_id = team_id or config.USER_TEAM_ID

        # Get league state
        league_state = session_manager._engine.draft_state_manager.league_state

        # Verify team exists
        if target_team_id not in league_state.teams:
            raise HTTPException(
                status_code=404,
                detail=f"Team not found"
            )

        # Get available players
        available_players_df = session_manager._engine.draft_state_manager.get_available_players(
            session_manager._engine.all_players_df
        )

        # Calculate standings (needed for needs analysis)
        standings = calculate_projected_standings(league_state, target_team_id)

        # Calculate team needs
        needs = calculate_team_needs(
            target_team_id,
            league_state,
            available_players_df,
            standings
        )

        # Get best overall targets
        best_targets = get_best_overall_targets(
            target_team_id,
            needs,
            available_players_df,
            limit=10
        )

        # Build team_needs_data dict for serializer
        team = league_state.teams[target_team_id]
        team_needs_data = {
            'team_id': target_team_id,
            'team_name': team.team_name,
            'needs': needs,
            'best_targets': best_targets
        }

        # Serialize to contract format
        response = serialize_recommendations(team_needs_data, user_team_id=config.USER_TEAM_ID)

        logger.info(
            f"Returned recommendations for team {target_team_id}: "
            f"{len(response.category_gaps)} category gaps, "
            f"{len(response.recommended_players)} players"
        )

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backend error: {e}")
