"""
FastAPI server for draft session control.

Provides HTTP endpoints to start, stop, pause, resume, and monitor draft sessions.
"""

import logging
from pathlib import Path
from typing import Optional, Dict
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .. import config
from .session_manager import (
    SessionManager,
    SessionAlreadyActiveError,
    NoActiveSessionError
)
from .result_cache import ResultCache
from .standings_calculator import calculate_projected_standings, get_standings_summary
from .competition_analyzer import calculate_competition_metrics
from .team_needs_analyzer import calculate_team_needs, get_best_overall_targets
from .api_contract_endpoints import contract_router

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Fantasy Baseball Draft Session API",
    description="Control draft session lifecycle for live draft mode",
    version="1.0.0"
)

# CORS middleware for web UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include contract API endpoints (stable contract)
app.include_router(contract_router, prefix="", tags=["Contract API"])

# Global session manager instance
session_manager = SessionManager(Path(config.DRAFT_SESSIONS_DIR))


# ===== Pydantic Models =====

class StartSessionRequest(BaseModel):
    """Request model for starting a draft session."""
    league_id: str = Field(..., description="Fantrax league ID")
    season: int = Field(..., description="Projection season (e.g., 2026)")
    poll_interval_seconds: int = Field(5, ge=1, le=60, description="Seconds between Fantrax polls")
    keepers_file: Optional[str] = Field(None, description="Path to keeper CSV file")
    api_key: Optional[str] = Field(None, description="Fantrax API authentication key")
    num_teams: int = Field(12, ge=4, le=20, description="Number of teams in league")


class SessionStatusResponse(BaseModel):
    """Response model for session operations."""
    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Human-readable status message")
    session: Optional[Dict] = Field(None, description="Session state details")


# ===== API Endpoints =====
# NOTE: The endpoints below are legacy endpoints maintained for backward compatibility.
# New frontends should use the Contract API endpoints defined in api_contract_endpoints.py

@app.post("/draft-session/start", response_model=SessionStatusResponse)
def start_draft_session(request: StartSessionRequest):
    """
    Start a new draft session.

    Initializes LiveDraftEngine, fetches projections, and begins polling Fantrax.

    Returns:
        SessionStatusResponse with session details

    Raises:
        409 Conflict: If a session is already active
        500 Internal Server Error: If engine initialization fails
    """
    try:
        logger.info(
            f"Starting draft session: league={request.league_id}, "
            f"season={request.season}, poll_interval={request.poll_interval_seconds}s"
        )

        session = session_manager.start_session(
            league_id=request.league_id,
            season=request.season,
            poll_interval=request.poll_interval_seconds,
            keepers_file=request.keepers_file,
            api_key=request.api_key,
            num_teams=request.num_teams
        )

        return SessionStatusResponse(
            success=True,
            message=f"Session {session.session_id} started successfully",
            session=session.to_dict()
        )

    except SessionAlreadyActiveError as e:
        logger.warning(f"Cannot start session: {e}")
        raise HTTPException(status_code=409, detail=str(e))

    except Exception as e:
        logger.error(f"Failed to start session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start session: {e}")


