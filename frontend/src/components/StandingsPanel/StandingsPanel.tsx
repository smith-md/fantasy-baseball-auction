// Standings Panel - Projected final standings

import React, { useState } from 'react';
import { useDraft } from '../../contexts/DraftContext';
import { formatRank } from '../../utils/formatters';
import './styles.css';

export const StandingsPanel: React.FC = () => {
  const { standings, config } = useDraft();
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  if (!standings || !config) {
    return <div className="panel">Loading standings...</div>;
  }

  const toggleExpand = (teamId: string) => {
    setExpandedTeam(expandedTeam === teamId ? null : teamId);
  };

  const allCategories = [...config.categories.hitters, ...config.categories.pitchers];
  const rateStats = new Set(['OBP', 'SLG', 'ERA', 'WHIP']);
  const formatStat = (category: string, value: number) =>
    rateStats.has(category) ? value.toFixed(3) : value.toFixed(0);

  return (
    <div className="panel standings-panel">
      <h2>Projected Standings</h2>
      <p className="panel-subtitle">
        Final standings if draft ended now (remaining slots filled with replacement-level players)
      </p>

      <table className="standings-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Team</th>
            <th style={{ textAlign: 'center' }}>Total Points</th>
            <th style={{ textAlign: 'center' }}>Gap</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {standings.standings.map((team, idx) => (
            <React.Fragment key={team.team_id}>
              <tr
                className={team.is_user_team ? 'user-team' : ''}
                onClick={() => toggleExpand(team.team_id)}
              >
                <td className="rank-cell">{idx + 1}</td>
                <td className="team-name-cell">
                  {team.team_name}
                  {team.is_user_team && <span className="user-badge">YOU</span>}
                </td>
                <td className="total-points-cell">{team.total_points.toFixed(1)}</td>
                <td className="gap-cell">
                  {idx > 0 ? `+${(standings.standings[idx - 1].total_points - team.total_points).toFixed(1)}` : '-'}
                </td>
                <td className="expand-cell">
                  {expandedTeam === team.team_id ? '▼' : '▶'}
                </td>
              </tr>

              {expandedTeam === team.team_id && (
                <tr className="category-breakdown">
                  <td colSpan={5}>
                    <div className="category-details">
                      <table className="category-table">
                        <thead>
                          <tr>
                            <th>Category</th>
                            <th>Projected Stats</th>
                            <th>Rank</th>
                            <th>Points</th>
                            <th>Gap to Next</th>
                          </tr>
                        </thead>
                        <tbody>
                          {allCategories.map(category => (
                            <tr key={category}>
                              <td className="category-name">{category}</td>
                              <td>{team.projected_stats[category] != null ? formatStat(category, team.projected_stats[category]) : '-'}</td>
                              <td>{formatRank(team.category_ranks[category])}</td>
                              <td>{team.category_points[category]}</td>
                              <td>
                                {team.gaps_to_next[category]
                                  ? `${team.gaps_to_next[category].stats.toFixed(2)} (${team.gaps_to_next[category].points} pts)`
                                  : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
};
