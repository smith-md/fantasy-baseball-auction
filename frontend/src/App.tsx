// Main App - Draft Day Decision Support UI

import React from 'react';
import { DraftProvider, useDraft } from './contexts/DraftContext';
import { AvailablePlayersPanel } from './components/AvailablePlayersPanel/AvailablePlayersPanel';
import { StandingsPanel } from './components/StandingsPanel/StandingsPanel';
import { CompetitionPanel } from './components/CompetitionPanel/CompetitionPanel';
import { TeamNeedsPanel } from './components/TeamNeedsPanel/TeamNeedsPanel';
import './App.css';

const DraftDashboard: React.FC = () => {
  const { loading, error, lastUpdated, refreshData } = useDraft();

  const formatLastUpdated = () => {
    if (!lastUpdated) return 'Never';
    const now = new Date();
    const diffMs = now.getTime() - lastUpdated.getTime();
    const diffSecs = Math.floor(diffMs / 1000);

    if (diffSecs < 60) return `${diffSecs}s ago`;
    const diffMins = Math.floor(diffSecs / 60);
    if (diffMins < 60) return `${diffMins}m ago`;
    return lastUpdated.toLocaleTimeString();
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-content">
          <h1>Draft Day Assistant</h1>
          <div className="header-controls">
            <div className="last-updated">
              Last updated: {formatLastUpdated()}
            </div>
            <button
              className="refresh-button"
              onClick={refreshData}
              disabled={loading}
            >
              {loading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>
      </header>

      <main className="app-main">
        {error && (
          <div className="error-banner">
            Error: {error}
            <button onClick={refreshData}>Retry</button>
          </div>
        )}

        {loading && !lastUpdated ? (
          <div className="loading-screen">
            <div className="loading-spinner"></div>
            <p>Loading draft data...</p>
          </div>
        ) : (
          <div className="panels-grid">
            <AvailablePlayersPanel />
            <StandingsPanel />
            <CompetitionPanel />
            <TeamNeedsPanel />
          </div>
        )}
      </main>

      <footer className="app-footer">
        <p>Fantasy Baseball Auction Draft Valuation System</p>
      </footer>
    </div>
  );
};

function App() {
  return (
    <DraftProvider autoRefreshInterval={10000}>
      <DraftDashboard />
    </DraftProvider>
  );
}

export default App;