@app.post("/draft-session/stop", response_model=SessionStatusResponse)
def stop_draft_session():
    """
    Stop the current draft session permanently.

    Gracefully shuts down polling and marks session as ended.

    Returns:
        SessionStatusResponse with final session state

    Raises:
        404 Not Found: If no active session exists
    """
    try:
        logger.info("Stopping draft session")

        session = session_manager.stop_session()

        return SessionStatusResponse(
            success=True,
            message=f"Session {session.session_id} stopped successfully",
            session=session.to_dict()
        )

    except NoActiveSessionError as e:
        logger.warning(f"Cannot stop session: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"Failed to stop session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop session: {e}")


@app.post("/draft-session/pause", response_model=SessionStatusResponse)
def pause_draft_session():
    """
    Pause polling temporarily without ending session.

    Session remains active but polling stops until resumed.

    Returns:
        SessionStatusResponse with paused session state

    Raises:
        404 Not Found: If no active session exists
    """
    try:
        logger.info("Pausing draft session")

        session = session_manager.pause_session()

        return SessionStatusResponse(
            success=True,
            message=f"Session {session.session_id} paused",
            session=session.to_dict()
        )

    except NoActiveSessionError as e:
        logger.warning(f"Cannot pause session: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"Failed to pause session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to pause session: {e}")


@app.post("/draft-session/resume", response_model=SessionStatusResponse)
def resume_draft_session():
    """
    Resume a paused draft session.

    Restarts polling if session was paused.

    Returns:
        SessionStatusResponse with resumed session state

    Raises:
        404 Not Found: If no active session exists
    """
    try:
        logger.info("Resuming draft session")

        session = session_manager.resume_session()

        return SessionStatusResponse(
            success=True,
            message=f"Session {session.session_id} resumed",
            session=session.to_dict()
        )

    except NoActiveSessionError as e:
        logger.warning(f"Cannot resume session: {e}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"Failed to resume session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resume session: {e}")


@app.get("/draft-session/status")
def get_session_status():
    """
    Get current session status.

    Returns real-time status including session metadata, poll counts,
    and engine state (picks, budget, roster spots).

    Returns:
        Dictionary with comprehensive session status
    """
    try:
        status = session_manager.get_status()
        return status

    except Exception as e:
        logger.error(f"Failed to get status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@app.get("/draft-session/results")
def get_latest_results():
    """
    Get latest valuation results from cache.

    Returns cached player valuations, team summaries, and league state.
    This is a convenience endpoint that reads from the ResultCache.

    Returns:
        Dictionary with player valuations and league state

    Raises:
        404 Not Found: If no results are cached yet
    """
    try:
        result_cache = ResultCache(Path(config.DRAFT_CACHE_DIR))
        results = result_cache.get_latest()

        if not results:
            raise HTTPException(
                status_code=404,
                detail="No cached results available yet. Start a session and wait for first poll."
            )

        return results

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to get results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get results: {e}")


@app.get("/draft-session/standings")
def get_projected_standings():
    """
    Get projected final standings based on current rosters + replacement fills.

    Calculates what the final league standings would be if the draft ended now,
    with remaining roster spots filled by replacement-level players.

    Returns:
        Dict with:
        - standings: List of team standing dicts sorted by total_points
        - summary: Key metrics about the standings

    Raises:
        404 Not Found: If no active session exists
        500 Internal Server Error: If calculation fails
    """
    try:
        # Need active engine to access league state
        if not session_manager._engine:
            raise HTTPException(
                status_code=404,
                detail="No active session. Start a session first to calculate standings."
            )

        league_state = session_manager._engine.draft_state_manager.league_state

        # Calculate standings with user team marked
        standings = calculate_projected_standings(
            league_state,
            user_team_id=config.USER_TEAM_ID
        )
        summary = get_standings_summary(standings)

        return {
            'standings': standings,
            'summary': summary
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to calculate standings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to calculate standings: {e}")


@app.get("/draft-session/competition")
def get_competition_metrics():
    """
    Get league-wide resource availability and competition metrics.

    Shows remaining budgets and roster spots across all teams,
    helping identify which teams can still compete for specific players.

    Returns:
        Dict with:
        - teams: List of team resource dicts sorted by budget
        - league_totals: Summary of league-wide resources

    Raises:
        404 Not Found: If no active session exists
        500 Internal Server Error: If calculation fails
    """
    try:
        # Need active engine to access league state
        if not session_manager._engine:
            raise HTTPException(
                status_code=404,
                detail="No active session. Start a session first to view competition."
            )

        league_state = session_manager._engine.draft_state_manager.league_state

        # Calculate competition metrics with user team marked
        metrics = calculate_competition_metrics(
            league_state,
            user_team_id=config.USER_TEAM_ID
        )

        return metrics

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to calculate competition metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to calculate competition metrics: {e}")


@app.get("/draft-session/team-needs")
def get_team_needs(team_id: Optional[str] = None):
    """
    Get strategic needs and player recommendations for a team.

    Analyzes which categories are easiest to improve and recommends
    specific players to help gain roto points efficiently.

    Args:
        team_id: Optional team ID (defaults to USER_TEAM_ID from config)

    Returns:
        Dict with:
        - team_id: Team being analyzed
        - team_name: Team name
        - needs: List of category needs sorted by ease_score
        - best_overall_targets: Top 10 players addressing multiple needs

    Raises:
        404 Not Found: If no active session exists
        500 Internal Server Error: If calculation fails
    """
    try:
        # Need active engine to access league state
        if not session_manager._engine:
            raise HTTPException(
                status_code=404,
                detail="No active session. Start a session first to calculate team needs."
            )

        # Use provided team_id or default to USER_TEAM_ID
        target_team_id = team_id or config.USER_TEAM_ID

        league_state = session_manager._engine.draft_state_manager.league_state

        # Check that team exists
        if target_team_id not in league_state.teams:
            raise HTTPException(
                status_code=404,
                detail=f"Team {target_team_id} not found in league state"
            )

        # Get available players from engine
        available_players_df = session_manager._engine.draft_state_manager.get_available_players(
            session_manager._engine.all_players_df
        )

        # Calculate standings (needed for team needs analysis)
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

        team = league_state.teams[target_team_id]

        return {
            'team_id': target_team_id,
            'team_name': team.team_name,
            'budget_remaining': round(team.budget_remaining, 2),
            'open_slots': team.total_open_slots,
            'needs': needs,
            'best_overall_targets': best_targets
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to calculate team needs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to calculate team needs: {e}")


@app.get("/draft-session/config")
def get_frontend_config():
    """
    Get frontend configuration settings.

    Returns configuration needed by the frontend including user team ID,
    league settings, roster structure, and scoring categories.

    Returns:
        Dict with frontend configuration
    """
    return {
        'user_team_id': config.USER_TEAM_ID,
        'num_teams': config.NUM_TEAMS,
        'budget_per_team': config.BUDGET_PER_TEAM,
        'roster_slots': {
            **config.HITTER_ROSTER,
            **config.PITCHER_ROSTER
        },
        'categories': {
            'hitters': config.HITTER_CATEGORIES,
            'pitchers': config.PITCHER_CATEGORIES
        },
        'auto_refresh_interval': config.FRONTEND_AUTO_REFRESH_INTERVAL
    }


@app.get("/health")
def health_check():
    """
    Simple health check endpoint.

    Returns:
        Status OK if server is running
    """
    return {
        "status": "ok",
        "service": "Fantasy Baseball Draft Session API",
        "version": "1.0.0"
    }


# Startup event
@app.on_event("startup")
async def startup_event():
    """Log startup message."""
    logger.info("Draft Session API server started")
    logger.info(f"Session directory: {config.DRAFT_SESSIONS_DIR}")
    logger.info(f"Cache directory: {config.DRAFT_CACHE_DIR}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully stop active sessions on shutdown."""
    logger.info("Draft Session API server shutting down")

    try:
        # Attempt to stop active session if exists
        session_manager.stop_session()
        logger.info("Active session stopped during shutdown")
    except NoActiveSessionError:
        logger.info("No active session to stop")
    except Exception as e:
        logger.error(f"Error stopping session during shutdown: {e}")


# ===== STATIC FILE SERVING FOR REACT FRONTEND =====

# Mount static assets and serve frontend
static_dir = Path(__file__).parent.parent.parent / "dist"

if static_dir.exists():
    logger.info(f"Serving frontend from: {static_dir}")

    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    # Serve index.html for root and SPA routes
    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        """Serve the React frontend at root."""
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        else:
            raise HTTPException(status_code=404, detail="Frontend index.html not found")

    @app.get("/draft", include_in_schema=False)
    async def serve_frontend_draft():
        """Serve the React frontend at /draft route (SPA fallback)."""
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        else:
            raise HTTPException(status_code=404, detail="Frontend index.html not found")
else:
    logger.warning(
        f"Frontend dist directory not found at {static_dir}. "
        "Frontend will not be served. Run 'npm run build' in the frontend directory."
    )
