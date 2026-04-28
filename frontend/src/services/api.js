export const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const readErrorMessage = async (response, fallbackMessage) => {
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    const error = await response.json().catch(() => ({}));
    return error.detail || error.message || fallbackMessage;
  }

  const text = await response.text().catch(() => '');
  return text || fallbackMessage;
};

// ── Auth helpers ──────────────────────────────────────────────────────────

const getAuthHeaders = () => {
  const token = localStorage.getItem('access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const clearStoredAuth = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

const notifyAuthExpired = () => {
  window.dispatchEvent(new Event('auth-expired'));
};

const parseJwtPayload = (token) => {
  try {
    const payload = token?.split('.')?.[1];
    if (!payload) return null;

    const normalized = payload
      .replace(/-/g, '+')
      .replace(/_/g, '/')
      .padEnd(Math.ceil(payload.length / 4) * 4, '=');

    return JSON.parse(window.atob(normalized));
  } catch {
    return null;
  }
};

const isTokenExpiringSoon = (token, minValiditySeconds = 30) => {
  const payload = parseJwtPayload(token);
  if (!payload?.exp) return true;
  return payload.exp * 1000 - Date.now() <= minValiditySeconds * 1000;
};

let _refreshPromise = null;

const tryRefreshToken = async () => {
  // Deduplicate concurrent refresh attempts
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    const refreshToken = localStorage.getItem('refresh_token');
    if (!refreshToken) return false;

    try {
      const resp = await fetch(
        `${API_BASE_URL}/api/v1/auth/refresh`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        },
      );
      if (!resp.ok) return false;

      const data = await resp.json();
      localStorage.setItem('access_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
};

export const ensureFreshAccessToken = async ({ minValiditySeconds = 30 } = {}) => {
  const currentToken = localStorage.getItem('access_token');
  if (currentToken && !isTokenExpiringSoon(currentToken, minValiditySeconds)) {
    return currentToken;
  }

  const hadSession = Boolean(currentToken || localStorage.getItem('refresh_token'));
  const refreshed = await tryRefreshToken();
  const nextToken = localStorage.getItem('access_token');
  if (refreshed && nextToken) {
    return nextToken;
  }

  if (hadSession) {
    clearStoredAuth();
    notifyAuthExpired();
  }
  return null;
};

export const authFetch = async (url, options = {}) => {
  const headers = { ...getAuthHeaders(), ...(options.headers || {}) };
  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    // Try refreshing the token once
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Retry the original request with the new token
      const retryHeaders = { ...getAuthHeaders(), ...(options.headers || {}) };
      return fetch(url, { ...options, headers: retryHeaders });
    }

    // Refresh failed — clear everything and signal logout
    clearStoredAuth();
    notifyAuthExpired();
  }

  return response;
};

// ── Auth API ──────────────────────────────────────────────────────────────

export const sendOTP = async (phone) => {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/send-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, 'Failed to send OTP'));
  }
  return response.json();
};

export const verifyOTP = async (phone, otp) => {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/verify-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, otp }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, 'Invalid OTP'));
  }
  return response.json();
};

export const adminLogin = async (username, password) => {
  const response = await fetch(`${API_BASE_URL}/api/v1/auth/admin-login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response, 'Login failed'));
  }
  return response.json();
};

// ── Incident API ──────────────────────────────────────────────────────────

export const reportIncident = async (formData) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error('Failed to report incident');
  }

  return response.json();
};

export const submitManualReport = async (formData) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/manual-report`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to submit manual report');
  }

  return response.json();
};

export const getAvailableAgents = async () => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/agents/available`);
  if (!response.ok) throw new Error('Failed to fetch available agents');
  return response.json();
};

export const getAllAgents = async () => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/agents/all`);
  if (!response.ok) throw new Error('Failed to fetch agents');
  return response.json();
};

