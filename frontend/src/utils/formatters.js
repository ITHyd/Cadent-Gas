/**
 * Format a use_case identifier for display.
 * Handles CO-specific capitalisation:
 *   co_alarm           → "CO Alarm"
 *   co_orange_flames   → "CO Orange Flames"
 *   suspected_co_leak  → "Suspected CO Leak"
 *   gas_smell          → "Gas Smell"
 */
export const formatUseCase = (uc) => {
  if (!uc) return '';
  return uc
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bCo\b/g, 'CO');
};

/**
 * Format any snake_case key for display.
 * Also handles CO capitalisation.
 */
export const formatKey = (key) => {
  if (!key) return '';
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bCo\b/g, 'CO');
};
