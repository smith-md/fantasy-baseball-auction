// Team Needs Panel - Strategic recommendations for user's team

import React from 'react';
import { useDraft } from '../../contexts/DraftContext';
import { formatCurrency, formatRank, formatSGP } from '../../utils/formatters';
import './styles.css';

export const TeamNeedsPanel: React.FC = () => {
  const { teamNeeds } = useDraft();

  if (!teamNeeds) {
    return <div className="panel">Loading team needs...</div>;
  }

  return (
    <div className="panel team-needs-panel">
      <h2>Team Needs & Recommendations</h2>
      <p className="panel-subtitle">
        Categories ranked by ease of improvement for {teamNeeds.team_name}
      </p>

      <div className="team-status">
        <span className="status-item">
          <strong>Budget:</strong> {formatCurrency(teamNeeds.budget_remaining)}
        </span>
        <span className="status-item">
          <strong>Open Slots:</strong> {teamNeeds.open_slots}
        </span>
      </div>

      <div className="needs-list">
        {teamNeeds.needs.length === 0 ? (
          <div className="no-needs">
            All categories at rank 1! No improvement opportunities.
          </div>
        ) : (
          teamNeeds.needs.map(need => (
            <div key={need.category} className="need-card">
              <div className="need-header">
                <div className="need-category">
                  <span className="category-name">{need.category}</span>
                  <span className="category-rank">
                    Currently {formatRank(need.current_rank)}
                  </span>
                </div>
                <div className="need-metrics">
                  <div className="metric">
                    <span className="metric-label">Ease Score</span>
                    <span className={`ease-score score-${Math.floor(need.ease_score * 10)}`}>
                      {(need.ease_score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Need to {need.stats_gap_type}</span>
                    <span className="stats-needed">{need.stats_needed}</span>
                  </div>
                </div>
              </div>

              {need.top_recommendations.length > 0 && (
                <div className="recommendations">
                  <h4>Top Targets</h4>
                  <table className="recommendations-table">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Pos</th>
                        <th>Cost</th>
                        <th>{need.category} SGP</th>
                        <th>Total SGP</th>
                      </tr>
                    </thead>
                    <tbody>
                      {need.top_recommendations.map((player, idx) => (
                        <tr key={`${player.player_name}-${idx}`}>
                          <td className="player-name">{player.player_name}</td>
                          <td className="positions">{player.positions.join(', ')}</td>
                          <td>{formatCurrency(player.auction_value)}</td>
                          <td className="category-sgp">{formatSGP(player.category_sgp)}</td>
                          <td className="total-sgp">{formatSGP(player.total_sgp)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {teamNeeds.best_overall_targets.length > 0 && (
        <div className="best-targets-section">
          <h3>Best Overall Targets (Multi-Category Value)</h3>
          <p className="section-subtitle">
            Players addressing your top 3 needs
          </p>
          <table className="targets-table">
            <thead>
              <tr>
                <th>Player</th>
                <th>Positions</th>
                <th>Cost</th>
                <th>Need SGP</th>
                <th>Total SGP</th>
                <th>Addresses</th>
              </tr>
            </thead>
            <tbody>
              {teamNeeds.best_overall_targets.slice(0, 10).map((player, idx) => (
                <tr key={`${player.player_name}-${idx}`}>
                  <td className="player-name">{player.player_name}</td>
                  <td>{player.positions.join(', ')}</td>
                  <td>{formatCurrency(player.auction_value)}</td>
                  <td className="need-sgp">{formatSGP(player.need_sgp)}</td>
                  <td>{formatSGP(player.raw_value)}</td>
                  <td className="addresses-categories">
                    {player.addresses_categories.join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