export const getIncident = async (incidentId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}`);

  if (!response.ok) {
    throw new Error('Failed to fetch incident');
  }

  return response.json();
};

export const getUserIncidents = async (userId, tenantId = null) => {
  const url = tenantId 
    ? `${API_BASE_URL}/api/v1/incidents/user/${userId}?tenant_id=${tenantId}`
    : `${API_BASE_URL}/api/v1/incidents/user/${userId}`;
  
  const response = await authFetch(url);

  if (!response.ok) {
    throw new Error('Failed to fetch user incidents');
  }

  const data = await response.json();
  return data;
};

export const getCompanyIncidents = async (tenantId, status = null) => {
  const url = status 
    ? `${API_BASE_URL}/api/v1/incidents/company/${tenantId}?status=${status}`
    : `${API_BASE_URL}/api/v1/incidents/company/${tenantId}`;
  
  const response = await authFetch(url);

  if (!response.ok) {
    throw new Error('Failed to fetch company incidents');
  }

  return response.json();
};

export const getCompanyStats = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/company/${tenantId}/stats`);

  if (!response.ok) {
    throw new Error('Failed to fetch company stats');
  }

  return response.json();
};

export const assignAgent = async (incidentId, agentId) => {
  const formData = new FormData();
  formData.append('agent_id', agentId);

  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/assign`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error('Failed to assign agent');
  }

  return response.json();
};

export const getAgentIncidents = async (agentId, status = null) => {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : '';
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/agent/${agentId}/incidents${suffix}`);
  if (!response.ok) throw new Error('Failed to fetch agent incidents');
  return response.json();
};

export const updateAgentStatus = async (incidentId, agentStatus) => {
  const formData = new FormData();
  formData.append('agent_status', agentStatus);

  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/agent-status`, {
    method: 'PUT',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update agent status');
  }

  return response.json();
};

export const updateAgentLocation = async (incidentId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/agent-location`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update agent location');
  }

  return response.json();
};

export const addFieldMilestone = async (incidentId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/milestones`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to add milestone');
  }

  return response.json();
};

export const createAssistanceRequest = async (incidentId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/assistance-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to create assistance request');
  }

  return response.json();
};

export const updateAssistanceRequest = async (incidentId, requestId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/assistance-requests/${requestId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update assistance request');
  }

  return response.json();
};

export const createItemRequest = async (incidentId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/item-requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to create item request');
  }

  return response.json();
};

export const updateItemRequest = async (incidentId, requestId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/item-requests/${requestId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update item request');
  }

  return response.json();
};

export const getCompanyOpsRequests = async (tenantId, kind = 'all', status = null, includeClosed = false) => {
  const params = new URLSearchParams({ kind, include_closed: includeClosed ? 'true' : 'false' });
  if (status) params.append('status', status);

  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/company/${tenantId}/ops-requests?${params.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch operations requests');
  return response.json();
};

export const resolveIncident = async (
  incidentId,
  resolvedBy,
  resolutionNotes = null,
  options = {},
) => {
  const formData = new FormData();
  formData.append('resolved_by', resolvedBy);
  if (resolutionNotes) {
    formData.append('resolution_notes', resolutionNotes);
  }
  if (options.itemsUsed?.length) {
    formData.append('items_used', options.itemsUsed.join(','));
  }

  const checklist = options.checklist || {};
  const checklistPayload = {
    root_cause: checklist.rootCause || checklist.root_cause || '',
    actions_taken: checklist.actionsTaken || checklist.actions_taken || [],
    verification_evidence: checklist.verificationEvidence || checklist.verification_evidence || '',
    verification_evidence_note: checklist.verificationEvidenceNote || checklist.verification_evidence_note || '',
    verification_result: checklist.verificationResult || checklist.verification_result || '',
    safety_checks_completed: checklist.safetyChecksCompleted ?? checklist.safety_checks_completed ?? false,
    handoff_confirmed: checklist.handoffConfirmed ?? checklist.handoff_confirmed ?? false,
  };
  formData.append('resolution_checklist_json', JSON.stringify(checklistPayload));

  // Append resolution media files (proof of fix)
  if (options.files?.length) {
    for (const file of options.files) {
      formData.append('files', file);
    }
  }

  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/resolve`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to resolve incident');
  }

  return response.json();
};

export const approveResolution = async (incidentId, approvedBy, approvalNotes = null) => {
  const formData = new FormData();
  formData.append('approved_by', approvedBy);
  if (approvalNotes) {
    formData.append('approval_notes', approvalNotes);
  }

  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/approve-resolution`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to approve resolution');
  }

  return response.json();
};

export const validateIncident = async (incidentId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/validate`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to validate incident');
  }
  return response.json();
};

export const markIncidentFalse = async (incidentId, notes) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/mark-false`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to mark incident as false');
  }
  return response.json();
};

export const lookupCustomerByPhone = async (phone) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/auth/lookup-by-phone?phone=${encodeURIComponent(phone)}`
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Customer not found');
  }
  return response.json();
};

