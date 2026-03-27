import { useState, useEffect } from 'react';
import { formatUseCase } from '../utils/formatters';
import {
  getKBStats,
  getTrueIncidentsKB,
  getFalseIncidentsKB,
  addKBEntry,
  updateKBEntry,
  deleteKBEntry,
  searchKB
} from '../services/api';
import CustomSelect from '../components/CustomSelect';
import { useAuth } from '../contexts/AuthContext';

const formatKbDisplayId = (entry) => {
  const rawId = String(entry?.kb_id || entry?.id || '').trim();
  const normalized = rawId.toLowerCase();
  const trueMatch = normalized.match(/^(?:co_)?(?:seed_)?true_(\d+)$/);
  const falseMatch = normalized.match(/^(?:co_)?(?:seed_)?false_(\d+)$/);

  if (trueMatch) return `true_${trueMatch[1].padStart(3, '0')}`;
  if (falseMatch) return `false_${falseMatch[1].padStart(3, '0')}`;
  return rawId || 'N/A';
};

const buildSequentialKbDisplayId = (kbType, indexOnPage, page, pageSize, totalItems) => {
  const prefix = kbType === 'true' ? 'true' : 'false';
  const absoluteIndex = ((page - 1) * pageSize) + indexOnPage;
  const sequence = Math.max(totalItems - absoluteIndex, 1);
  return `${prefix}_${String(sequence).padStart(3, '0')}`;
};

