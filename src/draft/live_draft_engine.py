"""
Main orchestrator for live draft mode.

The LiveDraftEngine coordinates all components:
- Fetches projections once at startup
- Polls Fantrax for new draft events
- Updates league state when picks occur
- Re-runs valuation pipeline on each update
- Caches results for consumption
"""

import logging
import time
import signal
import sys
import tempfile
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime

from .. import config
from ..data_fetcher import FanGraphsFetcher
from ..projection_combiner import combine_hitter_projections, combine_pitcher_projections
from ..stat_converter import (
    convert_hitter_stats,
    convert_pitcher_stats,
    get_hitter_categories_for_normalization,
    get_pitcher_categories_for_normalization,
)
from ..sgp_normalizer import normalize_hitters, normalize_pitchers
from ..position_optimizer import optimize_positions
from ..replacement_calculator import calculate_replacement_and_var
from ..dollar_allocator import allocate_dollars
from ..keeper_handler import process_keepers

from .draft_event import DraftEvent, create_initial_league_state
from .draft_state_manager import DraftStateManager
from .fantrax_client import FantraxClient
from .event_store import DraftEventStore, create_session_filepath
from .result_cache import ResultCache

logger = logging.getLogger(__name__)


class LiveDraftEngine:
    """Main orchestrator for live draft mode."""

    def __init__(
        self,
        season: int,
        league_id: str,
        api_key: Optional[str] = None,
        keepers_file: Optional[str] = None,
        poll_interval: int = 5,
        num_teams: int = 12
    ):
        """
        Initialize live draft engine.

        Args:
            season: Projection season (e.g., 2026)
            league_id: Fantrax league identifier
            api_key: Fantrax API authentication key
            keepers_file: Optional path to keeper CSV file
            poll_interval: Seconds between Fantrax polls (default: 5)
            num_teams: Number of teams in league (default: 12)
        """
        self.season = season
        self.league_id = league_id
        self.keepers_file = keepers_file
        self.poll_interval = poll_interval
        self.num_teams = num_teams

        # Components (initialized in initialize())
        self.fantrax_client = FantraxClient(league_id=league_id, api_key=api_key)
        self.state_manager: Optional[DraftStateManager] = None
        self.event_store: Optional[DraftEventStore] = None
        self.result_cache: Optional[ResultCache] = None

        # Cached projections (fetched once at startup)
        self.base_hitters_df: Optional[pd.DataFrame] = None
        self.base_pitchers_df: Optional[pd.DataFrame] = None

        # Session state
        self.session_active = False
        self.shutdown_requested = False

        # Performance tracking
        self.last_valuation_time = 0.0

    def initialize(self) -> None:
        """
        One-time setup for live draft session.

        Steps:
        1. Fetch projections from FanGraphs (steps 1-2 from main.py)
        2. Combine projection systems
        3. Fetch team/player mappings from Fantrax
        4. Initialize or load league state
        5. Setup event store and result cache
        6. Process keepers if provided
        7. Run initial valuation (pre-draft)
        """
        logger.info("="*60)
        logger.info("INITIALIZING LIVE DRAFT SESSION")
        logger.info("="*60)

        # Step 1-2: Fetch and combine projections
        logger.info("Fetching projections from FanGraphs...")
        fetcher = FanGraphsFetcher(season=self.season, use_cache=True)
        all_projections = fetcher.fetch_all()

        hitter_projections = all_projections['hitters']
        pitcher_projections = all_projections['pitchers']

        self.base_hitters_df = combine_hitter_projections(hitter_projections)
        self.base_pitchers_df = combine_pitcher_projections(pitcher_projections)

        logger.info(
            f"Loaded {len(self.base_hitters_df)} hitters, "
            f"{len(self.base_pitchers_df)} pitchers"
        )

        # Fetch Fantrax mappings
        logger.info("Fetching team/player mappings from Fantrax...")
        self.fantrax_client.load_mappings()

        # Setup event store
        event_file = create_session_filepath(
            base_dir=Path(config.DRAFT_EVENTS_DIR),
            league_id=self.league_id
        )
        self.event_store = DraftEventStore(event_file)
        logger.info(f"Event store: {event_file}")

        # Setup result cache
        self.result_cache = ResultCache(cache_dir=Path(config.DRAFT_CACHE_DIR))

        # Initialize or resume league state
        existing_events = self.event_store.load_all_events()

        if existing_events:
            logger.info(f"Resuming from {len(existing_events)} existing events")
            initial_state = create_initial_league_state(
                num_teams=self.num_teams,
                team_names=self.fantrax_client.team_id_to_name
            )
            self.state_manager = DraftStateManager(initial_state)
            self.state_manager.apply_events(existing_events)
        else:
            logger.info("Starting fresh draft session")
            initial_state = create_initial_league_state(
                num_teams=self.num_teams,
                team_names=self.fantrax_client.team_id_to_name
            )
            self.state_manager = DraftStateManager(initial_state)

        # Process keepers if provided
        if self.keepers_file:
            logger.info(f"Loading keepers from {self.keepers_file}")
            # Keepers will be processed in first valuation run

        # Run initial valuation
        logger.info("Running initial valuation (pre-draft)...")
        start_time = time.time()
        initial_valuations = self.run_valuation_pipeline()
        self.last_valuation_time = time.time() - start_time

        logger.info(
            f"Initial valuation complete: {len(initial_valuations)} players "
            f"(${self.state_manager.state.available_budget} available) "
            f"[{self.last_valuation_time:.2f}s]"
        )

        # Cache initial results
        self.result_cache.update(
            valuations_df=initial_valuations,
            league_state=self.state_manager.state,
            timestamp=datetime.now()
        )

        self.session_active = True
        logger.info("Live draft session initialized")

    def run_valuation_pipeline(self) -> pd.DataFrame:
        """
        Run full valuation pipeline with current draft state.

        This is the KEY integration point that reuses existing pipeline
        code (steps 3-8 from main.py) without modification.

        Returns:
            DataFrame with updated valuations for remaining players

        Performance target: < 1 second
        """
        # Convert current draft state to keeper format
        keeper_df = self.state_manager.to_keeper_format()

        # Write to temporary CSV file
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.csv',
            delete=False,
            newline=''
        ) as temp_file:
            temp_path = temp_file.name
            if len(keeper_df) > 0:
                keeper_df.to_csv(temp_file, index=False)
            else:
                # Write empty CSV with headers
                temp_file.write("player_id,keeper_salary\n")

        try:
            # Make copies of base projections (avoid modifying cached data)
            hitters_df = self.base_hitters_df.copy()
            pitchers_df = self.base_pitchers_df.copy()

            # Step 3: Process keepers (drafted players as "keepers")
            if len(keeper_df) > 0 or self.keepers_file:
                # Merge actual keepers with drafted players
                keeper_file_to_use = temp_path if len(keeper_df) > 0 else self.keepers_file

                hitters_df, pitchers_df, adjusted_budget, adjusted_roster_spots, _ = \
                    process_keepers(keeper_file_to_use, hitters_df, pitchers_df)
            else:
                adjusted_budget = config.TOTAL_BUDGET
                adjusted_roster_spots = config.TOTAL_PLAYERS

            # Step 4: Convert rate stats
            hitters_df = convert_hitter_stats(hitters_df)
            pitchers_df = convert_pitcher_stats(pitchers_df)

            # Step 5: Calculate SGP
            hitter_categories = get_hitter_categories_for_normalization()
            pitcher_categories = get_pitcher_categories_for_normalization()

            hitters_df = normalize_hitters(hitters_df, hitter_categories)
            pitchers_df = normalize_pitchers(pitchers_df, pitcher_categories)

            # Step 6: Optimize positions
            assignments_df = optimize_positions(hitters_df, pitchers_df)

            # Step 7: Calculate replacement and VAR
            assignments_df = calculate_replacement_and_var(assignments_df)

            # Step 8: Allocate dollars
            assignments_df = allocate_dollars(
                assignments_df,
                total_budget=adjusted_budget,
                total_players=adjusted_roster_spots
            )

            return assignments_df

        finally:
            # Clean up temp file
            try:
                Path(temp_path).unlink()
            except:
                pass

    def poll_and_update(self) -> Optional[pd.DataFrame]:
        """
        Single poll cycle: check for new picks and update if found.

        Returns:
            Updated valuations DataFrame if new picks detected, None otherwise
        """
        # Fetch current draft results from Fantrax
        try:
            raw_data = self.fantrax_client.fetch_draft_results()
        except Exception as e:
            logger.error(f"Failed to fetch draft results: {e}")
            return None

        # Normalize to events
        all_events = self.fantrax_client.normalize_to_events(
            raw_data,
            fangraphs_players_df=pd.concat([
                self.base_hitters_df,
                self.base_pitchers_df
            ])
        )

        # Filter to new events (picks after last_processed_pick)
        new_events = [
            e for e in all_events
            if e.pick_number > self.state_manager.state.last_processed_pick
        ]

        if not new_events:
            return None  # No new picks

        # Apply new events to state
        logger.info(f"Detected {len(new_events)} new pick(s)")
        for event in new_events:
            logger.info(
                f"  Pick {event.pick_number}: {event.player_name} → "
                f"{self.fantrax_client.team_id_to_name.get(event.team_id, event.team_id)} "
                f"(${event.price})"
            )

            # Apply to state
            self.state_manager.apply_event(event)

            # Append to event store
            self.event_store.append_event(event)

        # Re-run valuation pipeline
        logger.info("Recomputing valuations...")
        start_time = time.time()
        updated_valuations = self.run_valuation_pipeline()
        self.last_valuation_time = time.time() - start_time

        logger.info(
            f"Valuation complete: {len(updated_valuations)} players, "
            f"${self.state_manager.state.available_budget} available "
            f"[{self.last_valuation_time:.2f}s]"
        )

        # Update cache
        self.result_cache.update(
            valuations_df=updated_valuations,
            league_state=self.state_manager.state,
            timestamp=datetime.now()
        )

        return updated_valuations

    def run_live_session(
        self,
        duration_minutes: Optional[int] = None,
        output_callback: Optional[Callable] = None
    ) -> None:
        """
        Main event loop for live draft session.

        Args:
            duration_minutes: Run for N minutes (None = run until interrupted)
            output_callback: Optional function to call with each new valuation
                           Signature: callback(valuations_df, league_state)

        The loop polls Fantrax every poll_interval seconds and processes
        new draft events. Press Ctrl+C to stop gracefully.
        """
        # Setup signal handler for graceful shutdown
        def signal_handler(sig, frame):
            logger.info("\nShutdown requested (Ctrl+C)")
            self.shutdown_requested = True

        signal.signal(signal.SIGINT, signal_handler)

        logger.info("="*60)
        logger.info("STARTING LIVE DRAFT POLLING")
        logger.info("="*60)
        logger.info(f"League: {self.league_id}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Current state: {self.state_manager.state.total_picks()} picks, "
                   f"${self.state_manager.state.available_budget} available")
        logger.info("Press Ctrl+C to stop")
        logger.info("="*60)

        start_time = time.time()
        poll_count = 0

        while self.session_active and not self.shutdown_requested:
            # Check duration limit
            if duration_minutes is not None:
                elapsed_minutes = (time.time() - start_time) / 60
                if elapsed_minutes >= duration_minutes:
                    logger.info(f"Duration limit reached ({duration_minutes} minutes)")
                    break

            # Poll for updates
            poll_count += 1
            logger.debug(f"Poll #{poll_count}...")

            try:
                updated_valuations = self.poll_and_update()

                if updated_valuations is not None:
                    # New picks detected and processed
                    if output_callback:
                        output_callback(updated_valuations, self.state_manager.state)

            except Exception as e:
                logger.error(f"Error during poll cycle: {e}", exc_info=True)
                # Continue polling despite errors

            # Sleep until next poll
            time.sleep(self.poll_interval)

        # Cleanup
        self.session_active = False
        logger.info("="*60)
        logger.info("LIVE DRAFT SESSION ENDED")
        logger.info("="*60)
        logger.info(f"Final state: {self.state_manager.state.total_picks()} picks, "
                   f"${self.state_manager.state.available_budget} remaining")
        logger.info(f"Total polls: {poll_count}")
        logger.info(f"Average valuation time: {self.last_valuation_time:.2f}s")
        logger.info("="*60)

    def save_checkpoint(self) -> None:
        """Save current state to checkpoint file."""
        checkpoint_dir = Path(config.DRAFT_CHECKPOINTS_DIR)
        checkpoint_file = checkpoint_dir / f"state_{self.league_id}_pick{self.state_manager.state.last_processed_pick}.json"

        self.state_manager.save_checkpoint(checkpoint_file)

    def close(self) -> None:
        """Clean up resources."""
        if self.fantrax_client:
            self.fantrax_client.close()
