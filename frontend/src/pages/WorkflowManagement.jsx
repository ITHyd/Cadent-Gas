import { useMemo, useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import WorkflowBuilderVisual from '../components/WorkflowBuilderVisual';
import { getTenantWorkflows } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { formatUseCase } from '../utils/formatters';

const WorkflowManagement = () => {
  const { user } = useAuth();
  const { workflowName } = useParams();
  const navigate = useNavigate();
  const tenantId = user?.tenant_id;

  const [workflows, setWorkflows] = useState([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState(null);
  const [selectedUseCase, setSelectedUseCase] = useState('');
  const [showBuilder, setShowBuilder] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [activationMessage, setActivationMessage] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(12);
  const pageSizeOptions = [10, 30, 50, 100];

  const scrollbarId = 'wf-mgmt-scrollbar';

  const styles = {
    container: {
      height: '100vh',
      backgroundColor: '#f3f4f6',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      boxSizing: 'border-box',
    },
    contentWrapper: {
      maxWidth: '1200px',
      width: '100%',
      margin: '0 auto',
      padding: '0 2rem',
    },
    topSection: {
      flexShrink: 0,
      paddingTop: '2rem',
    },
    scrollArea: {
      flex: 1,
      overflowY: 'auto',
      paddingBottom: '2rem',
    },
    header: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '1.25rem',
      gap: '1rem',
      flexWrap: 'wrap',
    },
    title: {
      fontSize: '2.25rem',
      fontWeight: '700',
      color: '#111827',
    },
    button: {
      padding: '0.6rem 1.25rem',
      backgroundColor: '#2563eb',
      color: 'white',
      border: 'none',
      borderRadius: '0.5rem',
      cursor: 'pointer',
      fontWeight: '600',
      fontSize: '0.9rem',
    },
    searchRow: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '1rem',
      marginBottom: '1.25rem',
    },
    grid: {
      display: 'grid',
      gridTemplateColumns: 'repeat(3, 1fr)',
      gap: '1.25rem',
    },
    workflowCard: {
      backgroundColor: 'white',
      borderRadius: '0.75rem',
      padding: '1.25rem',
      boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1)',
      cursor: 'pointer',
      transition: 'all 0.2s',
    },
    workflowHeader: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'start',
      marginBottom: '1rem',
      gap: '0.75rem',
    },
    workflowTitle: {
      fontSize: '1.05rem',
      fontWeight: '600',
      color: '#111827',
      marginBottom: '0.25rem',
      overflowWrap: 'anywhere',
    },
    workflowUseCase: {
      fontSize: '0.875rem',
      color: '#6b7280',
      overflowWrap: 'anywhere',
    },
    badge: {
      padding: '0.25rem 0.75rem',
      borderRadius: '9999px',
      fontSize: '0.75rem',
      fontWeight: '600',
    },
    activeBadge: {
      backgroundColor: '#d1fae5',
      color: '#065f46',
    },
    workflowInfo: {
      display: 'flex',
      gap: '0.6rem',
      marginTop: '1rem',
      fontSize: '0.875rem',
      color: '#6b7280',
      flexWrap: 'wrap',
    },
    actions: {
      display: 'flex',
      gap: '0.5rem',
      marginTop: '1rem',
      paddingTop: '1rem',
      borderTop: '1px solid #e5e7eb',
    },
    actionButton: {
      padding: '0.5rem 1rem',
      border: '1px solid #d1d5db',
      borderRadius: '0.375rem',
      backgroundColor: 'white',
      cursor: 'pointer',
      fontSize: '0.875rem',
    },
    searchInput: {
      width: '100%',
      padding: '0.6rem 0.75rem 0.6rem 2.25rem',
      borderRadius: '0.5rem',
      border: '1px solid #d1d5db',
      backgroundColor: 'white',
      color: '#111827',
      fontSize: '0.875rem',
      outline: 'none',
    },
    searchWrapper: {
      position: 'relative',
      flex: 1,
      maxWidth: '400px',
    },
    searchIcon: {
      position: 'absolute',
      left: '0.75rem',
      top: '50%',
      transform: 'translateY(-50%)',
      color: '#9ca3af',
      fontSize: '0.875rem',
      pointerEvents: 'none',
    },
    resultCount: {
      fontSize: '0.8rem',
      color: '#6b7280',
      marginBottom: '0.75rem',
    },
    pagination: {
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      gap: '0.5rem',
      marginTop: '1.5rem',
      flexWrap: 'wrap',
      position: 'relative',
    },
    pageSizeWrapper: {
      position: 'absolute',
      right: 0,
      display: 'flex',
      alignItems: 'center',
      gap: '0.4rem',
      fontSize: '0.8rem',
      color: '#6b7280',
    },
    pageSizeCombo: {
      width: '60px',
      padding: '0.35rem 0.5rem',
      border: '1px solid #d1d5db',
      borderRadius: '0.375rem',
      backgroundColor: 'white',
      fontSize: '0.8rem',
      color: '#374151',
      textAlign: 'center',
      outline: 'none',
    },
    pageButton: {
      padding: '0.4rem 0.85rem',
      border: '1px solid #d1d5db',
      borderRadius: '0.375rem',
      backgroundColor: 'white',
      cursor: 'pointer',
      fontSize: '0.8rem',
      color: '#374151',
    },
    pageButtonActive: {
      backgroundColor: '#2563eb',
      color: 'white',
      border: '1px solid #2563eb',
    },
    pageButtonDisabled: {
      opacity: 0.4,
      cursor: 'default',
    },
  };

  const getLatestByUseCase = (items) => {
    const byUseCase = new Map();
    items.forEach((wf) => {
      const existing = byUseCase.get(wf.use_case);
      if (!existing || Number(wf.version) > Number(existing.version)) {
        byUseCase.set(wf.use_case, wf);
      }
    });

    return Array.from(byUseCase.values()).sort((a, b) =>
      a.use_case.localeCompare(b.use_case)
    );
  };

  const latestWorkflows = useMemo(() => getLatestByUseCase(workflows), [workflows]);

  const filteredWorkflows = useMemo(() => {
    if (!searchQuery.trim()) return latestWorkflows;
    const q = searchQuery.toLowerCase();
    return latestWorkflows.filter(
      (wf) =>
        wf.workflow_id?.toLowerCase().includes(q) ||
        wf.use_case?.toLowerCase().includes(q) ||
        wf.workflow_id?.replaceAll('_', ' ').toLowerCase().includes(q) ||
        wf.use_case?.replaceAll('_', ' ').toLowerCase().includes(q)
    );
  }, [latestWorkflows, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredWorkflows.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const paginatedWorkflows = filteredWorkflows.slice(
    (safeCurrentPage - 1) * pageSize,
    safeCurrentPage * pageSize
  );

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, pageSize]);

  const loadWorkflows = async () => {
    setIsLoading(true);
    setError('');
    try {
      const data = await getTenantWorkflows(tenantId);
      setWorkflows(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || 'Failed to load workflows');
      setWorkflows([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadWorkflows();
  }, []);

  // Handle workflow name from URL parameter - set selected workflow (latest version)
  useEffect(() => {
    if (workflowName && latestWorkflows.length > 0) {
      const workflow = latestWorkflows.find(wf => wf.use_case === workflowName);
      if (workflow) {
        setSelectedUseCase(workflow.use_case);
        setSelectedWorkflow(workflow);
      }
    }
  }, [workflowName, latestWorkflows]);

  useEffect(() => {
    if (latestWorkflows.length === 0) {
      setSelectedWorkflow(null);
      setSelectedUseCase('');
      return;
    }

    if (!selectedUseCase) {
      setSelectedUseCase(latestWorkflows[0].use_case);
      setSelectedWorkflow(latestWorkflows[0]);
      return;
    }

    const active = latestWorkflows.find((wf) => wf.use_case === selectedUseCase);
    setSelectedWorkflow(active || latestWorkflows[0]);
  }, [latestWorkflows, selectedUseCase]);

  const handleCreateWorkflow = () => {
    setActivationMessage('');
    setSelectedWorkflow(null);
    setShowBuilder(true);
  };

  const handleEditWorkflow = (workflow) => {
    setActivationMessage('');
    // Navigate to workflow-specific route
    navigate(`/super/workflows/${workflow.use_case}`);
  };

  // Show builder if we have a workflow name in URL OR showBuilder state is true
  const shouldShowBuilder = workflowName || showBuilder;

  if (shouldShowBuilder) {
    return (
      <WorkflowBuilderVisual
        workflow={selectedWorkflow}
        tenantId={tenantId}
        onClose={() => {
          setShowBuilder(false);
          navigate('/super/workflows');
        }}
        onSave={async (savedWorkflow) => {
          setShowBuilder(false);
          navigate('/super/workflows');
          await loadWorkflows();
          if (savedWorkflow?.version) {
            setActivationMessage(
              `Activated version ${savedWorkflow.version} for use_case ${savedWorkflow.use_case}. New executions will use it.`
            );
          }
          if (savedWorkflow?.use_case) {
            setSelectedUseCase(savedWorkflow.use_case);
          }
        }}
      />
    );
  }

  return (
    <div style={styles.container}>
      <style>{`
        .${scrollbarId}::-webkit-scrollbar { width: 6px; }
        .${scrollbarId}::-webkit-scrollbar-track { background: transparent; }
        .${scrollbarId}::-webkit-scrollbar-thumb {
          background: #c4c8cf;
          border-radius: 3px;
        }
        .${scrollbarId}::-webkit-scrollbar-thumb:hover { background: #9ca3af; }
        .${scrollbarId} { scrollbar-width: thin; scrollbar-color: #c4c8cf transparent; }
        input[list]::-webkit-calendar-picker-indicator { display: none !important; }
        input[list]::-webkit-list-button { display: none !important; }
      `}</style>

      <div style={styles.topSection}>
        <div style={styles.contentWrapper}>
          <div style={styles.header}>
            <h1 style={styles.title}>Workflow Management</h1>
          </div>

          <div style={styles.searchRow}>
            <div style={styles.searchWrapper}>
              <span style={styles.searchIcon}>&#128269;</span>
              <input
                style={styles.searchInput}
                type="text"
                placeholder="Search by ID or use case..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <button
              style={styles.button}
              onClick={handleCreateWorkflow}
              onMouseEnter={(e) => {
                e.target.style.backgroundColor = '#1d4ed8';
              }}
              onMouseLeave={(e) => {
                e.target.style.backgroundColor = '#2563eb';
              }}
            >
              + Create Workflow
            </button>
          </div>

          {error && <p style={{ color: '#dc2626', marginBottom: '1rem' }}>{error}</p>}
          {activationMessage && (
            <p style={{ color: '#065f46', marginBottom: '1rem' }}>{activationMessage}</p>
          )}
        </div>
      </div>

      <div className={scrollbarId} style={styles.scrollArea}>
        <div style={styles.contentWrapper}>
          {isLoading && <p style={{ color: '#6b7280' }}>Loading workflows...</p>}

          {!isLoading && (
            <p style={styles.resultCount}>
              Showing {paginatedWorkflows.length} of {filteredWorkflows.length} workflow{filteredWorkflows.length !== 1 ? 's' : ''}
              {searchQuery.trim() && ` matching "${searchQuery.trim()}"`}
            </p>
          )}

          <div style={styles.grid}>
            {!isLoading &&
              paginatedWorkflows.map((workflow) => (
                <div
                  key={workflow.workflow_id}
                  style={styles.workflowCard}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.boxShadow =
                      '0 10px 15px -3px rgba(0, 0, 0, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.boxShadow =
                      '0 1px 3px 0 rgba(0, 0, 0, 0.1)';
                  }}
                >
                  <div style={styles.workflowHeader}>
                    <div>
                      <h3 style={styles.workflowTitle}>{formatUseCase(workflow.use_case)}</h3>
                      <p style={styles.workflowUseCase}>{workflow.workflow_id?.replaceAll('_', ' ')}</p>
                    </div>
                    <span style={{ ...styles.badge, ...styles.activeBadge }}>Active v{workflow.version}</span>
                  </div>

                  <div style={styles.workflowInfo}>
                    <span>Version {workflow.version}</span>
                    <span>|</span>
                    <span>{workflow.nodes?.length || 0} nodes</span>
                    <span>|</span>
                    <span>{workflow.updated_at?.slice(0, 10) || 'N/A'}</span>
                  </div>

                  <div style={styles.actions}>
                    <button
                      style={styles.actionButton}
                      onClick={() => handleEditWorkflow(workflow)}
                      onMouseEnter={(e) => {
                        e.target.style.backgroundColor = '#f3f4f6';
                      }}
                      onMouseLeave={(e) => {
                        e.target.style.backgroundColor = 'white';
                      }}
                    >
                      Edit
                    </button>
                  </div>
                </div>
              ))}
          </div>

          {!isLoading && filteredWorkflows.length > 0 && (
            <div style={styles.pagination}>
              {totalPages > 1 && (
                <>
                  <button
                    style={{
                      ...styles.pageButton,
                      ...(safeCurrentPage <= 1 ? styles.pageButtonDisabled : {}),
                    }}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={safeCurrentPage <= 1}
                  >
                    Prev
                  </button>

                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter((page) => {
                      if (totalPages <= 7) return true;
                      if (page === 1 || page === totalPages) return true;
                      return Math.abs(page - safeCurrentPage) <= 1;
                    })
                    .reduce((acc, page, idx, arr) => {
                      if (idx > 0 && page - arr[idx - 1] > 1) acc.push('...');
                      acc.push(page);
                      return acc;
                    }, [])
                    .map((item, idx) =>
                      item === '...' ? (
                        <span key={`ellipsis-${idx}`} style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                          ...
                        </span>
                      ) : (
                        <button
                          key={item}
                          style={{
                            ...styles.pageButton,
                            ...(item === safeCurrentPage ? styles.pageButtonActive : {}),
                          }}
                          onClick={() => setCurrentPage(item)}
                        >
                          {item}
                        </button>
                      )
                    )}

                  <button
                    style={{
                      ...styles.pageButton,
                      ...(safeCurrentPage >= totalPages ? styles.pageButtonDisabled : {}),
                    }}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={safeCurrentPage >= totalPages}
                  >
                    Next
                  </button>
                </>
              )}

              <div style={styles.pageSizeWrapper}>
                <span>Rows:</span>
                <input
                  list="pageSizeList"
                  style={styles.pageSizeCombo}
                  defaultValue={pageSize}
                  key={pageSize}
                  onBlur={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (val > 0) setPageSize(val);
                    else e.target.value = pageSize;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.target.blur();
                    }
                  }}
                  onChange={(e) => {
                    const val = parseInt(e.target.value, 10);
                    if (pageSizeOptions.includes(val)) setPageSize(val);
                  }}
                />
                <datalist id="pageSizeList">
                  {pageSizeOptions.map((size) => (
                    <option key={size} value={size} />
                  ))}
                </datalist>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default WorkflowManagement;

