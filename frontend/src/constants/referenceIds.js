// Generate reference IDs from REF-1000 to REF-9999 (9,000 total IDs)
export const DEMO_REFERENCE_IDS = Array.from({ length: 9000 }, (_, i) => {
  const num = 1000 + i;
  return `REF-${num.toString().padStart(4, '0')}`;
});

export const normalizeDemoReferenceId = (value) => {
  if (value == null) return null;

  const cleaned = String(value).trim().toUpperCase();
  if (!cleaned) return null;

  const match = cleaned.match(/^(?:CRM|REF)[-_\s]?(\d{4})$/);
  if (!match) return null;

  const normalized = `REF-${match[1]}`;

  // Check if the number is in valid range (1000-9999)
  const num = parseInt(match[1], 10);
  return (num >= 1000 && num <= 9999) ? normalized : null;
};
