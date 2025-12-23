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

# FanGraphs API Endpoints (unofficial JSON endpoints)
FANGRAPHS_BASE_URL = "https://www.fangraphs.com/api/leaders/major-league/data"

# Projection systems to fetch
PROJECTION_SYSTEMS = ['steamer', 'zips', 'atc']

# FanGraphs projection system mappings
PROJECTION_TYPE_MAP = {
    'steamer': 'steamerr',  # Note: FanGraphs uses 'steamerr' for ROS projections
    'zips': 'rzips',
    'atc': 'ratc',
}

# Required stats for hitters
HITTER_STATS_REQUIRED = [
    'PA', 'AB', 'R', 'RBI', 'SB', 'OBP', 'SLG'
]

# Optional but preferred hitter stats (for validation/alternate calculations)
HITTER_STATS_OPTIONAL = ['H', 'BB', 'HBP', 'SF', 'TB']

# Required stats for pitchers
PITCHER_STATS_REQUIRED = [
    'IP', 'W', 'QS', 'SV', 'HLD', 'K', 'ERA', 'WHIP'
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