const KnowledgeBase = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('true');
  const [stats, setStats] = useState({ total_true: 0, total_false: 0, recent_additions: 0 });
  const [trueIncidents, setTrueIncidents] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [falseIncidents, setFalseIncidents] = useState({ items: [], total: 0, page: 1, pages: 1 });
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showViewModal, setShowViewModal] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const tenantId = user?.tenant_id;

  useEffect(() => {
    loadStats();
    loadKBData();
  }, [activeTab, currentPage, pageSize]);

  const loadStats = async () => {
    try {
      const data = await getKBStats(tenantId);
      setStats(data);
    } catch {
      return;
    }
  };

  const loadKBData = async () => {
    setLoading(true);
    try {
      if (activeTab === 'true') {
        const data = await getTrueIncidentsKB(currentPage, pageSize, tenantId);
        setTrueIncidents(data);
      } else {
        const data = await getFalseIncidentsKB(currentPage, pageSize, tenantId);
        setFalseIncidents(data);
      }
    } catch {
      return;
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) { loadKBData(); return; }
    setLoading(true);
    try {
      const data = await searchKB(searchQuery, activeTab, 20);
      if (activeTab === 'true') {
        setTrueIncidents({ items: data.results, total: data.total, page: 1, pages: 1 });
      } else {
        setFalseIncidents({ items: data.results, total: data.total, page: 1, pages: 1 });
      }
    } catch {
      return;
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (kbId, kbType) => {
    if (!window.confirm('Are you sure you want to delete this KB entry?')) return;
    try {
      await deleteKBEntry(kbType, kbId);
      loadKBData();
      loadStats();
    } catch {
      return;
    }
  };

  const handleEdit = (entry) => { setSelectedEntry(entry); setShowEditModal(true); };
  const handleView = (entry) => { setSelectedEntry(entry); setShowViewModal(true); };

  const currentData = activeTab === 'true' ? trueIncidents : falseIncidents;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.title}>Knowledge Base Management</h1>
        <p style={styles.subtitle}>Manage verified true and false incidents for AI learning</p>
      </div>

      {/* Stats Cards */}
      <div style={styles.statsGrid}>
        <div style={{...styles.statCard, borderLeft: '4px solid #10b981'}}>
          <div style={{...styles.statValue, color: '#059669'}}>{stats.total_true}</div>
          <div style={styles.statLabel}>True Incidents</div>
        </div>
        <div style={{...styles.statCard, borderLeft: '4px solid #f59e0b'}}>
          <div style={{...styles.statValue, color: '#d97706'}}>{stats.total_false}</div>
          <div style={styles.statLabel}>False Incidents</div>
        </div>
        <div style={{...styles.statCard, borderLeft: '4px solid #6366f1'}}>
          <div style={{...styles.statValue, color: '#4f46e5'}}>{stats.total_true + stats.total_false}</div>
          <div style={styles.statLabel}>Total Entries</div>
        </div>
        <div style={{...styles.statCard, borderLeft: '4px solid #0ea5e9'}}>
          <div style={{...styles.statValue, color: '#0284c7'}}>{stats.recent_additions}</div>
          <div style={styles.statLabel}>Recent (7 days)</div>
        </div>
      </div>

      {/* Tabs */}
      <div style={styles.tabContainer}>
        <button
          style={{...styles.tab, ...(activeTab === 'true' ? styles.activeTabTrue : {})}}
          onClick={() => { setActiveTab('true'); setCurrentPage(1); }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: '6px'}}><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          True Incidents ({stats.total_true})
        </button>
        <button
          style={{...styles.tab, ...(activeTab === 'false' ? styles.activeTabFalse : {})}}
          onClick={() => { setActiveTab('false'); setCurrentPage(1); }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{marginRight: '6px'}}><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          False Incidents ({stats.total_false})
        </button>
      </div>

      {/* Search and Actions */}
      <div style={styles.toolbar}>
        <div style={styles.searchContainer}>
          <input
            type="text"
            placeholder="Search KB entries..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            style={styles.searchInput}
          />
          <button onClick={handleSearch} style={styles.searchButton}>Search</button>
          {searchQuery && (
            <button onClick={() => { setSearchQuery(''); loadKBData(); }} style={{...styles.searchButton, backgroundColor: '#6b7280'}}>Clear</button>
          )}
        </div>
        <button onClick={() => setShowAddModal(true)} style={styles.addButton}>+ Add Entry</button>
      </div>

      {/* Table */}
      {loading ? (
        <div style={styles.loading}>Loading...</div>
      ) : currentData.items.length === 0 ? (
        <div style={styles.emptyState}>No KB entries found.</div>
      ) : (
        <>
          <div style={styles.tableContainer}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>ID</th>
                  <th style={{...styles.th, width: activeTab === 'true' ? '12%' : '12%'}}>Use Case</th>
                  <th style={{...styles.th, width: '45%'}}>Description</th>
                  <th style={styles.th}>Tags</th>
                  <th style={{...styles.th, textAlign: 'center'}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {currentData.items.map((entry, index) => {
                  const displayKbId = buildSequentialKbDisplayId(
                    activeTab,
                    index,
                    currentPage,
                    pageSize,
                    currentData.total || currentData.items.length,
                  );
                  const entryWithDisplayId = { ...entry, display_kb_id: displayKbId };
                  return (
                    <tr key={entry.kb_id} style={styles.tr} onClick={() => handleView(entryWithDisplayId)} title="Click to view details">
                      <td style={{...styles.td, fontFamily: 'monospace', fontSize: '0.78rem', color: '#6b7280', whiteSpace: 'nowrap'}}>{displayKbId}</td>
                      <td style={styles.td}>
                        <span style={styles.useCaseBadge}>
                          {(entry.use_case || entry.reported_as || 'N/A').replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td style={{...styles.td, maxWidth: '520px'}}>
                        <div style={{overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: '1.4'}}>
                          {entry.description || entry.false_positive_reason || entry.actual_issue || 'N/A'}
                        </div>
                      </td>
                      <td style={styles.td}>
                        <div style={{display: 'flex', flexWrap: 'wrap', gap: '3px', maxWidth: '180px'}}>
                          {(entry.tags || []).slice(0, 3).map((tag, i) => (
                            <span key={i} style={styles.tagChip}>{tag}</span>
                          ))}
                          {(entry.tags || []).length > 3 && (
                            <span style={{...styles.tagChip, backgroundColor: '#e2e8f0', color: '#475569'}}>+{entry.tags.length - 3}</span>
                          )}
                        </div>
                      </td>
                      <td style={{...styles.td, textAlign: 'center'}} onClick={(e) => e.stopPropagation()}>
                        <div style={styles.actionButtons}>
                          <button onClick={() => handleView(entryWithDisplayId)} style={styles.actionButton} title="View Details">
                            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                          </button>
                          <button onClick={() => handleEdit(entryWithDisplayId)} style={styles.actionButton} title="Edit">
                            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                          </button>
                          <button onClick={() => handleDelete(entry.kb_id, activeTab)} style={styles.actionButton} title="Delete">
                            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <PaginationBar
            currentPage={currentPage}
            totalPages={currentData.pages}
            totalItems={currentData.total}
            pageSize={pageSize}
            onPageChange={setCurrentPage}
            onPageSizeChange={(size) => { setPageSize(size); setCurrentPage(1); }}
          />
        </>
      )}

      {/* View Modal */}
      {showViewModal && selectedEntry && (
        <ViewKBModal
          entry={selectedEntry}
          kbType={activeTab}
          onClose={() => { setShowViewModal(false); setSelectedEntry(null); }}
          onEdit={() => { setShowViewModal(false); handleEdit(selectedEntry); }}
        />
      )}

      {/* Add Modal */}
      {showAddModal && (
        <AddKBModal
          kbType={activeTab}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => { setShowAddModal(false); loadKBData(); loadStats(); }}
        />
      )}

      {/* Edit Modal */}
      {showEditModal && selectedEntry && (
        <EditKBModal
          entry={selectedEntry}
          kbType={activeTab}
          onClose={() => { setShowEditModal(false); setSelectedEntry(null); }}
          onSuccess={() => { setShowEditModal(false); setSelectedEntry(null); loadKBData(); }}
        />
      )}
    </div>
  );
};

// ── View Detail Modal ──────────────────────────────────────────────────
const ViewKBModal = ({ entry, kbType, onClose, onEdit }) => {
  const isTrue = kbType === 'true';
  const incidentPattern = entry.incident_pattern || {};
  const patternFields = incidentPattern.pattern_fields || {};
  const manufacturer = incidentPattern.manufacturer || entry.manufacturer || null;
  const model = incidentPattern.model || entry.model || null;
  const workflowOutcome = incidentPattern.workflow_outcome || entry.outcome || null;
  const summaryText = isTrue
    ? (entry.description || entry.root_cause || entry.resolution_summary || 'N/A')
    : (entry.false_positive_reason || entry.actual_issue || entry.resolution || 'N/A');
  const likelyMeaning = entry.root_cause || entry.actual_issue || patternFields.likely_meaning || null;
  const detailRows = [
    { label: isTrue ? 'Use Case' : 'Reported As', value: formatUseCase(entry.use_case || entry.reported_as || '') || 'N/A' },
    { label: 'Manufacturer', value: manufacturer },
    { label: 'Model', value: model },
    { label: 'Outcome', value: workflowOutcome ? formatUseCase(String(workflowOutcome).replace(/_/g, ' ')) : null },
    { label: isTrue ? 'Likely Cause' : 'Actual Issue', value: likelyMeaning },
  ].filter((row) => row.value);

  const Section = ({ title, children, icon }) => (
    <div style={{marginBottom: '16px'}}>
      <div style={{fontSize: '0.72rem', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px'}}>
        {icon && <span style={{fontSize: '0.9rem'}}>{icon}</span>}
        {title}
      </div>
      <div style={{fontSize: '0.88rem', color: '#1e293b', lineHeight: '1.55'}}>{children}</div>
    </div>
  );

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={{...styles.modal, maxWidth: '720px', padding: 0, borderRadius: '16px', overflow: 'hidden'}} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{
          padding: '20px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
          background: isTrue ? 'linear-gradient(135deg, #ecfdf5 0%, #f0fdf4 100%)' : 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
          borderBottom: `1px solid ${isTrue ? '#a7f3d0' : '#fde68a'}`,
        }}>
          <div>
            <div style={{display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px'}}>
              <span style={{
                padding: '3px 10px', borderRadius: '6px', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
                backgroundColor: isTrue ? '#059669' : '#d97706', color: 'white',
              }}>
                {isTrue ? 'True Incident' : 'False Alarm'}
              </span>
              <span style={{fontFamily: 'monospace', fontSize: '0.78rem', color: '#64748b'}}>{entry.display_kb_id || formatKbDisplayId(entry)}</span>
            </div>
            <div style={{fontSize: '0.82rem', fontWeight: 600, color: '#374151', marginTop: '2px'}}>
              {formatUseCase(entry.use_case || entry.reported_as || '')}
            </div>
          </div>
          <button onClick={onClose} style={{background: 'none', border: 'none', cursor: 'pointer', padding: '4px', borderRadius: '6px', color: '#64748b'}}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Body */}
        <div style={{padding: '20px 24px', maxHeight: '60vh', overflowY: 'auto'}}>
          <Section title="Summary">
            <div style={{padding: '10px 14px', borderRadius: '10px', backgroundColor: isTrue ? '#f0fdf4' : '#fff7ed', border: `1px solid ${isTrue ? '#bbf7d0' : '#fed7aa'}`, color: isTrue ? '#166534' : '#9a3412'}}>
              {summaryText}
            </div>
          </Section>

          {detailRows.length > 0 && (
            <Section title="Classification">
              <div style={{display: 'grid', gap: '8px'}}>
                {detailRows.map((row) => (
                  <div key={row.label} style={{display: 'grid', gridTemplateColumns: '140px 1fr', gap: '10px', alignItems: 'start'}}>
                    <span style={{fontSize: '0.78rem', color: '#64748b', fontWeight: 700}}>{row.label}</span>
                    <span style={{fontSize: '0.86rem', color: '#1e293b'}}>{row.value}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {patternFields && Object.keys(patternFields).length > 0 && (
            <Section title="Pattern Details">
              <div style={{display: 'grid', gap: '8px'}}>
                {Object.entries(patternFields).map(([field, value]) => (
                  <div key={field} style={{display: 'grid', gridTemplateColumns: '140px 1fr', gap: '10px', alignItems: 'start'}}>
                    <span style={{fontSize: '0.78rem', color: '#64748b', fontWeight: 700}}>{field.replace(/_/g, ' ')}</span>
                    <span style={{fontSize: '0.86rem', color: '#1e293b'}}>{String(value)}</span>
                  </div>
                ))}
              </div>
            </Section>
          )}

          {(entry.resolution_summary || entry.resolution || entry.review_notes) && (
            <Section title="Review Notes">
              <div style={{padding: '10px 14px', borderRadius: '10px', backgroundColor: '#eff6ff', border: '1px solid #bfdbfe', color: '#1d4ed8'}}>
                {entry.review_notes || entry.resolution_summary || entry.resolution}
              </div>
            </Section>
          )}

          {/* Tags */}
          {entry.tags && entry.tags.length > 0 && (
            <Section title="Tags">
              <div style={{display: 'flex', flexWrap: 'wrap', gap: '5px'}}>
                {entry.tags.map((tag, i) => (
                  <span key={i} style={styles.tagChip}>{tag}</span>
                ))}
              </div>
            </Section>
          )}

          {/* Metadata */}
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '8px', paddingTop: '12px', borderTop: '1px solid #e2e8f0'}}>
            <div style={{fontSize: '0.78rem', color: '#94a3b8'}}>
              Verified by: <span style={{fontWeight: 600, color: '#475569'}}>{entry.verified_by || 'system'}</span>
            </div>
            <div style={{fontSize: '0.78rem', color: '#94a3b8'}}>
              Created: <span style={{fontWeight: 600, color: '#475569'}}>{entry.created_at ? new Date(entry.created_at).toLocaleString() : 'N/A'}</span>
            </div>
            {entry.tenant_id && (
              <div style={{fontSize: '0.78rem', color: '#94a3b8'}}>
                Tenant: <span style={{fontWeight: 600, color: '#475569'}}>{entry.tenant_id}</span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{padding: '14px 24px', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'flex-end', gap: '10px', backgroundColor: '#f9fafb'}}>
          <button onClick={onClose} style={styles.cancelButton}>Close</button>
          <button onClick={onEdit} style={styles.submitButton}>Edit Entry</button>
        </div>
      </div>
    </div>
  );
};

// ── Pagination Component ────────────────────────────────────────────────
const PaginationBar = ({ currentPage, totalPages, totalItems, pageSize, onPageChange, onPageSizeChange }) => {
  const startItem = totalItems === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  const getPageNumbers = () => {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
    if (currentPage <= 4) return [1, 2, 3, 4, 5, '...', totalPages];
    if (currentPage >= totalPages - 3) return [1, '...', totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    return [1, '...', currentPage - 1, currentPage, currentPage + 1, '...', totalPages];
  };

  const pgBtnBase = {
    minWidth: '36px', height: '36px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    border: '1px solid #e2e8f0', borderRadius: '0.5rem', fontSize: '0.8rem', fontWeight: '600',
    cursor: 'pointer', transition: 'all 0.15s', background: 'white', color: '#334155', padding: '0 0.5rem',
  };
  const pgBtnActive = { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white', borderColor: 'transparent', boxShadow: '0 2px 8px rgba(102,126,234,0.3)' };
  const pgBtnDisabled = { opacity: 0.4, cursor: 'not-allowed' };
  const pgBtnEllipsis = { border: 'none', cursor: 'default', background: 'none', color: '#94a3b8' };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap',
      gap: '1rem', marginTop: '1.25rem', padding: '0.75rem 1rem',
      background: 'white', borderRadius: '0.75rem', boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    }}>
      <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
        Showing <strong style={{ color: '#0f172a' }}>{startItem}-{endItem}</strong> of{' '}
        <strong style={{ color: '#0f172a' }}>{totalItems}</strong> entries
      </div>
      <div style={{ display: 'flex', gap: '0.375rem', alignItems: 'center' }}>
        <button onClick={() => onPageChange(1)} disabled={currentPage === 1} style={{...pgBtnBase, ...(currentPage === 1 ? pgBtnDisabled : {})}} title="First page">&laquo;</button>
        <button onClick={() => onPageChange(Math.max(1, currentPage - 1))} disabled={currentPage === 1} style={{...pgBtnBase, ...(currentPage === 1 ? pgBtnDisabled : {})}} title="Previous">&lsaquo;</button>
        {getPageNumbers().map((page, i) =>
          page === '...' ? (
            <span key={`e${i}`} style={{...pgBtnBase, ...pgBtnEllipsis}}>...</span>
          ) : (
            <button key={page} onClick={() => onPageChange(page)} style={{...pgBtnBase, ...(page === currentPage ? pgBtnActive : {})}}>{page}</button>
          )
        )}
        <button onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))} disabled={currentPage === totalPages || totalPages === 0} style={{...pgBtnBase, ...(currentPage === totalPages || totalPages === 0 ? pgBtnDisabled : {})}} title="Next">&rsaquo;</button>
        <button onClick={() => onPageChange(totalPages)} disabled={currentPage === totalPages || totalPages === 0} style={{...pgBtnBase, ...(currentPage === totalPages || totalPages === 0 ? pgBtnDisabled : {})}} title="Last page">&raquo;</button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Rows:</span>
        <CustomSelect
          value={pageSize}
          onChange={(v) => onPageSizeChange(Number(v))}
          options={[5, 10, 20, 50].map((n) => ({ value: n, label: String(n) }))}
          small
          style={{ minWidth: 60 }}
        />
      </div>
    </div>
  );
};

// ── Add Modal Component ────────────────────────────────────────────────
const AddKBModal = ({ kbType, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    description: '', outcome: '', use_case: '',
    reported_as: '', actual_issue: '', false_positive_reason: '', tags: ''
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const entry = kbType === 'true' ? {
        use_case: formData.use_case, description: formData.description,
        outcome: formData.outcome, key_indicators: {}, risk_factors: {},
        tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean)
      } : {
        reported_as: formData.reported_as, actual_issue: formData.actual_issue,
        false_positive_reason: formData.false_positive_reason, key_indicators: {},
        tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean)
      };
      await addKBEntry(kbType, entry, 'admin_user');
      onSuccess();
    } catch {
      return;
    }
  };

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={{...styles.modal, borderRadius: '16px'}} onClick={(e) => e.stopPropagation()}>
        <h2 style={styles.modalTitle}>Add {kbType === 'true' ? 'True' : 'False'} Incident</h2>
        <form onSubmit={handleSubmit}>
          {kbType === 'true' ? (
            <>
              <input type="text" placeholder="Use Case (e.g., gas_smell)" value={formData.use_case} onChange={(e) => setFormData({...formData, use_case: e.target.value})} style={styles.input} required />
              <textarea placeholder="Description" value={formData.description} onChange={(e) => setFormData({...formData, description: e.target.value})} style={styles.textarea} required />
              <input type="text" placeholder="Outcome (e.g., emergency_dispatch)" value={formData.outcome} onChange={(e) => setFormData({...formData, outcome: e.target.value})} style={styles.input} required />
            </>
          ) : (
            <>
              <input type="text" placeholder="Reported As (e.g., gas_smell)" value={formData.reported_as} onChange={(e) => setFormData({...formData, reported_as: e.target.value})} style={styles.input} required />
              <input type="text" placeholder="Actual Issue" value={formData.actual_issue} onChange={(e) => setFormData({...formData, actual_issue: e.target.value})} style={styles.input} required />
              <textarea placeholder="False Positive Reason" value={formData.false_positive_reason} onChange={(e) => setFormData({...formData, false_positive_reason: e.target.value})} style={styles.textarea} required />
            </>
          )}
          <input type="text" placeholder="Tags (comma-separated)" value={formData.tags} onChange={(e) => setFormData({...formData, tags: e.target.value})} style={styles.input} />
          <div style={styles.modalActions}>
            <button type="button" onClick={onClose} style={styles.cancelButton}>Cancel</button>
            <button type="submit" style={styles.submitButton}>Add Entry</button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ── Edit Modal Component ────────────────────────────────────────────────
const EditKBModal = ({ entry, kbType, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    description: entry.description || '', outcome: entry.outcome || '',
    reported_as: entry.reported_as || '', actual_issue: entry.actual_issue || '',
    false_positive_reason: entry.false_positive_reason || '', tags: (entry.tags || []).join(', ')
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const updates = kbType === 'true' ? {
        description: formData.description, outcome: formData.outcome,
        tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean)
      } : {
        reported_as: formData.reported_as, actual_issue: formData.actual_issue,
        false_positive_reason: formData.false_positive_reason,
        tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean)
      };
      await updateKBEntry(kbType, entry.kb_id, updates);
      onSuccess();
    } catch {
      return;
    }
  };

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={{...styles.modal, borderRadius: '16px'}} onClick={(e) => e.stopPropagation()}>
        <h2 style={styles.modalTitle}>Edit KB Entry: {entry.display_kb_id || formatKbDisplayId(entry)}</h2>
        <form onSubmit={handleSubmit}>
          {kbType === 'true' ? (
            <>
              <textarea placeholder="Description" value={formData.description} onChange={(e) => setFormData({...formData, description: e.target.value})} style={styles.textarea} required />
              <input type="text" placeholder="Outcome" value={formData.outcome} onChange={(e) => setFormData({...formData, outcome: e.target.value})} style={styles.input} required />
            </>
          ) : (
            <>
              <input type="text" placeholder="Reported As" value={formData.reported_as} onChange={(e) => setFormData({...formData, reported_as: e.target.value})} style={styles.input} required />
              <input type="text" placeholder="Actual Issue" value={formData.actual_issue} onChange={(e) => setFormData({...formData, actual_issue: e.target.value})} style={styles.input} required />
              <textarea placeholder="False Positive Reason" value={formData.false_positive_reason} onChange={(e) => setFormData({...formData, false_positive_reason: e.target.value})} style={styles.textarea} required />
            </>
          )}
          <input type="text" placeholder="Tags (comma-separated)" value={formData.tags} onChange={(e) => setFormData({...formData, tags: e.target.value})} style={styles.input} />
          <div style={styles.modalActions}>
            <button type="button" onClick={onClose} style={styles.cancelButton}>Cancel</button>
            <button type="submit" style={styles.submitButton}>Update Entry</button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ── Styles ──────────────────────────────────────────────────────────────
