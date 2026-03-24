import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  getTenantConnectors,
  getSyncStatus,
  getSyncLogs,
  getTenants,
  getDeadLetterEvents,
  replayDeadLetterEvent,
  replayAllDeadLetterEvents,
  getSyncEventTrace,
  deleteConnector,
  deactivateConnector,
  activateConnector,
  backfillConnector,
} from '../services/api';
import CustomSelect from '../components/CustomSelect';
import { formatIncidentId } from '../utils/incidentIds';

const HEALTH_DOT = {
  healthy: '#047857',
  degraded: '#f59e0b',
  unhealthy: '#ef4444',
  unknown: '#94a3b8',
};

const STATUS_FILTERS = ['all', 'completed', 'failed', 'pending', 'dead_letter'];
const DIR_FILTERS = ['all', 'inbound', 'outbound'];

const ConnectorStatus = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [connectors, setConnectors] = useState([]);
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncLogs, setSyncLogs] = useState([]);
  const [deadLetterEvents, setDeadLetterEvents] = useState([]);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [replayBusy, setReplayBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [tenantLoading, setTenantLoading] = useState(true);
  const [tenantOptions, setTenantOptions] = useState([]);
  const [selectedTenantId, setSelectedTenantId] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [dirFilter, setDirFilter] = useState('all');
  const [actionBusy, setActionBusy] = useState('');
  const [syncPage, setSyncPage] = useState(0);
  const [syncTotal, setSyncTotal] = useState(0);
  const [syncPerPage, setSyncPerPage] = useState(20);
  const perPageOptions = [10, 20, 50, 100];
  const [toast, setToast] = useState(null); // { type: 'success'|'error', message, details }
  const [deleteConfirm, setDeleteConfirm] = useState(null); // { configId, displayName }

  useEffect(() => {
    let cancelled = false;

    const loadTenants = async () => {
      setTenantLoading(true);
      try {
        const isSuper = user?.role === 'super_user' || user?.role === 'admin';
        if (isSuper) {
          const data = await getTenants();
          const tenants = data.tenants || [];
          if (cancelled) return;

          setTenantOptions(tenants);
          const defaultTenant =
            (user?.tenant_id && tenants.find((t) => t.tenant_id === user.tenant_id)?.tenant_id) ||
            tenants[0]?.tenant_id ||
            '';
          setSelectedTenantId(defaultTenant);
          return;
        }

        if (user?.tenant_id) {
          if (cancelled) return;
          setTenantOptions([{ tenant_id: user.tenant_id, display_name: user.tenant_id }]);
          setSelectedTenantId(user.tenant_id);
          return;
        }

        if (!cancelled) {
          setTenantOptions([]);
          setSelectedTenantId('');
        }
      } catch {
        if (!cancelled) {
          setTenantOptions([]);
          setSelectedTenantId(user?.tenant_id || '');
        }
      } finally {
        if (!cancelled) setTenantLoading(false);
      }
    };

    loadTenants();
    return () => {
      cancelled = true;
    };
  }, [user?.role, user?.tenant_id]);

  const fetchData = useCallback(async () => {
    if (!selectedTenantId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const [connRes, statusRes, logsRes, dlqRes] = await Promise.all([
        getTenantConnectors(selectedTenantId),
        getSyncStatus(selectedTenantId),
        getSyncLogs(selectedTenantId, {
          status: statusFilter !== 'all' ? statusFilter : undefined,
          direction: dirFilter !== 'all' ? dirFilter : undefined,
          limit: syncPerPage,
          offset: syncPage * syncPerPage,
        }),
        getDeadLetterEvents(selectedTenantId, 50),
      ]);
      setConnectors(connRes.connectors || []);
      setSyncStatus(statusRes);
      setSyncLogs(logsRes.events || []);
      setSyncTotal(logsRes.total ?? 0);
      setDeadLetterEvents(dlqRes.events || []);
    } catch {
      /* fetch error handled silently */
    } finally {
      setLoading(false);
    }
  }, [selectedTenantId, statusFilter, dirFilter, syncPage, syncPerPage]);

  const showToast = useCallback((type, message, details = null) => {
    setToast({ type, message, details });
    setTimeout(() => setToast(null), 6000);
  }, []);

  const handleReplayOne = async (eventId) => {
    if (!selectedTenantId || !eventId) return;
    setReplayBusy(`one:${eventId}`);
    try {
      await replayDeadLetterEvent(selectedTenantId, eventId);
      await fetchData();
    } catch (err) {
      showToast('error', 'Replay failed', err.message || 'Unknown error');
    } finally {
      setReplayBusy('');
    }
  };

  const handleReplayAll = async () => {
    if (!selectedTenantId) return;
    setReplayBusy('all');
    try {
      await replayAllDeadLetterEvents(selectedTenantId);
      await fetchData();
    } catch (err) {
      showToast('error', 'Replay all failed', err.message || 'Unknown error');
    } finally {
      setReplayBusy('');
    }
  };

  const handleViewTrace = async (eventId) => {
    if (!selectedTenantId || !eventId) return;
    setReplayBusy(`trace:${eventId}`);
    try {
      const trace = await getSyncEventTrace(selectedTenantId, eventId);
      setSelectedTrace(trace);
    } catch (err) {
      showToast('error', 'Failed to fetch event trace', err.message || 'Unknown error');
    } finally {
      setReplayBusy('');
    }
  };

  const handleDeleteConnector = (configId, displayName) => {
    if (!selectedTenantId || !configId) return;
    setDeleteConfirm({ configId, displayName: displayName || configId });
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    const { configId } = deleteConfirm;
    setDeleteConfirm(null);
    setActionBusy(`delete:${configId}`);
    try {
      await deleteConnector(configId, selectedTenantId);
      showToast('success', 'Connector deleted successfully');
      await fetchData();
    } catch (err) {
      showToast('error', 'Delete failed', err.message || 'Unknown error');
    } finally {
      setActionBusy('');
    }
  };

  const handleToggleActive = async (connector) => {
    const configId = connector.config_id;
    setActionBusy(`toggle:${configId}`);
    try {
      if (connector.is_active) {
        await deactivateConnector(configId, selectedTenantId);
      } else {
        await activateConnector(configId, selectedTenantId);
      }
      await fetchData();
    } catch (err) {
      showToast('error', 'Toggle failed', err.message || 'Unknown error');
    } finally {
      setActionBusy('');
    }
  };

  const handleEditConnector = (connector) => {
    navigate(
      `/super/connectors/setup?tenant_id=${encodeURIComponent(selectedTenantId)}&config_id=${encodeURIComponent(connector.config_id)}`
    );
  };

  const handleSyncNow = async (connector) => {
    const configId = connector.config_id;
    setActionBusy(`sync:${configId}`);
    try {
      const result = await backfillConnector(selectedTenantId, connector.connector_type, 100);
      const imported = result.imported ?? 0;
      const skipped = result.skipped ?? 0;
      const failed = result.failed ?? 0;
      const errors = result.errors ?? [];
      const firstError = errors.length > 0 ? (typeof errors[0] === 'string' ? errors[0] : errors[0]?.error) : null;
      const toastType = failed > 0 && imported === 0 ? 'error' : failed > 0 ? 'warning' : 'success';
      const subtitle = failed > 0 && firstError
        ? `${firstError}${errors.length > 1 ? ` (+${errors.length - 1} more)` : ''}`
        : imported > 0 ? `${imported} incidents created from ${connector.display_name || connector.connector_type}` : null;
      showToast(toastType, `Sync complete — ${imported} imported, ${skipped} skipped, ${failed} failed`, subtitle);
      await fetchData();
    } catch (err) {
      showToast('error', 'Sync failed', err.message || 'Unknown error');
    } finally {
      setActionBusy('');
    }
  };

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const formatTime = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  };

  if (tenantLoading || loading) {
    return (
      <div style={S.container}>
        <div style={S.header}>
          <h1 style={S.title}>Connectors</h1>
          <p style={S.subtitle}>Loading connector data...</p>
        </div>
      </div>
    );
  }

  return (
    <div style={S.container}>
      {toast && (
        <div style={{
          position: 'fixed', top: '24px', right: '24px', zIndex: 100,
          display: 'flex', alignItems: 'flex-start', gap: '12px',
          minWidth: '340px', maxWidth: '480px',
          padding: '14px 18px', borderRadius: '12px',
          background: toast.type === 'success' ? '#f0fdf4' : toast.type === 'warning' ? '#fffbeb' : '#fef2f2',
          border: `1px solid ${toast.type === 'success' ? '#bbf7d0' : toast.type === 'warning' ? '#fde68a' : '#fecaca'}`,
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          animation: 'slideIn 0.3s ease-out',
        }}>
          <span style={{
            width: '28px', height: '28px', borderRadius: '50%', flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px',
            background: toast.type === 'success' ? '#047857' : toast.type === 'warning' ? '#d97706' : '#b91c1c', color: '#fff',
          }}>
            {toast.type === 'success' ? '\u2713' : '!'}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontWeight: 700, fontSize: '0.85rem',
              color: toast.type === 'success' ? '#047857' : toast.type === 'warning' ? '#92400e' : '#b91c1c',
            }}>
              {toast.message}
            </div>
            {toast.details && (
              <div style={{ fontSize: '0.78rem', color: '#6b7280', marginTop: '3px' }}>
                {toast.details}
              </div>
            )}
          </div>
          <button onClick={() => setToast(null)} style={{
            border: 'none', background: 'transparent', cursor: 'pointer',
            color: '#9ca3af', fontSize: '16px', padding: '0 0 0 4px', lineHeight: 1,
          }}>&times;</button>
        </div>
      )}

      <div style={S.header}>
        <div>
          <h1 style={S.title}>Connectors</h1>
          <p style={S.subtitle}>
            Monitor external system integrations and sync activity
            {selectedTenantId ? ` for ${selectedTenantId}` : ''}
          </p>
        </div>
        <div style={S.headerActions}>
          <CustomSelect
            value={selectedTenantId}
            onChange={setSelectedTenantId}
            options={tenantOptions.map((t) => ({
              value: t.tenant_id,
              label: t.display_name ? `${t.display_name} (${t.tenant_id})` : t.tenant_id,
            }))}
            placeholder={tenantOptions.length === 0 ? 'No tenant available' : 'Select tenant'}
            disabled={!tenantOptions.length}
            style={{ minWidth: 260 }}
          />
          <button
            onClick={() => navigate(`/super/connectors/setup?tenant_id=${encodeURIComponent(selectedTenantId || '')}`)}
            style={S.setupButton}
            disabled={!selectedTenantId}
          >
            Setup Connector
          </button>
        </div>
      </div>

      {!selectedTenantId && (
        <div style={S.card}>
          <p style={{ color: '#6b7280', margin: 0 }}>Select a tenant to view connector data.</p>
        </div>
      )}

      <div style={S.card}>
        <h2 style={S.cardTitle}>Active Connectors</h2>
        {connectors.length === 0 ? (
          <p style={{ color: '#6b7280' }}>No connectors configured for this tenant.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={S.table}>
              <thead>
                <tr>
                  <th style={S.th}>Name</th>
                  <th style={S.th}>Type</th>
                  <th style={S.th}>Health</th>
                  <th style={S.th}>Instance</th>
                  <th style={S.th}>Last Sync</th>
                  <th style={S.th}>Status</th>
                  <th style={S.th}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {connectors.map((c) => (
                  <tr key={c.config_id} style={S.tr}>
                    <td style={S.td}>
                      <span style={{ fontWeight: 600, color: '#111827' }}>{c.display_name}</span>
                    </td>
                    <td style={S.td}>{c.connector_type}</td>
                    <td style={S.td}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ width: 8, height: 8, borderRadius: '50%', background: HEALTH_DOT[c.health_status] || HEALTH_DOT.unknown }} />
                        {c.health_status || 'unknown'}
                      </span>
                    </td>
                    <td style={{ ...S.td, fontSize: '0.82rem', color: '#6b7280' }}>
                      {c.instance_url || '-'}
                    </td>
                    <td style={S.td}>{formatTime(c.last_successful_sync_at)}</td>
                    <td style={S.td}>
                      <span style={{
                        display: 'inline-flex', alignItems: 'center', gap: '5px',
                        padding: '3px 10px', borderRadius: '999px', fontSize: '0.76rem', fontWeight: 700,
                        background: c.is_active ? '#f0fdf4' : '#f1f5f9',
                        color: c.is_active ? '#047857' : '#6b7280',
                      }}>
                        <span style={{ width: 7, height: 7, borderRadius: '50%', background: c.is_active ? '#047857' : '#94a3b8' }} />
                        {c.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td style={S.td}>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        {c.is_active && (
                          <button type="button" onClick={() => handleSyncNow(c)}
                            disabled={actionBusy === `sync:${c.config_id}`}
                            style={{ border: '1px solid #bfdbfe', borderRadius: '7px', background: '#eff6ff', color: '#1d4ed8', fontSize: '0.74rem', fontWeight: 700, padding: '5px 8px', cursor: 'pointer' }}>
                            {actionBusy === `sync:${c.config_id}` ? 'Syncing...' : 'Sync Now'}
                          </button>
                        )}
                        <button type="button" onClick={() => handleEditConnector(c)}
                          style={{ border: '1px solid #d1d5db', borderRadius: '7px', background: '#fff', color: '#374151', fontSize: '0.74rem', fontWeight: 700, padding: '5px 8px', cursor: 'pointer' }}>
                          Edit
                        </button>
                        <button type="button" onClick={() => handleToggleActive(c)}
                          disabled={actionBusy === `toggle:${c.config_id}`}
                          style={{
                            border: '1px solid', borderRadius: '7px', fontSize: '0.74rem', fontWeight: 700, padding: '5px 8px', cursor: 'pointer',
                            background: c.is_active ? '#fef2f2' : '#f0fdf4', color: c.is_active ? '#b91c1c' : '#047857',
                            borderColor: c.is_active ? '#fecaca' : '#bbf7d0',
                          }}>
                          {actionBusy === `toggle:${c.config_id}` ? '...' : c.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button type="button" onClick={() => handleDeleteConnector(c.config_id, c.display_name)}
                          disabled={actionBusy === `delete:${c.config_id}`}
                          style={{ border: '1px solid #fecaca', borderRadius: '7px', background: '#fef2f2', color: '#b91c1c', fontSize: '0.74rem', fontWeight: 700, padding: '5px 8px', cursor: 'pointer' }}>
                          {actionBusy === `delete:${c.config_id}` ? '...' : 'Delete'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {syncStatus && (
        <div style={S.card}>
          <h2 style={S.cardTitle}>Sync Overview</h2>
          <div style={S.kpiRow}>
            <KPI label="Total Events" value={syncStatus.total_events} color="#2563eb" />
            <KPI label="Completed" value={syncStatus.completed} color="#047857" />
            <KPI label="Pending" value={syncStatus.pending + (syncStatus.processing || 0)} color="#f59e0b" />
            <KPI label="Failed" value={syncStatus.failed} color="#ef4444" />
            <KPI label="Dead Letter" value={syncStatus.dead_letter} color="#7c3aed" />
          </div>
          {syncStatus.last_event_at && (
            <p style={{ margin: '12px 0 0', fontSize: '0.82rem', color: '#6b7280' }}>
              Last event: {syncStatus.last_event_type} at {formatTime(syncStatus.last_event_at)}
            </p>
          )}
        </div>
      )}

      <div style={S.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginBottom: '14px' }}>
          <h2 style={{ ...S.cardTitle, marginBottom: 0 }}>Sync Event Feed</h2>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <FilterGroup label="Status" options={STATUS_FILTERS} value={statusFilter} onChange={(v) => { setStatusFilter(v); setSyncPage(0); }} />
            <FilterGroup label="Direction" options={DIR_FILTERS} value={dirFilter} onChange={(v) => { setDirFilter(v); setSyncPage(0); }} />
          </div>
        </div>

        {syncLogs.length === 0 ? (
          <p style={{ color: '#6b7280', padding: '20px 0' }}>No sync events match the current filters.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={S.table}>
              <thead>
                <tr>
                  <th style={S.th}>Event</th>
                  <th style={S.th}>Direction</th>
                  <th style={S.th}>Status</th>
                  <th style={S.th}>Incident</th>
                  <th style={S.th}>External ID</th>
                  <th style={S.th}>Time</th>
                  <th style={S.th}>Error</th>
                </tr>
              </thead>
              <tbody>
                {syncLogs.map((evt) => (
                  <tr key={evt.event_id} style={S.tr}>
                    <td style={S.td}><span style={{ fontWeight: 600, fontSize: '0.82rem' }}>{evt.event_type}</span></td>
                    <td style={S.td}>
                      <span style={{
                        fontSize: '0.74rem', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
                        background: evt.direction === 'outbound' ? '#eff6ff' : '#faf5ff',
                        color: evt.direction === 'outbound' ? '#1d4ed8' : '#7c3aed',
                      }}>
                        {evt.direction}
                      </span>
                    </td>
                    <td style={S.td}><EventStatusBadge status={evt.status} /></td>
                    <td style={{ ...S.td, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.78rem' }}>
                      {evt.incident_id ? formatIncidentId(evt.incident_id) : '-'}
                    </td>
                    <td style={{ ...S.td, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.78rem' }}>
                      {evt.external_id || '-'}
                    </td>
                    <td style={S.td}>{formatTime(evt.created_at)}</td>
                    <td style={{ ...S.td, fontSize: '0.78rem', color: '#ef4444', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {evt.error_message || ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {syncLogs.length > 0 && (
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            paddingTop: '12px', borderTop: '1px solid #f3f4f6', marginTop: '8px',
            flexWrap: 'wrap', gap: '8px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '0.78rem', color: '#6b7280' }}>
                Showing {syncPage * syncPerPage + 1}–{Math.min((syncPage + 1) * syncPerPage, syncTotal)} of {syncTotal}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                <span style={{ fontSize: '0.76rem', color: '#6b7280', fontWeight: 600 }}>Rows:</span>
                <CustomSelect
                  value={syncPerPage}
                  onChange={(v) => { setSyncPerPage(Number(v)); setSyncPage(0); }}
                  options={perPageOptions.map((n) => ({ value: n, label: String(n) }))}
                  small
                  style={{ minWidth: 64 }}
                />
              </div>
            </div>
            {syncTotal > syncPerPage && (
              <div style={{ display: 'flex', gap: '6px' }}>
                <button
                  onClick={() => setSyncPage((p) => Math.max(0, p - 1))}
                  disabled={syncPage === 0}
                  style={{
                    ...S.paginationBtn,
                    opacity: syncPage === 0 ? 0.4 : 1,
                    cursor: syncPage === 0 ? 'default' : 'pointer',
                  }}
                >
                  Previous
                </button>
                <button
                  onClick={() => setSyncPage((p) => p + 1)}
                  disabled={(syncPage + 1) * syncPerPage >= syncTotal}
                  style={{
                    ...S.paginationBtn,
                    opacity: (syncPage + 1) * syncPerPage >= syncTotal ? 0.4 : 1,
                    cursor: (syncPage + 1) * syncPerPage >= syncTotal ? 'default' : 'pointer',
                  }}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div style={S.card}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', gap: '10px', flexWrap: 'wrap' }}>
          <h2 style={{ ...S.cardTitle, marginBottom: 0 }}>Dead Letter Queue</h2>
          <button
            type="button"
            onClick={handleReplayAll}
            disabled={replayBusy === 'all' || deadLetterEvents.length === 0}
            style={{
              border: 'none',
              borderRadius: '8px',
              padding: '8px 12px',
              background: replayBusy === 'all' ? '#cbd5e1' : '#7c3aed',
              color: '#fff',
              fontSize: '0.78rem',
              fontWeight: 700,
              cursor: replayBusy === 'all' ? 'not-allowed' : 'pointer',
            }}
          >
            {replayBusy === 'all' ? 'Replaying...' : 'Replay All'}
          </button>
        </div>
        {deadLetterEvents.length === 0 ? (
          <p style={{ color: '#6b7280', margin: 0 }}>No dead-letter events for this tenant.</p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={S.table}>
              <thead>
                <tr>
                  <th style={S.th}>Event</th>
                  <th style={S.th}>Incident</th>
                  <th style={S.th}>Error</th>
                  <th style={S.th}>Retries</th>
                  <th style={S.th}>Created</th>
                  <th style={S.th}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {deadLetterEvents.map((evt) => (
                  <tr key={evt.event_id} style={S.tr}>
                    <td style={S.td}>{evt.event_type}</td>
                    <td style={{ ...S.td, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.78rem' }}>
                      {evt.incident_id ? formatIncidentId(evt.incident_id) : '-'}
                    </td>
                    <td style={{ ...S.td, maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#b91c1c' }}>
                      {evt.error_message || '-'}
                    </td>
                    <td style={S.td}>{evt.retry_count || 0}</td>
                    <td style={S.td}>{formatTime(evt.created_at)}</td>
                    <td style={S.td}>
                      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          onClick={() => handleReplayOne(evt.event_id)}
                          disabled={replayBusy === `one:${evt.event_id}`}
                          style={{
                            border: '1px solid #ddd6fe',
                            borderRadius: '7px',
                            background: '#f5f3ff',
                            color: '#6d28d9',
                            fontSize: '0.74rem',
                            fontWeight: 700,
                            padding: '5px 8px',
                            cursor: 'pointer',
                          }}
                        >
                          {replayBusy === `one:${evt.event_id}` ? 'Replaying...' : 'Replay'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleViewTrace(evt.event_id)}
                          disabled={replayBusy === `trace:${evt.event_id}`}
                          style={{
                            border: '1px solid #d1d5db',
                            borderRadius: '7px',
                            background: '#fff',
                            color: '#374151',
                            fontSize: '0.74rem',
                            fontWeight: 700,
                            padding: '5px 8px',
                            cursor: 'pointer',
                          }}
                        >
                          Trace
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {deleteConfirm && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 60, padding: '16px',
        }}>
          <div style={{
            width: 'min(420px, 92vw)', background: '#fff', borderRadius: '16px',
            boxShadow: '0 20px 45px rgba(15, 23, 42, 0.25)', padding: '28px',
            animation: 'slideIn 0.2s ease-out',
          }}>
            <div style={{
              width: '48px', height: '48px', borderRadius: '50%', margin: '0 auto 16px',
              background: '#fef2f2', display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
            </div>
            <h3 style={{ margin: '0 0 8px', fontSize: '1.1rem', fontWeight: 700, color: '#111827', textAlign: 'center' }}>
              Delete Connector
            </h3>
            <p style={{ margin: '0 0 6px', fontSize: '0.88rem', color: '#4b5563', textAlign: 'center', lineHeight: 1.5 }}>
              Are you sure you want to delete <strong>{deleteConfirm.displayName}</strong>?
            </p>
            <p style={{ margin: '0 0 24px', fontSize: '0.8rem', color: '#9ca3af', textAlign: 'center' }}>
              This will permanently remove the connector and all its stored credentials. This action cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => setDeleteConfirm(null)}
                style={{
                  flex: 1, padding: '10px 16px', borderRadius: '10px',
                  border: '1px solid #d1d5db', background: '#fff', color: '#374151',
                  fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                style={{
                  flex: 1, padding: '10px 16px', borderRadius: '10px',
                  border: 'none', background: '#dc2626', color: '#fff',
                  fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer',
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedTrace && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(15, 23, 42, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 50,
          padding: '16px',
        }}>
          <div style={{
            width: 'min(760px, 96vw)',
            maxHeight: '84vh',
            overflow: 'auto',
            background: '#fff',
            borderRadius: '12px',
            boxShadow: '0 20px 45px rgba(15, 23, 42, 0.25)',
            padding: '16px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', color: '#111827' }}>Event Trace</h3>
              <button
                type="button"
                onClick={() => setSelectedTrace(null)}
                style={{ border: 'none', background: 'transparent', fontSize: '1rem', cursor: 'pointer', color: '#6b7280' }}
              >
                Close
              </button>
            </div>
            <pre style={{
              margin: 0,
              padding: '12px',
              borderRadius: '8px',
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              fontSize: '0.74rem',
              lineHeight: 1.55,
              color: '#334155',
              overflowX: 'auto',
            }}>
              {JSON.stringify(selectedTrace, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};

function KPI({ label, value, color }) {
  return (
    <div style={{
      flex: '1 1 120px', textAlign: 'center', padding: '14px 10px',
      background: '#f9fafb', borderRadius: '10px', border: '1px solid #e5e7eb',
    }}>
      <div style={{ fontSize: '1.8rem', fontWeight: 700, color }}>{value ?? 0}</div>
      <div style={{ fontSize: '0.78rem', color: '#6b7280', marginTop: '4px' }}>{label}</div>
    </div>
  );
}

function FilterGroup({ label, options, value, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <span style={{ fontSize: '0.76rem', color: '#6b7280', fontWeight: 600, marginRight: '4px' }}>{label}:</span>
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          style={{
            padding: '4px 10px', fontSize: '0.74rem', fontWeight: 600,
            borderRadius: '999px', border: '1px solid', cursor: 'pointer', transition: 'all 0.15s',
            background: value === opt ? '#030304' : '#ffffff',
            color: value === opt ? '#ffffff' : '#4d6178',
            borderColor: value === opt ? '#030304' : '#d7e3ee',
          }}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function EventStatusBadge({ status }) {
  const cfg = {
    completed: { bg: '#f0fdf4', color: '#047857', dot: '#047857' },
    pending: { bg: '#fffbeb', color: '#b45309', dot: '#f59e0b' },
    processing: { bg: '#eff6ff', color: '#1d4ed8', dot: '#3b82f6' },
    failed: { bg: '#fef2f2', color: '#b91c1c', dot: '#ef4444' },
    dead_letter: { bg: '#faf5ff', color: '#7c3aed', dot: '#a78bfa' },
  }[status] || { bg: '#f1f5f9', color: '#4d6178', dot: '#94a3b8' };

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 9px', borderRadius: '999px', fontSize: '0.74rem', fontWeight: 700,
      background: cfg.bg, color: cfg.color,
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: cfg.dot }} />
      {status}
    </span>
  );
}

const S = {
  container: {
    minHeight: '100vh',
    backgroundColor: '#f3f4f6',
    padding: '2rem 2.5rem',
  },
  header: {
    marginBottom: '1.5rem',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: '0.75rem',
    flexWrap: 'wrap',
  },
  headerActions: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
  },
  setupButton: {
    border: 'none',
    borderRadius: '0.5rem',
    padding: '0.5rem 0.9rem',
    background: '#8DE971',
    color: '#030304',
    fontWeight: 700,
    fontSize: '0.8rem',
    cursor: 'pointer',
  },
  title: {
    fontSize: '2rem',
    fontWeight: 'bold',
    color: '#111827',
    marginBottom: '0.5rem',
  },
  subtitle: {
    color: '#6b7280',
    margin: 0,
  },
  card: {
    backgroundColor: 'white',
    borderRadius: '0.75rem',
    padding: '1.5rem',
    boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1)',
    marginBottom: '1.25rem',
  },
  cardTitle: {
    fontSize: '1.1rem',
    fontWeight: 700,
    color: '#111827',
    marginTop: 0,
    marginBottom: '14px',
  },
  kpiRow: {
    display: 'flex',
    gap: '12px',
    flexWrap: 'wrap',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: '0.85rem',
  },
  th: {
    textAlign: 'left',
    padding: '10px 12px',
    borderBottom: '2px solid #e5e7eb',
    color: '#6b7280',
    fontWeight: 600,
    fontSize: '0.78rem',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '10px 12px',
    borderBottom: '1px solid #f3f4f6',
    color: '#374151',
  },
  tr: {
    transition: 'background 0.1s',
  },
  paginationBtn: {
    border: '1px solid #d1d5db',
    borderRadius: '7px',
    background: '#fff',
    color: '#374151',
    fontSize: '0.76rem',
    fontWeight: 600,
    padding: '5px 12px',
  },
};

export default ConnectorStatus;
