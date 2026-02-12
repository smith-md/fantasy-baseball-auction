"""
Keeper league initialization.

Initializes LeagueState with keepers pre-drafted, enabling
keeper leagues to start with non-empty rosters.
"""

import pandas as pd
from datetime import datetime
from typing import Optional
import logging

from .league_schema import (
    LeagueState,
    DraftEvent,
    create_initial_league_state_v2
)
from .player_pool_manager import PlayerPoolManager
from .draft_state_manager_v2 import DraftStateManagerV2
from .. import config

logger = logging.getLogger(__name__)


class KeeperInitializer:
    """Handles initialization of keeper leagues with pre-drafted players."""

    @staticmethod
    def initialize_from_keepers(
        keeper_file: str,
        hitters_df: pd.DataFrame,
        pitchers_df: pd.DataFrame,
        league_id: str = 'keeper_league',
        num_teams: int = 12,
        budget_per_team: float = 500.0
    ) -> LeagueState:
        """
        Create LeagueState with keepers pre-drafted.

        Args:
            keeper_file: Path to keeper CSV file
            hitters_df: Hitter projections DataFrame
            pitchers_df: Pitcher projections DataFrame
            league_id: League identifier
            num_teams: Number of teams in the league
            budget_per_team: Budget per team

        Returns:
            LeagueState with keepers already drafted

        Raises:
            FileNotFoundError: If keeper file doesn't exist
            ValueError: If keeper file is invalid
        """
        logger.info(f"Initializing keeper league from {keeper_file}...")

        # Step 1: Initialize full player pool (all undrafted)
        logger.debug("Initializing player pool from projections...")
        player_pool_manager = PlayerPoolManager()
        players = player_pool_manager.initialize_player_pool(hitters_df, pitchers_df)

        # Step 2: Load keeper CSV
        logger.debug(f"Loading keepers from {keeper_file}...")
        try:
            keepers_df = pd.read_csv(keeper_file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Keeper file not found: {keeper_file}")

        # Validate keeper CSV format
        required_cols = ['player_id', 'team_id', 'keeper_salary']
        missing = set(required_cols) - set(keepers_df.columns)
        if missing:
            raise ValueError(f"Keeper CSV missing required columns: {missing}")

        # Optionally add player_name if missing (lookup from player pool)
        if 'player_name' not in keepers_df.columns:
            keepers_df['player_name'] = keepers_df['player_id'].apply(
                lambda pid: players.get(str(pid)).player_name if str(pid) in players
                else f"Unknown_{pid}"
            )

        logger.info(f"Found {len(keepers_df)} keepers")

        # Step 3: Extract unique team IDs and create team_names dict
        team_ids = keepers_df['team_id'].unique()
        team_names = {team_id: f"Team {team_id}" for team_id in team_ids}

        # If keeper CSV has team_name column, use it
        if 'team_name' in keepers_df.columns:
            team_name_map = dict(zip(keepers_df['team_id'], keepers_df['team_name']))
            team_names.update(team_name_map)

        # Step 4: Create initial empty LeagueState
        logger.debug("Creating initial LeagueState...")
        initial_state = create_initial_league_state_v2(
            league_id=league_id,
            players=players,
            num_teams=num_teams,
            budget_per_team=budget_per_team,
            team_names=team_names
        )

        # Step 5: Create DraftEvents for each keeper
        logger.debug("Creating keeper DraftEvents...")
        keeper_events = []

        for idx, keeper in keepers_df.iterrows():
            player_id = str(keeper['player_id'])

            # Validate player exists in pool
            if player_id not in players:
                logger.warning(
                    f"Keeper player_id {player_id} not found in player pool - skipping"
                )
                continue

            event = DraftEvent(
                pick_number=0,  # Special value for keepers
                player_id=player_id,
                player_name=keeper['player_name'],
                team_id=str(keeper['team_id']),
                price=float(keeper['keeper_salary']),
                timestamp=datetime.now(),
                assigned_position=None  # Will be assigned by state manager
            )
            keeper_events.append(event)

        logger.info(
            f"Created {len(keeper_events)} keeper events "
            f"(total cost: ${sum(e.price for e in keeper_events):.0f})"
        )

        # Step 6: Apply keeper events to populate state
        logger.debug("Applying keeper events to LeagueState...")
        state_manager = DraftStateManagerV2(
            initial_state,
            hitters_df,
            pitchers_df
        )

        try:
            state_manager.apply_events(keeper_events)
        except Exception as e:
            logger.error(f"Failed to apply keeper events: {e}")
            raise ValueError(f"Keeper initialization failed: {e}") from e

        # Mark draft as inactive (keepers are pre-draft)
        state_manager.state.draft.active = False

        # Update metadata
        state_manager.state.metadata.source = 'keeper_initialization'
        state_manager.state.metadata.notes = (
            f"Initialized with {len(keeper_events)} keepers "
            f"from {keeper_file}"
        )

        logger.info(
            f"Keeper league initialized successfully: "
            f"{len(keeper_events)} keepers drafted, "
            f"${sum(t.budget_remaining for t in state_manager.state.teams.values()):.0f} "
            f"total budget remaining"
        )

        return state_manager.state

    @staticmethod
    def create_keeper_csv_template(
        output_file: str,
        num_teams: int = 12,
        num_keepers_per_team: int = 5
    ) -> None:
        """
        Create a template keeper CSV file.

        Args:
            output_file: Path for output CSV
            num_teams: Number of teams
            num_keepers_per_team: Number of keeper slots per team
        """
        template_data = []

        for i in range(1, num_teams + 1):
            team_id = f"team_{i:02d}"
            team_name = f"Team {i}"

            for j in range(1, num_keepers_per_team + 1):
                template_data.append({
                    'player_id': f'player_{i}_{j}',  # Placeholder
                    'player_name': f'Player {i}-{j}',  # Placeholder
                    'team_id': team_id,
                    'team_name': team_name,
                    'keeper_salary': 10  # Placeholder
                })

        template_df = pd.DataFrame(template_data)
        template_df.to_csv(output_file, index=False)

        logger.info(f"Created keeper CSV template: {output_file}")

    @staticmethod
    def validate_keepers(
        keepers_df: pd.DataFrame,
        hitters_df: pd.DataFrame,
        pitchers_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Validate keeper data and return any issues.

        Args:
            keepers_df: Keeper DataFrame to validate
            hitters_df: Hitter projections
            pitchers_df: Pitcher projections

        Returns:
            DataFrame with validation issues (empty if all valid)
        """
        issues = []

        # Create player ID lookup
        all_player_ids = set(
            list(hitters_df['player_id'].astype(str)) +
            list(pitchers_df['player_id'].astype(str))
        )

        # Check each keeper
        for idx, keeper in keepers_df.iterrows():
            player_id = str(keeper['player_id'])

            # Check if player exists
            if player_id not in all_player_ids:
                issues.append({
                    'row': idx,
                    'player_id': player_id,
                    'team_id': keeper.get('team_id'),
                    'issue': 'Player not found in projections'
                })

            # Check salary is positive
            if keeper['keeper_salary'] <= 0:
                issues.append({
                    'row': idx,
                    'player_id': player_id,
                    'team_id': keeper.get('team_id'),
                    'issue': f'Invalid salary: {keeper["keeper_salary"]}'
                })

        issues_df = pd.DataFrame(issues)

        if len(issues_df) > 0:
            logger.warning(f"Found {len(issues_df)} keeper validation issues")
        else:
            logger.info("All keepers validated successfully")

        return issues_df

    @staticmethod
    def export_keepers_from_state(
        league_state: LeagueState,
        output_file: str
    ) -> None:
        """
        Export current roster state as keeper CSV.

        Useful for saving current draft state as keepers for next season.

        Args:
            league_state: LeagueState to export
            output_file: Path for output CSV
        """
        keeper_data = []

        for team in league_state.teams.values():
            for position, player_ids in team.roster.items():
                for player_id in player_ids:
                    player = league_state.players[player_id]

                    keeper_data.append({
                        'player_id': player_id,
                        'player_name': player.player_name,
                        'team_id': team.team_id,
                        'team_name': team.team_name,
                        'keeper_salary': player.price,
                        'position': position
                    })

        keepers_df = pd.DataFrame(keeper_data)
        keepers_df.to_csv(output_file, index=False)

        logger.info(
            f"Exported {len(keepers_df)} players to keeper CSV: {output_file}"
        )
