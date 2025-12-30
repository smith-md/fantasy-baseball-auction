// Draft Context - Global state management for draft data

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type {
  DraftResults,
  StandingsResponse,
  CompetitionResponse,
  TeamNeedsResponse,
  DraftConfig,
} from '../types/draft';
import { fetchAllData } from '../services/api';

interface DraftContextValue {
  // Data
  results: DraftResults | null;
  standings: StandingsResponse | null;
  competition: CompetitionResponse | null;
  teamNeeds: TeamNeedsResponse | null;
  config: DraftConfig | null;

  // Status
  loading: boolean;
  lastUpdated: Date | null;
  error: string | null;

  // Actions
  refreshData: () => Promise<void>;
}

const DraftContext = createContext<DraftContextValue | undefined>(undefined);

export const useDraft = () => {
  const context = useContext(DraftContext);
  if (!context) {
    throw new Error('useDraft must be used within a DraftProvider');
  }
  return context;
};

interface DraftProviderProps {
  children: React.ReactNode;
  autoRefreshInterval?: number;
}

export const DraftProvider: React.FC<DraftProviderProps> = ({
  children,
  autoRefreshInterval = 10000, // 10 seconds default
}) => {
  const [results, setResults] = useState<DraftResults | null>(null);
  const [standings, setStandings] = useState<StandingsResponse | null>(null);
  const [competition, setCompetition] = useState<CompetitionResponse | null>(null);
  const [teamNeeds, setTeamNeeds] = useState<TeamNeedsResponse | null>(null);
  const [config, setConfig] = useState<DraftConfig | null>(null);

  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await fetchAllData();

      setResults(data.results);
      setStandings(data.standings);
      setCompetition(data.competition);
      setTeamNeeds(data.teamNeeds);
      setConfig(data.config);
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Failed to fetch draft data:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch on mount
  useEffect(() => {
    refreshData();
  }, [refreshData]);

  // Auto-refresh interval
  useEffect(() => {
    if (!autoRefreshInterval) return;

    const interval = setInterval(() => {
      refreshData();
    }, autoRefreshInterval);

    return () => clearInterval(interval);
  }, [autoRefreshInterval, refreshData]);

  const value: DraftContextValue = {
    results,
    standings,
    competition,
    teamNeeds,
    config,
    loading,
    lastUpdated,
    error,
    refreshData,
  };

  return <DraftContext.Provider value={value}>{children}</DraftContext.Provider>;
};
