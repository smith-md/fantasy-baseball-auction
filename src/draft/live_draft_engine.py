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
from ..sgp.replacement_baseline import calculate_replacement_baseline

from .draft_event import DraftEvent  # Keep for compatibility with event_store
from .league_schema import create_initial_league_state_v2, DraftEvent
from .draft_state_manager_v2 import DraftStateManagerV2
from .player_pool_manager import PlayerPoolManager
from .replacement_state_calculator import ReplacementStateCalculator
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
        self.state_manager: Optional[DraftStateManagerV2] = None
        self.event_store: Optional[DraftEventStore] = None
        self.result_cache: Optional[ResultCache] = None

        # Cached projections (fetched once at startup)
        self.base_hitters_df: Optional[pd.DataFrame] = None
        self.base_pitchers_df: Optional[pd.DataFrame] = None

        # Latest valuated DataFrame (with SGP columns, updated each pipeline run)
        self.all_players_df: Optional[pd.DataFrame] = None

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

        # Fetch rosters from Fantrax for keeper initialization
        logger.info("Fetching team rosters from Fantrax...")
        self.fantrax_rosters_raw: Optional[Dict] = None
        try:
            self.fantrax_rosters_raw = self.fantrax_client.fetch_rosters()
        except Exception as e:
            logger.warning(f"Could not fetch rosters from Fantrax: {e}. Keepers will not be loaded.")

        # Setup event store
        event_file = create_session_filepath(
            base_dir=Path(config.DRAFT_EVENTS_DIR),
            league_id=self.league_id
        )
        self.event_store = DraftEventStore(event_file)
        logger.info(f"Event store: {event_file}")

        # Setup result cache
        self.result_cache = ResultCache(cache_dir=Path(config.DRAFT_CACHE_DIR))

        # Initialize player pool from projections (v2 schema)
        logger.info("Initializing player pool...")
        player_pool_manager = PlayerPoolManager()
        players_dict = player_pool_manager.initialize_player_pool(
            self.base_hitters_df,
            self.base_pitchers_df
        )

        # Load per-team budgets from settings file if present
        import json
        team_budgets = None
        budgets_file = Path(config.DRAFT_BUDGETS_DIR) / f"draft_budgets_{self.season}.json"
        if budgets_file.exists():
            with open(budgets_file) as f:
                budgets_data = json.load(f)
            team_budgets = budgets_data.get('team_budgets')
            logger.info(f"Loaded per-team budgets from {budgets_file}")
        else:
            logger.info(f"No budget file found at {budgets_file}, using default ${config.BUDGET_PER_TEAM}/team")

        # Initialize or resume league state (v2)
        existing_events = self.event_store.load_all_events()

        # Check for existing checkpoint
        checkpoint_dir = Path(config.DRAFT_CHECKPOINTS_DIR)
        checkpoint_file = checkpoint_dir / f"state_{self.league_id}.json"

        if checkpoint_file.exists() or checkpoint_file.with_suffix('.json.gz').exists():
            logger.info("Loading from checkpoint...")
            self.state_manager = DraftStateManagerV2.load_checkpoint(
                checkpoint_file,
                self.base_hitters_df,
                self.base_pitchers_df,
                league_id=self.league_id
            )
        elif existing_events:
            logger.info(f"Resuming from {len(existing_events)} existing events")
            initial_state = create_initial_league_state_v2(
                league_id=self.league_id,
                players=players_dict,
                num_teams=self.num_teams,
                budget_per_team=config.BUDGET_PER_TEAM,
                team_names=self.fantrax_client.team_id_to_name,
                team_budgets=team_budgets
            )
            self.state_manager = DraftStateManagerV2(
                initial_state,
                self.base_hitters_df,
                self.base_pitchers_df
            )
            self.state_manager.apply_events(existing_events)
        else:
            logger.info("Starting fresh draft session")
            initial_state = create_initial_league_state_v2(
                league_id=self.league_id,
                players=players_dict,
                num_teams=self.num_teams,
                budget_per_team=config.BUDGET_PER_TEAM,
                team_names=self.fantrax_client.team_id_to_name,
                team_budgets=team_budgets
            )
            self.state_manager = DraftStateManagerV2(
                initial_state,
                self.base_hitters_df,
                self.base_pitchers_df
            )

            # Apply Fantrax roster keepers if available
            if self.fantrax_rosters_raw:
                self._apply_fantrax_keepers()

        # Process keepers if provided (legacy file-based fallback)
        if self.keepers_file:
            logger.info(f"Loading keepers from {self.keepers_file}")
            # Keepers will be processed in first valuation run

        # Run initial valuation
        logger.info("Running initial valuation (pre-draft)...")
        start_time = time.time()
        initial_valuations = self.run_valuation_pipeline()
        self.all_players_df = initial_valuations
        self.last_valuation_time = time.time() - start_time

        total_budget_remaining = sum(t.budget_remaining for t in self.state_manager.state.teams.values())
        logger.info(
            f"Initial valuation complete: {len(initial_valuations)} players "
            f"(${total_budget_remaining:.0f} available) "
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


    def _apply_fantrax_keepers(self) -> None:
        """
        Parse Fantrax roster data and apply keepers to the initial league state.

        Called once on a fresh session start. Keepers are applied as pick_number=0
        DraftEvents so they are reflected in team rosters and budgets before the
        auction begins.
        """
        import pandas as pd

        fangraphs_df = pd.concat([self.base_hitters_df, self.base_pitchers_df])

        keepers = self.fantrax_client.parse_rosters_to_keepers(
            self.fantrax_rosters_raw,
            fangraphs_players_df=fangraphs_df
        )

        if not keepers:
            logger.warning("No keepers parsed from Fantrax rosters -- check response structure in logs")
            return

        keeper_events = []
        for k in keepers:
            event = DraftEvent(
                pick_number=0,
                player_id=k['player_id'],
                player_name=k['player_name'],
                team_id=k['team_id'],
                price=k['keeper_salary'],
                timestamp=__import__('datetime').datetime.now(),
                assigned_position=None
            )
            keeper_events.append(event)

        logger.info(f"Applying {len(keeper_events)} Fantrax keepers to league state...")
        try:
            self.state_manager.apply_events(keeper_events)
            total_cost = sum(e.price for e in keeper_events)
            logger.info(f"Keepers applied: ${total_cost:.0f} total salary committed")
        except Exception as e:
            logger.error(f"Failed to apply Fantrax keepers: {e}", exc_info=True)

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

            # Step 7b: Calculate and store ReplacementState (v2 schema)
            # Get available players (undrafted)
            available_hitters = self.state_manager.get_available_players(hitters_df)
            available_pitchers = self.state_manager.get_available_players(pitchers_df)

            # Calculate replacement baselines
            hitter_baseline = calculate_replacement_baseline(available_hitters, 'hitters')
            pitcher_baseline = calculate_replacement_baseline(available_pitchers, 'pitchers')

            # Convert to ReplacementState and store in LeagueState
            replacement_state = ReplacementStateCalculator.calculate_replacement_state(
                hitter_baseline,
                pitcher_baseline,
                available_hitters,
                available_pitchers
            )
            self.state_manager.state.replacement = replacement_state

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
        self.all_players_df = updated_valuations
        self.last_valuation_time = time.time() - start_time

        total_budget_remaining = sum(t.budget_remaining for t in self.state_manager.state.teams.values())
        logger.info(
            f"Valuation complete: {len(updated_valuations)} players, "
            f"${total_budget_remaining:.0f} available "
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
        output_callback: Optional[Callable] = None,
        should_poll_callback: Optional[Callable[[], bool]] = None
    ) -> None:
        """
        Main event loop for live draft session.

        Args:
            duration_minutes: Run for N minutes (None = run until interrupted)
            output_callback: Optional function to call with each new valuation
                           Signature: callback(valuations_df, league_state)
            should_poll_callback: Optional callback to check if polling should occur
                                Returns True to poll, False to pause
                                Enables external control (e.g., SessionManager)

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
        total_budget_remaining = sum(t.budget_remaining for t in self.state_manager.state.teams.values())
        logger.info(f"League: {self.league_id}")
        logger.info(f"Poll interval: {self.poll_interval}s")
        logger.info(f"Current state: {self.state_manager.state.total_picks()} picks, "
                   f"${total_budget_remaining:.0f} available")
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

            # Check if external controller wants to pause
            if should_poll_callback and not should_poll_callback():
                time.sleep(1)  # Sleep briefly and check again
                continue

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
        total_budget_remaining = sum(t.budget_remaining for t in self.state_manager.state.teams.values())
        logger.info("="*60)
        logger.info("LIVE DRAFT SESSION ENDED")
        logger.info("="*60)
        logger.info(f"Final state: {self.state_manager.state.total_picks()} picks, "
                   f"${total_budget_remaining:.0f} remaining")
        logger.info(f"Total polls: {poll_count}")
        logger.info(f"Average valuation time: {self.last_valuation_time:.2f}s")
        logger.info("="*60)

    def save_checkpoint(self) -> None:
        """Save current state to checkpoint file (v2 with compression)."""
        checkpoint_dir = Path(config.DRAFT_CHECKPOINTS_DIR)
        checkpoint_file = checkpoint_dir / f"state_{self.league_id}.json"

        self.state_manager.save_checkpoint(checkpoint_file)

    def close(self) -> None:
        """Clean up resources."""
        if self.fantrax_client:
            self.fantrax_client.close()
