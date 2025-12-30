// Utility functions for formatting numbers and currency

export const formatCurrency = (value: number): string => {
  return `$${value.toFixed(0)}`;
};

export const formatDecimal = (value: number, decimals: number = 2): string => {
  return value.toFixed(decimals);
};

export const formatPercentage = (value: number, decimals: number = 3): string => {
  return value.toFixed(decimals);
};

export const formatSGP = (value: number): string => {
  return value.toFixed(1);
};

export const formatRank = (rank: number): string => {
  const suffix = rank === 1 ? 'st' : rank === 2 ? 'nd' : rank === 3 ? 'rd' : 'th';
  return `${rank}${suffix}`;
};