export const confirmIncidentValid = async (incidentId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/confirm-valid`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to confirm incident');
  }
  return response.json();
};

export const transcribeAudio = async (audioBlob) => {
  const formData = new FormData();
  formData.append('file', audioBlob, 'recording.webm');

  const response = await authFetch(`${API_BASE_URL}/api/v1/agents/transcribe`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Transcription failed');
  }

  return response.json();
};

export const getWorkflow = async (workflowId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/workflows/${workflowId}`);

  if (!response.ok) {
    throw new Error('Failed to fetch workflow');
  }

  return response.json();
};

export const getTenantWorkflows = async (tenantId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/workflows/tenant/${tenantId}`
  );

  if (!response.ok) {
    throw new Error('Failed to fetch tenant workflows');
  }

  return response.json();
};

export const updateWorkflow = async (workflowId, workflowData) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/workflows/${workflowId}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(workflowData),
    }
  );

  if (!response.ok) {
    throw new Error('Failed to update workflow');
  }

  return response.json();
};

export const createWorkflow = async (workflowData) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/workflows/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(workflowData),
  });

  if (!response.ok) {
    throw new Error('Failed to create workflow');
  }

  return response.json();
};

// Super User Workflow Versioning
export const getWorkflowVersions = async (workflowId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/workflows/${workflowId}/versions`);
  if (!response.ok) throw new Error('Failed to fetch workflow versions');
  return response.json();
};

export const getWorkflowVersion = async (workflowId, version) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/workflows/${workflowId}/versions/${version}`);
  if (!response.ok) throw new Error('Failed to fetch workflow version');
  return response.json();
};

export const renameWorkflowVersion = async (workflowId, version, versionLabel) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/workflows/${workflowId}/versions/${version}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version_label: versionLabel }),
  });
  if (!response.ok) throw new Error('Failed to rename workflow version');
  return response.json();
};

export const deleteWorkflowVersion = async (workflowId, version) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/workflows/${workflowId}/versions/${version}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete workflow version');
  return response.json();
};

export const activateWorkflowVersion = async (workflowId, version) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/workflows/${workflowId}/versions/${version}/activate`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to activate workflow version');
  return response.json();
};

export const uploadFile = async (file, sessionId) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('session_id', sessionId);

  const response = await authFetch(`${API_BASE_URL}/api/v1/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error('Failed to upload file');
  }

  return response.json();
};


// Knowledge Base API functions
export const getKBStats = async (tenantId = null) => {
  const url = tenantId 
    ? `${API_BASE_URL}/api/v1/kb/stats?tenant_id=${tenantId}`
    : `${API_BASE_URL}/api/v1/kb/stats`;
  
  const response = await authFetch(url);
  if (!response.ok) throw new Error('Failed to fetch KB stats');
  return response.json();
};

export const getTrueIncidentsKB = async (page = 1, limit = 20, tenantId = null) => {
  const params = new URLSearchParams({ page: page.toString(), limit: limit.toString() });
  if (tenantId) params.append('tenant_id', tenantId);
  
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/true?${params}`);
  if (!response.ok) throw new Error('Failed to fetch true incidents KB');
  return response.json();
};

export const getFalseIncidentsKB = async (page = 1, limit = 20, tenantId = null) => {
  const params = new URLSearchParams({ page: page.toString(), limit: limit.toString() });
  if (tenantId) params.append('tenant_id', tenantId);
  
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/false?${params}`);
  if (!response.ok) throw new Error('Failed to fetch false incidents KB');
  return response.json();
};

export const getRecentKBEntries = async (limit = 10, tenantId = null) => {
  const params = new URLSearchParams({ limit: limit.toString() });
  if (tenantId) params.append('tenant_id', tenantId);
  
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/recent?${params}`);
  if (!response.ok) throw new Error('Failed to fetch recent KB entries');
  return response.json();
};

export const addKBEntry = async (kbType, entry, verifiedBy) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/${kbType}?verified_by=${verifiedBy}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  });
  if (!response.ok) throw new Error(`Failed to add ${kbType} KB entry`);
  return response.json();
};

export const updateKBEntry = async (kbType, kbId, updates) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/${kbType}/${kbId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!response.ok) throw new Error(`Failed to update KB entry`);
  return response.json();
};

