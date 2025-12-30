// TypeScript interfaces matching API responses

export interface Player {
  player_name: string;
  team: string;
  positions: string[];
  assigned_position: string;
  auction_value: number;
  overall_rank: number;
  position_rank: number;
  raw_value: number;  // Personal value (SGP)
  VAR: number;
  replacement_level: number;
  // Stats (hitters)
  PA?: number;
  AB?: number;
  R?: number;
  RBI?: number;
  SB?: number;
  OBP?: number;
  SLG?: number;
  // Stats (pitchers)
  IP?: number;
  W_QS?: number;
  SV_HLD?: number;
  K?: number;
  ERA?: number;
  WHIP?: number;
  // SGP breakdown
  R_sgp?: number;
  RBI_sgp?: number;
  SB_sgp?: number;
  OBP_sgp?: number;
  SLG_sgp?: number;
  W_QS_sgp?: number;
  SV_HLD_sgp?: number;
  K_sgp?: number;
  ERA_sgp?: number;
  WHIP_sgp?: number;
}

export interface TeamStats {
  counting: Record<string, number>;
  rate: Record<string, number>;
}

export interface TeamSummary {
  team_id: string;
  team_name: string;
  picks: number;
  spent: number;
  budget_remaining: number;
  spots_remaining: number;
  stats: TeamStats;
}

export interface DraftResults {
  schema_version: string;
  timestamp: string;
  last_pick: number;
  total_picks: number;
  available_budget: number;
  available_roster_spots: number;
  num_players: number;
  team_summary: TeamSummary[];
  players: Player[];
}

export interface CategoryGap {
  points: number;
  stats: number;
}

export interface TeamStanding {
  team_id: string;
  team_name: string;
  total_points: number;
  category_points: Record<string, number>;
  category_ranks: Record<string, number>;
  projected_stats: Record<string, number>;
  gaps_to_next: Record<string, CategoryGap>;
  is_user_team: boolean;
}

export interface StandingsSummary {
  num_teams: number;
  leader_team: string;
  leader_points: number;
  last_place_points: number;
  point_spread: number;
}

export interface StandingsResponse {
  standings: TeamStanding[];
  summary: StandingsSummary;
}

export interface TeamCompetition {
  team_id: string;
  team_name: string;
  budget_remaining: number;
  total_open_slots: number;
  open_slots_by_position: Record<string, number>;
  competition_score: number;
  high_need_positions: string[];
  is_user_team: boolean;
}

export interface LeagueTotals {
  total_budget_remaining: number;
  total_open_slots: number;
  avg_budget_per_team: number;
  avg_slots_per_team: number;
  avg_budget_per_slot: number;
}

export interface CompetitionResponse {
  teams: TeamCompetition[];
  league_totals: LeagueTotals;
}

export interface PlayerRecommendation {
  player_name: string;
  positions: string[];
  auction_value: number;
  raw_value: number;
  category_sgp: number;
  total_sgp: number;
}

export interface BestOverallTarget {
  player_name: string;
  positions: string[];
  auction_value: number;
  raw_value: number;
  need_sgp: number;
  addresses_categories: string[];
}

export interface CategoryNeed {
  category: string;
  current_rank: number;
  next_rank: number;
  points_to_next_rank: number;
  stats_needed: number;
  stats_gap_type: 'increase' | 'reduce';
  ease_score: number;
  top_recommendations: PlayerRecommendation[];
}

export interface TeamNeedsResponse {
  team_id: string;
  team_name: string;
  budget_remaining: number;
  open_slots: number;
  needs: CategoryNeed[];
  best_overall_targets: BestOverallTarget[];
}

export interface DraftConfig {
  user_team_id: string;
  num_teams: number;
  budget_per_team: number;
  roster_slots: Record<string, number>;
  categories: {
    hitters: string[];
    pitchers: string[];
  };
  auto_refresh_interval: number;
}
