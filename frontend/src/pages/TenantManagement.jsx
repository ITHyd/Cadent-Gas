import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatUseCase } from '../utils/formatters';
import {
  getTenants, getSuperTenantDetail, getTenantConnectors,
  getAdminGroups, createAdminGroup, updateAdminGroup, deleteAdminGroup, assignUserToGroup,
  deleteTenant,
} from '../services/api';
import CustomSelect from '../components/CustomSelect';

const TenantManagement = () => {
  const navigate = useNavigate();
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedTenant, setExpandedTenant] = useState(null);
  const [tenantDetail, setTenantDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeDetailTab, setActiveDetailTab] = useState('users');
  const [tenantConnectors, setTenantConnectors] = useState({});  // tenant_id -> connectors list
  const [adminGroups, setAdminGroups] = useState([]);
  const [groupBusy, setGroupBusy] = useState('');
  const [newGroup, setNewGroup] = useState({ display_name: '', connector_scope: [], description: '' });
  const [showGroupForm, setShowGroupForm] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null); // group_id being edited
  const [assignBusy, setAssignBusy] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);

  useEffect(() => { loadTenants(); }, []);

  const loadTenants = async () => {
    try {
      const data = await getTenants();
      const tenantList = data.tenants || [];
      setTenants(tenantList);

      // Fetch connectors for each tenant in parallel
      const connMap = {};
      await Promise.allSettled(
        tenantList.map(async (t) => {
          try {
            const cData = await getTenantConnectors(t.tenant_id);
            connMap[t.tenant_id] = cData.connectors || [];
          } catch {
            connMap[t.tenant_id] = [];
          }
        })
      );
      setTenantConnectors(connMap);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTenant = async (tenantId) => {
    try {
      await deleteTenant(tenantId);
      if (expandedTenant === tenantId) {
        setExpandedTenant(null);
        setTenantDetail(null);
      }
      setConfirmDelete(null);
      await loadTenants();
    } catch {
      setConfirmDelete(null);
    }
  };

  const handleExpand = async (tenantId) => {
    if (expandedTenant === tenantId) {
      setExpandedTenant(null);
      setTenantDetail(null);
      return;
    }
    setExpandedTenant(tenantId);
    setActiveDetailTab('users');
    setDetailLoading(true);
    try {
      const [data, cData, gData] = await Promise.all([
        getSuperTenantDetail(tenantId),
        getTenantConnectors(tenantId).catch(() => ({ connectors: [] })),
        getAdminGroups(tenantId).catch(() => ({ admin_groups: [] })),
      ]);
      setTenantDetail({ ...data, connectors: cData.connectors || [] });
      setAdminGroups(gData.admin_groups || []);
    } catch {
    } finally {
      setDetailLoading(false);
    }
  };

  const formatDate = (d) => {
    if (!d) return '—';
    return new Date(d).toLocaleDateString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  const roleLabel = (r) => ({
    user: 'Users', agent: 'Agents', company: 'Admins', super_user: 'Super Users', admin: 'Admins',
  }[r] || r);

  const roleColor = (r) => ({
    user: '#3b82f6', agent: '#8b5cf6', company: '#f59e0b', super_user: '#ef4444', admin: '#ef4444',
  }[r] || '#6b7280');

  const statusDot = (s) => (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
      padding: '0.2rem 0.7rem', borderRadius: '999px', fontSize: '0.7rem', fontWeight: '700',
      background: s === 'active' ? '#d1fae5' : '#fee2e2',
      color: s === 'active' ? '#065f46' : '#991b1b',
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: s === 'active' ? '#10b981' : '#ef4444',
      }} />
      {s === 'active' ? 'Active' : 'Inactive'}
    </span>
  );

  const connectorTypeStyle = (type) => {
    const styles = {
      servicenow: { bg: '#dbeafe', color: '#1d4ed8', label: 'ServiceNow' },
      sap: { bg: '#fef3c7', color: '#92400e', label: 'SAP' },
      jira: { bg: '#ede9fe', color: '#6d28d9', label: 'Jira' },
      aws: { bg: '#fce7f3', color: '#9d174d', label: 'AWS' },
    };
    return styles[type] || { bg: '#f3f4f6', color: '#6b7280', label: type };
  };

  const healthColor = (h) => ({
    healthy: '#10b981', degraded: '#f59e0b', down: '#ef4444', unknown: '#94a3b8',
  }[h] || '#94a3b8');

  // Compute visible user count for a tenant (excludes auto-provisioned users from inactive connectors)
  const getVisibleUserCount = (t) => {
    const total = t.users?.total || 0;
    const autoProv = t.users?.auto_provisioned_by_source || {};
    const activeTypes = new Set(
      (tenantConnectors[t.tenant_id] || []).filter((c) => c.is_active).map((c) => c.connector_type),
    );
    let hidden = 0;
    for (const [source, count] of Object.entries(autoProv)) {
      if (!activeTypes.has(source)) hidden += count;
    }
    return total - hidden;
  };

  // ── Totals across all tenants ──
  const totals = tenants.reduce((acc, t) => ({
    tenants: acc.tenants + 1,
    users: acc.users + getVisibleUserCount(t),
    incidents: acc.incidents + (t.incidents?.total || 0),
    workflows: acc.workflows + (t.workflows || 0),
  }), { tenants: 0, users: 0, incidents: 0, workflows: 0 });

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: '#f3f4f6', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ width: 48, height: 48, border: '4px solid #e5e7eb', borderTopColor: '#667eea', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 1rem' }} />
          <span style={{ color: '#64748b', fontWeight: 600 }}>Loading tenants...</span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f3f4f6', padding: '2rem 2.5rem' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      {/* Header */}
      <div style={{ maxWidth: 1200, margin: '0 auto', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
          <h1 style={{
            fontSize: '2rem', fontWeight: 800, margin: 0,
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          }}>
            Tenant Management
          </h1>
          <button
            onClick={() => navigate('/super/tenants/onboard')}
            style={{
              padding: '0.6rem 1rem',
              borderRadius: '0.625rem',
              border: 'none',
              background: '#8DE971',
              color: '#030304',
              fontSize: '0.82rem',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 8px 20px -14px rgba(3,3,4,0.9)',
            }}
          >
            Create Tenant
          </button>
        </div>
        <p style={{ color: '#64748b', fontSize: '1rem', margin: 0 }}>
          View and manage platform tenants, users, incidents, workflows, and field agents.
        </p>
      </div>

      {/* Stats */}
      <div style={{ maxWidth: 1200, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {[
          { label: 'Total Tenants', value: totals.tenants, color: '#667eea', icon: '🏢' },
          { label: 'Total Users', value: totals.users, color: '#3b82f6', icon: '👥' },
          { label: 'Total Incidents', value: totals.incidents, color: '#f59e0b', icon: '📋' },
          { label: 'Total Workflows', value: totals.workflows, color: '#10b981', icon: '⚙️' },
        ].map((s, i) => (
          <div key={i} style={{
            background: 'white', borderRadius: '1rem', padding: '1.5rem',
            boxShadow: '0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)',
            display: 'flex', alignItems: 'center', gap: '1rem',
          }}>
            <div style={{
              width: 48, height: 48, borderRadius: '0.75rem',
              background: s.color + '12', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '1.5rem',
            }}>{s.icon}</div>
            <div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, color: '#0f172a' }}>{s.value}</div>
              <div style={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 600 }}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Tenant Table */}
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <div style={{
          background: 'white', borderRadius: '1rem', overflow: 'hidden',
          boxShadow: '0 1px 3px rgba(0,0,0,0.06), 0 4px 16px rgba(0,0,0,0.04)',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f8fafc' }}>
                {['Tenant', 'Status', 'Users', 'Incidents', 'Workflows', 'Connectors', 'Created', 'Actions', ''].map((h, i) => (
                  <th key={i} style={{
                    padding: '1rem 1.25rem', textAlign: 'left', fontSize: '0.75rem',
                    fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                    letterSpacing: '0.06em', borderBottom: '1px solid #e2e8f0',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <React.Fragment key={t.tenant_id}>
                  <tr
                    style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                    onClick={() => handleExpand(t.tenant_id)}
                    onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9' }}>
                      <div style={{ fontWeight: 700, color: '#0f172a', fontSize: '0.9rem' }}>{t.tenant_id}</div>
                      <div style={{ display: 'flex', gap: '0.375rem', marginTop: '0.35rem', flexWrap: 'wrap' }}>
                        {Object.entries(t.users?.by_role || {}).map(([role, count]) => (
                          <span key={role} style={{
                            fontSize: '0.625rem', fontWeight: 600, padding: '0.1rem 0.4rem',
                            borderRadius: '0.25rem', background: roleColor(role) + '15',
                            color: roleColor(role),
                          }}>
                            {count} {roleLabel(role)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9' }}>
                      {statusDot(t.status)}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: '#0f172a' }}>
                      {getVisibleUserCount(t)}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9' }}>
                      <div style={{ fontWeight: 700, color: '#0f172a' }}>{t.incidents?.total || 0}</div>
                      {(t.incidents?.pending || 0) > 0 && (
                        <span style={{ fontSize: '0.7rem', color: '#ef4444', fontWeight: 600 }}>
                          {t.incidents.pending} pending
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: '#0f172a' }}>
                      {t.workflows || 0}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9' }}>
                      {(tenantConnectors[t.tenant_id] || []).length > 0 ? (
                        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                          {(tenantConnectors[t.tenant_id] || []).map((c, ci) => {
                            const s = connectorTypeStyle(c.connector_type);
                            return (
                              <span key={ci} style={{
                                display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                                fontSize: '0.65rem', fontWeight: 700, padding: '0.15rem 0.5rem',
                                borderRadius: '0.3rem', background: s.bg, color: s.color,
                              }}>
                                <span style={{
                                  width: 6, height: 6, borderRadius: '50%',
                                  background: healthColor(c.health_status || 'unknown'),
                                  flexShrink: 0,
                                }} />
                                {s.label}
                                {c.is_active && <span style={{ fontSize: '0.55rem', opacity: 0.7 }}>(live)</span>}
                              </span>
                            );
                          })}
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.75rem', color: '#cbd5e1', fontStyle: 'italic' }}>None</span>
                      )}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9', fontSize: '0.8rem', color: '#64748b' }}>
                      {formatDate(t.created_at)}
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9' }}>
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }} onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/super/tenants/${t.tenant_id}/mappings`)}
                          style={{
                            padding: '0.3rem 0.65rem', borderRadius: '0.375rem', fontSize: '0.7rem',
                            fontWeight: 600, border: '1px solid #e9d5ff', background: '#faf5ff',
                            color: '#6d28d9', cursor: 'pointer', whiteSpace: 'nowrap',
                          }}
                        >
                          Edit Mapping
                        </button>
                        {confirmDelete === t.tenant_id ? (
                          <>
                            <span style={{ fontSize: '0.65rem', fontWeight: 700, color: '#991b1b' }}>Sure?</span>
                            <button
                              onClick={() => handleDeleteTenant(t.tenant_id)}
                              style={{
                                padding: '0.3rem 0.55rem', borderRadius: '0.375rem', fontSize: '0.65rem',
                                fontWeight: 700, border: '1px solid #fca5a5', background: '#dc2626',
                                color: '#fff', cursor: 'pointer', whiteSpace: 'nowrap',
                              }}
                            >
                              Yes
                            </button>
                            <button
                              onClick={() => setConfirmDelete(null)}
                              style={{
                                padding: '0.3rem 0.55rem', borderRadius: '0.375rem', fontSize: '0.65rem',
                                fontWeight: 600, border: '1px solid #e2e8f0', background: '#f8fafc',
                                color: '#64748b', cursor: 'pointer', whiteSpace: 'nowrap',
                              }}
                            >
                              No
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => setConfirmDelete(t.tenant_id)}
                            style={{
                              padding: '0.3rem 0.65rem', borderRadius: '0.375rem', fontSize: '0.7rem',
                              fontWeight: 600, border: '1px solid #fecaca', background: '#fef2f2',
                              color: '#dc2626', cursor: 'pointer', whiteSpace: 'nowrap',
                            }}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #f1f5f9', textAlign: 'right' }}>
                      <span style={{
                        display: 'inline-block', transform: expandedTenant === t.tenant_id ? 'rotate(180deg)' : 'rotate(0)',
                        transition: 'transform 0.2s', fontSize: '0.8rem', color: '#94a3b8',
                      }}>▼</span>
                    </td>
                  </tr>

                  {/* Expanded detail panel */}
                  {expandedTenant === t.tenant_id && (
                    <tr>
                      <td colSpan="9" style={{ padding: 0, borderBottom: '1px solid #e2e8f0' }}>
                        {detailLoading ? (
                          <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>Loading details...</div>
                        ) : tenantDetail ? (
                          <div style={{ background: '#f8fafc', padding: '1.5rem' }}>
                            {/* Detail tabs */}
                            {(() => {
                              const activeTypes = new Set(
                                (tenantDetail.connectors || []).filter((c) => c.is_active).map((c) => c.connector_type),
                              );
                              const visibleUsers = (tenantDetail.users || []).filter(
                                (u) => !u.auto_provisioned || !u.provisioned_from || activeTypes.has(u.provisioned_from),
                              );
                              return (<>
                            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', borderBottom: '2px solid #e2e8f0', paddingBottom: 0 }}>
                              {[
                                { key: 'users', label: `Users (${visibleUsers.length})`, icon: '👥' },
                                { key: 'incidents', label: `Incidents (${tenantDetail.incidents?.total || 0})`, icon: '📋' },
                                { key: 'workflows', label: `Workflows (${tenantDetail.workflows?.length || 0})`, icon: '⚙️' },
                                { key: 'connectors', label: `Connectors (${tenantDetail.connectors?.length || 0})`, icon: '🔗' },
                                { key: 'agents', label: `Agents (${tenantDetail.agents?.length || 0})`, icon: '🔧' },
                                { key: 'admin_groups', label: `Admin Groups (${adminGroups.length})`, icon: '🛡️' },
                              ].map((tab) => (
                                <button key={tab.key}
                                  onClick={(e) => { e.stopPropagation(); setActiveDetailTab(tab.key); }}
                                  style={{
                                    padding: '0.625rem 1rem', border: 'none', background: 'transparent',
                                    cursor: 'pointer', fontSize: '0.8rem', fontWeight: 600,
                                    color: activeDetailTab === tab.key ? '#667eea' : '#64748b',
                                    borderBottom: `2px solid ${activeDetailTab === tab.key ? '#667eea' : 'transparent'}`,
                                    marginBottom: '-2px', transition: 'all 0.15s',
                                  }}
                                >
                                  {tab.label}
                                </button>
                              ))}
                            </div>

                            {/* Users tab */}
                            {activeDetailTab === 'users' && (
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
                                {visibleUsers.map((u) => (
                                  <div key={u.user_id} style={{
                                    background: 'white', borderRadius: '0.75rem', padding: '1rem',
                                    border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '0.75rem',
                                  }}>
                                    <div style={{
                                      width: 40, height: 40, borderRadius: '50%',
                                      background: roleColor(u.role) + '20', display: 'flex',
                                      alignItems: 'center', justifyContent: 'center',
                                      fontSize: '0.85rem', fontWeight: 700, color: roleColor(u.role), flexShrink: 0,
                                    }}>
                                      {u.full_name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || '??'}
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#0f172a' }}>{u.full_name}</div>
                                      <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>{u.phone}</div>
                                    </div>
                                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                                      <div style={{ display: 'flex', gap: '0.25rem', justifyContent: 'flex-end', alignItems: 'center' }}>
                                        {u.auto_provisioned && (
                                          <span style={{
                                            fontSize: '0.55rem', fontWeight: 700, padding: '0.1rem 0.35rem',
                                            borderRadius: '0.2rem', background: '#dbeafe', color: '#1d4ed8',
                                            letterSpacing: '0.03em',
                                          }}>
                                            {(u.provisioned_from || 'synced').toUpperCase()}
                                          </span>
                                        )}
                                        <span style={{
                                          fontSize: '0.625rem', fontWeight: 700, padding: '0.15rem 0.5rem',
                                          borderRadius: '0.25rem', background: roleColor(u.role) + '15',
                                          color: roleColor(u.role),
                                        }}>
                                          {u.role}
                                        </span>
                                      </div>
                                      <div style={{ fontSize: '0.6rem', color: u.is_active ? '#10b981' : '#ef4444', marginTop: '0.25rem', fontWeight: 600 }}>
                                        {u.is_active ? 'Active' : 'Inactive'}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}

                            {/* Incidents tab */}
                            {activeDetailTab === 'incidents' && (
                              <div>
                                {/* Summary chips */}
                                <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
                                  {[
                                    { label: 'Total', value: tenantDetail.incidents?.total || 0, color: '#3b82f6' },
                                    { label: 'Pending', value: tenantDetail.incidents?.pending || 0, color: '#ef4444' },
                                    { label: 'Dispatched', value: tenantDetail.incidents?.dispatched || 0, color: '#8b5cf6' },
                                    { label: 'Resolved', value: tenantDetail.incidents?.resolved || 0, color: '#10b981' },
                                  ].map((c, i) => (
                                    <div key={i} style={{
                                      padding: '0.5rem 1rem', borderRadius: '0.5rem',
                                      background: c.color + '10', border: `1px solid ${c.color}25`,
                                      display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    }}>
                                      <span style={{ fontSize: '1.1rem', fontWeight: 800, color: c.color }}>{c.value}</span>
                                      <span style={{ fontSize: '0.75rem', fontWeight: 600, color: c.color }}>{c.label}</span>
                                    </div>
                                  ))}
                                </div>

                                {tenantDetail.recent_incidents?.length > 0 ? (
                                  <table style={{ width: '100%', borderCollapse: 'collapse', background: 'white', borderRadius: '0.5rem', overflow: 'hidden' }}>
                                    <thead>
                                      <tr>
                                        {['ID', 'Type', 'Status', 'Risk', 'Created'].map((h, i) => (
                                          <th key={i} style={{
                                            padding: '0.75rem 1rem', textAlign: 'left', fontSize: '0.7rem',
                                            fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                                            background: '#f8fafc', borderBottom: '1px solid #e2e8f0',
                                          }}>{h}</th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {tenantDetail.recent_incidents.map((inc) => (
                                        <tr key={inc.incident_id}>
                                          <td style={{ padding: '0.625rem 1rem', fontSize: '0.8rem', fontFamily: 'monospace', color: '#667eea', fontWeight: 600, borderBottom: '1px solid #f1f5f9' }}>
                                            {inc.incident_id?.slice(-8).toUpperCase()}
                                          </td>
                                          <td style={{ padding: '0.625rem 1rem', fontSize: '0.8rem', color: '#334155', borderBottom: '1px solid #f1f5f9' }}>
                                            {inc.type || '—'}
                                          </td>
                                          <td style={{ padding: '0.625rem 1rem', borderBottom: '1px solid #f1f5f9' }}>
                                            <span style={{
                                              padding: '0.15rem 0.5rem', borderRadius: '0.25rem', fontSize: '0.7rem', fontWeight: 600,
                                              background: inc.status === 'resolved' ? '#d1fae5' : inc.status === 'pending_company_action' ? '#fee2e2' : '#f3f4f6',
                                              color: inc.status === 'resolved' ? '#065f46' : inc.status === 'pending_company_action' ? '#991b1b' : '#374151',
                                            }}>
                                              {inc.status?.replace(/_/g, ' ')}
                                            </span>
                                          </td>
                                          <td style={{ padding: '0.625rem 1rem', fontSize: '0.8rem', fontWeight: 600, borderBottom: '1px solid #f1f5f9',
                                            color: (inc.risk_score || 0) >= 0.7 ? '#ef4444' : (inc.risk_score || 0) >= 0.4 ? '#f59e0b' : '#10b981',
                                          }}>
                                            {inc.risk_score != null ? `${(inc.risk_score * 100).toFixed(0)}%` : '—'}
                                          </td>
                                          <td style={{ padding: '0.625rem 1rem', fontSize: '0.75rem', color: '#64748b', borderBottom: '1px solid #f1f5f9' }}>
                                            {formatDate(inc.created_at)}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', background: 'white', borderRadius: '0.5rem' }}>
                                    No incidents recorded for this tenant.
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Workflows tab */}
                            {activeDetailTab === 'workflows' && (
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '0.75rem' }}>
                                {tenantDetail.workflows?.length > 0 ? tenantDetail.workflows.map((wf) => (
                                  <div key={wf.workflow_id + '_v' + wf.version} style={{
                                    background: 'white', borderRadius: '0.75rem', padding: '1rem',
                                    border: '1px solid #e2e8f0',
                                  }}>
                                    <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#0f172a', marginBottom: '0.35rem' }}>
                                      {formatUseCase(wf.use_case) || wf.workflow_id}
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                      <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '0.25rem', background: '#ede9fe', color: '#6d28d9', fontWeight: 600 }}>
                                        v{wf.version}
                                      </span>
                                      <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '0.25rem', background: '#dbeafe', color: '#1d4ed8', fontWeight: 600 }}>
                                        {wf.nodes} nodes
                                      </span>
                                      <span style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '0.25rem', background: '#f3f4f6', color: '#374151', fontWeight: 600, fontFamily: 'monospace' }}>
                                        {wf.workflow_id}
                                      </span>
                                    </div>
                                  </div>
                                )) : (
                                  <div style={{ gridColumn: '1 / -1', padding: '2rem', textAlign: 'center', color: '#94a3b8', background: 'white', borderRadius: '0.5rem' }}>
                                    No workflows configured for this tenant.
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Connectors tab */}
                            {activeDetailTab === 'connectors' && (
                              <div>
                                {tenantDetail.connectors?.length > 0 ? (
                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '0.75rem' }}>
                                    {tenantDetail.connectors.map((c, ci) => {
                                      const s = connectorTypeStyle(c.connector_type);
                                      return (
                                        <div key={ci} style={{
                                          background: 'white', borderRadius: '0.75rem', padding: '1.25rem',
                                          border: `1px solid ${c.is_active ? '#d1fae5' : '#e2e8f0'}`,
                                          position: 'relative', overflow: 'hidden',
                                        }}>
                                          {/* Active indicator strip */}
                                          <div style={{
                                            position: 'absolute', top: 0, left: 0, right: 0, height: 3,
                                            background: c.is_active
                                              ? `linear-gradient(90deg, ${healthColor(c.health_status)}, ${healthColor(c.health_status)}80)`
                                              : '#e2e8f0',
                                          }} />

                                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                                            <div>
                                              <div style={{ fontWeight: 700, fontSize: '0.9rem', color: '#0f172a', marginBottom: '0.25rem' }}>
                                                {c.display_name || c.connector_type}
                                              </div>
                                              <span style={{
                                                fontSize: '0.65rem', fontWeight: 700, padding: '0.15rem 0.5rem',
                                                borderRadius: '0.3rem', background: s.bg, color: s.color,
                                              }}>
                                                {s.label}
                                              </span>
                                            </div>
                                            <div style={{ textAlign: 'right' }}>
                                              <span style={{
                                                fontSize: '0.65rem', fontWeight: 700, padding: '0.15rem 0.5rem',
                                                borderRadius: '0.3rem',
                                                background: c.is_active ? '#d1fae5' : '#fee2e2',
                                                color: c.is_active ? '#065f46' : '#991b1b',
                                              }}>
                                                {c.is_active ? 'Active' : 'Inactive'}
                                              </span>
                                              <div style={{
                                                display: 'flex', alignItems: 'center', gap: '0.3rem',
                                                marginTop: '0.35rem', justifyContent: 'flex-end',
                                              }}>
                                                <span style={{
                                                  width: 7, height: 7, borderRadius: '50%',
                                                  background: healthColor(c.health_status || 'unknown'),
                                                }} />
                                                <span style={{ fontSize: '0.65rem', color: '#64748b', fontWeight: 600 }}>
                                                  {(c.health_status || 'unknown').charAt(0).toUpperCase() + (c.health_status || 'unknown').slice(1)}
                                                </span>
                                              </div>
                                            </div>
                                          </div>

                                          <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '0.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                                              <span style={{ fontWeight: 600 }}>URL:</span>
                                              <span style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#475569', wordBreak: 'break-all' }}>
                                                {c.instance_url || '—'}
                                              </span>
                                            </div>
                                          </div>

                                          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', fontSize: '0.65rem' }}>
                                            <span style={{
                                              padding: '0.1rem 0.4rem', borderRadius: '0.25rem',
                                              background: '#f3f4f6', color: '#374151', fontWeight: 600,
                                            }}>
                                              Auth: {c.auth_method || '—'}
                                            </span>
                                            {c.last_successful_sync_at && (
                                              <span style={{
                                                padding: '0.1rem 0.4rem', borderRadius: '0.25rem',
                                                background: '#eff6ff', color: '#1d4ed8', fontWeight: 600,
                                              }}>
                                                Last sync: {formatDate(c.last_successful_sync_at)}
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8', background: 'white', borderRadius: '0.5rem' }}>
                                    <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>🔗</div>
                                    <div style={{ fontWeight: 600 }}>No connectors configured</div>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); navigate('/super/connectors/setup'); }}
                                      style={{
                                        marginTop: '0.75rem', padding: '0.4rem 0.8rem', borderRadius: '0.375rem',
                                        fontSize: '0.75rem', fontWeight: 600, border: '1px solid #dbeafe',
                                        background: '#eff6ff', color: '#1d4ed8', cursor: 'pointer',
                                      }}
                                    >
                                      Setup Connector
                                    </button>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Agents tab */}
                            {activeDetailTab === 'agents' && (
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.75rem' }}>
                                {tenantDetail.agents?.length > 0 ? tenantDetail.agents.map((a) => (
                                  <div key={a.agent_id} style={{
                                    background: 'white', borderRadius: '0.75rem', padding: '1rem',
                                    border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '0.75rem',
                                  }}>
                                    <div style={{
                                      width: 40, height: 40, borderRadius: '50%',
                                      background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
                                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                                      color: 'white', fontSize: '0.8rem', fontWeight: 700, flexShrink: 0,
                                    }}>
                                      {a.full_name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                      <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#0f172a' }}>{a.full_name}</div>
                                      <div style={{ fontSize: '0.7rem', color: '#64748b' }}>{a.specialization}</div>
                                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.25rem', alignItems: 'center' }}>
                                        <span style={{ fontSize: '0.65rem', color: '#f59e0b' }}>{'★'.repeat(Math.floor(a.rating))}</span>
                                        <span style={{ fontSize: '0.6rem', color: '#94a3b8' }}>{a.rating}/5</span>
                                        <span style={{ fontSize: '0.6rem', color: '#cbd5e1' }}>|</span>
                                        <span style={{ fontSize: '0.6rem', color: '#94a3b8' }}>{a.total_jobs} jobs</span>
                                      </div>
                                    </div>
                                    <span style={{
                                      fontSize: '0.625rem', fontWeight: 700, padding: '0.15rem 0.5rem',
                                      borderRadius: '0.25rem',
                                      background: a.is_available ? '#d1fae5' : '#fee2e2',
                                      color: a.is_available ? '#065f46' : '#991b1b',
                                    }}>
                                      {a.is_available ? 'Available' : 'Busy'}
                                    </span>
                                  </div>
                                )) : (
                                  <div style={{ gridColumn: '1 / -1', padding: '2rem', textAlign: 'center', color: '#94a3b8', background: 'white', borderRadius: '0.5rem' }}>
                                    No field agents registered.
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Admin Groups tab */}
                            {activeDetailTab === 'admin_groups' && (
                              <div>
                                {/* Group list */}
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                                  {adminGroups.map((g) => (
                                    <div key={g.group_id} style={{
                                      background: 'white', borderRadius: '0.75rem', padding: '1rem',
                                      border: '1px solid #e2e8f0',
                                    }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                                        <div>
                                          <div style={{ fontWeight: 700, fontSize: '0.85rem', color: '#0f172a' }}>{g.display_name}</div>
                                          <div style={{ fontSize: '0.7rem', color: '#94a3b8', fontFamily: 'monospace' }}>{g.group_id}</div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '4px' }}>
                                          <button
                                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.75rem', color: '#3b82f6', fontWeight: 600 }}
                                            onClick={async (e) => { e.stopPropagation(); setEditingGroup(editingGroup === g.group_id ? null : g.group_id); setNewGroup({ display_name: g.display_name, connector_scope: [...(g.connector_scope || [])], description: g.description || '' }); }}
                                          >Edit</button>
                                          <button
                                            style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.75rem', color: '#ef4444', fontWeight: 600 }}
                                            disabled={groupBusy === g.group_id}
                                            onClick={async (e) => {
                                              e.stopPropagation();
                                              if (!window.confirm(`Delete group "${g.display_name}"? Users in this group will become unscoped (see all).`)) return;
                                              setGroupBusy(g.group_id);
                                              try {
                                                await deleteAdminGroup(t.tenant_id, g.group_id);
                                                setAdminGroups((prev) => prev.filter((grp) => grp.group_id !== g.group_id));
                                              } catch { }
                                              finally { setGroupBusy(''); }
                                            }}
                                          >Delete</button>
                                        </div>
                                      </div>
                                      {g.description && <div style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '0.5rem' }}>{g.description}</div>}
                                      <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                                        {(g.connector_scope || []).length === 0 ? (
                                          <span style={{ fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px', borderRadius: '999px', background: '#d1fae5', color: '#065f46' }}>All (General Admin)</span>
                                        ) : (g.connector_scope || []).map((s) => (
                                          <span key={s} style={{
                                            fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
                                            background: s === 'portal' ? '#fef3c7' : '#dbeafe',
                                            color: s === 'portal' ? '#92400e' : '#1e40af',
                                          }}>{s === 'portal' ? 'Chatbot' : s.toUpperCase()}</span>
                                        ))}
                                      </div>
                                      {/* Members */}
                                      <div style={{ marginTop: '0.5rem', fontSize: '0.7rem', color: '#94a3b8' }}>
                                        Members: {(tenantDetail.users || []).filter((u) => u.admin_group_id === g.group_id).map((u) => u.full_name).join(', ') || 'None'}
                                      </div>

                                      {/* Inline edit form */}
                                      {editingGroup === g.group_id && (
                                        <div style={{ marginTop: '0.75rem', padding: '0.75rem', background: '#f8fafc', borderRadius: '0.5rem', border: '1px solid #e2e8f0' }}>
                                          <input value={newGroup.display_name} onChange={(e) => setNewGroup({ ...newGroup, display_name: e.target.value })}
                                            placeholder="Group Name" style={{ width: '100%', padding: '6px 10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '0.8rem', marginBottom: '6px' }} />
                                          <input value={newGroup.description} onChange={(e) => setNewGroup({ ...newGroup, description: e.target.value })}
                                            placeholder="Description" style={{ width: '100%', padding: '6px 10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '0.8rem', marginBottom: '6px' }} />
                                          <div style={{ fontSize: '0.72rem', fontWeight: 600, color: '#475569', marginBottom: '4px' }}>Connector Scope:</div>
                                          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '8px' }}>
                                            {['portal', 'servicenow', 'sap', 'jira', 'zendesk'].map((s) => (
                                              <label key={s} style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.72rem', cursor: 'pointer' }}>
                                                <input type="checkbox" checked={newGroup.connector_scope.includes(s)}
                                                  onChange={(e) => {
                                                    const scope = e.target.checked
                                                      ? [...newGroup.connector_scope, s]
                                                      : newGroup.connector_scope.filter((x) => x !== s);
                                                    setNewGroup({ ...newGroup, connector_scope: scope });
                                                  }} />
                                                {s === 'portal' ? 'Chatbot' : s.toUpperCase()}
                                              </label>
                                            ))}
                                          </div>
                                          <div style={{ display: 'flex', gap: '6px' }}>
                                            <button style={{ padding: '5px 12px', borderRadius: '6px', border: 'none', background: '#3b82f6', color: '#fff', fontSize: '0.75rem', fontWeight: 600, cursor: 'pointer' }}
                                              disabled={!newGroup.display_name || groupBusy === `edit:${g.group_id}`}
                                              onClick={async () => {
                                                setGroupBusy(`edit:${g.group_id}`);
                                                try {
                                                  await updateAdminGroup(t.tenant_id, g.group_id, newGroup);
                                                  setAdminGroups((prev) => prev.map((grp) => grp.group_id === g.group_id ? { ...grp, ...newGroup } : grp));
                                                  setEditingGroup(null);
                                                } catch { }
                                                finally { setGroupBusy(''); }
                                              }}
                                            >Save</button>
                                            <button style={{ padding: '5px 12px', borderRadius: '6px', border: '1px solid #d1d5db', background: '#fff', fontSize: '0.75rem', cursor: 'pointer' }}
                                              onClick={() => setEditingGroup(null)}
                                            >Cancel</button>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                  {adminGroups.length === 0 && (
                                    <div style={{ gridColumn: '1 / -1', padding: '2rem', textAlign: 'center', color: '#94a3b8', background: 'white', borderRadius: '0.5rem' }}>
                                      No admin groups configured. All company users can see all incidents.
                                    </div>
                                  )}
                                </div>

                                {/* Create group form */}
                                {!showGroupForm ? (
                                  <button
                                    style={{ padding: '8px 16px', borderRadius: '8px', border: '1px dashed #94a3b8', background: 'transparent', color: '#64748b', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer', width: '100%' }}
                                    onClick={() => { setShowGroupForm(true); setNewGroup({ display_name: '', connector_scope: [], description: '' }); }}
                                  >+ Create Admin Group</button>
                                ) : (
                                  <div style={{ background: 'white', borderRadius: '0.75rem', padding: '1rem', border: '1px solid #e2e8f0' }}>
                                    <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: '0.75rem' }}>New Admin Group</div>
                                    <input value={newGroup.display_name} onChange={(e) => setNewGroup({ ...newGroup, display_name: e.target.value })}
                                      placeholder="Group Name (e.g. SAP Team)" style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '0.8rem', marginBottom: '8px' }} />
                                    <input value={newGroup.description} onChange={(e) => setNewGroup({ ...newGroup, description: e.target.value })}
                                      placeholder="Description (optional)" style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #d1d5db', fontSize: '0.8rem', marginBottom: '8px' }} />
                                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#475569', marginBottom: '6px' }}>Connector Scope (empty = sees everything):</div>
                                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px' }}>
                                      {['portal', 'servicenow', 'sap', 'jira', 'zendesk'].map((s) => (
                                        <label key={s} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.78rem', cursor: 'pointer' }}>
                                          <input type="checkbox" checked={newGroup.connector_scope.includes(s)}
                                            onChange={(e) => {
                                              const scope = e.target.checked
                                                ? [...newGroup.connector_scope, s]
                                                : newGroup.connector_scope.filter((x) => x !== s);
                                              setNewGroup({ ...newGroup, connector_scope: scope });
                                            }} />
                                          {s === 'portal' ? 'Chatbot' : s.toUpperCase()}
                                        </label>
                                      ))}
                                    </div>
                                    <div style={{ display: 'flex', gap: '8px' }}>
                                      <button
                                        style={{ padding: '8px 16px', borderRadius: '8px', border: 'none', background: '#3b82f6', color: '#fff', fontSize: '0.8rem', fontWeight: 600, cursor: 'pointer' }}
                                        disabled={!newGroup.display_name || groupBusy === 'create'}
                                        onClick={async () => {
                                          setGroupBusy('create');
                                          try {
                                            const result = await createAdminGroup(t.tenant_id, newGroup);
                                            setAdminGroups((prev) => [...prev, result.group]);
                                            setShowGroupForm(false);
                                            setNewGroup({ display_name: '', connector_scope: [], description: '' });
                                          } catch { }
                                          finally { setGroupBusy(''); }
                                        }}
                                      >Create</button>
                                      <button
                                        style={{ padding: '8px 16px', borderRadius: '8px', border: '1px solid #d1d5db', background: '#fff', fontSize: '0.8rem', cursor: 'pointer' }}
                                        onClick={() => setShowGroupForm(false)}
                                      >Cancel</button>
                                    </div>
                                  </div>
                                )}

                                {/* User → Group assignment */}
                                {adminGroups.length > 0 && (
                                  <div style={{ marginTop: '1.25rem' }}>
                                    <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: '0.75rem', color: '#334155' }}>User Group Assignments</div>
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '0.5rem' }}>
                                      {(tenantDetail.users || []).filter((u) => u.role === 'company').map((u) => (
                                        <div key={u.user_id} style={{
                                          background: 'white', borderRadius: '0.5rem', padding: '0.75rem',
                                          border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', gap: '0.75rem',
                                        }}>
                                          <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontWeight: 600, fontSize: '0.8rem', color: '#0f172a' }}>{u.full_name}</div>
                                            <div style={{ fontSize: '0.68rem', color: '#94a3b8' }}>{u.username || u.phone}</div>
                                          </div>
                                          <CustomSelect
                                            value={u.admin_group_id || ''}
                                            disabled={assignBusy === u.user_id}
                                            onChange={async (v) => {
                                              const groupId = v || null;
                                              setAssignBusy(u.user_id);
                                              try {
                                                await assignUserToGroup(t.tenant_id, u.user_id, groupId);
                                                setTenantDetail((prev) => ({
                                                  ...prev,
                                                  users: prev.users.map((usr) =>
                                                    usr.user_id === u.user_id ? { ...usr, admin_group_id: groupId } : usr
                                                  ),
                                                }));
                                              } catch { }
                                              finally { setAssignBusy(''); }
                                            }}
                                            options={[
                                              { value: '', label: 'No Group (All Access)' },
                                              ...adminGroups.map((g) => ({ value: g.group_id, label: g.display_name })),
                                            ]}
                                            small
                                            style={{ minWidth: 140 }}
                                          />
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                          </>);
                            })()}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>

          {tenants.length === 0 && (
            <div style={{ padding: '3rem', textAlign: 'center', color: '#94a3b8' }}>
              <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🏢</div>
              <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#334155', marginBottom: '0.5rem' }}>No Tenants Found</div>
              <div style={{ fontSize: '0.85rem' }}>Tenants will appear here once users are registered.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TenantManagement;
