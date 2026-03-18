import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getTenantMapping,
  getTenantMappingVersions,
  rollbackTenantMapping,
  updateTenantMapping,
} from '../services/api';
import CustomSelect from '../components/CustomSelect';

const CONNECTOR_OPTIONS = ['servicenow', 'sap', 'jira', 'aws'];
const DIRECTION_OPTIONS = [
  { value: 'inbound', label: 'Inbound' },
  { value: 'outbound', label: 'Outbound' },
  { value: 'both', label: 'Both' },
];
const TRANSFORM_OPTIONS = [
  { value: 'direct', label: 'Direct' },
  { value: 'lookup', label: 'Lookup' },
  { value: 'template', label: 'Template' },
  { value: 'custom', label: 'Custom' },
];

const EMPTY_FIELD = { external_field: '', canonical_field: '', direction: 'inbound', transform_type: 'direct', transform_config: {}, is_required: false };

const TenantMappingEditor = () => {
  const { tenantId } = useParams();
  const navigate = useNavigate();
  const [connectorType, setConnectorType] = useState('servicenow');
  const [fieldMaps, setFieldMaps] = useState([]);
  const [statusMapping, setStatusMapping] = useState([]);
  const [reverseStatusMapping, setReverseStatusMapping] = useState([]);
  const [priorityMapping, setPriorityMapping] = useState([]);
  const [priorityToRisk, setPriorityToRisk] = useState([]);
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState('fields');
  const [rollbackConfirm, setRollbackConfirm] = useState(null);

  const showToast = useCallback((type, message) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const objToRows = (obj) => Object.entries(obj || {}).map(([k, v]) => ({ key: k, value: v }));
  const rowsToObj = (rows) => {
    const o = {};
    rows.forEach((r) => { if (r.key.trim()) o[r.key.trim()] = r.value; });
    return o;
  };

  const loadData = async () => {
    if (!tenantId) return;
    setLoading(true);
    setError('');
    try {
      const [mappingRes, versionsRes] = await Promise.all([
        getTenantMapping(tenantId, connectorType),
        getTenantMappingVersions(tenantId, connectorType, 20),
      ]);
      const m = mappingRes?.mapping || {};
      setFieldMaps(m.field_maps || []);
      setStatusMapping(objToRows(m.status_mapping));
      setReverseStatusMapping(objToRows(m.reverse_status_mapping));
      setPriorityMapping(objToRows(m.priority_mapping));
      setPriorityToRisk(objToRows(m.priority_to_risk));
      setVersions(versionsRes?.versions || []);
    } catch (err) {
      setError(err.message || 'Failed to load mapping');
      setFieldMaps([]);
      setStatusMapping([]);
      setReverseStatusMapping([]);
      setPriorityMapping([]);
      setPriorityToRisk([]);
      setVersions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [tenantId, connectorType]);

  const buildPayload = () => ({
    field_maps: fieldMaps,
    status_mapping: rowsToObj(statusMapping),
    reverse_status_mapping: rowsToObj(reverseStatusMapping),
    priority_mapping: rowsToObj(priorityMapping),
    priority_to_risk: rowsToObj(priorityToRisk),
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateTenantMapping(tenantId, connectorType, buildPayload());
      await loadData();
      showToast('success', 'Mapping saved successfully');
    } catch (err) {
      showToast('error', err.message || 'Failed to save mapping');
    } finally {
      setSaving(false);
    }
  };

  const handleRollback = async (version) => {
    setRollbackConfirm(null);
    try {
      await rollbackTenantMapping(tenantId, connectorType, version);
      await loadData();
      showToast('success', `Rolled back to version ${version}`);
    } catch (err) {
      showToast('error', err.message || 'Rollback failed');
    }
  };

  // Field map helpers
  const updateField = (idx, key, val) => setFieldMaps((prev) => prev.map((f, i) => i === idx ? { ...f, [key]: val } : f));
  const removeField = (idx) => setFieldMaps((prev) => prev.filter((_, i) => i !== idx));
  const addField = () => setFieldMaps((prev) => [...prev, { ...EMPTY_FIELD }]);

  // Key-value helpers
  const updateKV = (setter, idx, prop, val) => setter((prev) => prev.map((r, i) => i === idx ? { ...r, [prop]: val } : r));
  const removeKV = (setter, idx) => setter((prev) => prev.filter((_, i) => i !== idx));
  const addKV = (setter) => setter((prev) => [...prev, { key: '', value: '' }]);

  const TABS = [
    { key: 'fields', label: 'Field Mappings', count: fieldMaps.length },
    { key: 'status', label: 'Status Mapping', count: statusMapping.length },
    { key: 'reverse_status', label: 'Reverse Status', count: reverseStatusMapping.length },
    { key: 'priority', label: 'Priority Mapping', count: priorityMapping.length },
    { key: 'risk', label: 'Priority to Risk', count: priorityToRisk.length },
  ];

  const renderKVSection = (rows, setter, fromLabel, toLabel) => (
    <div>
      {rows.length === 0 ? (
        <div style={S.emptyState}>No mappings configured yet</div>
      ) : (
        <div style={{ display: 'grid', gap: '8px' }}>
          <div style={S.kvHeader}>
            <span style={{ flex: 1 }}>{fromLabel}</span>
            <span style={{ width: 20, textAlign: 'center', color: '#94a3b8' }}></span>
            <span style={{ flex: 1 }}>{toLabel}</span>
            <span style={{ width: 36 }}></span>
          </div>
          {rows.map((r, i) => (
            <div key={i} style={S.kvRow}>
              <input
                style={S.kvInput}
                value={r.key}
                onChange={(e) => updateKV(setter, i, 'key', e.target.value)}
                placeholder={fromLabel}
              />
              <span style={{ color: '#94a3b8', fontSize: '1rem', flexShrink: 0 }}>&rarr;</span>
              <input
                style={S.kvInput}
                value={r.value}
                onChange={(e) => updateKV(setter, i, 'value', e.target.value)}
                placeholder={toLabel}
              />
              <button type="button" onClick={() => removeKV(setter, i)} style={S.removeBtn} title="Remove">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          ))}
        </div>
      )}
      <button type="button" onClick={() => addKV(setter)} style={S.addBtn}>+ Add Mapping</button>
    </div>
  );

  return (
    <div style={{ minHeight: '100vh', background: '#f3f4f6', padding: '2rem 2.5rem' }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* Toast */}
        {toast && (
          <div style={{
            position: 'fixed', top: 20, right: 20, zIndex: 100,
            padding: '12px 20px', borderRadius: 10,
            background: toast.type === 'success' ? '#f0fdf4' : '#fef2f2',
            border: `1px solid ${toast.type === 'success' ? '#bbf7d0' : '#fecaca'}`,
            color: toast.type === 'success' ? '#166534' : '#991b1b',
            fontWeight: 600, fontSize: '0.85rem',
            boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
            display: 'flex', alignItems: 'center', gap: '8px',
          }}>
            {toast.type === 'success' ? '✓' : '!'} {toast.message}
            <button onClick={() => setToast(null)} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', fontSize: '16px', padding: 0, marginLeft: '4px' }}>&times;</button>
          </div>
        )}

        {/* Rollback Confirmation Modal */}
        {rollbackConfirm !== null && (
          <div style={S.overlay}>
            <div style={S.modal}>
              <div style={{ textAlign: 'center', marginBottom: '16px' }}>
                <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#fef3c7', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px' }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                </div>
                <h3 style={{ margin: '0 0 6px', color: '#111827' }}>Rollback to Version {rollbackConfirm}?</h3>
                <p style={{ margin: 0, color: '#6b7280', fontSize: '0.85rem' }}>This will replace the current active mapping with version {rollbackConfirm}.</p>
              </div>
              <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                <button onClick={() => setRollbackConfirm(null)} style={S.secondaryBtn}>Cancel</button>
                <button onClick={() => handleRollback(rollbackConfirm)} style={{ ...S.primaryBtn, background: '#d97706' }}>Rollback</button>
              </div>
            </div>
          </div>
        )}

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <h1 style={{ margin: 0, fontSize: '1.7rem', fontWeight: 800, color: '#111827' }}>Mapping Editor</h1>
            <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: '0.88rem' }}>
              Configure how fields sync between <strong>{connectorType}</strong> and your platform for <strong>{tenantId}</strong>
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button type="button" onClick={() => navigate('/super/tenants')} style={S.secondaryBtn}>Back</button>
            <button type="button" onClick={handleSave} disabled={saving} style={{ ...S.primaryBtn, opacity: saving ? 0.6 : 1 }}>
              {saving ? 'Saving...' : 'Save New Version'}
            </button>
          </div>
        </div>

        {/* Connector selector */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '1.25rem' }}>
          <span style={{ color: '#334155', fontSize: '0.85rem', fontWeight: 600 }}>Connector:</span>
          <CustomSelect
            value={connectorType}
            onChange={setConnectorType}
            options={CONNECTOR_OPTIONS.map((opt) => ({ value: opt, label: opt.charAt(0).toUpperCase() + opt.slice(1) }))}
            style={{ minWidth: 160 }}
          />
        </div>

        {error && (
          <div style={{ background: '#fef2f2', color: '#991b1b', border: '1px solid #fecaca', borderRadius: 10, padding: '10px 14px', marginBottom: '14px', fontSize: '0.85rem' }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={S.card}><p style={{ color: '#6b7280', margin: 0 }}>Loading mapping...</p></div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '14px' }}>
            {/* Main Content */}
            <div style={S.card}>
              {/* Tabs */}
              <div style={S.tabBar}>
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setActiveTab(t.key)}
                    style={{
                      ...S.tab,
                      color: activeTab === t.key ? '#1d4ed8' : '#64748b',
                      borderBottom: `2px solid ${activeTab === t.key ? '#1d4ed8' : 'transparent'}`,
                      background: activeTab === t.key ? '#eff6ff' : 'transparent',
                    }}
                  >
                    {t.label}
                    <span style={{
                      marginLeft: 6, padding: '1px 7px', borderRadius: 10, fontSize: '0.7rem', fontWeight: 700,
                      background: activeTab === t.key ? '#dbeafe' : '#f1f5f9', color: activeTab === t.key ? '#1d4ed8' : '#94a3b8',
                    }}>{t.count}</span>
                  </button>
                ))}
              </div>

              {/* Field Mappings Tab */}
              {activeTab === 'fields' && (
                <div>
                  {fieldMaps.length === 0 ? (
                    <div style={S.emptyState}>No field mappings configured yet</div>
                  ) : (
                    <div style={{ overflowX: 'auto' }}>
                      <table style={S.table}>
                        <thead>
                          <tr>
                            <th style={S.th}>External Field</th>
                            <th style={{ ...S.th, width: 20, textAlign: 'center', padding: '8px 4px' }}></th>
                            <th style={S.th}>Platform Field</th>
                            <th style={S.th}>Direction</th>
                            <th style={S.th}>Transform</th>
                            <th style={{ ...S.th, textAlign: 'center' }}>Required</th>
                            <th style={{ ...S.th, width: 36 }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {fieldMaps.map((f, i) => (
                            <tr key={i}>
                              <td style={S.td}>
                                <input style={S.cellInput} value={f.external_field || ''} onChange={(e) => updateField(i, 'external_field', e.target.value)} placeholder="e.g. number" />
                              </td>
                              <td style={{ ...S.td, textAlign: 'center', color: '#94a3b8', padding: '8px 4px' }}>&rarr;</td>
                              <td style={S.td}>
                                <input style={S.cellInput} value={f.canonical_field || ''} onChange={(e) => updateField(i, 'canonical_field', e.target.value)} placeholder="e.g. external_number" />
                              </td>
                              <td style={S.td}>
                                <CustomSelect
                                  value={f.direction || 'inbound'}
                                  onChange={(v) => updateField(i, 'direction', v)}
                                  options={DIRECTION_OPTIONS}
                                  small
                                />
                              </td>
                              <td style={S.td}>
                                <CustomSelect
                                  value={f.transform_type || 'direct'}
                                  onChange={(v) => updateField(i, 'transform_type', v)}
                                  options={TRANSFORM_OPTIONS}
                                  small
                                />
                              </td>
                              <td style={{ ...S.td, textAlign: 'center' }}>
                                <label style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                  <input
                                    type="checkbox"
                                    checked={!!f.is_required}
                                    onChange={(e) => updateField(i, 'is_required', e.target.checked)}
                                    style={{ width: 16, height: 16, accentColor: '#2563eb', cursor: 'pointer' }}
                                  />
                                </label>
                              </td>
                              <td style={S.td}>
                                <button type="button" onClick={() => removeField(i)} style={S.removeBtn} title="Remove">
                                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <button type="button" onClick={addField} style={S.addBtn}>+ Add Field Mapping</button>
                </div>
              )}

              {/* Status Mapping */}
              {activeTab === 'status' && renderKVSection(statusMapping, setStatusMapping, 'External Status', 'Platform Status')}
              {activeTab === 'reverse_status' && renderKVSection(reverseStatusMapping, setReverseStatusMapping, 'Platform Status', 'External Status')}
              {activeTab === 'priority' && renderKVSection(priorityMapping, setPriorityMapping, 'External Priority', 'Platform Priority')}
              {activeTab === 'risk' && renderKVSection(priorityToRisk, setPriorityToRisk, 'Priority Level', 'Risk Score')}
            </div>

            {/* Version History Sidebar */}
            <div style={S.card}>
              <h3 style={{ margin: '0 0 12px', fontSize: '0.95rem', color: '#0f172a', fontWeight: 700 }}>Version History</h3>
              {versions.length === 0 ? (
                <div style={S.emptyState}>No versions yet</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {versions.map((v) => (
                    <div key={v.mapping_id} style={{
                      borderRadius: 10, padding: '10px 12px',
                      border: `1px solid ${v.is_active ? '#bbf7d0' : '#e2e8f0'}`,
                      background: v.is_active ? '#f0fdf4' : '#fff',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <strong style={{ color: '#0f172a', fontSize: '0.85rem' }}>v{v.version}</strong>
                          {v.is_active && (
                            <span style={{ fontSize: '0.68rem', fontWeight: 700, color: '#fff', background: '#16a34a', padding: '1px 7px', borderRadius: 6 }}>Active</span>
                          )}
                        </div>
                        {!v.is_active && (
                          <button type="button" onClick={() => setRollbackConfirm(v.version)} style={S.linkBtn}>Restore</button>
                        )}
                      </div>
                      <div style={{ marginTop: '4px', color: '#94a3b8', fontSize: '0.72rem' }}>
                        {v.updated_at ? new Date(v.updated_at).toLocaleString() : '-'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const S = {
  card: {
    background: '#fff',
    borderRadius: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
    padding: '16px 18px',
  },
  tabBar: {
    display: 'flex',
    gap: '2px',
    borderBottom: '2px solid #e5e7eb',
    marginBottom: '16px',
    overflowX: 'auto',
  },
  tab: {
    border: 'none',
    padding: '10px 14px',
    fontSize: '0.82rem',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    borderRadius: '6px 6px 0 0',
    marginBottom: '-2px',
    transition: 'all 0.15s',
    display: 'flex',
    alignItems: 'center',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
  },
  th: {
    textAlign: 'left',
    padding: '8px 10px',
    fontSize: '0.72rem',
    fontWeight: 700,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    borderBottom: '2px solid #f1f5f9',
  },
  td: {
    padding: '6px 10px',
    borderBottom: '1px solid #f1f5f9',
    verticalAlign: 'middle',
  },
  cellInput: {
    width: '100%',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    padding: '6px 8px',
    fontSize: '0.8rem',
    color: '#1f2937',
    background: '#fafafa',
    outline: 'none',
    transition: 'border-color 0.15s',
  },
  kvHeader: {
    display: 'flex',
    gap: '10px',
    alignItems: 'center',
    padding: '0 0 6px',
    fontSize: '0.72rem',
    fontWeight: 700,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    borderBottom: '2px solid #f1f5f9',
    marginBottom: '4px',
  },
  kvRow: {
    display: 'flex',
    gap: '10px',
    alignItems: 'center',
  },
  kvInput: {
    flex: 1,
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    padding: '7px 10px',
    fontSize: '0.82rem',
    color: '#1f2937',
    background: '#fafafa',
    outline: 'none',
  },
  addBtn: {
    marginTop: '12px',
    border: '1px dashed #cbd5e1',
    borderRadius: 8,
    padding: '8px 16px',
    background: 'transparent',
    color: '#2563eb',
    fontWeight: 600,
    fontSize: '0.82rem',
    cursor: 'pointer',
    width: '100%',
    transition: 'background 0.15s, border-color 0.15s',
  },
  removeBtn: {
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    padding: '4px',
    borderRadius: 4,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyState: {
    textAlign: 'center',
    color: '#94a3b8',
    fontSize: '0.85rem',
    padding: '2rem 1rem',
  },
  primaryBtn: {
    border: 'none',
    borderRadius: 8,
    padding: '9px 16px',
    background: '#8DE971',
    color: '#030304',
    fontWeight: 700,
    fontSize: '0.82rem',
    cursor: 'pointer',
  },
  secondaryBtn: {
    border: '1px solid #d1d5db',
    borderRadius: 8,
    padding: '9px 16px',
    background: '#fff',
    color: '#111827',
    fontWeight: 600,
    fontSize: '0.82rem',
    cursor: 'pointer',
  },
  linkBtn: {
    border: '1px solid #c7d2fe',
    borderRadius: 6,
    padding: '3px 10px',
    background: '#eef2ff',
    color: '#4338ca',
    fontWeight: 700,
    fontSize: '0.72rem',
    cursor: 'pointer',
  },
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.45)', zIndex: 100,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  modal: {
    background: '#fff', borderRadius: 16, padding: '28px 32px', maxWidth: 400,
    boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
  },
};

export default TenantMappingEditor;