export const deleteKBEntry = async (kbType, kbId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/${kbType}/${kbId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Failed to delete KB entry`);
  return response.json();
};

export const searchKB = async (query, kbType = null, limit = 10) => {
  const params = new URLSearchParams({ query, limit: limit.toString() });
  if (kbType) params.append('kb_type', kbType);

  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/search?${params}`);
  if (!response.ok) throw new Error('Failed to search KB');
  return response.json();
};

export const verifyIncidentKB = async (incidentData, useCase) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/kb/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ incident_data: incidentData, use_case: useCase }),
  });
  if (!response.ok) throw new Error('Failed to verify incident against KB');
  return response.json();
};

// ── Tenant Management API ───────────────────────────────────────────────

export const getTenants = async () => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/tenants`);
  if (!response.ok) throw new Error('Failed to fetch tenants');
  return response.json();
};

export const getSuperTenantDetail = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/super/tenants/${tenantId}`);
  if (!response.ok) throw new Error('Failed to fetch tenant detail');
  return response.json();
};

// ── Operations Center API ────────────────────────────────────────────────

export const assignBackupAgent = async (incidentId, requestId, payload) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/${incidentId}/assistance-requests/${requestId}/assign-backup`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to assign backup agent');
  }
  return response.json();
};

export const createCustomerNotification = async (incidentId, payload) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/${incidentId}/notifications`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to create notification');
  }
  return response.json();
};

export const getCustomerNotifications = async (incidentId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/${incidentId}/notifications`);
  if (!response.ok) throw new Error('Failed to fetch notifications');
  return response.json();
};

// ── User Notes API ────────────────────────────────────────────────────

export const addUserNote = async (incidentId, note) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/${incidentId}/user-notes`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to add note');
  }
  return response.json();
};

export const updateUserNote = async (incidentId, noteId, note) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/${incidentId}/user-notes/${noteId}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update note');
  }
  return response.json();
};

export const deleteUserNote = async (incidentId, noteId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/${incidentId}/user-notes/${noteId}`,
    { method: 'DELETE' }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to delete note');
  }
  return response.json();
};

// ── SMS Preference API ───────────────────────────────────────────────

export const updateSmsPreference = async (incidentId, smsEnabled, phone = null) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/${incidentId}/sms-preference`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sms_enabled: smsEnabled, phone }),
    }
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to update SMS preference');
  }
  return response.json();
};

// ── In-App Notification API ────────────────────────────────────────────

export const getUserNotifications = async (userId, unreadOnly = false) => {
  const params = unreadOnly ? '?unread_only=true' : '';
  const response = await authFetch(`${API_BASE_URL}/api/v1/incidents/notifications/${userId}${params}`);
  if (!response.ok) throw new Error('Failed to fetch notifications');
  return response.json();
};

export const markNotificationRead = async (userId, notificationId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/notifications/${userId}/mark-read/${notificationId}`,
    { method: 'POST' }
  );
  if (!response.ok) throw new Error('Failed to mark notification read');
  return response.json();
};

export const markAllNotificationsRead = async (userId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/incidents/notifications/${userId}/mark-all-read`,
    { method: 'POST' }
  );
  if (!response.ok) throw new Error('Failed to mark all notifications read');
  return response.json();
};

// ── Connector API ────────────────────────────────────────────────────────

export const getTenantConnectors = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/tenant/${tenantId}`);
  if (!response.ok) throw new Error('Failed to fetch connectors');
  return response.json();
};

export const getAvailableConnectors = async () => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/available`);
  if (!response.ok) throw new Error('Failed to fetch available connectors');
  return response.json();
};

export const getSyncStatus = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/sync/${tenantId}/status`);
  if (!response.ok) throw new Error('Failed to fetch sync status');
  return response.json();
};

export const getSyncLogs = async (tenantId, { status, direction, limit = 50, offset = 0 } = {}) => {
  const params = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
  if (status) params.append('status', status);
  if (direction) params.append('direction', direction);
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/sync/${tenantId}/logs?${params}`);
  if (!response.ok) throw new Error('Failed to fetch sync logs');
  return response.json();
};

export const getDeadLetterEvents = async (tenantId, limit = 50) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/sync/${tenantId}/dead-letter?limit=${encodeURIComponent(limit)}`
  );
  if (!response.ok) throw new Error('Failed to fetch dead-letter events');
  return response.json();
};

export const replayDeadLetterEvent = async (tenantId, eventId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/sync/${tenantId}/dead-letter/${eventId}/replay`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to replay event');
  }
  return response.json();
};

