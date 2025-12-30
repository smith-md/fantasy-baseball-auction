// Available Players Panel - Primary action panel for draft decisions

import React, { useState, useMemo } from 'react';
import { useDraft } from '../../contexts/DraftContext';
import type { Player } from '../../types/draft';
import { formatCurrency, formatSGP } from '../../utils/formatters';
import './styles.css';

type SortField = 'raw_value' | 'auction_value' | 'overall_rank';
type SortDirection = 'asc' | 'desc';

export const AvailablePlayersPanel: React.FC = () => {
  const { results } = useDraft();
  const [sortField, setSortField] = useState<SortField>('raw_value');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [filterPosition, setFilterPosition] = useState<string>('');
  const [filterMinValue, setFilterMinValue] = useState<string>('');

  const availablePlayers = useMemo(() => {
    if (!results) return [];

    // Filter to only undrafted players (no team)
    let players = results.players.filter(p => !p.team || p.team === '');

    // Apply position filter
    if (filterPosition) {
      players = players.filter(p =>
        p.positions.includes(filterPosition) || p.assigned_position === filterPosition
      );
    }

    // Apply minimum value filter
    if (filterMinValue) {
      const minVal = parseFloat(filterMinValue);
      if (!isNaN(minVal)) {
        players = players.filter(p => p.raw_value >= minVal);
      }
    }

    // Sort
    players.sort((a, b) => {
      let aVal: number, bVal: number;

      switch (sortField) {
        case 'raw_value':
          aVal = a.raw_value || 0;
          bVal = b.raw_value || 0;
          break;
        case 'auction_value':
          aVal = a.auction_value || 0;
          bVal = b.auction_value || 0;
          break;
        case 'overall_rank':
          aVal = a.overall_rank || 999;
          bVal = b.overall_rank || 999;
          break;
        default:
          return 0;
      }

      if (sortField === 'overall_rank') {
        // Lower rank is better
        return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
      }

      return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
    });

    return players;
  }, [results, filterPosition, filterMinValue, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (field === sortField) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const getCategories = () => {
    if (!results || !results.players.length) return [];
    const sample = results.players[0];
    const categories: string[] = [];

    // Hitter categories
    if (sample.R_sgp !== undefined) categories.push('R', 'RBI', 'SB', 'OBP', 'SLG');
    // Pitcher categories
    if (sample.W_QS_sgp !== undefined) categories.push('W_QS', 'SV_HLD', 'K', 'ERA', 'WHIP');

    return categories;
  };

  const getCategorySGP = (player: Player, category: string): number => {
    const key = `${category}_sgp` as keyof Player;
    return (player[key] as number) || 0;
  };

  const positions = ['C', '1B', '2B', '3B', 'SS', 'OF', 'P'];

  return (
    <div className="panel available-players-panel">
      <h2>Available Players</h2>

      <div className="filters">
        <label>
          Position:
          <select value={filterPosition} onChange={e => setFilterPosition(e.target.value)}>
            <option value="">All Positions</option>
            {positions.map(pos => (
              <option key={pos} value={pos}>{pos}</option>
            ))}
          </select>
        </label>

        <label>
          Min Personal Value:
          <input
            type="number"
            value={filterMinValue}
            onChange={e => setFilterMinValue(e.target.value)}
            placeholder="0"
            step="1"
          />
        </label>

        <span className="player-count">
          Showing {availablePlayers.length} players
        </span>
      </div>

      <div className="table-container">
        <table className="players-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Pos</th>
              <th
                className={`sortable ${sortField === 'overall_rank' ? 'sorted' : ''}`}
                onClick={() => handleSort('overall_rank')}
              >
                Rank {sortField === 'overall_rank' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className={`sortable ${sortField === 'auction_value' ? 'sorted' : ''}`}
                onClick={() => handleSort('auction_value')}
              >
                Market $ {sortField === 'auction_value' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              <th
                className={`sortable personal-value ${sortField === 'raw_value' ? 'sorted' : ''}`}
                onClick={() => handleSort('raw_value')}
              >
                Personal SGP {sortField === 'raw_value' && (sortDirection === 'asc' ? '↑' : '↓')}
              </th>
              {getCategories().map(cat => (
                <th key={cat} className="category-sgp" title={`${cat} SGP`}>
                  {cat}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {availablePlayers.slice(0, 100).map((player, idx) => (
              <tr key={`${player.player_name}-${idx}`}>
                <td className="player-name">{player.player_name}</td>
                <td>{player.positions.join(', ')}</td>
                <td>{player.overall_rank}</td>
                <td>{formatCurrency(player.auction_value)}</td>
                <td className={`personal-value ${player.raw_value > player.auction_value ? 'value-surplus' : ''}`}>
                  {formatSGP(player.raw_value)}
                </td>
                {getCategories().map(cat => (
                  <td key={cat} className="category-sgp">
                    {formatSGP(getCategorySGP(player, cat))}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
