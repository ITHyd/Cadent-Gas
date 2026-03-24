export const DEMO_REFERENCE_IDS = [
  "REF-1001",
  "REF-1002",
  "REF-1003",
  "REF-1004",
  "REF-1005",
  "REF-1006",
  "REF-1007",
  "REF-1008",
  "REF-1009",
  "REF-1010",
  "REF-1011",
  "REF-1012",
  "REF-1013",
  "REF-1014",
  "REF-1015",
  "REF-1016",
  "REF-1017",
  "REF-1018",
  "REF-1019",
  "REF-1020",
];

export const normalizeDemoReferenceId = (value) => {
  if (value == null) return null;

  const cleaned = String(value).trim().toUpperCase();
  if (!cleaned) return null;

  const match = cleaned.match(/^(?:CRM|REF)[-_\s]?(\d{4})$/);
  if (!match) return null;

  const normalized = `REF-${match[1]}`;
  return DEMO_REFERENCE_IDS.includes(normalized) ? normalized : null;
};