const styles = {
  container: { minHeight: '100vh', backgroundColor: '#f3f4f6', padding: '2rem 2.5rem' },
  header: { marginBottom: '2rem' },
  title: { fontSize: '2rem', fontWeight: 'bold', color: '#111827', marginBottom: '0.5rem' },
  subtitle: { color: '#6b7280' },
  statsGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' },
  statCard: { backgroundColor: 'white', borderRadius: '12px', padding: '1.25rem 1.5rem', boxShadow: '0 1px 3px 0 rgba(0,0,0,0.08)' },
  statValue: { fontSize: '1.8rem', fontWeight: 'bold' },
  statLabel: { color: '#6b7280', marginTop: '0.25rem', fontSize: '0.85rem' },
  tabContainer: { display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '2px solid #e5e7eb' },
  tab: {
    padding: '0.75rem 1.5rem', border: 'none', backgroundColor: 'transparent', cursor: 'pointer',
    fontSize: '0.92rem', fontWeight: '500', color: '#6b7280', borderBottom: '2px solid transparent',
    marginBottom: '-2px', display: 'flex', alignItems: 'center', transition: 'all 0.15s',
  },
  activeTabTrue: { color: '#059669', borderBottomColor: '#059669', fontWeight: '600' },
  activeTabFalse: { color: '#d97706', borderBottomColor: '#d97706', fontWeight: '600' },
  toolbar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', gap: '1rem' },
  searchContainer: { display: 'flex', gap: '0.5rem', flex: 1, maxWidth: '500px' },
  searchInput: { flex: 1, padding: '0.5rem 1rem', border: '1px solid #d1d5db', borderRadius: '0.5rem', fontSize: '0.875rem', outline: 'none' },
  searchButton: { padding: '0.5rem 1.25rem', backgroundColor: '#2563eb', color: 'white', border: 'none', borderRadius: '0.5rem', cursor: 'pointer', fontSize: '0.84rem', fontWeight: '500' },
  addButton: { padding: '0.5rem 1.25rem', backgroundColor: '#10b981', color: 'white', border: 'none', borderRadius: '0.5rem', cursor: 'pointer', fontSize: '0.84rem', fontWeight: '600' },
  tableContainer: { backgroundColor: 'white', borderRadius: '12px', boxShadow: '0 1px 3px 0 rgba(0,0,0,0.08)', overflow: 'hidden' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { padding: '12px 16px', textAlign: 'left', fontSize: '0.72rem', fontWeight: '600', color: '#64748b', textTransform: 'uppercase', backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', letterSpacing: '0.03em' },
  tr: { borderBottom: '1px solid #f1f5f9', cursor: 'pointer', transition: 'background 0.12s' },
  td: { padding: '12px 16px', fontSize: '0.84rem', color: '#1e293b', verticalAlign: 'middle' },
  badge: { padding: '3px 10px', borderRadius: '9999px', fontSize: '0.7rem', fontWeight: '600', color: 'white', textTransform: 'capitalize' },
  useCaseBadge: {
    padding: '3px 10px', borderRadius: '6px', fontSize: '0.76rem', fontWeight: 600,
    backgroundColor: '#f0f9ff', color: '#0369a1', border: '1px solid #bae6fd',
    textTransform: 'capitalize', whiteSpace: 'nowrap',
  },
  tagChip: {
    padding: '2px 8px', borderRadius: '4px', fontSize: '0.68rem', fontWeight: 500,
    backgroundColor: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0',
  },
  actionButtons: { display: 'flex', gap: '4px', justifyContent: 'center' },
  actionButton: { padding: '4px 6px', border: 'none', backgroundColor: 'transparent', cursor: 'pointer', borderRadius: '6px', transition: 'background 0.12s' },
  loading: { textAlign: 'center', padding: '3rem', fontSize: '1rem', color: '#6b7280' },
  emptyState: { textAlign: 'center', padding: '3rem', fontSize: '1rem', color: '#94a3b8', backgroundColor: 'white', borderRadius: '12px', boxShadow: '0 1px 3px 0 rgba(0,0,0,0.06)' },
  modalOverlay: { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(2px)' },
  modal: { backgroundColor: 'white', borderRadius: '0.5rem', padding: '2rem', maxWidth: '500px', width: '90%', maxHeight: '90vh', overflow: 'auto' },
  modalTitle: { fontSize: '1.35rem', fontWeight: 'bold', marginBottom: '1.25rem', color: '#0f172a' },
  input: { width: '100%', padding: '0.7rem', border: '1px solid #d1d5db', borderRadius: '0.5rem', marginBottom: '0.875rem', fontSize: '0.875rem', outline: 'none', boxSizing: 'border-box' },
  textarea: { width: '100%', padding: '0.7rem', border: '1px solid #d1d5db', borderRadius: '0.5rem', marginBottom: '0.875rem', fontSize: '0.875rem', minHeight: '100px', resize: 'vertical', outline: 'none', boxSizing: 'border-box' },
  modalActions: { display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '1.25rem' },
  cancelButton: { padding: '0.5rem 1.25rem', backgroundColor: '#e2e8f0', color: '#475569', border: 'none', borderRadius: '0.5rem', cursor: 'pointer', fontSize: '0.84rem', fontWeight: '500' },
  submitButton: { padding: '0.5rem 1.25rem', backgroundColor: '#2563eb', color: 'white', border: 'none', borderRadius: '0.5rem', cursor: 'pointer', fontSize: '0.84rem', fontWeight: '600' },
};

export default KnowledgeBase;
