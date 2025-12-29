"""
Fetch player projections from FanGraphs API.
"""

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
from tqdm import tqdm

from . import config


class FanGraphsFetcher:
    """Fetches player projections from FanGraphs unofficial JSON endpoints."""

    def __init__(self, season: int, use_cache: bool = True):
        """
        Initialize the FanGraphs fetcher.

        Args:
            season: The projection season (e.g., 2026)
            use_cache: Whether to use cached responses if available
        """
        self.season = season
        self.use_cache = use_cache
        self.cache_dir = Path(config.CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, player_type: str, projection_system: str) -> Path:
        """Get the cache file path for a specific request."""
        filename = f"{player_type}_{projection_system}_{self.season}.json"
        return self.cache_dir / filename

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached data is still valid (not expired)."""
        if not cache_path.exists():
            return False

        # Check if cache is older than CACHE_EXPIRY_DAYS
        cache_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        expiry_time = datetime.now() - timedelta(days=config.CACHE_EXPIRY_DAYS)

        return cache_time > expiry_time

    def _fetch_from_api(self, player_type: str, projection_system: str,
                       max_retries: int = 3) -> Optional[Dict]:
        """
        Fetch projections from FanGraphs API.

        Args:
            player_type: 'bat' for hitters, 'pit' for pitchers
            projection_system: Projection system name (e.g., 'steamer', 'zips', 'atc')
            max_retries: Maximum number of retry attempts

        Returns:
            JSON response as dict, or None if request failed
        """
        # Map projection system to FanGraphs API parameter
        fg_projection = config.PROJECTION_TYPE_MAP.get(projection_system, projection_system)

        # Build API URL using correct FanGraphs API structure
        params = {
            'type': fg_projection,
            'stats': player_type,
            'pos': 'all',
            'team': '0',
            'players': '0',
            'lg': 'all'
        }

        url = config.FANGRAPHS_BASE_URL

        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                return response.json()

            except requests.exceptions.RequestException as e:
                print(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    # Exponential backoff
                    wait_time = 2 ** attempt
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    print(f"Failed to fetch {player_type} projections for {projection_system}")
                    return None

        return None

    def _save_to_cache(self, data: Dict, cache_path: Path):
        """Save API response to cache file."""
        with open(cache_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _load_from_cache(self, cache_path: Path) -> Optional[Dict]:
        """Load API response from cache file."""
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading cache file {cache_path}: {e}")
            return None

    def fetch_projections(self, player_type: str, projection_system: str) -> Optional[pd.DataFrame]:
        """
        Fetch projections for a specific player type and projection system.

        Args:
            player_type: 'bat' for hitters, 'pit' for pitchers
            projection_system: Projection system name (e.g., 'steamer', 'zips', 'atc')

        Returns:
            DataFrame with player projections, or None if fetch failed
        """
        cache_path = self._get_cache_path(player_type, projection_system)

        # Try to load from cache first
        if self.use_cache and self._is_cache_valid(cache_path):
            print(f"Loading {player_type} {projection_system} from cache...")
            data = self._load_from_cache(cache_path)
        else:
            # Fetch from API
            print(f"Fetching {player_type} {projection_system} from FanGraphs API...")
            data = self._fetch_from_api(player_type, projection_system)

            if data is None:
                return None

            # Save to cache
            if self.use_cache:
                self._save_to_cache(data, cache_path)

        # Parse JSON into DataFrame
        try:
            # The actual structure of the JSON response may vary
            # Common patterns: data['data'], data['players'], or data itself is a list
            if isinstance(data, dict):
                if 'data' in data:
                    df = pd.DataFrame(data['data'])
                elif 'players' in data:
                    df = pd.DataFrame(data['players'])
                else:
                    # Try to find the first list value
                    for value in data.values():
                        if isinstance(value, list):
                            df = pd.DataFrame(value)
                            break
                    else:
                        df = pd.DataFrame([data])
            elif isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                print(f"Unexpected JSON structure for {player_type} {projection_system}")
                return None

            # Add projection system column for tracking
            df['projection_system'] = projection_system

            return df

        except Exception as e:
            print(f"Error parsing {player_type} {projection_system} data: {e}")
            return None

    def fetch_all_hitters(self) -> Dict[str, pd.DataFrame]:
        """
        Fetch hitter projections from all systems.

        Returns:
            Dictionary mapping projection system names to DataFrames
        """
        hitter_dfs = {}

        for system in tqdm(config.PROJECTION_SYSTEMS, desc="Fetching hitter projections"):
            df = self.fetch_projections('bat', system)
            if df is not None:
                hitter_dfs[system] = df

        return hitter_dfs

    def fetch_all_pitchers(self) -> Dict[str, pd.DataFrame]:
        """
        Fetch pitcher projections from all systems.

        Returns:
            Dictionary mapping projection system names to DataFrames
        """
        pitcher_dfs = {}

        for system in tqdm(config.PROJECTION_SYSTEMS, desc="Fetching pitcher projections"):
            df = self.fetch_projections('pit', system)
            if df is not None:
                pitcher_dfs[system] = df

        return pitcher_dfs

    def fetch_all(self) -> Dict[str, Dict[str, pd.DataFrame]]:
        """
        Fetch all projections (hitters and pitchers) from all systems.

        Returns:
            Dictionary with 'hitters' and 'pitchers' keys, each containing
            a dictionary mapping projection system names to DataFrames
        """
        print(f"\nFetching {self.season} projections...")

        return {
            'hitters': self.fetch_all_hitters(),
            'pitchers': self.fetch_all_pitchers(),
        }


def validate_hitter_df(df: pd.DataFrame) -> bool:
    """
    Validate that a hitter DataFrame has all required columns.

    Args:
        df: Hitter projections DataFrame

    Returns:
        True if valid, False otherwise
    """
    # Check for required stats
    missing_stats = [stat for stat in config.HITTER_STATS_REQUIRED if stat not in df.columns]

    if missing_stats:
        print(f"Warning: Missing required hitter stats: {missing_stats}")
        return False

    # Check for minimum playing time
    if 'PA' in df.columns:
        valid_players = (df['PA'] >= config.MIN_PA_HITTERS).sum()
        print(f"Found {valid_players} hitters with PA >= {config.MIN_PA_HITTERS}")

    return True


def validate_pitcher_df(df: pd.DataFrame) -> bool:
    """
    Validate that a pitcher DataFrame has all required columns.

    Args:
        df: Pitcher projections DataFrame

    Returns:
        True if valid, False otherwise
    """
    # Check for required stats
    missing_stats = [stat for stat in config.PITCHER_STATS_REQUIRED if stat not in df.columns]

    if missing_stats:
        print(f"Warning: Missing required pitcher stats: {missing_stats}")
        return False

    # Check for minimum playing time
    if 'IP' in df.columns:
        valid_players = (df['IP'] >= config.MIN_IP_PITCHERS).sum()
        print(f"Found {valid_players} pitchers with IP >= {config.MIN_IP_PITCHERS}")

    return True
