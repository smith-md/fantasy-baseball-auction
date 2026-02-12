"""
Session lifecycle management for draft sessions.

The SessionManager coordinates:
- Starting/stopping draft sessions
- Controlling the polling thread
- Pausing/resuming polling
- Persisting session state
- Providing thread-safe status queries
"""

import logging
import threading
import time
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from .. import config
from .session_state import SessionState
from .live_draft_engine import LiveDraftEngine

logger = logging.getLogger(__name__)


class SessionAlreadyActiveError(Exception):
    """Raised when attempting to start a session while one is already active."""
    pass


class NoActiveSessionError(Exception):
    """Raised when attempting to operate on a session when none is active."""
    pass


class SessionManager:
    """
    Manages draft session lifecycle and polling thread.

    Thread-safe coordinator between HTTP API and LiveDraftEngine.
    """

    def __init__(self, session_dir: Path):
        """
        Initialize SessionManager.

        Args:
            session_dir: Directory for persisting session state files
        """
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # Current session state
        self.current_session: Optional[SessionState] = None
        self._engine: Optional[LiveDraftEngine] = None
        self._polling_thread: Optional[threading.Thread] = None

        # Thread synchronization
        self._lock = threading.Lock()
        self._should_poll_event = threading.Event()

        logger.info(f"SessionManager initialized (session_dir={self.session_dir})")

    def start_session(
        self,
        league_id: str,
        season: int,
        poll_interval: int = 5,
        keepers_file: Optional[str] = None,
        api_key: Optional[str] = None,
        num_teams: int = 12
    ) -> SessionState:
        """
        Start a new draft session.

        Args:
            league_id: Fantrax league identifier
            season: Projection season (e.g., 2026)
            poll_interval: Seconds between polls (default: 5)
            keepers_file: Optional path to keeper CSV
            api_key: Optional Fantrax API key
            num_teams: Number of teams (default: 12)

        Returns:
            SessionState with active=True

        Raises:
            SessionAlreadyActiveError: If a session is already active
        """
        with self._lock:
            if self.current_session and self.current_session.active:
                raise SessionAlreadyActiveError(
                    f"Session {self.current_session.session_id} is already active"
                )

            # Create new session
            session_id = f"{league_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.current_session = SessionState(
                session_id=session_id,
                league_id=league_id,
                active=True,
                paused=False,
                started_at=datetime.now(),
                poll_interval_seconds=poll_interval,
                season=season,
                num_teams=num_teams
            )

            logger.info(f"Starting session {session_id} (league={league_id}, season={season})")

            # Initialize engine
            try:
                self._engine = LiveDraftEngine(
                    season=season,
                    league_id=league_id,
                    api_key=api_key,
                    keepers_file=keepers_file,
                    poll_interval=poll_interval,
                    num_teams=num_teams
                )

                # Initialize engine (fetch projections, load state)
                logger.info("Initializing LiveDraftEngine...")
                self._engine.initialize()
                logger.info("LiveDraftEngine initialized successfully")

            except Exception as e:
                # Cleanup on failure
                self.current_session.active = False
                self.current_session.ended_at = datetime.now()
                self._persist_session_state()
                self.current_session = None
                self._engine = None
                raise RuntimeError(f"Failed to initialize engine: {e}") from e

            # Start polling thread
            self._should_poll_event.set()  # Allow polling
            self._polling_thread = threading.Thread(
                target=self._polling_loop,
                name=f"PollingThread-{session_id}",
                daemon=True
            )
            self._polling_thread.start()

            # Persist initial session state
            self._persist_session_state()

            logger.info(f"Session {session_id} started successfully")
            return self.current_session

    def stop_session(self) -> SessionState:
        """
        Stop the current session permanently.

        Gracefully shuts down the polling thread and marks session as ended.

        Returns:
            SessionState with active=False

        Raises:
            NoActiveSessionError: If no session is active
        """
        with self._lock:
            if not self.current_session or not self.current_session.active:
                raise NoActiveSessionError("No active session to stop")

            logger.info(f"Stopping session {self.current_session.session_id}")

            # Mark session as ended
            self.current_session.active = False
            self.current_session.ended_at = datetime.now()

            # Signal engine to shutdown
            if self._engine:
                self._engine.shutdown_requested = True

            session = self.current_session

        # Wait for thread to exit (outside lock to avoid deadlock)
        if self._polling_thread and self._polling_thread.is_alive():
            logger.info("Waiting for polling thread to exit...")
            self._polling_thread.join(timeout=10.0)

            if self._polling_thread.is_alive():
                logger.warning("Polling thread did not exit cleanly within timeout")
            else:
                logger.info("Polling thread exited successfully")

        # Persist final state
        with self._lock:
            self._persist_session_state()
            logger.info(f"Session {session.session_id} stopped (duration={session.duration_seconds:.0f}s)")

        return session

    def pause_session(self) -> SessionState:
        """
        Pause polling without ending session.

        Polling loop will sleep but session remains active.

        Returns:
            SessionState with paused=True

        Raises:
            NoActiveSessionError: If no session is active
        """
        with self._lock:
            if not self.current_session or not self.current_session.active:
                raise NoActiveSessionError("No active session to pause")

            logger.info(f"Pausing session {self.current_session.session_id}")

            self.current_session.paused = True
            self._should_poll_event.clear()  # Stop polling

            self._persist_session_state()

            return self.current_session

    def resume_session(self) -> SessionState:
        """
        Resume a paused session.

        Returns:
            SessionState with paused=False

        Raises:
            NoActiveSessionError: If no session is active
        """
        with self._lock:
            if not self.current_session or not self.current_session.active:
                raise NoActiveSessionError("No active session to resume")

            logger.info(f"Resuming session {self.current_session.session_id}")

            self.current_session.paused = False
            self._should_poll_event.set()  # Resume polling

            self._persist_session_state()

            return self.current_session

    def get_status(self) -> Dict:
        """
        Get current session status.

        Thread-safe status query combining session state and engine status.

        Returns:
            Dictionary with session and engine status
        """
        with self._lock:
            if not self.current_session:
                return {
                    'session_active': False,
                    'message': 'No session exists'
                }

            status = {
                'session_active': self.current_session.active,
                'session_paused': self.current_session.paused,
                'session_id': self.current_session.session_id,
                'league_id': self.current_session.league_id,
                'started_at': self.current_session.started_at.isoformat() if self.current_session.started_at else None,
                'ended_at': self.current_session.ended_at.isoformat() if self.current_session.ended_at else None,
                'last_poll_at': self.current_session.last_poll_at.isoformat() if self.current_session.last_poll_at else None,
                'duration_seconds': self.current_session.duration_seconds,
                'poll_interval_seconds': self.current_session.poll_interval_seconds,
                'total_polls': self.current_session.total_polls,
                'total_picks_detected': self.current_session.total_picks_detected,
                'last_valuation_time_seconds': self.current_session.last_valuation_time_seconds
            }

            # Add engine status if available
            if self._engine and self._engine.state_manager:
                state = self._engine.state_manager.state
                status['engine_status'] = {
                    'last_processed_pick': state.draft.last_processed_pick,
                    'total_picks': state.total_picks(),
                    'available_budget': sum(t.budget_remaining for t in state.teams.values()),
                    'available_roster_spots': sum(t.total_open_slots for t in state.teams.values())
                }

            return status

    def _should_poll(self) -> bool:
        """
        Callback for LiveDraftEngine to check if polling should occur.

        Returns:
            True if polling should continue, False if paused
        """
        with self._lock:
            if not self.current_session:
                return False
            return self.current_session.active and not self.current_session.paused

    def _polling_loop(self):
        """
        Background thread function that manages polling lifecycle.

        Runs while session is active, calls engine.poll_and_update() unless paused.
        Handles errors gracefully and continues polling (per PRD requirements).
        """
        logger.info(f"Polling loop started for session {self.current_session.session_id}")

        while True:
            with self._lock:
                if not self.current_session or not self.current_session.active:
                    logger.info("Session no longer active, exiting polling loop")
                    break

                # Check if paused
                if self.current_session.paused or not self._should_poll_event.is_set():
                    # Release lock and sleep briefly before checking again
                    pass

            # If paused, sleep and continue
            if not self._should_poll_event.is_set():
                time.sleep(1)
                continue

            # Perform poll (outside lock to avoid blocking API requests)
            try:
                logger.debug("Executing poll_and_update...")
                start_time = time.time()

                result = self._engine.poll_and_update()

                elapsed = time.time() - start_time

                # Update session state
                with self._lock:
                    self.current_session.last_poll_at = datetime.now()
                    self.current_session.total_polls += 1

                    if result is not None:
                        # New picks detected (poll_and_update returns updated valuations)
                        new_picks = len(result)  # Approximate
                        self.current_session.total_picks_detected += 1  # Track poll that found picks
                        self.current_session.last_valuation_time_seconds = elapsed
                        logger.info(f"Poll detected updates ({elapsed:.2f}s)")
                    else:
                        logger.debug(f"Poll found no new picks ({elapsed:.2f}s)")

                    # Persist updated state
                    self._persist_session_state()

            except Exception as e:
                logger.error(f"Poll failed: {e}", exc_info=True)
                # Continue polling despite errors (per PRD)

            # Sleep for poll interval
            with self._lock:
                interval = self.current_session.poll_interval_seconds if self.current_session else 5

            time.sleep(interval)

        logger.info("Polling loop exited")

    def _persist_session_state(self):
        """
        Atomically persist current session state to disk.

        Uses temp file + rename pattern for atomic writes.
        Must be called with self._lock held.
        """
        if not self.current_session:
            return

        session_file = self.session_dir / f"session_{self.current_session.session_id}.json"
        temp_file = self.session_dir / f"session_{self.current_session.session_id}.tmp"

        try:
            # Write to temp file
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(self.current_session.to_json(indent=2))

            # Atomic rename
            temp_file.replace(session_file)

            logger.debug(f"Persisted session state to {session_file}")

        except Exception as e:
            logger.error(f"Failed to persist session state: {e}")
            # Continue execution despite persistence failure
