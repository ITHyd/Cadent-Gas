export const getIncidentNumericPart = (incidentId) => {
  if (!incidentId) return "";

  const normalized = String(incidentId).trim().toUpperCase();
  const prefixedMatch = normalized.match(/^(?:INC|REF)[-_]?(.+)$/i);
  return prefixedMatch ? prefixedMatch[1] : normalized;
};

export const formatIncidentId = (incidentId) => {
  if (!incidentId) return "";

  const suffix = getIncidentNumericPart(incidentId);
  if (!suffix) return "";
  return `INC-${suffix}`;
};

export const formatReferenceId = (incidentId) => {
  if (!incidentId) return "";

  const suffix = getIncidentNumericPart(incidentId);
  if (!suffix) return "";
  return `REF-${suffix}`;
};
