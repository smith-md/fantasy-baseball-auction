"""
Configuration constants for the fantasy baseball auction draft valuation model.
"""

# League Settings
NUM_TEAMS = 12
BUDGET_PER_TEAM = 500
TOTAL_BUDGET = NUM_TEAMS * BUDGET_PER_TEAM  # $6000

# Roster Construction
HITTER_ROSTER = {
    'C': 1,
    '1B': 1,
    '2B': 1,
    '3B': 1,
    'SS': 1,
    'OF': 3,
    'UTIL': 3,
    'BN_H': 2,  # Bench Hitters
}

PITCHER_ROSTER = {
    'P': 8,
    'BN_P': 3,  # Bench Pitchers
}

# Calculate total roster spots per team
HITTERS_PER_TEAM = sum(HITTER_ROSTER.values())  # 13
PITCHERS_PER_TEAM = sum(PITCHER_ROSTER.values())  # 11
ROSTER_SIZE = HITTERS_PER_TEAM + PITCHERS_PER_TEAM  # 24

# League-wide roster counts (12 teams)
TOTAL_HITTERS = NUM_TEAMS * HITTERS_PER_TEAM  # 156
TOTAL_PITCHERS = NUM_TEAMS * PITCHERS_PER_TEAM  # 132
TOTAL_PLAYERS = NUM_TEAMS * ROSTER_SIZE  # 288

# Roster slots for position assignment optimization
# Expand multi-position slots (OF, UTIL, P, BN) into individual slots
ROSTER_SLOTS = {
    'C': NUM_TEAMS * HITTER_ROSTER['C'],      # 12
    '1B': NUM_TEAMS * HITTER_ROSTER['1B'],    # 12
    '2B': NUM_TEAMS * HITTER_ROSTER['2B'],    # 12
    '3B': NUM_TEAMS * HITTER_ROSTER['3B'],    # 12
    'SS': NUM_TEAMS * HITTER_ROSTER['SS'],    # 12
    'OF': NUM_TEAMS * HITTER_ROSTER['OF'],    # 36
    'UTIL': NUM_TEAMS * HITTER_ROSTER['UTIL'], # 36
    'BN_H': NUM_TEAMS * HITTER_ROSTER['BN_H'], # 24
    'P': NUM_TEAMS * PITCHER_ROSTER['P'],     # 96
    'BN_P': NUM_TEAMS * PITCHER_ROSTER['BN_P'], # 36
}

# Scoring Categories
HITTER_CATEGORIES = ['R', 'RBI', 'SB', 'OBP', 'SLG']
PITCHER_CATEGORIES = ['W_QS', 'SV_HLD', 'K', 'ERA', 'WHIP']

# Rate stat categories that need special handling
HITTER_RATE_STATS = ['OBP', 'SLG']
PITCHER_RATE_STATS = ['ERA', 'WHIP']

# Compound categories that need to be summed before normalization
COMPOUND_CATEGORIES = {
    'W_QS': ['W', 'QS'],      # Wins + Quality Starts
    'SV_HLD': ['SV', 'HLD'],  # Saves + Holds
}

# FanGraphs API Endpoints
FANGRAPHS_BASE_URL = "https://www.fangraphs.com/api/projections"

# Projection systems to fetch
# Using all available UNIQUE systems for 2025: steamer, fangraphsdc
# Note: steamer600 is excluded as it's just steamer scaled to 600 PA
PROJECTION_SYSTEMS = ['steamer', 'fangraphsdc']

# FanGraphs projection system mappings (use as-is, no prefix needed)
PROJECTION_TYPE_MAP = {
    'steamer': 'steamer',
    'steamer600': 'steamer600',
    'fangraphsdc': 'fangraphsdc',
    'zips': 'zips',  # Keep for when available
    'atc': 'atc',    # Keep for when available
}

# Required stats for hitters
HITTER_STATS_REQUIRED = [
    'PA', 'AB', 'R', 'RBI', 'SB', 'OBP', 'SLG'
]

# Optional but preferred hitter stats (for validation/alternate calculations)
HITTER_STATS_OPTIONAL = ['H', 'BB', 'HBP', 'SF', 'TB']

# Required stats for pitchers
PITCHER_STATS_REQUIRED = [
    'IP', 'W', 'QS', 'SV', 'HLD', 'SO', 'ERA', 'WHIP'  # Note: FanGraphs uses 'SO' not 'K'
]

