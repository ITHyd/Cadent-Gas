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

export const getDisplayReferenceId = (incident) => {
  const storedReferenceId =
    incident?.reference_id ||
    incident?.structured_data?.reference_id ||
    incident?.structured_data?.ref_id;

  if (storedReferenceId) {
    return String(storedReferenceId).trim().toUpperCase();
  }

  return formatReferenceId(incident?.incident_id);
};
