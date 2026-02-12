"""
Player pool initialization and management.

Converts projection DataFrames into the PlayerState dictionary format
required by the v2 LeagueState schema.
"""

import pandas as pd
from typing import Dict, List
import logging

from .league_schema import PlayerState

logger = logging.getLogger(__name__)


class PlayerPoolManager:
    """Manages initialization and updates of the player pool."""

    @staticmethod
    def initialize_player_pool(
        hitters_df: pd.DataFrame,
        pitchers_df: pd.DataFrame
    ) -> Dict[str, PlayerState]:
        """
        Convert projection DataFrames to PlayerState dict.

        Args:
            hitters_df: DataFrame with hitter projections (must have player_id, player_name, positions)
            pitchers_df: DataFrame with pitcher projections (must have player_id, player_name, positions)

        Returns:
            Dictionary mapping player_id to PlayerState (all players initially undrafted)

        Raises:
            ValueError: If required columns are missing
        """
        # Validate required columns
        required_cols = ['player_id', 'player_name', 'positions']
        for df_name, df in [('hitters_df', hitters_df), ('pitchers_df', pitchers_df)]:
            missing = set(required_cols) - set(df.columns)
            if missing:
                raise ValueError(
                    f"{df_name} missing required columns: {missing}"
                )

        players = {}

        # Process hitters
        for _, player in hitters_df.iterrows():
            player_id = str(player['player_id'])
            player_name = str(player['player_name'])
            positions = player['positions']

            # Handle different position formats
            if isinstance(positions, str):
                # Parse comma-separated or space-separated
                if ',' in positions:
                    eligible_positions = [p.strip() for p in positions.split(',')]
                else:
                    eligible_positions = [positions.strip()]
            elif isinstance(positions, list):
                eligible_positions = positions
            else:
                # Default fallback - try to convert to string
                eligible_positions = [str(positions)]

            # Clean up positions (remove empty strings)
            eligible_positions = [p for p in eligible_positions if p]

            players[player_id] = PlayerState(
                player_id=player_id,
                player_name=player_name,
                eligible_positions=eligible_positions,
                drafted=False,
                drafted_team_id=None,
                price=None
            )

        # Process pitchers
        for _, player in pitchers_df.iterrows():
            player_id = str(player['player_id'])
            player_name = str(player['player_name'])
            positions = player['positions']

            # Handle different position formats
            if isinstance(positions, str):
                # Parse comma-separated or space-separated
                if ',' in positions:
                    eligible_positions = [p.strip() for p in positions.split(',')]
                else:
                    eligible_positions = [positions.strip()]
            elif isinstance(positions, list):
                eligible_positions = positions
            else:
                # Default fallback
                eligible_positions = [str(positions)]

            # Clean up positions
            eligible_positions = [p for p in eligible_positions if p]

            # Ensure pitchers have at least 'P' position
            if not eligible_positions or not any(p in ['P', 'SP', 'RP'] for p in eligible_positions):
                eligible_positions = ['P']

            players[player_id] = PlayerState(
                player_id=player_id,
                player_name=player_name,
                eligible_positions=eligible_positions,
                drafted=False,
                drafted_team_id=None,
                price=None
            )

        logger.info(
            f"Initialized player pool: {len(players)} players "
            f"({len(hitters_df)} hitters, {len(pitchers_df)} pitchers)"
        )

        return players

    @staticmethod
    def update_drafted_status(
        players: Dict[str, PlayerState],
        player_id: str,
        team_id: str,
        price: float
    ) -> None:
        """
        Mark a player as drafted and update their state.

        Args:
            players: Player pool dictionary
            player_id: Player to mark as drafted
            team_id: Team that drafted the player
            price: Auction price paid

        Raises:
            ValueError: If player not found or already drafted
        """
        if player_id not in players:
            raise ValueError(f"Player {player_id} not found in pool")

        player = players[player_id]

        if player.drafted:
            raise ValueError(
                f"Player {player.player_name} already drafted by {player.drafted_team_id}"
            )

        player.drafted = True
        player.drafted_team_id = team_id
        player.price = price

        logger.debug(
            f"Marked {player.player_name} as drafted by {team_id} for ${price}"
        )

    @staticmethod
    def get_drafted_players(players: Dict[str, PlayerState]) -> List[PlayerState]:
        """
        Get list of all drafted players.

        Args:
            players: Player pool dictionary

        Returns:
            List of PlayerState objects for drafted players
        """
        return [player for player in players.values() if player.drafted]

    @staticmethod
    def get_undrafted_players(players: Dict[str, PlayerState]) -> List[PlayerState]:
        """
        Get list of all undrafted players.

        Args:
            players: Player pool dictionary

        Returns:
            List of PlayerState objects for undrafted players
        """
        return [player for player in players.values() if not player.drafted]

    @staticmethod
    def get_team_players(
        players: Dict[str, PlayerState],
        team_id: str
    ) -> List[PlayerState]:
        """
        Get all players drafted by a specific team.

        Args:
            players: Player pool dictionary
            team_id: Team to filter by

        Returns:
            List of PlayerState objects for the team
        """
        return [
            player for player in players.values()
            if player.drafted and player.drafted_team_id == team_id
        ]

    @staticmethod
    def get_player_by_id(
        players: Dict[str, PlayerState],
        player_id: str
    ) -> PlayerState:
        """
        Get a player by ID.

        Args:
            players: Player pool dictionary
            player_id: Player ID to look up

        Returns:
            PlayerState object

        Raises:
            ValueError: If player not found
        """
        if player_id not in players:
            raise ValueError(f"Player {player_id} not found in pool")

        return players[player_id]

    @staticmethod
    def validate_player_pool(players: Dict[str, PlayerState]) -> None:
        """
        Validate player pool consistency.

        Args:
            players: Player pool dictionary

        Raises:
            ValueError: If pool is invalid
        """
        # Check for duplicate player_ids (should be impossible with dict, but check anyway)
        if len(players) != len(set(players.keys())):
            raise ValueError("Duplicate player_ids found in pool")

        # Validate each player
        for player_id, player in players.items():
            if player.player_id != player_id:
                raise ValueError(
                    f"Player ID mismatch: key={player_id}, player.player_id={player.player_id}"
                )

            if not player.eligible_positions:
                raise ValueError(f"Player {player_id} has no eligible positions")

            if player.drafted:
                if not player.drafted_team_id:
                    raise ValueError(f"Drafted player {player_id} missing team_id")
                if player.price is None:
                    raise ValueError(f"Drafted player {player_id} missing price")
            else:
                if player.drafted_team_id is not None:
                    raise ValueError(
                        f"Undrafted player {player_id} has team_id: {player.drafted_team_id}"
                    )
                if player.price is not None:
                    raise ValueError(f"Undrafted player {player_id} has price: {player.price}")

        logger.debug(f"Player pool validation passed: {len(players)} players")
