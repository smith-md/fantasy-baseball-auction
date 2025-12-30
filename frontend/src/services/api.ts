// API client for draft session endpoints

import axios from 'axios';
import type {
  DraftResults,
  StandingsResponse,
  CompetitionResponse,
  TeamNeedsResponse,
  DraftConfig,
} from '../types/draft';

const api = axios.create({
  baseURL: '/draft-session',
  timeout: 10000,
});

export const fetchResults = async (): Promise<DraftResults> => {
  const response = await api.get<DraftResults>('/results');
  return response.data;
};

export const fetchStandings = async (): Promise<StandingsResponse> => {
  const response = await api.get<StandingsResponse>('/standings');
  return response.data;
};

export const fetchCompetition = async (): Promise<CompetitionResponse> => {
  const response = await api.get<CompetitionResponse>('/competition');
  return response.data;
};

export const fetchTeamNeeds = async (teamId?: string): Promise<TeamNeedsResponse> => {
  const params = teamId ? { team_id: teamId } : {};
  const response = await api.get<TeamNeedsResponse>('/team-needs', { params });
  return response.data;
};

export const fetchConfig = async (): Promise<DraftConfig> => {
  const response = await api.get<DraftConfig>('/config');
  return response.data;
};

export const fetchAllData = async () => {
  const [results, standings, competition, teamNeeds, config] = await Promise.all([
    fetchResults(),
    fetchStandings(),
    fetchCompetition(),
    fetchTeamNeeds(),
    fetchConfig(),
  ]);

  return {
    results,
    standings,
    competition,
    teamNeeds,
    config,
  };
};
