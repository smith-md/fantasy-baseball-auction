// Competition Panel - League resources and positional competition

import React, { useState } from 'react';
import { useDraft } from '../../contexts/DraftContext';
import { formatCurrency } from '../../utils/formatters';
import './styles.css';

export const CompetitionPanel: React.FC = () => {
  const { competition } = useDraft();
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  if (!competition) {
    return <div className="panel">Loading competition data...</div>;
  }

  const toggleExpand = (teamId: string) => {
    setExpandedTeam(expandedTeam === teamId ? null : teamId);
  };

  return (
    <div className="panel competition-panel">
      <h2>League Resources & Competition</h2>
      <p className="panel-subtitle">
        Remaining budgets and roster needs across all teams
      </p>

      <table className="competition-table">
        <thead>
          <tr>
            <th>Team</th>
            <th>Budget</th>
            <th>Open Slots</th>
            <th>$/Slot</th>
            <th>Competition</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {competition.teams.map(team => (
            <React.Fragment key={team.team_id}>
              <tr
                className={team.is_user_team ? 'user-team' : ''}
                onClick={() => toggleExpand(team.team_id)}
              >
                <td className="team-name-cell">
                  {team.team_name}
                  {team.is_user_team && <span className="user-badge">YOU</span>}
                </td>
                <td className={`budget-cell ${team.budget_remaining > 400 ? 'high-budget' : ''}`}>
                  {formatCurrency(team.budget_remaining)}
                </td>
                <td>{team.total_open_slots}</td>
                <td>
                  {team.total_open_slots > 0
                    ? formatCurrency(team.budget_remaining / team.total_open_slots)
                    : '-'}
                </td>
                <td>
                  <div className="competition-bar">
                    <div
                      className="competition-fill"
                      style={{ width: `${team.competition_score * 100}%` }}
                    />
                    <span className="competition-score">{(team.competition_score * 100).toFixed(0)}%</span>
                  </div>
                </td>
                <td className="expand-cell">
                  {expandedTeam === team.team_id ? '▼' : '▶'}
                </td>
              </tr>

              {expandedTeam === team.team_id && (
                <tr className="position-breakdown">
                  <td colSpan={6}>
                    <div className="position-details">
                      <h4>Open Roster Slots by Position</h4>
                      <div className="position-grid">
                        {Object.entries(team.open_slots_by_position)
                          .filter(([_, count]) => count > 0)
                          .map(([position, count]) => (
                            <div
                              key={position}
                              className={`position-slot ${count >= 2 ? 'high-need' : ''}`}
                            >
                              <span className="position-name">{position}</span>
                              <span className="position-count">{count}</span>
                            </div>
                          ))}
                      </div>

                      {team.high_need_positions.length > 0 && (
                        <div className="high-need-notice">
                          High Need: {team.high_need_positions.join(', ')}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>

      <div className="league-summary">
        <div className="summary-stat">
          <span className="label">Total Budget Remaining:</span>
          <span className="value">{formatCurrency(competition.league_totals.total_budget_remaining)}</span>
        </div>
        <div className="summary-stat">
          <span className="label">Total Open Slots:</span>
          <span className="value">{competition.league_totals.total_open_slots}</span>
        </div>
        <div className="summary-stat">
          <span className="label">Avg $/Slot:</span>
          <span className="value">{formatCurrency(competition.league_totals.avg_budget_per_slot)}</span>
        </div>
      </div>
    </div>
  );
};