# Optional but preferred pitcher stats (for validation/alternate calculations)
PITCHER_STATS_OPTIONAL = ['ER', 'H', 'BB']

# Minimum thresholds for including players in valuation pool
# Players below these thresholds are excluded as not draftable
MIN_PA_HITTERS = 50   # Minimum plate appearances
MIN_IP_PITCHERS = 20  # Minimum innings pitched

# Dollar allocation
MINIMUM_BID = 1
MINIMUM_SPEND = TOTAL_PLAYERS * MINIMUM_BID  # $288
DOLLARS_TO_ALLOCATE = TOTAL_BUDGET - MINIMUM_SPEND  # $5712

# Position eligibility mappings
# Define which positions are eligible for UTIL slots
UTIL_ELIGIBLE_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH']

# Define which positions are eligible for bench slots
BN_H_ELIGIBLE_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH']
BN_P_ELIGIBLE_POSITIONS = ['SP', 'RP', 'P']

# Position type mapping (hitter vs pitcher)
HITTER_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH', 'UTIL', 'BN_H']
PITCHER_POSITIONS = ['SP', 'RP', 'P', 'BN_P']

# Cache settings
CACHE_DIR = 'data/cache'
OUTPUT_DIR = 'data/output'
CACHE_EXPIRY_DAYS = 7  # Cache API responses for 7 days

# Logging
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ===== SGP (Standings Gain Points) CONFIGURATION =====

# Historical Data
SGP_DATA_DIR = 'data/standings'
SGP_SEASONS = [2023, 2024, 2025]  # Seasons to use for SGP calculation

# Multi-Year Weighting (more recent seasons weighted higher)
SGP_SEASON_WEIGHTS = {
    2023: 1.0,
    2024: 1.5,
    2025: 2.0,
}

# Replacement Level Baselines for Ratio Categories
# Full-season roster of replacement-level players
REPLACEMENT_HITTER_PA = 450      # Average PA for replacement hitter
REPLACEMENT_PITCHER_IP = 150     # Average IP for replacement pitcher

# Replacement level rate stats (auto-calculated from player pool if None)
REPLACEMENT_OBP = None   # Auto-calculate if None
REPLACEMENT_SLG = None   # Auto-calculate if None
REPLACEMENT_ERA = None   # Auto-calculate if None
REPLACEMENT_WHIP = None  # Auto-calculate if None

# Diagnostic Output
DIAGNOSTICS_DIR = 'data/diagnostics'
SGP_WRITE_DIAGNOSTICS = True

# SGP Calculation Method
SGP_METHOD = 'median_gap'  # 'median_gap' (only method supported initially)

# ===== LIVE DRAFT CONFIGURATION =====

# Fantrax API
FANTRAX_BASE_URL = "https://www.fantrax.com/fxea/general"

# Polling
DEFAULT_POLL_INTERVAL = 5  # seconds between Fantrax polls
POLL_TIMEOUT = 300  # maximum time to wait for a poll (5 minutes)

# Event storage
DRAFT_EVENTS_DIR = 'data/draft_events'
DRAFT_CACHE_DIR = 'data/draft_cache'
DRAFT_CHECKPOINTS_DIR = 'data/draft_checkpoints'
FANTRAX_MAPPINGS_DIR = 'data/mappings'

# Performance
ENABLE_PIPELINE_TIMING = True  # Log timing for each valuation run
TARGET_VALUATION_TIME = 1.0  # Target time in seconds for pipeline recompute

# ===== DRAFT SESSION API CONFIGURATION =====

# Session storage
DRAFT_SESSIONS_DIR = 'data/draft_sessions'

# API Server defaults
API_HOST = '127.0.0.1'
API_PORT = 8000

# Session limits
MAX_CONCURRENT_SESSIONS = 1  # Only one session at a time for MVP
SESSION_TIMEOUT_HOURS = 12   # Auto-expire sessions after 12 hours (future feature)

# ===== FRONTEND CONFIGURATION =====

# User Team ID - Change this to match your team in the league
USER_TEAM_ID = 'team_01'

# Auto-refresh interval for frontend (seconds)
FRONTEND_AUTO_REFRESH_INTERVAL = 10
