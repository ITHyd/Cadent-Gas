import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getAgentIncidents, updateAgentStatus } from '../services/api';
import ProfileDropdown from '../components/ProfileDropdown';
import NotificationBell from '../components/NotificationBell';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix default Leaflet marker icon (broken by bundlers)
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Known locations for seed data addresses
const LOCATION_COORDS = {
  westminster: [51.4975, -0.1357],
  deansgate: [53.4794, -2.2484],
  manchester: [53.4808, -2.2426],
  headingley: [53.8271, -1.5776],
  leeds: [53.8008, -1.5491],
  clifton: [51.4557, -2.6208],
  bristol: [51.4545, -2.5879],
  'canary wharf': [51.5054, -0.0235],
  london: [51.5074, -0.1278],
};

const OPEN_ASSISTANCE_STATUSES = new Set(['PENDING', 'ACKNOWLEDGED', 'IN_PROGRESS']);
const OPEN_ITEM_STATUSES = new Set(['REQUESTED', 'APPROVED', 'DISPATCHED', 'DELIVERED']);

const ROLE_META = {
  backup: { label: 'BACKUP', bg: '#fef3c7', color: '#92400e', border: '#fcd34d' },
  supervisor: { label: 'SUPERVISOR', bg: '#ede9fe', color: '#5b21b6', border: '#c4b5fd' },
  safety_support: { label: 'SAFETY SUPPORT', bg: '#fce7f3', color: '#9d174d', border: '#f9a8d4' },
};

const FieldAgentDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('all');
  const [busyIncidentId, setBusyIncidentId] = useState(null);
  const [lastSyncedAt, setLastSyncedAt] = useState(null);

  const agentId = user?.user_id;

  const getAgentRole = (incident) => {
    if (incident.assigned_agent_id === agentId) return 'primary';
    const backupEntry = (incident.backup_agents || []).find((b) => b.agent_id === agentId);
    return backupEntry ? (backupEntry.role || 'backup') : 'primary';
  };

  const getBackupContext = (incident) => {
    const backupEntry = (incident.backup_agents || []).find((b) => b.agent_id === agentId);
    if (!backupEntry) return null;
    const linkedRequest = (incident.assistance_requests || []).find((r) => r.request_id === backupEntry.request_id);
    return { ...backupEntry, request: linkedRequest };
  };

  const fetchAgentIncidents = async (showLoading = false) => {
    if (!agentId) return;

    try {
      if (showLoading) setLoading(true);
      const statusParam = filterStatus !== 'all' ? filterStatus : null;
      const data = await getAgentIncidents(agentId, statusParam);
      setIncidents(data.incidents || []);
      setLastSyncedAt(new Date());
    } catch {
      // silently handled
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgentIncidents(true);
  }, [agentId, filterStatus]);

  useEffect(() => {
    if (!agentId) return undefined;
    const timer = setInterval(() => fetchAgentIncidents(false), 30000);
    return () => clearInterval(timer);
  }, [agentId, filterStatus]);

  const optimisticStatusUpdate = async (incidentId, nextStatus) => {
    const previous = incidents;
    setBusyIncidentId(incidentId);

    setIncidents((current) => current.map((incident) => (
      incident.incident_id === incidentId
        ? { ...incident, agent_status: nextStatus }
        : incident
    )));

    try {
      await updateAgentStatus(incidentId, nextStatus);
      fetchAgentIncidents(false);
    } catch {
      setIncidents(previous);
      alert('Failed to update status. Please retry.');
    } finally {
      setBusyIncidentId(null);
    }
  };

  const stats = useMemo(() => {
    const getOpenAssist = (incident) => (incident.assistance_requests || []).filter((req) => OPEN_ASSISTANCE_STATUSES.has((req.status || '').toUpperCase())).length;
    const getOpenItems = (incident) => (incident.item_requests || []).filter((req) => OPEN_ITEM_STATUSES.has((req.status || '').toUpperCase())).length;

    const checklistComplete = (incident) => {
      const checklist = incident.resolution_checklist || {};
      return Boolean(
        checklist.root_cause
        && Array.isArray(checklist.actions_taken)
        && checklist.actions_taken.length > 0
        && checklist.verification_result
        && checklist.safety_checks_completed === true
        && checklist.handoff_confirmed === true
      );
    };

    return {
      assigned: incidents.filter((incident) => incident.agent_status === 'ASSIGNED').length,
      enRoute: incidents.filter((incident) => incident.agent_status === 'EN_ROUTE').length,
      onSite: incidents.filter((incident) => incident.agent_status === 'ON_SITE').length,
      inProgress: incidents.filter((incident) => incident.agent_status === 'IN_PROGRESS').length,
      completed: incidents.filter((incident) => incident.agent_status === 'COMPLETED').length,
      pendingAssistance: incidents.reduce((sum, incident) => sum + getOpenAssist(incident), 0),
      pendingItems: incidents.reduce((sum, incident) => sum + getOpenItems(incident), 0),
      closureBlockers: incidents.filter((incident) => incident.agent_status === 'IN_PROGRESS' && !checklistComplete(incident)).length,
    };
  }, [incidents]);

  const getRiskMeta = (riskScore) => {
    if (!riskScore) return { label: 'Unknown', bg: '#f1f5f9', color: '#475569' };
    if (riskScore >= 0.8) return { label: 'Critical', bg: '#fef2f2', color: '#b91c1c' };
    if (riskScore >= 0.5) return { label: 'High', bg: '#fff7ed', color: '#b45309' };
    if (riskScore >= 0.3) return { label: 'Medium', bg: '#fef9c3', color: '#a16207' };
    return { label: 'Low', bg: '#ecfdf5', color: '#047857' };
  };

  const getStatusMeta = (agentStatus) => {
    const map = {
      ASSIGNED: { label: 'Assigned', bg: '#e0f2fe', color: '#075985' },
      EN_ROUTE: { label: 'En Route', bg: '#fff7ed', color: '#b45309' },
      ON_SITE: { label: 'On Site', bg: '#ede9fe', color: '#5b21b6' },
      IN_PROGRESS: { label: 'In Progress', bg: '#e5f4f1', color: '#030304' },
      COMPLETED: { label: 'Completed', bg: '#dcfce7', color: '#047857' },
    };

    return map[agentStatus] || { label: agentStatus || 'Unknown', bg: '#f1f5f9', color: '#475569' };
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';

    return new Date(dateString).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getOpenAssistanceCount = (incident) => (incident.assistance_requests || []).filter((req) => OPEN_ASSISTANCE_STATUSES.has((req.status || '').toUpperCase())).length;
  const getOpenItemCount = (incident) => (incident.item_requests || []).filter((req) => OPEN_ITEM_STATUSES.has((req.status || '').toUpperCase())).length;

  const renderQuickAction = (incident) => {
    if (incident.agent_status === 'ASSIGNED') {
      return (
        <button
          type="button"
          className="primary-btn"
          style={{ minHeight: '34px', padding: '7px 11px', fontSize: '0.75rem' }}
          disabled={busyIncidentId === incident.incident_id}
          onClick={(event) => {
            event.stopPropagation();
            optimisticStatusUpdate(incident.incident_id, 'EN_ROUTE');
          }}
        >
          {busyIncidentId === incident.incident_id ? 'Updating...' : 'Mark En Route'}
        </button>
      );
    }

    if (incident.agent_status === 'EN_ROUTE') {
      return (
        <button
          type="button"
          className="secondary-btn"
          style={{ minHeight: '34px', padding: '7px 11px', fontSize: '0.75rem' }}
          disabled={busyIncidentId === incident.incident_id}
          onClick={(event) => {
            event.stopPropagation();
            optimisticStatusUpdate(incident.incident_id, 'ON_SITE');
          }}
        >
          {busyIncidentId === incident.incident_id ? 'Updating...' : 'Mark On Site'}
        </button>
      );
    }

    if (incident.agent_status === 'ON_SITE') {
      return (
        <button
          type="button"
          className="secondary-btn"
          style={{ minHeight: '34px', padding: '7px 11px', fontSize: '0.75rem' }}
          disabled={busyIncidentId === incident.incident_id}
          onClick={(event) => {
            event.stopPropagation();
            optimisticStatusUpdate(incident.incident_id, 'IN_PROGRESS');
          }}
        >
          {busyIncidentId === incident.incident_id ? 'Updating...' : 'Start Diagnosis'}
        </button>
      );
    }

    return null;
  };

  // Resolve coordinates from address/location text
  const resolveCoords = (incident) => {
    const text = (incident.user_address || incident.location || '').toLowerCase();
    for (const [key, coords] of Object.entries(LOCATION_COORDS)) {
      if (text.includes(key)) return coords;
    }
    return null;
  };

  const mappedIncidents = useMemo(
    () => incidents.map((inc) => ({ ...inc, _coords: resolveCoords(inc) })).filter((inc) => inc._coords),
    [incidents],
  );

  return (
    <div className="app-shell" style={{ position: 'relative' }}>
      <div className="ambient-grid" />
      <ProfileDropdown />
      <NotificationBell />

      <div className="page-container" style={{ position: 'relative', zIndex: 1 }}>
        <header className="panel" style={{ padding: '22px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '14px', flexWrap: 'wrap' }}>
            <div>
              <span className="eyebrow">Field Operations</span>
              <h1 className="page-heading" style={{ marginTop: '10px' }}>Field Agent Dashboard</h1>
              <p className="page-subheading">Track field jobs, launch workspace, and manage support requests in real time.</p>
            </div>

            <div style={{ display: 'grid', gap: '6px', justifyItems: 'end' }}>
              <button type="button" className="secondary-btn" onClick={() => navigate('/dashboard')}>
                Back to Main Dashboard
              </button>
              <span style={{ fontSize: '0.75rem', color: '#6f8399', fontWeight: 600 }}>
                {lastSyncedAt ? `Last synced: ${lastSyncedAt.toLocaleTimeString()}` : 'Syncing...'}
              </span>
            </div>
          </div>
        </header>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '10px', marginBottom: '14px' }}>
          {[
            { label: 'Assigned', value: stats.assigned, color: '#030304' },
            { label: 'En Route', value: stats.enRoute, color: '#b45309' },
            { label: 'On Site', value: stats.onSite, color: '#5b21b6' },
            { label: 'In Progress', value: stats.inProgress, color: '#8DE971' },
            { label: 'Completed', value: stats.completed, color: '#047857' },
            { label: 'Assist Requests', value: stats.pendingAssistance, color: '#b91c1c' },
            { label: 'Item Requests', value: stats.pendingItems, color: '#0369a1' },
            { label: 'Closure Blockers', value: stats.closureBlockers, color: '#9f1239' },
          ].map((card) => (
            <article key={card.label} className="kpi-card">
              <div className="kpi-label">{card.label}</div>
              <div className="kpi-value" style={{ color: card.color }}>{card.value}</div>
            </article>
          ))}
        </section>

        {/* UK Map */}
        <section className="panel" style={{ padding: '16px', marginBottom: '14px' }}>
          <h3 style={{ margin: '0 0 10px', fontSize: '0.85rem', fontWeight: 700, color: '#11263c' }}>Incident Locations</h3>
          <div style={{ borderRadius: '12px', overflow: 'hidden', height: '320px' }}>
            <MapContainer
              center={[53.0, -1.5]}
              zoom={6}
              style={{ height: '100%', width: '100%' }}
              scrollWheelZoom={true}
            >
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {mappedIncidents.map((inc) => (
                <Marker key={inc.incident_id} position={inc._coords}>
                  <Popup>
                    <strong>{inc.incident_id}</strong><br />
                    {(inc.classified_use_case || inc.incident_type || 'Incident').replaceAll('_', ' ')}<br />
                    <span style={{ fontSize: '0.8em', color: '#64748b' }}>{inc.user_address || inc.location || ''}</span>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          </div>
        </section>

        <section className="panel" style={{ padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
            <div className="segmented" style={{ marginBottom: 0 }}>
              {['all', 'ASSIGNED', 'EN_ROUTE', 'ON_SITE', 'IN_PROGRESS', 'COMPLETED'].map((status) => (
                <button
                  key={status}
                  type="button"
                  className={`segment-btn ${filterStatus === status ? 'active' : ''}`}
                  onClick={() => setFilterStatus(status)}
                >
                  {status === 'all' ? 'All Incidents' : status.replace('_', ' ')}
                </button>
              ))}
            </div>

            <button type="button" className="secondary-btn" onClick={() => fetchAgentIncidents(false)}>
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="panel-soft" style={{ padding: '32px', textAlign: 'center' }}>
              <p style={{ margin: 0 }}>Loading assigned incidents...</p>
            </div>
          ) : incidents.length === 0 ? (
            <div className="panel-soft" style={{ padding: '32px', textAlign: 'center' }}>
              <h3 style={{ marginBottom: '6px' }}>No Incidents Found</h3>
              <p style={{ margin: 0 }}>No records match the selected filter.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '10px' }}>
              {incidents.map((incident) => {
                const statusMeta = getStatusMeta(incident.agent_status);
                const riskMeta = getRiskMeta(incident.risk_score);
                const openAssist = getOpenAssistanceCount(incident);
                const openItems = getOpenItemCount(incident);
                const role = getAgentRole(incident);
                const roleMeta = ROLE_META[role];
                const backupCtx = role !== 'primary' ? getBackupContext(incident) : null;

                return (
                  <article
                    key={incident.incident_id}
                    className="panel-soft"
                    style={{
                      border: roleMeta ? `2px solid ${roleMeta.border}` : '1px solid #d4e2ef',
                      background: '#fff',
                      padding: '13px',
                      borderRadius: '14px',
                      cursor: 'pointer',
                    }}
                    onClick={() => navigate(`/agent/incidents/${incident.incident_id}`)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <h3 style={{ margin: 0, fontSize: '1rem', color: '#11263c' }}>{incident.incident_id}</h3>
                        {roleMeta && (
                          <span
                            style={{
                              borderRadius: '999px',
                              padding: '3px 10px',
                              fontSize: '0.68rem',
                              fontWeight: 800,
                              letterSpacing: '0.05em',
                              background: roleMeta.bg,
                              color: roleMeta.color,
                              border: `1px solid ${roleMeta.border}`,
                            }}
                          >
                            {roleMeta.label}
                          </span>
                        )}
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span
                          style={{
                            borderRadius: '999px',
                            padding: '4px 9px',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            background: riskMeta.bg,
                            color: riskMeta.color,
                            border: `1px solid ${riskMeta.color}2c`,
                          }}
                        >
                          {riskMeta.label} {(incident.risk_score ? incident.risk_score * 100 : 0).toFixed(0)}%
                        </span>

                        <span
                          style={{
                            borderRadius: '999px',
                            padding: '4px 9px',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            background: statusMeta.bg,
                            color: statusMeta.color,
                          }}
                        >
                          {statusMeta.label}
                        </span>
                      </div>
                    </div>

                    {/* Backup context panel */}
                    {backupCtx && (
                      <div
                        style={{
                          margin: '8px 0',
                          padding: '10px 12px',
                          borderRadius: '10px',
                          background: roleMeta.bg,
                          border: `1px solid ${roleMeta.border}`,
                        }}
                      >
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: roleMeta.color, marginBottom: '4px' }}>
                          Support Assignment
                        </div>
                        {backupCtx.request && (
                          <p style={{ margin: '0 0 4px', fontSize: '0.82rem', color: '#4d6178' }}>
                            Reason: {backupCtx.request.reason || 'N/A'}
                          </p>
                        )}
                        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', fontSize: '0.76rem', color: '#6e859d', fontWeight: 600 }}>
                          {incident.assigned_agent_id && incident.assigned_agent_id !== agentId && (
                            <span>Primary Agent: {incident.assigned_agent?.full_name || incident.assigned_agent_id}</span>
                          )}
                          {backupCtx.request?.priority && <span>Priority: {backupCtx.request.priority}</span>}
                          {backupCtx.assigned_at && (
                            <span>Assigned: {formatDate(backupCtx.assigned_at)}</span>
                          )}
                        </div>
                      </div>
                    )}

                    <p style={{ margin: '6px 0 8px', color: '#4d6178', fontSize: '0.9rem' }}>
                      {(incident.classified_use_case || incident.incident_type || 'Incident').replaceAll('_', ' ')}
                    </p>

                    <p style={{ margin: 0, fontSize: '0.88rem', color: '#5f738a' }}>
                      {incident.description || 'No description provided.'}
                    </p>

                    <div style={{ marginTop: '9px', display: 'flex', gap: '10px', flexWrap: 'wrap', fontSize: '0.78rem', color: '#6e859d', fontWeight: 600 }}>
                      <span>Assigned: {formatDate(incident.assigned_at)}</span>
                      <span>Location: {incident.user_address || incident.location || 'N/A'}</span>
                      <span>Assistance Open: {openAssist}</span>
                      <span>Items Open: {openItems}</span>
                    </div>

                    <div style={{ marginTop: '10px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {renderQuickAction(incident)}

                      <button
                        type="button"
                        className="primary-btn"
                        style={{ minHeight: '34px', padding: '7px 11px', fontSize: '0.75rem' }}
                        onClick={(event) => {
                          event.stopPropagation();
                          navigate(`/agent/incidents/${incident.incident_id}`);
                        }}
                      >
                        Open Workspace
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <style>{`
        @media (max-width: 1080px) {
          .page-container > section:first-of-type {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 700px) {
          .page-container > section:first-of-type {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
};

export default FieldAgentDashboard;
