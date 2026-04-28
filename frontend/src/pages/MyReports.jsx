import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getUserIncidents } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { formatReferenceId } from '../utils/incidentIds';
import CustomSelect from '../components/CustomSelect';
import ProfileDropdown from '../components/ProfileDropdown';
import NotificationBell from '../components/NotificationBell';

const MyReports = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);

  const pageSizeOptions = [10, 20, 30, 50, 100];

  const userId = user?.user_id;
  const tenantId = user?.tenant_id;

  useEffect(() => {
    fetchIncidents();

    // Auto-refresh every 30 seconds
    const interval = setInterval(() => {
      fetchIncidents();
    }, 30000);

    return () => clearInterval(interval);
  }, [userId, tenantId]);

  const fetchIncidents = async () => {
    try {
      setLoading(true);
      const data = await getUserIncidents(userId, tenantId);
      setIncidents(data.incidents || []);
    } catch {
      // fetch failed silently
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    const colors = {
      new: '#030304',
      submitted: '#0e7490',
      classifying: '#6d28d9',
      in_progress: '#b45309',
      paused: '#b45309',
      analyzing: '#b45309',
      pending_company_action: '#b91c1c',
      dispatched: '#8DE971',
      resolved: '#047857',
      completed: '#047857',
      emergency: '#b91c1c',
      false_report: '#64748b',
      closed: '#475569',
    };

    return colors[status] || '#475569';
  };

  const getStatusLabel = (status) => {
    const labels = {
      new: 'New',
      submitted: 'Submitted',
      classifying: 'Classifying',
      in_progress: 'In Progress',
      paused: 'Paused',
      analyzing: 'Analyzing',
      pending_company_action: 'Pending Action',
      dispatched: 'Engineer Dispatched',
      resolved: 'Resolved',
      completed: 'Completed',
      emergency: 'Emergency',
      false_report: 'False Report',
      closed: 'Closed',
    };

    return labels[status] || status;
  };

  const getOutcomeLabel = (outcome) => {
    const labels = {
      emergency_dispatch: 'Emergency Dispatch',
      schedule_engineer: 'Engineer Scheduled',
      monitor: 'Monitoring',
      close_with_guidance: 'Guidance Provided',
      false_report: 'No Action Required',
    };

    return labels[outcome] || '';
  };

  const getAgentStatusLabel = (agentStatus) => {
    const labels = {
      ASSIGNED: 'Engineer Assigned',
      EN_ROUTE: 'Engineer En Route',
      ON_SITE: 'Engineer On Site',
      IN_PROGRESS: 'Repair In Progress',
      COMPLETED: 'Field Work Completed',
    };

    return labels[agentStatus] || '';
  };

  const getCurrentPhaseLabel = (incident) => {
    if (incident.agent_status) {
      return getAgentStatusLabel(incident.agent_status) || getStatusLabel(incident.status);
    }

    if (incident.status === 'pending_company_action' && incident.structured_data?.manual_report) {
      return 'Manual report under review';
    }
    if (incident.status === 'pending_company_action') {
      return 'Waiting for dispatch team assignment';
    }
    if (incident.status === 'dispatched' && !incident.agent_status) {
      return 'Engineer dispatch in progress';
    }
    if (['resolved', 'completed'].includes(incident.status)) {
      return 'Case resolved';
    }

    return getStatusLabel(incident.status);
  };

  const getLatestStatusUpdate = (incident) => {
    const history = incident.status_history || [];
    if (!history.length) return null;
    return history[history.length - 1];
  };

  const getSlaSignal = (incident) => {
    if (!incident.estimated_resolution_at || !isActive(incident.status)) return null;

    const eta = new Date(incident.estimated_resolution_at).getTime();
    const now = Date.now();
    if (Number.isNaN(eta)) return null;

    const diffMinutes = Math.floor((eta - now) / 60000);
    if (diffMinutes < 0) return { label: `ETA exceeded by ${Math.abs(diffMinutes)}m`, color: '#b91c1c' };
    if (diffMinutes <= 30) return { label: `ETA due in ${diffMinutes}m`, color: '#b45309' };
    return { label: 'On schedule', color: '#047857' };
  };

  const isActive = (status) => {
    return ['new', 'submitted', 'in_progress', 'analyzing', 'pending_company_action', 'dispatched', 'emergency'].includes(status);
  };

  const isFalseReport = (incident) => {
    return (
      incident.status === 'false_report' ||
      incident.outcome === 'false_report' ||
      incident.outcome === 'close_with_guidance' ||
      incident.kb_match_type === 'false_incident'
    );
  };

  const getTimelineSteps = (incident) => {
    const steps = [
      { label: 'Reported', completed: true },
      { label: 'Assessed', completed: incident.outcome != null },
    ];

    const needsDispatch = incident.outcome && ['emergency_dispatch', 'schedule_engineer'].includes(incident.outcome);
    if (needsDispatch || incident.assigned_agent_id) {
      steps.push({ label: 'Dispatched', completed: incident.assigned_agent_id != null });
    }

    steps.push({
      label: 'Resolved',
      completed: ['resolved', 'completed'].includes(incident.status),
    });

    return steps;
  };

  const filteredIncidents = useMemo(() => {
    let result = incidents;

    if (filter === 'true') result = result.filter((incident) => !isFalseReport(incident));
    else if (filter === 'false') result = result.filter((incident) => isFalseReport(incident));
    else if (filter === 'manual') {
      result = result.filter((incident) => incident.structured_data?.manual_report === true);
    } else if (filter === 'active') {
      result = result.filter((incident) =>
        ['new', 'submitted', 'classifying', 'in_progress', 'analyzing', 'pending_company_action', 'dispatched'].includes(incident.status)
      );
    } else if (filter === 'resolved') {
      result = result.filter((incident) => ['resolved', 'completed'].includes(incident.status));
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      result = result.filter((incident) =>
        incident.incident_id?.toLowerCase().includes(query) ||
        incident.incident_type?.toLowerCase().includes(query) ||
        incident.classified_use_case?.toLowerCase().includes(query) ||
        incident.description?.toLowerCase().includes(query) ||
        incident.status?.toLowerCase().includes(query) ||
        incident.incident_type?.replaceAll('_', ' ').toLowerCase().includes(query) ||
        incident.classified_use_case?.replaceAll('_', ' ').toLowerCase().includes(query)
      );
    }

    return result;
  }, [incidents, filter, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredIncidents.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);

  const paginatedIncidents = filteredIncidents.slice(
    (safeCurrentPage - 1) * pageSize,
    safeCurrentPage * pageSize
  );

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, pageSize, filter]);

  const trueIncidents = incidents.filter((incident) => !isFalseReport(incident));
  const falseIncidents = incidents.filter((incident) => isFalseReport(incident));

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';

    return new Date(dateString).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatTimeAgo = (dateString) => {
    if (!dateString) return 'N/A';

    const now = new Date();
    const date = new Date(dateString);
    const diffMs = now - date;

    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMinutes < 1) return 'Just now';
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const renderProgress = (incident) => {
    const steps = getTimelineSteps(incident);
    const completedCount = steps.filter((step) => step.completed).length;
    const progress = (completedCount / steps.length) * 100;

    return (
      <div style={{ marginTop: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <div
            style={{
              flex: 1,
              height: '6px',
              borderRadius: '999px',
              background: '#e2ebf4',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: '100%',
                borderRadius: '999px',
                background: progress === 100 ? '#047857' : '#030304',
                transition: 'width 0.3s ease',
              }}
            />
          </div>
          <span style={{ fontSize: '0.76rem', color: '#7087a0', fontWeight: 600 }}>{completedCount}/{steps.length}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))`, gap: '6px' }}>
          {steps.map((step) => (
            <div key={step.label} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  width: '7px',
                  height: '7px',
                  borderRadius: '999px',
                  background: step.completed ? '#047857' : '#b6c9dc',
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: '0.74rem',
                  color: step.completed ? '#0f5132' : '#7e94ad',
                  fontWeight: step.completed ? 700 : 500,
                  whiteSpace: 'nowrap',
                }}
              >
                {step.label}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="app-shell" style={{ display: 'grid', placeItems: 'center' }}>
        <div className="panel" style={{ maxWidth: '420px', width: '100%', padding: '32px', textAlign: 'center' }}>
          <h3 style={{ marginBottom: '6px' }}>Loading Reports</h3>
          <p style={{ margin: 0 }}>Fetching your incident history...</p>
        </div>
      </div>
    );
  }

  const manualReports = incidents.filter((incident) => incident.structured_data?.manual_report === true);

  const filterButtons = [
    { id: 'all', label: `All Reports (${incidents.length})` },
    { id: 'active', label: `Active (${incidents.filter((incident) => isActive(incident.status)).length})` },
    { id: 'resolved', label: `Resolved (${incidents.filter((incident) => ['resolved', 'completed'].includes(incident.status)).length})` },
    { id: 'manual', label: `Manual (${manualReports.length})` },
    { id: 'true', label: `True Incidents (${trueIncidents.length})` },
    { id: 'false', label: `False Reports (${falseIncidents.length})` },
  ];

  return (
    <div className="app-shell" style={{ position: 'relative' }}>
      <div className="ambient-grid" />
      <ProfileDropdown />
      {user?.role !== 'company' && <NotificationBell />}

      <div className="page-container" style={{ position: 'relative', zIndex: 1 }}>
        <header className="panel" style={{ padding: '22px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
            <div>
              <span className="eyebrow">Reporter Portal</span>
              <h1 className="page-heading" style={{ marginTop: '11px' }}>My Reports</h1>
              <p className="page-subheading">Track incident progress, estimated resolution, and dispatch status in one place.</p>
            </div>

            <div style={{ display: 'flex', gap: '10px', alignSelf: 'center' }}>
              <button
                onClick={fetchIncidents}
                className="secondary-btn"
                disabled={loading}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  opacity: loading ? 0.6 : 1,
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
              >
                <span style={{ fontSize: '1rem' }}>🔄</span>
                {loading ? 'Refreshing...' : 'Refresh'}
              </button>
              <a href="/dashboard" className="secondary-btn">
                Back to Dashboard
              </a>
            </div>
          </div>

          <div style={{ marginTop: '18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <div className="segmented" style={{ flexWrap: 'wrap' }}>
              {filterButtons.map((button) => (
                <button
                  key={button.id}
                  type="button"
                  className={`segment-btn ${filter === button.id ? 'active' : ''}`}
                  onClick={() => setFilter(button.id)}
                >
                  {button.label}
                </button>
              ))}
            </div>

            <div style={{ minWidth: '260px', flex: '1 1 320px', maxWidth: '420px' }}>
              <input
                type="text"
                className="input-control"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search by report ID, type, status, or description"
              />
            </div>
          </div>
        </header>

        <section className="panel" style={{ padding: '18px' }}>
          <div style={{ fontSize: '0.85rem', color: '#5f738a', fontWeight: 600, marginBottom: '14px' }}>
            Showing {paginatedIncidents.length} of {filteredIncidents.length} reports
            {searchQuery.trim() ? ` matching "${searchQuery.trim()}"` : ''}
          </div>

          {filteredIncidents.length === 0 ? (
            <div className="panel-soft" style={{ padding: '38px 18px', textAlign: 'center' }}>
              <h3 style={{ marginBottom: '6px' }}>No Reports Found</h3>
              <p style={{ margin: 0 }}>
                {filter === 'all' ? 'You have not submitted any incidents yet.' : `No ${filter} reports match your filters.`}
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {paginatedIncidents.map((incident) => {
                const statusColor = getStatusColor(incident.status);
                const currentPhase = getCurrentPhaseLabel(incident);
                const latestUpdate = getLatestStatusUpdate(incident);
                const slaSignal = getSlaSignal(incident);
                const formattedType = (incident.incident_type || incident.classified_use_case || 'Incident')
                  .replaceAll('_', ' ')
                  .replace(/\b\w/g, (character) => character.toUpperCase());
                const isManualReport = incident.structured_data?.manual_report === true;

                return (
                  <article
                    key={incident.incident_id}
                    onClick={() => navigate(`/my-reports/${incident.incident_id}`)}
                    style={{
                      border: '1px solid #d7e3ee',
                      borderLeft: `4px solid ${statusColor}`,
                      borderRadius: '14px',
                      background: '#fff',
                      padding: '14px 14px 12px',
                      cursor: 'pointer',
                      transition: 'all 0.2s ease',
                    }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.transform = 'translateY(-1px)';
                      event.currentTarget.style.boxShadow = '0 16px 26px -24px rgba(15,31,51,0.66)';
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.transform = 'translateY(0)';
                      event.currentTarget.style.boxShadow = 'none';
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {isActive(incident.status) && (
                          <span
                            style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '999px',
                              background: '#b91c1c',
                              display: 'inline-block',
                              animation: 'reportPulse 1.7s ease-in-out infinite',
                            }}
                          />
                        )}
                        <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 700, fontSize: '0.82rem', color: '#37526c' }}>
                          {formatReferenceId(incident.incident_id)}
                        </span>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                        {isManualReport && (
                          <span
                            style={{
                              fontSize: '0.7rem',
                              border: '1px solid #c4b5fd',
                              background: '#ede9fe',
                              color: '#5b21b6',
                              padding: '3px 8px',
                              borderRadius: '999px',
                              fontWeight: 700,
                            }}
                          >
                            Manual Report
                          </span>
                        )}

                        {incident.outcome && (
                          <span
                            style={{
                              fontSize: '0.74rem',
                              border: '1px solid #d7e3ee',
                              background: '#f5f9fd',
                              color: '#4d647c',
                              padding: '3px 8px',
                              borderRadius: '999px',
                              fontWeight: 600,
                            }}
                          >
                            {getOutcomeLabel(incident.outcome)}
                          </span>
                        )}

                        <span
                          style={{
                            fontSize: '0.74rem',
                            color: '#fff',
                            background: statusColor,
                            borderRadius: '999px',
                            padding: '4px 10px',
                            fontWeight: 700,
                          }}
                        >
                          {getStatusLabel(incident.status)}
                        </span>
                      </div>
                    </div>

                    <h3 style={{ margin: '10px 0 4px', color: '#11263c', fontSize: '1.2rem' }}>{formattedType}</h3>

                    {/* Severity badge for manual reports */}
                    {isManualReport && incident.structured_data?.severity && (
                      <span style={{
                        display: 'inline-block',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '999px',
                        marginBottom: '6px',
                        background: incident.structured_data.severity === 'critical' ? '#fef2f2'
                          : incident.structured_data.severity === 'high' ? '#fef2f2'
                            : incident.structured_data.severity === 'medium' ? '#fffbeb'
                              : '#ecfdf5',
                        color: incident.structured_data.severity === 'critical' ? '#7f1d1d'
                          : incident.structured_data.severity === 'high' ? '#dc2626'
                            : incident.structured_data.severity === 'medium' ? '#b45309'
                              : '#047857',
                        border: `1px solid ${incident.structured_data.severity === 'critical' ? '#fca5a5'
                          : incident.structured_data.severity === 'high' ? '#fca5a5'
                            : incident.structured_data.severity === 'medium' ? '#fde68a'
                              : '#a7f3d0'
                          }`,
                      }}>
                        Severity: {incident.structured_data.severity.charAt(0).toUpperCase() + incident.structured_data.severity.slice(1)}
                      </span>
                    )}

                    <div
                      className="panel-soft"
                      style={{
                        marginTop: '10px',
                        padding: '8px 10px',
                        borderRadius: '10px',
                        display: 'grid',
                        gap: '5px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: '0.79rem', color: '#37526c', fontWeight: 700 }}>
                          Current Phase: {currentPhase}
                        </span>
                        {slaSignal && (
                          <span style={{ fontSize: '0.74rem', color: slaSignal.color, fontWeight: 700 }}>
                            {slaSignal.label}
                          </span>
                        )}
                      </div>

                      {latestUpdate && (
                        <div style={{ fontSize: '0.75rem', color: '#5f738a', fontWeight: 600 }}>
                          Latest Update: {latestUpdate.message || getStatusLabel(latestUpdate.status)} · {formatTimeAgo(latestUpdate.timestamp)}
                        </div>
                      )}
                    </div>

                    <div
                      style={{
                        marginTop: '11px',
                        display: 'flex',
                        gap: '12px',
                        flexWrap: 'wrap',
                        fontSize: '0.8rem',
                        color: '#5f738a',
                        fontWeight: 600,
                      }}
                    >
                      <span>Reported {formatTimeAgo(incident.created_at)}</span>
                      {incident.estimated_resolution_at && isActive(incident.status) && (
                        <span style={{ color: '#030304' }}>Estimated Resolution: {formatDate(incident.estimated_resolution_at)}</span>
                      )}
                      <span style={{ marginLeft: 'auto', color: '#030304' }}>View Details</span>
                    </div>

                    {renderProgress(incident)}
                  </article>
                );
              })}
            </div>
          )}

          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="secondary-btn"
                disabled={safeCurrentPage <= 1}
                style={{ opacity: safeCurrentPage <= 1 ? 0.5 : 1 }}
                onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              >
                Previous
              </button>

              <span style={{ fontSize: '0.84rem', color: '#5f738a', fontWeight: 700 }}>
                Page {safeCurrentPage} of {totalPages}
              </span>

              <button
                type="button"
                className="secondary-btn"
                disabled={safeCurrentPage >= totalPages}
                style={{ opacity: safeCurrentPage >= totalPages ? 0.5 : 1 }}
                onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
              >
                Next
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.82rem', color: '#5f738a', fontWeight: 700 }}>Rows per page</span>
              <CustomSelect
                value={pageSize}
                onChange={(v) => setPageSize(Number(v))}
                options={pageSizeOptions.map((n) => ({ value: n, label: String(n) }))}
                small
                style={{ minWidth: 72 }}
              />
            </div>
          </div>
        </section>
      </div>

      <style>{`
        @keyframes reportPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.35; }
        }
      `}</style>
    </div>
  );
};

export default MyReports;