export const replayAllDeadLetterEvents = async (tenantId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/sync/${tenantId}/dead-letter/replay-all`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to replay all dead-letter events');
  }
  return response.json();
};

export const getSyncEventTrace = async (tenantId, eventId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/sync/${tenantId}/events/${eventId}/trace`,
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch event trace');
  }
  return response.json();
};

export const getConnectorHealth = async (configId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/${configId}/health`);
  if (!response.ok) throw new Error('Failed to fetch connector health');
  return response.json();
};

export const updateConnector = async (configId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/${configId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update connector');
  }
  return response.json();
};

export const deactivateConnector = async (configId, tenantId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/${configId}/deactivate?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to deactivate connector');
  }
  return response.json();
};

export const deleteConnector = async (configId, tenantId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/${configId}?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete connector');
  }
  return response.json();
};

export const backfillConnector = async (tenantId, connectorType, limit = 50, filters = {}) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/backfill/${encodeURIComponent(tenantId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ connector_type: connectorType, limit, offset: 0, filters }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Backfill failed');
  }
  return response.json();
};

// ── Tenant API ───────────────────────────────────────────────────────────

export const createTenant = async (data) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json();
    throw new Error(err.detail || 'Failed to create tenant');
  }
  return response.json();
};

export const getTenantById = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}`);
  if (!response.ok) throw new Error('Failed to fetch tenant');
  return response.json();
};

export const updateTenant = async (tenantId, data) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update tenant');
  return response.json();
};

export const updateTenantStatus = async (tenantId, status) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/status`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) throw new Error('Failed to update tenant status');
  return response.json();
};

export const deleteTenant = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}?hard=true`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete tenant');
  return response.json();
};

export const updateTenantConfig = async (tenantId, config) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update tenant config');
  }
  return response.json();
};

export const createTenantUser = async (tenantId, data) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create tenant user');
  }
  return response.json();
};

export const getTenantMapping = async (tenantId, connectorType) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/mappings/${connectorType}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch tenant mapping');
  }
  return response.json();
};

export const updateTenantMapping = async (tenantId, connectorType, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/mappings/${connectorType}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update tenant mapping');
  }
  return response.json();
};

export const getTenantMappingVersions = async (tenantId, connectorType, limit = 25) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/tenants/${tenantId}/mappings/${connectorType}/versions?limit=${encodeURIComponent(limit)}`
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to fetch mapping versions');
  }
  return response.json();
};

export const rollbackTenantMapping = async (tenantId, connectorType, version) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/tenants/${tenantId}/mappings/${connectorType}/rollback/${version}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to rollback tenant mapping');
  }
  return response.json();
};

// Onboarding connector helper APIs
export const configureConnector = async (payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/configure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to configure connector');
  }
  return response.json();
};

export const storeConnectorCredentials = async (configId, payload) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/connectors/${configId}/credentials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to store credentials');
  }
  return response.json();
};

export const testConnector = async (configId, tenantId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/${configId}/test?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Connector test failed');
  }
  return response.json();
};

export const activateConnector = async (configId, tenantId) => {
  const response = await authFetch(
    `${API_BASE_URL}/api/v1/connectors/${configId}/activate?tenant_id=${encodeURIComponent(tenantId)}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to activate connector');
  }
  return response.json();
};

// ── Admin Group API ──────────────────────────────────────────────────────────

export const getAdminGroups = async (tenantId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/admin-groups`);
  if (!response.ok) throw new Error('Failed to fetch admin groups');
  return response.json();
};

export const createAdminGroup = async (tenantId, data) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/admin-groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create admin group');
  }
  return response.json();
};

export const updateAdminGroup = async (tenantId, groupId, data) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/admin-groups/${groupId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update admin group');
  }
  return response.json();
};

export const deleteAdminGroup = async (tenantId, groupId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/admin-groups/${groupId}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete admin group');
  return response.json();
};

export const assignUserToGroup = async (tenantId, userId, adminGroupId) => {
  const response = await authFetch(`${API_BASE_URL}/api/v1/tenants/${tenantId}/users/${userId}/admin-group`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ admin_group_id: adminGroupId }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to assign user to group');
  }
  return response.json();
};
