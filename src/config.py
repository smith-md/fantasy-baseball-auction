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

# Per-team roster slots (used for team state tracking)
ROSTER_SLOTS_PER_TEAM = {**HITTER_ROSTER, **PITCHER_ROSTER}

# League-wide roster slots for position assignment optimization
ROSTER_SLOTS = {
    pos: NUM_TEAMS * count for pos, count in ROSTER_SLOTS_PER_TEAM.items()
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
# Using all available UNIQUE systems for 2026: steamer, fangraphsdc
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

# Total players in the draft pool � includes fringe players beyond actual roster slots.
# Real roster spots = TOTAL_PLAYERS (288). Extra players get assigned a position for
# valuation purposes but will have negative/near-zero dollar values.
PLAYER_POOL_SIZE = 500

# New owner budget bonuses (added to base $500 before trades)
NEW_OWNER_YEAR1_BONUS = 30  # Year 1 owners start with $530
NEW_OWNER_YEAR2_BONUS = 15  # Year 2 owners start with $515

# Tracks which year each team is in (for new owner bonus calculation)
# Used to determine base budget before trade adjustments in future years.
# Omit a team_id (or set to 3+) for veterans on the default $500 base.
TEAM_OWNER_YEAR = {
    '7bqu0ogpml34g0kc': 2,  # Dan Pers - year 2
    '7oml65nsml34g0kb': 2,  # Zach - year 2
}

# Directory for versioned draft settings (budgets, etc.)
# Per-season budget files live here as draft_budgets_{season}.json
# These are seeded manually until transaction history import is implemented.
DRAFT_BUDGETS_DIR = 'settings'

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

# ===== LEAGUE CONFIGURATION =====

# Fantrax league ID and season - set these to auto-start sessions
LEAGUE_ID = '45zdadwuml34g0k7'
LEAGUE_SEASON = 2026

# ===== FRONTEND CONFIGURATION =====

# User Team ID - Change this to match your team in the league
USER_TEAM_ID = 'jp9m7ovmml34g0kb'

# Auto-refresh interval for frontend (seconds)
FRONTEND_AUTO_REFRESH_INTERVAL = 10

# ===== PLAYER ID CROSS-REFERENCE =====

# SFBB player ID map - maps Fantrax player IDs to player names and FanGraphs IDs
PLAYERID_MAP_URL = "https://www.smartfantasybaseball.com/PLAYERIDMAPCSV"
PLAYERID_MAP_CACHE = "data/mappings/player_id_map.csv"
