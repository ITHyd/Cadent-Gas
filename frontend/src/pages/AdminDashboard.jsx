import { useEffect, useMemo, useState } from 'react';
import IncidentMap from '../components/IncidentMap';
import {
  approveResolution,
  assignAgent,
  assignBackupAgent,
  confirmIncidentValid,
  createCustomerNotification,
  getAllAgents,
  getAvailableAgents,
  getCompanyIncidents,
  getCompanyOpsRequests,
  getCompanyStats,
  getIncident,
  getFalseIncidentsKB,
  getTenantWorkflows,
  getTrueIncidentsKB,
  markIncidentFalse,
  resolveIncident,
  updateAssistanceRequest,
  updateItemRequest,
  validateIncident,
} from '../services/api';
import { formatIncidentId } from '../utils/incidentIds';
import { useAuth } from '../contexts/AuthContext';
import ProfileDropdown from '../components/ProfileDropdown';
import NotificationBell from '../components/NotificationBell';
import SyncStatusBadge from '../components/SyncStatusBadge';
import {
  DateRangeSelector,
  DonutChart,
  FunnelChart,
  HeatmapChart,
  LineTrendChart,
  TrendBadge,
} from '../components/ModernDashboardCharts';

const FILTER_TO_STATUS = {
  new: 'new,classifying,analyzing',
  in_progress: 'in_progress,waiting_input,paused',
  pending: 'pending_company_action',
  dispatched: 'dispatched',
  resolved: 'resolved',
  completed: 'completed',
  all: null,
};

const filterCompanyIncidentsByTab = (incidents, filter) => {
  const items = Array.isArray(incidents) ? incidents : [];
  let filtered = [];

  switch (filter) {
    case 'new':
      // New tab: Show most recently created portal/chatbot incidents (last 24 hours)
      const now = new Date();
      const twentyFourHoursAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);

      filtered = items.filter((incident) => {
        const isPortalIncident = !incident.external_ref || !incident.external_ref.connector_type;
        const createdAt = new Date(incident.created_at);
        const isRecent = createdAt >= twentyFourHoursAgo;

        return isPortalIncident && isRecent;
      });
      break;
    case 'in_progress':
      filtered = items.filter((incident) => ['in_progress', 'waiting_input', 'paused'].includes(incident.status));
      break;
    case 'pending':
      filtered = items.filter((incident) => incident.status === 'pending_company_action');
      break;
    case 'dispatched':
      filtered = items.filter((incident) => incident.status === 'dispatched');
      break;
    case 'resolved':
      filtered = items.filter((incident) => incident.status === 'resolved');
      break;
    case 'completed':
      filtered = items.filter((incident) => incident.status === 'completed');
      break;
    case 'all':
    default:
      filtered = items;
      break;
  }

  // Sort all filtered results by created_at descending (most recent first)
  return filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
};

const paginationBtnStyle = {
  border: '1px solid #cbd5e1',
  background: '#fff',
  borderRadius: '6px',
  padding: '5px 10px',
  fontSize: '0.78rem',
  fontWeight: 600,
  color: '#334155',
  cursor: 'pointer',
  lineHeight: 1.3,
};

const SlaIndicator = ({ deadline, slaStatus }) => {
  if (!deadline) return null;

  const now = new Date();
  const deadlineDate = new Date(deadline);
  const remainingMs = deadlineDate - now;
  const remainingMinutes = Math.floor(remainingMs / 60000);

  let color = '#047857';
  let label = `${remainingMinutes}m left`;
  let bg = '#ecfdf5';

  if (remainingMs <= 0) {
    color = '#b91c1c';
    label = `BREACHED ${Math.abs(remainingMinutes)}m ago`;
    bg = '#fef2f2';
  } else if (slaStatus === 'warning' || remainingMinutes <= 10) {
    color = '#b45309';
    label = `${remainingMinutes}m left`;
    bg = '#fff7ed';
  }

  return (
    <div style={{
      fontSize: '0.72rem', fontWeight: 700,
      padding: '3px 8px', borderRadius: '999px',
      background: bg, color,
      border: `1px solid ${color}30`,
      display: 'inline-flex', alignItems: 'center', gap: '4px',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      {label}
    </div>
  );
};

const formatKbDisplayId = (match, fallback) => {
  const rawId = String(match?.kb_id || match?.id || '').trim();
  const normalized = rawId.toLowerCase();
  const trueMatch = normalized.match(/^(?:co_)?(?:seed_)?true_(\d+)$/);
  const falseMatch = normalized.match(/^(?:co_)?(?:seed_)?false_(\d+)$/);

  if (trueMatch) return `true_${trueMatch[1].padStart(3, '0')}`;
  if (falseMatch) return `false_${falseMatch[1].padStart(3, '0')}`;
  return rawId || fallback;
};

const AdminDashboard = () => {
  const { user } = useAuth();
  const tenantId = user?.tenant_id;

  const [incidents, setIncidents] = useState([]);
  const [allIncidents, setAllIncidents] = useState([]);
  const [stats, setStats] = useState(null);
  const [kbTrueEntries, setKbTrueEntries] = useState([]);
  const [kbFalseEntries, setKbFalseEntries] = useState([]);
  const [tenantWorkflows, setTenantWorkflows] = useState([]);
  const [availableAgents, setAvailableAgents] = useState([]);
  const [allAgents, setAllAgents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [mainTab, setMainTab] = useState('home');

  const formatDateForExcel = (dateString) => {
    if (!dateString) return '';

    const date = new Date(dateString);
    const day = String(date.getDate()).padStart(2, '0');
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[date.getMonth()];
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${day}-${month}-${year} ${hours}:${minutes}`;
  };

  const exportIncidentsToExcel = () => {
    if (incidents.length === 0) return;

    // Sort incidents by created_at descending (latest first)
    const sortedIncidents = [...incidents].sort((a, b) =>
      new Date(b.created_at) - new Date(a.created_at)
    );

    // Prepare data for export
    const exportData = sortedIncidents.map(incident => ({
      'Reference ID': incident.reference_id || 'N/A',
      'Incident ID': incident.incident_id,
      'Reported By': incident.user_name || incident.user_phone || 'N/A',
      'Workflow Classification': incident.outcome || 'Pending',
      'KB Classification': incident.kb_match_type || 'N/A',
      'Status': incident.status,
      'Created At': formatDateForExcel(incident.created_at)
    }));

    // Convert to CSV
    const headers = Object.keys(exportData[0]);
    const csvContent = [
      headers.join(','),
      ...exportData.map(row =>
        headers.map(header => {
          const value = row[header];
          // Escape commas and quotes in values
          if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
            return `"${value.replace(/"/g, '""')}"`;
          }
          return value;
        }).join(',')
      )
    ].join('\n');

    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    const timestamp = new Date().toISOString().slice(0, 10);
    const filename = `company_incidents_${filter}_${timestamp}.csv`;

    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };
  const [filter, setFilter] = useState('all');
  const [dateRange, setDateRange] = useState('30d');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [page, setPage] = useState(1);
  const ITEMS_PER_PAGE = 10;
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [trackedAgent, setTrackedAgent] = useState(null);

  const [assigningAgentIncidentId, setAssigningAgentIncidentId] = useState(null);
  const [selectedAgentId, setSelectedAgentId] = useState('');

  const [resolvingIncidentId, setResolvingIncidentId] = useState(null);
  const [resolutionNotes, setResolutionNotes] = useState('');

  // Company approval modal
  const [approvingIncidentId, setApprovingIncidentId] = useState(null);
  const [approvingIncident, setApprovingIncident] = useState(null);
  const [approvalNotes, setApprovalNotes] = useState('');
  const [opsTab, setOpsTab] = useState('assistance');
  const [opsRequests, setOpsRequests] = useState({ assistance_requests: [], item_requests: [] });
  const [opsActionBusy, setOpsActionBusy] = useState('');
  const [selectedOpsRequest, setSelectedOpsRequest] = useState(null);

  // Backup assignment modal
  const [assignBackupModal, setAssignBackupModal] = useState(null);
  const [selectedBackupAgentId, setSelectedBackupAgentId] = useState('');

  // Item dispatch modal
  const [itemDispatchModal, setItemDispatchModal] = useState(null);
  const [dispatchEta, setDispatchEta] = useState('');
  const [warehouseNotes, setWarehouseNotes] = useState('');

  // Customer notification modal
  const [customerNotifModal, setCustomerNotifModal] = useState(null);
  const [notifMessage, setNotifMessage] = useState('');

  // Incident detail modal
  const [detailIncident, setDetailIncident] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedOutcomeDrilldown, setSelectedOutcomeDrilldown] = useState(null);
  const [expandedKbEntry, setExpandedKbEntry] = useState(null);
  const [kbReviewBusy, setKbReviewBusy] = useState('');

  const [toast, setToast] = useState(null);

  useEffect(() => {
    fetchData();
  }, [tenantId]);

  useEffect(() => {
    setIncidents(filterCompanyIncidentsByTab(allIncidents, filter));
  }, [allIncidents, filter]);

  // Auto-refresh ops data every 30s
  useEffect(() => {
    if (mainTab !== 'operations') return undefined;
    const timer = setInterval(() => fetchData({ background: true }), 30000);
    return () => clearInterval(timer);
  }, [mainTab, tenantId]);

  const fetchData = async (options = {}) => {
    const { background = false } = options;
    try {
      if (background) setRefreshing(true);
      else setLoading(true);

      // Load essential data first (fast)
      const [
        allIncidentsData,
        statsData,
        availableAgentsData,
        allAgentsData,
        opsData,
        workflowData,
      ] = await Promise.all([
        getCompanyIncidents(tenantId),
        getCompanyStats(tenantId),
        getAvailableAgents().catch(() => ({ agents: [] })),
        getAllAgents().catch(() => ({ agents: [] })),
        getCompanyOpsRequests(tenantId).catch(() => ({ assistance_requests: [], item_requests: [] })),
        getTenantWorkflows(tenantId).catch(() => []),
      ]);

      const allLoadedIncidents = allIncidentsData.incidents || [];
      setAllIncidents(allLoadedIncidents);
      setStats(statsData || null);
      setKbTrueEntries([]);
      setKbFalseEntries([]);
      setTenantWorkflows(Array.isArray(workflowData) ? workflowData : workflowData?.workflows || []);
      setAvailableAgents(availableAgentsData.agents || []);
      setAllAgents(allAgentsData.agents || []);
      setOpsRequests({
        assistance_requests: opsData.assistance_requests || [],
        item_requests: opsData.item_requests || [],
      });

      if (selectedIncident) {
        const latestSelected = allLoadedIncidents.find(
          (incident) => incident.incident_id === selectedIncident.incident_id
        );
        setSelectedIncident(latestSelected || null);
      }

      // Load KB data in background (lazy load, not blocking)
      if (!background) {
        Promise.all([
          getTrueIncidentsKB(1, 100, tenantId).catch(() => ({ items: [] })),
          getFalseIncidentsKB(1, 100, tenantId).catch(() => ({ items: [] })),
        ]).then(([trueKbData, falseKbData]) => {
          setKbTrueEntries(trueKbData.items || []);
          setKbFalseEntries(falseKbData.items || []);
        });
      }
    } catch {
      showToast('Failed to load dashboard data', 'error');
    } finally {
      if (background) setRefreshing(false);
      else setLoading(false);
    }
  };

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3200);
  };

  const handleAssignAgent = async () => {
    if (!assigningAgentIncidentId || !selectedAgentId) {
      showToast('Select an agent to dispatch', 'error');
      return;
    }

    try {
      await assignAgent(assigningAgentIncidentId, selectedAgentId);
      showToast('Agent dispatched successfully');
      setAssigningAgentIncidentId(null);
      setSelectedAgentId('');
      fetchData({ background: true });
    } catch {
      showToast('Failed to assign agent', 'error');
    }
  };

  const handleResolveIncident = async () => {
    if (!resolvingIncidentId) return;

    try {
      await resolveIncident(
        resolvingIncidentId,
        user?.user_id || 'company_user',
        resolutionNotes,
        {
          checklist: {
            rootCause: 'Admin closure validation',
            actionsTaken: [resolutionNotes || 'Resolved after field completion review'],
            verificationEvidence: 'Admin dashboard closure',
            verificationResult: 'PASS',
            safetyChecksCompleted: true,
            handoffConfirmed: true,
          },
        }
      );

      showToast('Incident marked as resolved');
      setResolvingIncidentId(null);
      setResolutionNotes('');
      fetchData({ background: true });
    } catch {
      showToast('Failed to resolve incident', 'error');
    }
  };

  const handleOpenApproval = (inc) => {
    setApprovingIncidentId(inc.incident_id);
    setApprovingIncident(inc);
    setApprovalNotes('');
  };

  const handleApproveResolution = async () => {
    if (!approvingIncidentId) return;
    try {
      await approveResolution(
        approvingIncidentId,
        user?.user_id || 'company_user',
        approvalNotes || undefined
      );
      showToast('Resolution approved successfully');
      setApprovingIncidentId(null);
      setApprovingIncident(null);
      setApprovalNotes('');
      fetchData({ background: true });
    } catch {
      showToast('Failed to approve resolution', 'error');
    }
  };

  const handleValidate = async (incidentId, options = {}) => {
    const { silent = false, keepModalOpen = false } = options;
    try {
      setKbReviewBusy('validate');
      await validateIncident(incidentId);
      await fetchData({ background: true });
      try {
        const fresh = await getIncident(incidentId);
        if (keepModalOpen || detailIncident?.incident_id === incidentId) {
          setDetailIncident(fresh);
        } else {
          setDetailIncident(fresh);
        }
      } catch {
        // ignore detail refresh failure
      }
      if (!silent) {
        showToast('KB validation complete - review results below', 'info');
      }
    } catch (error) {
      showToast(error?.message || 'Failed to validate incident', 'error');
    } finally {
      setKbReviewBusy('');
    }
  };

  const handleMarkFalse = async (incidentId) => {
    try {
      setKbReviewBusy('false');
      await markIncidentFalse(incidentId, 'Marked as false report by reviewer');
      showToast('Incident marked as false report - syncing to external system', 'success');
      setDetailIncident(null);
      fetchData({ background: true });
    } catch (error) {
      showToast(error?.message || 'Failed to mark incident as false report', 'error');
    } finally {
      setKbReviewBusy('');
    }
  };

  const handleConfirmValid = async (incidentId) => {
    try {
      setKbReviewBusy('confirm');
      await confirmIncidentValid(incidentId);
      showToast('Incident confirmed valid - ready for agent assignment', 'success');
      setDetailIncident(null);
      fetchData({ background: true });
    } catch (error) {
      showToast(error?.message || 'Failed to confirm incident', 'error');
    } finally {
      setKbReviewBusy('');
    }
  };

  const handleOpsRequestUpdate = async (kind, incidentId, requestId, status, extra = {}) => {
    try {
      const busyKey = `${kind}:${requestId}`;
      setOpsActionBusy(busyKey);
      if (kind === 'assistance') {
        await updateAssistanceRequest(incidentId, requestId, {
          status,
          updated_by: user?.user_id || 'company_user',
          note: `Updated from operations center to ${status}`,
        });
      } else {
        await updateItemRequest(incidentId, requestId, {
          status,
          updated_by: user?.user_id || 'company_user',
          note: `Updated from operations center to ${status}`,
          ...extra,
        });
      }
      showToast('Request updated successfully');
      fetchData({ background: true });
    } catch {
      showToast('Failed to update request', 'error');
    } finally {
      setOpsActionBusy('');
    }
  };

  const handleAssignBackup = async () => {
    if (!assignBackupModal || !selectedBackupAgentId) return;
    try {
      await assignBackupAgent(
        assignBackupModal.incidentId,
        assignBackupModal.requestId,
        {
          agent_id: selectedBackupAgentId,
          assigned_by: user?.user_id || 'company_user',
          role: assignBackupModal.requestType || 'backup',
        }
      );
      showToast('Backup engineer assigned successfully');
      setAssignBackupModal(null);
      setSelectedBackupAgentId('');
      fetchData({ background: true });
    } catch (error) {
      showToast(error.message || 'Failed to assign backup', 'error');
    }
  };

  const handleDispatchItem = async () => {
    if (!itemDispatchModal) return;
    try {
      await updateItemRequest(
        itemDispatchModal.incidentId,
        itemDispatchModal.requestId,
        {
          status: 'DISPATCHED',
          updated_by: user?.user_id || 'company_user',
          note: warehouseNotes || 'Dispatched from warehouse',
          eta_minutes: dispatchEta ? parseInt(dispatchEta, 10) : null,
          warehouse_notes: warehouseNotes || null,
        }
      );
      showToast('Item dispatched with ETA');
      setItemDispatchModal(null);
      setDispatchEta('');
      setWarehouseNotes('');
      fetchData({ background: true });
    } catch (error) {
      showToast('Failed to dispatch item', 'error');
    }
  };

  const handleSendCustomerNotification = async () => {
    if (!customerNotifModal || !notifMessage.trim()) return;
    try {
      await createCustomerNotification(customerNotifModal.incidentId, {
        notification_type: 'delay_notice',
        title: 'Update from Operations',
        message: notifMessage,
        severity: 'info',
      });
      showToast('Customer notification sent');
      setCustomerNotifModal(null);
      setNotifMessage('');
    } catch (error) {
      showToast('Failed to send notification', 'error');
    }
  };

  const handleIncidentRowClick = async (incident) => {
    setSelectedIncident(incident); // Keep map selection working
    try {
      setDetailLoading(true);
      const fullData = await getIncident(incident.incident_id);
      setDetailIncident(fullData || incident);
    } catch {
      // Fallback: show list-level data in modal
      setDetailIncident(incident);
    } finally {
      setDetailLoading(false);
    }
  };

  const getStatusMeta = (status) => {
    const map = {
      new: { label: 'New', bg: '#e0f2fe', text: '#075985', dot: '#0284c7' },
      submitted: { label: 'Submitted', bg: '#ecfeff', text: '#0e7490', dot: '#0891b2' },
      classifying: { label: 'Classifying', bg: '#f3e8ff', text: '#7e22ce', dot: '#9333ea' },
      in_progress: { label: 'In Progress', bg: '#fff7ed', text: '#b45309', dot: '#d97706' },
      analyzing: { label: 'Analyzing', bg: '#fff7ed', text: '#b45309', dot: '#d97706' },
      pending_company_action: { label: 'Pending Action', bg: '#fef2f2', text: '#b91c1c', dot: '#dc2626' },
      dispatched: { label: 'Agent Dispatched', bg: '#ecfdf5', text: '#047857', dot: '#059669' },
      resolved: { label: 'Resolved', bg: '#ecfdf5', text: '#047857', dot: '#059669' },
      completed: { label: 'Completed', bg: '#ecfdf5', text: '#047857', dot: '#059669' },
    };

    return map[status] || { label: status || 'Unknown', bg: '#f1f5f9', text: '#475569', dot: '#64748b' };
  };

  const getRiskMeta = (score = 0) => {
    if (score >= 0.8) return { label: 'Critical', color: '#b91c1c', bg: '#fef2f2' };
    if (score >= 0.5) return { label: 'High', color: '#b45309', bg: '#fff7ed' };
    if (score >= 0.3) return { label: 'Medium', color: '#a16207', bg: '#fef9c3' };
    return { label: 'Low', color: '#047857', bg: '#ecfdf5' };
  };

  const formatDateTime = (value) => {
    if (!value) return 'N/A';

    return new Date(value).toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    });
  };

  const formatCategoryLabel = (value) => {
    if (!value) return 'Unknown';
    return value
      .replaceAll('_', ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  };

  const getPercent = (value, total) => {
    if (!total) return 0;
    return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
  };

  const getRangeBounds = () => {
    const end = customEndDate ? new Date(`${customEndDate}T23:59:59`) : new Date();
    if (dateRange === 'custom' && customStartDate) {
      return {
        start: new Date(`${customStartDate}T00:00:00`),
        end,
      };
    }

    const dayMap = { '7d': 7, '30d': 30, '90d': 90 };
    const days = dayMap[dateRange] || 30;
    const start = new Date(end);
    start.setDate(end.getDate() - days + 1);
    start.setHours(0, 0, 0, 0);
    return { start, end };
  };

  const isWithinRange = (value, start, end) => {
    if (!value) return false;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return false;
    return parsed >= start && parsed <= end;
  };

  const getPreviousRangeBounds = () => {
    const { start, end } = getRangeBounds();
    const durationMs = Math.max(86400000, end.getTime() - start.getTime() + 1);
    const prevEnd = new Date(start.getTime() - 1);
    const prevStart = new Date(prevEnd.getTime() - durationMs + 1);
    return { start: prevStart, end: prevEnd };
  };

  const formatDurationLabel = (items) => {
    if (!items.length) return 'No dwell data';
    const avgMs = items.reduce((sum, incident) => {
      const created = new Date(incident.created_at || Date.now());
      return sum + Math.max(0, Date.now() - created.getTime());
    }, 0) / items.length;
    const hours = avgMs / 3600000;
    if (hours >= 24) return `${(hours / 24).toFixed(1)}d avg age`;
    if (hours >= 1) return `${hours.toFixed(1)}h avg age`;
    return `${Math.max(1, Math.round(avgMs / 60000))}m avg age`;
  };

  const countSymptomSignals = (incident) => {
    const sd = incident.structured_data || {};
    const keys = ['symptoms', 'co_symptoms', 'co_alarm', 'co_alarm_triggered', 'hissing_sound', 'meter_moving', 'is_evacuated'];
    return keys.reduce((sum, key) => {
      const value = sd[key];
      return sum + (value === true || value === 'yes' || value === 'Yes' ? 1 : 0);
    }, 0);
  };

  const totalOpsCount = (opsRequests.assistance_requests?.length || 0) + (opsRequests.item_requests?.length || 0);
  const breachedCount = useMemo(() => {
    const ar = (opsRequests.assistance_requests || []).filter((r) => r.sla_status === 'breached').length;
    const ir = (opsRequests.item_requests || []).filter((r) => r.sla_status === 'breached').length;
    return ar + ir;
  }, [opsRequests]);

  const dashboardInsights = useMemo(() => {
    const range = getRangeBounds();
    const previousRange = getPreviousRangeBounds();
    const filteredIncidents = allIncidents.filter((incident) => isWithinRange(incident.created_at, range.start, range.end));
    const previousIncidents = allIncidents.filter((incident) => isWithinRange(incident.created_at, previousRange.start, previousRange.end));
    const filteredTrueKb = kbTrueEntries.filter((entry) => isWithinRange(entry.created_at, range.start, range.end));
    const filteredFalseKb = kbFalseEntries.filter((entry) => isWithinRange(entry.created_at, range.start, range.end));
    const filteredWorkflows = tenantWorkflows.filter((workflow) => {
      if (!workflow.created_at) return true;
      return isWithinRange(workflow.created_at, range.start, range.end);
    });

    const stageBuckets = {
      New: filteredIncidents.filter((incident) => ['new', 'classifying', 'analyzing'].includes(incident.status)),
      'In Progress': filteredIncidents.filter((incident) => ['in_progress', 'waiting_input', 'paused'].includes(incident.status)),
      'Pending Action': filteredIncidents.filter((incident) => incident.status === 'pending_company_action'),
      Dispatched: filteredIncidents.filter((incident) => incident.status === 'dispatched'),
      'Pending Review': filteredIncidents.filter((incident) => incident.status === 'resolved'),
      Completed: filteredIncidents.filter((incident) => incident.status === 'completed'),
    };

    const statusMix = Object.entries(stageBuckets).map(([label, items], index) => ({
      label,
      value: items.length,
      color: ['#2563eb', '#0f766e', '#dc2626', '#7c3aed', '#059669', '#334155'][index],
      subLabel: formatDurationLabel(items),
    }));

    const riskMix = [
      { label: 'Critical', value: 0, color: '#b91c1c' },
      { label: 'High', value: 0, color: '#c2410c' },
      { label: 'Medium', value: 0, color: '#ca8a04' },
      { label: 'Low', value: 0, color: '#15803d' },
    ];

    const validationCounts = {
      'True KB Match': filteredIncidents.filter((incident) => incident.kb_match_type === 'true').length,
      'False KB Match': filteredIncidents.filter((incident) => incident.kb_match_type === 'false').length,
      'Admin Confirmed': filteredIncidents.filter((incident) => incident.kb_match_type === 'admin_confirmed').length,
      Unvalidated: filteredIncidents.filter((incident) => !incident.kb_match_type).length,
    };

    const validationMix = [
      { label: 'True KB Match', value: validationCounts['True KB Match'], color: '#047857' },
      { label: 'False KB Match', value: validationCounts['False KB Match'], color: '#b91c1c' },
      { label: 'Admin Confirmed', value: validationCounts['Admin Confirmed'], color: '#2563eb' },
      { label: 'Unvalidated', value: validationCounts.Unvalidated, color: '#94a3b8' },
    ];

    const useCaseCounts = {};
    const outcomeCounts = {};
    const riskHeatmap = {
      Critical: { New: 0, 'In Progress': 0, 'Pending Action': 0, Dispatched: 0, 'Pending Review': 0, Completed: 0 },
      High: { New: 0, 'In Progress': 0, 'Pending Action': 0, Dispatched: 0, 'Pending Review': 0, Completed: 0 },
      Medium: { New: 0, 'In Progress': 0, 'Pending Action': 0, Dispatched: 0, 'Pending Review': 0, Completed: 0 },
      Low: { New: 0, 'In Progress': 0, 'Pending Action': 0, Dispatched: 0, 'Pending Review': 0, Completed: 0 },
    };

    filteredIncidents.forEach((incident) => {
      const riskScore = incident.risk_score ?? 0;
      const riskBand = riskScore >= 0.8 ? 'Critical' : riskScore >= 0.5 ? 'High' : riskScore >= 0.3 ? 'Medium' : 'Low';
      const statusBand = ['new', 'classifying', 'analyzing'].includes(incident.status)
        ? 'New'
        : ['in_progress', 'waiting_input', 'paused'].includes(incident.status)
          ? 'In Progress'
          : incident.status === 'pending_company_action'
            ? 'Pending Action'
            : incident.status === 'dispatched'
              ? 'Dispatched'
              : incident.status === 'resolved'
                ? 'Pending Review'
                : 'Completed';
      const riskMetaIndex = riskMix.findIndex((item) => item.label === riskBand);
      if (riskMetaIndex >= 0) riskMix[riskMetaIndex].value += 1;
      riskHeatmap[riskBand][statusBand] += 1;

      const useCase = incident.incident_type || incident.classified_use_case || 'unclassified';
      useCaseCounts[useCase] = (useCaseCounts[useCase] || 0) + 1;

      const outcome = incident.outcome || 'pending_decision';
      outcomeCounts[outcome] = (outcomeCounts[outcome] || 0) + 1;
    });

    const topUseCases = Object.entries(useCaseCounts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5)
      .map(([label, value]) => ({ label: formatCategoryLabel(label), value, color: '#0f766e' }));

    const decisionMix = Object.entries(outcomeCounts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 6)
      .map(([label, value], index) => ({
        label: formatCategoryLabel(label),
        value,
        color: ['#2563eb', '#7c3aed', '#047857', '#b45309', '#64748b', '#0f766e'][index] || '#64748b',
      }));

    const validatedIncidents = filteredIncidents.filter((incident) => Boolean(incident.kb_match_type)).length;
    const currentTrueValidation = validationCounts['True KB Match'];
    const previousTrueValidation = previousIncidents.filter((incident) => incident.kb_match_type === 'true').length;
    const currentFalseValidation = validationCounts['False KB Match'];
    const previousFalseValidation = previousIncidents.filter((incident) => incident.kb_match_type === 'false').length;
    const trendDelta = (current, previous) => {
      if (!previous) return current ? 100 : 0;
      return Math.round(((current - previous) / previous) * 100);
    };

    const buildLineSeries = (days) => {
      const labels = [];
      const trueSeries = [];
      const falseSeries = [];
      const end = range.end;
      for (let index = days - 1; index >= 0; index -= 1) {
        const bucketStart = new Date(end);
        bucketStart.setDate(end.getDate() - index);
        bucketStart.setHours(0, 0, 0, 0);
        const bucketEnd = new Date(bucketStart);
        bucketEnd.setHours(23, 59, 59, 999);
        labels.push(`${bucketStart.getDate()}/${bucketStart.getMonth() + 1}`);
        trueSeries.push(filteredTrueKb.filter((entry) => isWithinRange(entry.created_at, bucketStart, bucketEnd)).length);
        falseSeries.push(filteredFalseKb.filter((entry) => isWithinRange(entry.created_at, bucketStart, bucketEnd)).length);
      }
      return { labels, series: [{ label: 'True', values: trueSeries, color: '#10b981' }, { label: 'False', values: falseSeries, color: '#ef4444' }] };
    };

    return {
      rangeLabel: `${range.start.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })} - ${range.end.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}`,
      filteredIncidents,
      statusMix,
      funnelSteps: statusMix,
      riskMix,
      riskHeatmap,
      validationMix,
      topUseCases,
      decisionMix,
      workflowCount: filteredWorkflows.length,
      workflowUseCases: new Set(filteredWorkflows.map((workflow) => workflow.use_case).filter(Boolean)).size,
      kbTrue: filteredTrueKb.length,
      kbFalse: filteredFalseKb.length,
      validatedIncidents,
      validationRate: getPercent(validatedIncidents, filteredIncidents.length),
      donutSegments: [
        { label: 'True', value: currentTrueValidation, color: '#10b981' },
        { label: 'False', value: currentFalseValidation, color: '#ef4444' },
        { label: 'Unvalidated', value: validationCounts.Unvalidated, color: '#94a3b8' },
      ],
      trueTrendDelta: trendDelta(currentTrueValidation, previousTrueValidation),
      falseTrendDelta: trendDelta(currentFalseValidation, previousFalseValidation),
      kbTrendLine: buildLineSeries(Math.min(dateRange === '7d' ? 7 : dateRange === '90d' ? 12 : 10, 12)),
      statsCards: [
        { label: 'Verified Incidents', value: filteredIncidents.length - currentFalseValidation, color: '#030304' },
        { label: 'Pending Action', value: stageBuckets['Pending Action'].length, color: '#b91c1c' },
        { label: 'Dispatched', value: stageBuckets.Dispatched.length, color: '#8b5cf6' },
        { label: 'Resolved', value: stageBuckets['Pending Review'].length + stageBuckets.Completed.length, color: '#047857' },
        { label: 'Ops Requests', value: totalOpsCount, color: breachedCount > 0 ? '#b91c1c' : '#8b5cf6' },
      ],
    };
  }, [allIncidents, kbFalseEntries, kbTrueEntries, tenantWorkflows, dateRange, customEndDate, customStartDate, totalOpsCount, breachedCount]);

  const getSlaColor = (slaStatus) => {
    if (slaStatus === 'breached') return '#b91c1c';
    if (slaStatus === 'warning') return '#b45309';
    return '#047857';
  };

  const getPriorityMeta = (priority) => {
    const map = {
      CRITICAL: { bg: '#fef2f2', color: '#b91c1c', border: '#fecaca' },
      HIGH: { bg: '#fff7ed', color: '#b45309', border: '#fed7aa' },
      MEDIUM: { bg: '#fef9c3', color: '#a16207', border: '#fde68a' },
      NORMAL: { bg: '#e0f2fe', color: '#075985', border: '#bae6fd' },
      LOW: { bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' },
      URGENT: { bg: '#fef2f2', color: '#b91c1c', border: '#fecaca' },
    };
    return map[(priority || '').toUpperCase()] || map.NORMAL;
  };

  if (loading && allIncidents.length === 0) {
    return (
      <div className="app-shell" style={{ display: 'grid', placeItems: 'center' }}>
        <div className="panel" style={{ maxWidth: '420px', width: '100%', padding: '32px', textAlign: 'center' }}>
          <h3 style={{ marginBottom: '6px' }}>Loading Admin Dashboard</h3>
          <p style={{ margin: 0 }}>Preparing incidents, agents, and operation metrics...</p>
        </div>
      </div>
    );
  }

  // â”€â”€ Render Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  const renderAssistanceActions = (request) => {
    const busy = opsActionBusy === `assistance:${request.request_id}`;
    const btnStyle = { minHeight: '30px', padding: '4px 8px', fontSize: '0.73rem' };
    const isBackupType = ['backup', 'safety_support', 'supervisor'].includes(request.type);

    return (
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
        {request.status === 'PENDING' && isBackupType && (
          <button
            type="button"
            className="primary-btn"
            style={btnStyle}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              setAssignBackupModal({
                incidentId: request.incident_id,
                requestId: request.request_id,
                requestType: request.type,
                priority: request.priority,
                incidentDescription: request.incident_description,
                incidentLocation: request.incident_location,
                primaryAgentId: request.agent_id,
                primaryAgent: request.primary_agent_name,
              });
            }}
          >
            Assign Backup
          </button>
        )}
        {request.status === 'PENDING' && !isBackupType && (
          <button type="button" className="secondary-btn" style={btnStyle} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('assistance', request.incident_id, request.request_id, 'ACKNOWLEDGED'); }}>Acknowledge</button>
        )}
        {request.status === 'PENDING' && (
          <button type="button" className="secondary-btn" style={{ ...btnStyle, borderColor: '#fecaca', color: '#b91c1c' }} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('assistance', request.incident_id, request.request_id, 'REJECTED'); }}>Reject</button>
        )}
        {request.status === 'ACKNOWLEDGED' && (
          <button type="button" className="secondary-btn" style={btnStyle} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('assistance', request.incident_id, request.request_id, 'IN_PROGRESS'); }}>Start</button>
        )}
        {request.status === 'IN_PROGRESS' && (
          <button type="button" className="secondary-btn" style={{ ...btnStyle, borderColor: '#8bcfb8', color: '#047857' }} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('assistance', request.incident_id, request.request_id, 'FULFILLED'); }}>Fulfill</button>
        )}
        <button
          type="button"
          className="secondary-btn"
          style={{ ...btnStyle, fontSize: '0.7rem' }}
          onClick={(e) => { e.stopPropagation(); setCustomerNotifModal({ incidentId: request.incident_id }); }}
        >
          Notify Customer
        </button>
      </div>
    );
  };

  const renderItemActions = (request) => {
    const busy = opsActionBusy === `item:${request.request_id}`;
    const btnStyle = { minHeight: '30px', padding: '4px 8px', fontSize: '0.73rem' };

    return (
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '8px' }}>
        {request.status === 'REQUESTED' && (
          <>
            <button type="button" className="primary-btn" style={btnStyle} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('item', request.incident_id, request.request_id, 'APPROVED'); }}>Approve</button>
            <button type="button" className="secondary-btn" style={{ ...btnStyle, borderColor: '#fecaca', color: '#b91c1c' }} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('item', request.incident_id, request.request_id, 'REJECTED'); }}>Reject</button>
          </>
        )}
        {request.status === 'APPROVED' && (
          <button
            type="button"
            className="primary-btn"
            style={btnStyle}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              setItemDispatchModal({
                incidentId: request.incident_id,
                requestId: request.request_id,
                itemName: request.item_name,
                quantity: request.quantity,
              });
            }}
          >
            Dispatch with ETA
          </button>
        )}
        {request.status === 'DISPATCHED' && (
          <button type="button" className="secondary-btn" style={{ ...btnStyle, borderColor: '#8bcfb8', color: '#047857' }} disabled={busy} onClick={(e) => { e.stopPropagation(); handleOpsRequestUpdate('item', request.incident_id, request.request_id, 'DELIVERED'); }}>Mark Delivered</button>
        )}
        <button
          type="button"
          className="secondary-btn"
          style={{ ...btnStyle, fontSize: '0.7rem' }}
          onClick={(e) => { e.stopPropagation(); setCustomerNotifModal({ incidentId: request.incident_id }); }}
        >
          Notify Customer
        </button>
      </div>
    );
  };

  const renderOpsRequestCard = (request, kind) => {
    const isSelected = selectedOpsRequest?.request_id === request.request_id;
    const slaColor = getSlaColor(request.sla_status);
    const prioMeta = getPriorityMeta(request.priority || request.urgency);

    return (
      <article
        key={request.request_id}
        className="panel-soft"
        style={{
          padding: '12px 14px',
          borderRadius: '14px',
          border: isSelected ? '2px solid #030304' : '1px solid #d4e2ef',
          borderLeft: `4px solid ${slaColor}`,
          cursor: 'pointer',
          background: isSelected ? '#eef6fd' : request.sla_status === 'breached' ? '#fef8f8' : '#fff',
          transition: 'all 0.15s ease',
        }}
        onClick={() => setSelectedOpsRequest(request)}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 700, color: '#345473', fontSize: '0.82rem' }}>
                {formatIncidentId(request.incident_id)}
              </span>
              <span style={{
                padding: '2px 7px', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700,
                background: prioMeta.bg, color: prioMeta.color, border: `1px solid ${prioMeta.border}`,
              }}>
                {request.priority || request.urgency}
              </span>
              {kind === 'assistance' && (
                <span style={{ fontSize: '0.78rem', color: '#5f738a', fontWeight: 600 }}>
                  {(request.type || 'general').replaceAll('_', ' ')}
                </span>
              )}
              {kind === 'item' && (
                <span style={{ fontSize: '0.78rem', color: '#5f738a', fontWeight: 600 }}>
                  {request.item_name} x{request.quantity}
                </span>
              )}
            </div>
            <div style={{ fontSize: '0.78rem', color: '#7f93aa', marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {kind === 'assistance' ? request.reason : request.notes || 'No notes'}
            </div>
            {request.primary_agent_name && (
              <div style={{ fontSize: '0.74rem', color: '#030304', marginTop: '3px' }}>
                Agent: {request.primary_agent_name} | {request.user_name || 'Unknown user'}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px', flexShrink: 0 }}>
            <SlaIndicator deadline={request.sla_deadline_at} slaStatus={request.sla_status} />
            <span style={{
              padding: '2px 7px', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700,
              background: request.status === 'PENDING' || request.status === 'REQUESTED' ? '#fff7ed' : '#e0f2fe',
              color: request.status === 'PENDING' || request.status === 'REQUESTED' ? '#b45309' : '#075985',
            }}>
              {request.status}
            </span>
          </div>
        </div>

        {kind === 'assistance' ? renderAssistanceActions(request) : renderItemActions(request)}
      </article>
    );
  };

  const renderOpsDetailPanel = () => {
    if (!selectedOpsRequest) {
      return (
        <div style={{ display: 'grid', placeItems: 'center', height: '100%', textAlign: 'center', padding: '22px' }}>
          <div>
            <h3 style={{ marginBottom: '6px', color: '#7f93aa' }}>Select a Request</h3>
            <p style={{ margin: 0, color: '#a3b5c7', fontSize: '0.86rem' }}>Click on a request card to view full details and incident context.</p>
          </div>
        </div>
      );
    }

    const req = selectedOpsRequest;
    const riskMeta = getRiskMeta(req.risk_score || 0);

    return (
      <div style={{ display: 'grid', gap: '10px', overflow: 'auto' }}>
        <div>
          <h3 style={{ margin: '0 0 8px', fontSize: '1rem' }}>Request Detail</h3>
          <div style={{ display: 'grid', gap: '6px', fontSize: '0.84rem' }}>
            <div><strong>Request ID:</strong> {req.request_id}</div>
            <div><strong>Type:</strong> {req.kind === 'assistance' ? (req.type || 'general').replaceAll('_', ' ') : 'Item Order'}</div>
            <div><strong>Status:</strong> {req.status}</div>
            {req.kind === 'assistance' && <div><strong>Reason:</strong> {req.reason}</div>}
            {req.kind === 'assistance' && req.details && <div><strong>Details:</strong> {req.details}</div>}
            {req.kind === 'item' && <div><strong>Item:</strong> {req.item_name} x{req.quantity}</div>}
            {req.kind === 'item' && req.notes && <div><strong>Notes:</strong> {req.notes}</div>}
            {req.assigned_agent_name && <div><strong>Assigned Backup:</strong> {req.assigned_agent_name}</div>}
            {req.estimated_delivery_at && <div><strong>ETA:</strong> {formatDateTime(req.estimated_delivery_at)}</div>}
            {req.warehouse_notes && <div><strong>Warehouse:</strong> {req.warehouse_notes}</div>}
          </div>
        </div>

        <div className="panel-soft" style={{ padding: '10px', borderRadius: '12px' }}>
          <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#030304', marginBottom: '6px' }}>Incident Context</div>
          <div style={{ display: 'grid', gap: '4px', fontSize: '0.82rem', color: '#4d6178' }}>
            <div><strong>Incident:</strong> {formatIncidentId(req.incident_id)}</div>
            <div><strong>Type:</strong> {(req.incident_type || 'N/A').replaceAll('_', ' ')}</div>
            <div><strong>User:</strong> {req.user_name || 'N/A'} {req.user_phone ? `(${req.user_phone})` : ''}</div>
            <div><strong>Location:</strong> {req.incident_location || 'N/A'}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <strong>Risk:</strong>
              <span style={{ padding: '1px 6px', borderRadius: '999px', fontSize: '0.72rem', fontWeight: 700, background: riskMeta.bg, color: riskMeta.color }}>
                {riskMeta.label} {((req.risk_score || 0) * 100).toFixed(0)}%
              </span>
            </div>
            {req.primary_agent_name && <div><strong>Primary Agent:</strong> {req.primary_agent_name}</div>}
          </div>
          {req.incident_description && (
            <p style={{ margin: '6px 0 0', fontSize: '0.8rem', color: '#5f738a' }}>{req.incident_description}</p>
          )}
        </div>

        {(req.history || []).length > 0 && (
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#030304', marginBottom: '6px' }}>History</div>
            <div style={{ display: 'grid', gap: '4px' }}>
              {(req.history || []).slice().reverse().map((entry, i) => (
                <div key={i} style={{ fontSize: '0.78rem', color: '#5f738a', display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                  <span><strong>{entry.status}</strong> {entry.note && `- ${entry.note}`}</span>
                  <span style={{ color: '#a3b5c7', flexShrink: 0 }}>{entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : ''}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  // â”€â”€ Incidents Tab Content â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  const renderIncidentSwipeLane = () => {
    const featuredIncidents = incidents
      .slice()
      .sort((left, right) => {
        const leftTime = left?.created_at ? new Date(left.created_at).getTime() : 0;
        const rightTime = right?.created_at ? new Date(right.created_at).getTime() : 0;
        return rightTime - leftTime;
      })
      .slice(0, 8);

    if (featuredIncidents.length === 0) {
      return null;
    }

    return (
      <div className="panel-soft" style={{ padding: '12px', borderRadius: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', marginBottom: '10px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>Incident Lane</div>
            <h3 style={{ margin: '4px 0 0', fontSize: '0.98rem' }}>Swipe Through Active Cases</h3>
          </div>
          <div style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600 }}>Swipe horizontally on touch devices</div>
        </div>

        <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '6px', scrollSnapType: 'x proximity' }}>
          {featuredIncidents.map((incident) => {
            const riskMeta = getRiskMeta(incident.risk_score ?? 0);
            const statusMeta = getStatusMeta(incident.status);
            return (
              <button
                key={incident.incident_id}
                type="button"
                onClick={() => handleIncidentRowClick(incident)}
                style={{
                  minWidth: '270px',
                  maxWidth: '270px',
                  padding: '14px',
                  borderRadius: '16px',
                  border: '1px solid #d5e2ee',
                  background: '#fff',
                  textAlign: 'left',
                  cursor: 'pointer',
                  display: 'grid',
                  gap: '8px',
                  scrollSnapAlign: 'start',
                  boxShadow: '0 10px 22px -20px rgba(15, 23, 42, 0.4)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 800, color: '#345473', fontSize: '0.82rem' }}>
                      {formatIncidentId(incident.incident_id)}
                    </div>
                    <div style={{ marginTop: '3px', color: '#0f172a', fontSize: '0.9rem', fontWeight: 700 }}>
                      {formatCategoryLabel(incident.incident_type || incident.classified_use_case || 'unclassified')}
                    </div>
                  </div>
                  <span style={{ padding: '3px 8px', borderRadius: '999px', background: statusMeta.bg, color: statusMeta.text, fontSize: '0.72rem', fontWeight: 800 }}>
                    {statusMeta.label}
                  </span>
                </div>

                <div style={{ fontSize: '0.8rem', color: '#64748b', minHeight: '36px' }}>
                  {incident.user_name || 'Unknown user'} | {incident.user_address || incident.location || 'No location'}
                </div>

                <div style={{ display: 'grid', gap: '4px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.77rem', fontWeight: 700, color: riskMeta.color }}>
                    <span>{riskMeta.label} risk</span>
                    <span>{((incident.risk_score ?? 0) * 100).toFixed(0)}%</span>
                  </div>
                  <div style={{ height: '6px', borderRadius: '999px', background: '#dbe5ef', overflow: 'hidden' }}>
                    <div style={{ width: `${Math.max(4, (incident.risk_score ?? 0) * 100)}%`, height: '100%', borderRadius: '999px', background: riskMeta.color }} />
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', fontSize: '0.76rem' }}>
                  <span style={{ color: '#475569', fontWeight: 700 }}>{formatDateTime(incident.created_at)}</span>
                  <span style={{ color: '#2563eb', fontWeight: 800 }}>Open detail</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  const renderHomeTab = () => (
    <>
      <section className="panel" style={{ padding: '16px', marginBottom: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>Dashboard Range</div>
            <h2 style={{ margin: '6px 0 4px', fontSize: '1.1rem', color: '#0f172a' }}>Operational Intelligence View</h2>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.84rem' }}>
              Filtered to {dashboardInsights.rangeLabel}. Funnel, validation, risk, and outcomes all update together.
            </p>
          </div>
          <DateRangeSelector
            value={dateRange}
            onChange={setDateRange}
            customStart={customStartDate}
            customEnd={customEndDate}
            onCustomStartChange={setCustomStartDate}
            onCustomEndChange={setCustomEndDate}
          />
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '10px', marginBottom: '14px' }}>
        {dashboardInsights.statsCards.map((card) => (
          <article key={card.label} className="kpi-card">
            <div className="kpi-label">{card.label}</div>
            <div className="kpi-value" style={{ color: card.color }}>{card.value}</div>
          </article>
        ))}
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '12px', marginBottom: '14px' }}>
        <article className="panel-soft" style={{ padding: '16px', borderRadius: '18px' }}>
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>Incident Funnel</div>
            <h3 style={{ margin: '6px 0 4px', fontSize: '1rem' }}>Lifecycle Drop-Off</h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.82rem' }}>Shows where cases are concentrating and the average age of incidents still sitting in each stage.</p>
          </div>
          <FunnelChart steps={dashboardInsights.funnelSteps} />
        </article>

        <article className="panel-soft" style={{ padding: '16px', borderRadius: '18px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', marginBottom: '10px' }}>
            <div>
              <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>KB Validation</div>
              <h3 style={{ margin: '6px 0 4px', fontSize: '1rem' }}>True / False / Unvalidated</h3>
            </div>
            <div style={{ display: 'grid', gap: '6px' }}>
              <TrendBadge delta={dashboardInsights.trueTrendDelta} label="true" />
              <TrendBadge delta={dashboardInsights.falseTrendDelta} label="false" />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: '12px', alignItems: 'center' }}>
            <DonutChart
              segments={dashboardInsights.donutSegments}
              centerLabel="Validated"
              centerValue={`${dashboardInsights.validationRate}%`}
            />
            <div style={{ display: 'grid', gap: '10px' }}>
              {dashboardInsights.validationMix.map((item) => (
                <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ width: '11px', height: '11px', borderRadius: '999px', background: item.color, display: 'inline-block' }} />
                    <span style={{ color: '#0f172a', fontSize: '0.84rem', fontWeight: 700 }}>{item.label}</span>
                  </div>
                  <span style={{ color: '#475569', fontSize: '0.82rem', fontWeight: 800 }}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </article>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '12px', marginBottom: '14px' }}>
        <article className="panel-soft" style={{ padding: '16px', borderRadius: '18px' }}>
          <div style={{ marginBottom: '10px' }}>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>KB Trend</div>
            <h3 style={{ margin: '6px 0 4px', fontSize: '1rem' }}>True vs False Pattern Flow</h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.82rem' }}>Pattern additions over the selected range, split into evenly spaced buckets.</p>
          </div>
          <LineTrendChart labels={dashboardInsights.kbTrendLine.labels} series={dashboardInsights.kbTrendLine.series} />
        </article>

        <article className="panel-soft" style={{ padding: '16px', borderRadius: '18px' }}>
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>Risk Heatmap</div>
            <h3 style={{ margin: '6px 0 4px', fontSize: '1rem' }}>Severity by Stage</h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.82rem' }}>Critical cases rise to the top visually so the team can spot concentration immediately.</p>
          </div>
          <HeatmapChart
            rows={['Critical', 'High', 'Medium', 'Low']}
            columns={['New', 'In Progress', 'Pending Action', 'Dispatched', 'Pending Review', 'Completed']}
            values={dashboardInsights.riskHeatmap}
            colorForValue={(row, value) => {
              const palette = {
                Critical: { background: value ? '#fee2e2' : '#f8fafc', border: '#fecaca', color: '#b91c1c', label: value ? 'Hot' : 'Clear' },
                High: { background: value ? '#ffedd5' : '#f8fafc', border: '#fed7aa', color: '#c2410c', label: value ? 'Watch' : 'Clear' },
                Medium: { background: value ? '#fef9c3' : '#f8fafc', border: '#fde68a', color: '#a16207', label: value ? 'Monitor' : 'Clear' },
                Low: { background: value ? '#dcfce7' : '#f8fafc', border: '#bbf7d0', color: '#15803d', label: value ? 'Stable' : 'Clear' },
              };
              return palette[row];
            }}
          />
        </article>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: '0.92fr 1.08fr', gap: '12px', marginBottom: '14px' }}>
        <article className="panel-soft" style={{ padding: '16px', borderRadius: '18px' }}>
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>Outcome Distribution</div>
            <h3 style={{ margin: '6px 0 4px', fontSize: '1rem' }}>Clickable Decision Mix</h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.82rem' }}>Click any outcome to inspect the underlying incidents, workflow route, and symptom intensity.</p>
          </div>

          <div style={{ display: 'grid', gap: '10px' }}>
            {dashboardInsights.decisionMix.length === 0 ? (
              <div style={{ color: '#8ea3b9', fontSize: '0.84rem' }}>Outcome data will appear once incidents are processed.</div>
            ) : dashboardInsights.decisionMix.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => setSelectedOutcomeDrilldown(item.label)}
                style={{
                  border: '1px solid #d7e3ee',
                  background: '#fff',
                  borderRadius: '14px',
                  padding: '12px',
                  cursor: 'pointer',
                  textAlign: 'left',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: '12px',
                }}
              >
                <div>
                  <div style={{ color: '#0f172a', fontSize: '0.86rem', fontWeight: 800 }}>{item.label}</div>
                  <div style={{ color: '#64748b', fontSize: '0.76rem' }}>Open workflow and symptom breakdown</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ width: '12px', height: '12px', borderRadius: '999px', background: item.color, display: 'inline-block' }} />
                  <span style={{ color: '#0f172a', fontSize: '0.96rem', fontWeight: 800 }}>{item.value}</span>
                </div>
              </button>
            ))}
          </div>
        </article>

        <article className="panel-soft" style={{ padding: '16px', borderRadius: '18px' }}>
          <div style={{ marginBottom: '12px' }}>
            <div style={{ fontSize: '0.74rem', letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b', fontWeight: 800 }}>Workflow Reach</div>
            <h3 style={{ margin: '6px 0 4px', fontSize: '1rem' }}>Most Reported Use Cases</h3>
            <p style={{ margin: 0, color: '#64748b', fontSize: '0.82rem' }}>A ranked view of the use cases driving the highest incident volume in the selected period.</p>
          </div>

          <div style={{ display: 'grid', gap: '12px' }}>
            {dashboardInsights.topUseCases.length === 0 ? (
              <div style={{ color: '#8ea3b9', fontSize: '0.84rem' }}>No classified incident types are available yet.</div>
            ) : dashboardInsights.topUseCases.map((item, index) => {
              const maxValue = dashboardInsights.topUseCases[0]?.value || 1;
              const width = getPercent(item.value, maxValue);
              return (
                <div
                  key={item.label}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '16px',
                    background: index === 0 ? 'linear-gradient(135deg, #ecfeff 0%, #f8fafc 100%)' : '#fff',
                    border: `1px solid ${item.color}22`,
                    boxShadow: index === 0 ? '0 16px 28px -24px rgba(15, 118, 110, 0.45)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
                      <div
                        style={{
                          width: '28px',
                          height: '28px',
                          borderRadius: '999px',
                          background: `${item.color}18`,
                          color: item.color,
                          display: 'grid',
                          placeItems: 'center',
                          fontSize: '0.78rem',
                          fontWeight: 800,
                          flexShrink: 0,
                        }}
                      >
                        {index + 1}
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ color: '#0f172a', fontSize: '0.88rem', fontWeight: 800 }}>{item.label}</div>
                        <div style={{ color: '#64748b', fontSize: '0.74rem' }}>
                          {item.value} reported incident{item.value === 1 ? '' : 's'}
                        </div>
                      </div>
                    </div>
                    <div style={{ color: item.color, fontSize: '0.82rem', fontWeight: 800 }}>
                      {getPercent(item.value, dashboardInsights.filteredIncidents.length || item.value)}%
                    </div>
                  </div>

                  <div style={{ height: '12px', borderRadius: '999px', background: '#e2e8f0', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${Math.max(10, width)}%`,
                        height: '100%',
                        borderRadius: '999px',
                        background: index === 0
                          ? 'linear-gradient(90deg, #0f766e 0%, #14b8a6 100%)'
                          : `linear-gradient(90deg, ${item.color} 0%, ${item.color}bb 100%)`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </article>
      </section>

      {renderIncidentSwipeLane()}
    </>
  );

  const renderIncidentsTab = () => {
    const totalPages = Math.max(1, Math.ceil(incidents.length / ITEMS_PER_PAGE));
    const safePage = Math.min(page, totalPages);
    const paginatedIncidents = incidents.slice((safePage - 1) * ITEMS_PER_PAGE, safePage * ITEMS_PER_PAGE);

    return (
      <section className="panel" style={{ padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
          <div className="segmented" style={{ flexWrap: 'wrap' }}>
            {[
              { id: 'new', label: `New (${stats?.new || 0})` },
              { id: 'in_progress', label: `In Progress (${stats?.in_progress || 0})` },
              { id: 'pending', label: `Pending (${stats?.pending || 0})` },
              { id: 'dispatched', label: `Dispatched (${stats?.dispatched || 0})` },
              { id: 'completed', label: `Completed (${stats?.completed || 0})` },
              { id: 'all', label: `All Incidents (${allIncidents.length})` },
            ].map((option) => (
              <button
                key={option.id}
                type="button"
                className={`segment-btn ${filter === option.id ? 'active' : ''}`}
                onClick={() => { setFilter(option.id); setPage(1); }}
              >
                {option.label}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button type="button" className="secondary-btn" onClick={() => fetchData({ background: true })}>
              {refreshing ? 'Refreshing...' : 'Refresh Data'}
            </button>
            <button
              type="button"
              className="secondary-btn"
              onClick={exportIncidentsToExcel}
              disabled={incidents.length === 0}
              style={{
                opacity: incidents.length === 0 ? 0.6 : 1,
                cursor: incidents.length === 0 ? 'not-allowed' : 'pointer'
              }}
            >
              📥 Export
            </button>
          </div>
        </div>

        <div style={{ marginBottom: '14px' }}>
          {renderIncidentSwipeLane()}
        </div>

        <div className="admin-ops-grid" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div className="panel-soft" style={{ padding: '10px', minHeight: '320px', display: 'flex', flexDirection: 'column' }}>
            {incidents.length === 0 ? (
              <div style={{ display: 'grid', placeItems: 'center', flex: 1, textAlign: 'center', padding: '22px' }}>
                <div>
                  <h3 style={{ marginBottom: '6px' }}>
                    {filter === 'new' && 'No New Incidents'}
                    {filter === 'in_progress' && 'No In-Progress Incidents'}
                    {filter === 'pending' && 'No Pending Incidents'}
                    {filter === 'dispatched' && 'No Dispatched Incidents'}
                    {filter === 'resolved' && 'No Incidents Pending Review'}
                    {filter === 'completed' && 'No Completed Incidents'}
                    {filter === 'all' && 'No Incidents Available'}
                  </h3>
                  <p style={{ margin: 0 }}>Try changing filters or wait for new verified incidents.</p>
                </div>
              </div>
            ) : (
              <>
                <div style={{ overflow: 'auto', flex: 1 }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Incident ID</th>
                        <th>Type</th>
                        <th>User</th>
                        <th>Location</th>
                        <th>Risk</th>
                        <th>Status</th>
                        <th>External</th>
                        <th>Created</th>
                        <th>Agent</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedIncidents.map((incident) => {
                        const statusMeta = getStatusMeta(incident.status);
                        const riskScore = incident.risk_score ?? 0;
                        const riskMeta = getRiskMeta(riskScore);
                        const assignedAgent = incident.assigned_agent_id
                          ? allAgents.find((agent) => agent.agent_id === incident.assigned_agent_id)
                          : null;

                        return (
                          <tr key={incident.incident_id} onClick={() => handleIncidentRowClick(incident)} style={{ cursor: 'pointer' }}>
                            <td>
                              <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 700, color: '#345473' }}>
                                {formatIncidentId(incident.incident_id)}
                              </span>
                            </td>
                            <td>{(incident.incident_type || incident.classified_use_case || 'N/A').replaceAll('_', ' ')}</td>
                            <td>
                              <div style={{ fontWeight: 600 }}>{incident.user_name || 'N/A'}</div>
                              <div style={{ fontSize: '0.8rem', color: '#8095ab' }}>{incident.user_phone || 'No phone'}</div>
                            </td>
                            <td>{incident.user_address || incident.location || 'N/A'}</td>
                            <td>
                              <div style={{ minWidth: '120px', border: `1px solid ${riskMeta.color}2a`, borderRadius: '10px', padding: '6px 8px', background: riskMeta.bg }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', fontWeight: 700, color: riskMeta.color }}>
                                  <span>{riskMeta.label}</span>
                                  <span>{(riskScore * 100).toFixed(0)}%</span>
                                </div>
                                <div style={{ height: '5px', background: '#d7e3ee', borderRadius: '999px', overflow: 'hidden', marginTop: '6px' }}>
                                  <div style={{ width: `${Math.max(3, riskScore * 100)}%`, height: '100%', borderRadius: '999px', background: riskMeta.color }} />
                                </div>
                              </div>
                            </td>
                            <td>
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', borderRadius: '999px', padding: '4px 9px', background: statusMeta.bg, color: statusMeta.text, fontSize: '0.76rem', fontWeight: 700 }}>
                                <span style={{ width: '7px', height: '7px', borderRadius: '999px', background: statusMeta.dot }} />
                                {statusMeta.label}
                              </span>
                            </td>
                            <td><SyncStatusBadge externalRef={incident.external_ref} /></td>
                            <td>{formatDateTime(incident.created_at)}</td>
                            <td>
                              {assignedAgent ? (
                                <div style={{ display: 'grid', gap: '4px' }}>
                                  <span style={{ fontSize: '0.82rem', fontWeight: 700 }}>{assignedAgent.full_name}</span>
                                  <button type="button" className="secondary-btn" style={{ padding: '4px 8px', minHeight: '30px', fontSize: '0.74rem' }} onClick={(event) => { event.stopPropagation(); setTrackedAgent({ ...assignedAgent, _ts: Date.now() }); }}>
                                    Track Agent
                                  </button>
                                </div>
                              ) : (
                                <span style={{ color: '#8ea3b9' }}>Unassigned</span>
                              )}
                            </td>
                            <td>
                              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                                {/* External incidents: Validate â†’ Review â†’ Confirm/False flow */}
                                {incident.status === 'new' && incident.external_ref && !incident.kb_match_type && (
                                  <button type="button" className="secondary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px', borderColor: '#93c5fd', color: '#1d4ed8', background: '#eff6ff' }} onClick={(event) => { event.stopPropagation(); handleValidate(incident.incident_id); }}>
                                    Validate
                                  </button>
                                )}
                                {incident.status === 'new' && incident.external_ref && incident.kb_match_type && incident.kb_match_type !== 'admin_confirmed' && (
                                  <button type="button" className="secondary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px', borderColor: '#93c5fd', color: '#1d4ed8', background: '#eff6ff' }} onClick={(event) => { event.stopPropagation(); setDetailIncident(incident); }}>
                                    Review
                                  </button>
                                )}
                                {incident.status === 'new' && incident.kb_match_type && incident.kb_match_type !== 'admin_confirmed' && (
                                  <button type="button" className="secondary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px', borderColor: '#86efac', color: '#047857', background: '#ecfdf5' }} onClick={(event) => { event.stopPropagation(); handleConfirmValid(incident.incident_id); }}>
                                    Confirm Valid
                                  </button>
                                )}
                                {incident.status === 'new' && incident.kb_match_type && incident.kb_match_type !== 'admin_confirmed' && (
                                  <button type="button" className="secondary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px', borderColor: '#fca5a5', color: '#b91c1c', background: '#fef2f2' }} onClick={(event) => { event.stopPropagation(); handleMarkFalse(incident.incident_id); }}>
                                    Mark False
                                  </button>
                                )}
                                {(incident.status === 'pending_company_action' || (incident.status === 'new' && incident.external_ref && (!incident.kb_match_type || incident.kb_match_type === 'admin_confirmed'))) && (
                                  <button type="button" className="primary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px' }} onClick={(event) => { event.stopPropagation(); setSelectedAgentId(''); setAssigningAgentIncidentId(incident.incident_id); }}>
                                    Assign Agent
                                  </button>
                                )}
                                {incident.status === 'dispatched' && incident.agent_status === 'COMPLETED' && (
                                  <button type="button" className="secondary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px', borderColor: '#8bcfb8', color: '#047857', background: '#ecfdf5' }} onClick={(event) => { event.stopPropagation(); setResolvingIncidentId(incident.incident_id); }}>
                                    Mark Resolved
                                  </button>
                                )}
                                {incident.status === 'resolved' && (
                                  <button type="button" className="secondary-btn" style={{ minHeight: '34px', fontSize: '0.75rem', padding: '7px 10px', borderColor: '#86efac', color: '#047857', background: '#ecfdf5' }} onClick={(event) => { event.stopPropagation(); handleOpenApproval(incident); }}>
                                    Review & Approve
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 4px 4px', borderTop: '1px solid #e2e8f0', marginTop: '8px' }}>
                    <span style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 600 }}>
                      Showing {(safePage - 1) * ITEMS_PER_PAGE + 1}â€“{Math.min(safePage * ITEMS_PER_PAGE, incidents.length)} of {incidents.length}
                    </span>
                    <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                      <button
                        type="button"
                        disabled={safePage <= 1}
                        onClick={() => setPage(1)}
                        style={{ ...paginationBtnStyle, opacity: safePage <= 1 ? 0.4 : 1 }}
                        title="First page"
                      >
                        &laquo;
                      </button>
                      <button
                        type="button"
                        disabled={safePage <= 1}
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        style={{ ...paginationBtnStyle, opacity: safePage <= 1 ? 0.4 : 1 }}
                      >
                        &lsaquo; Prev
                      </button>
                      {Array.from({ length: totalPages }, (_, i) => i + 1)
                        .filter((p) => p === 1 || p === totalPages || Math.abs(p - safePage) <= 1)
                        .reduce((acc, p, idx, arr) => {
                          if (idx > 0 && p - arr[idx - 1] > 1) acc.push('...');
                          acc.push(p);
                          return acc;
                        }, [])
                        .map((item, idx) =>
                          item === '...' ? (
                            <span key={`dots-${idx}`} style={{ padding: '0 4px', color: '#94a3b8', fontSize: '0.78rem' }}>&hellip;</span>
                          ) : (
                            <button
                              key={item}
                              type="button"
                              onClick={() => setPage(item)}
                              style={{
                                ...paginationBtnStyle,
                                background: item === safePage ? '#030304' : '#fff',
                                color: item === safePage ? '#fff' : '#334155',
                                fontWeight: item === safePage ? 700 : 600,
                              }}
                            >
                              {item}
                            </button>
                          ),
                        )}
                      <button
                        type="button"
                        disabled={safePage >= totalPages}
                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                        style={{ ...paginationBtnStyle, opacity: safePage >= totalPages ? 0.4 : 1 }}
                      >
                        Next &rsaquo;
                      </button>
                      <button
                        type="button"
                        disabled={safePage >= totalPages}
                        onClick={() => setPage(totalPages)}
                        style={{ ...paginationBtnStyle, opacity: safePage >= totalPages ? 0.4 : 1 }}
                        title="Last page"
                      >
                        &raquo;
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          <div className="panel-soft" style={{ height: '420px', padding: '10px' }}>
            <div style={{ height: '100%', borderRadius: '14px', overflow: 'hidden' }}>
              <IncidentMap
                incidents={incidents}
                onAssignAgent={(incidentId) => { setSelectedAgentId(''); setAssigningAgentIncidentId(incidentId); }}
                selectedIncident={selectedIncident}
                trackedAgent={trackedAgent}
              />
            </div>
          </div>
        </div>
      </section>
    );
  };

  // â”€â”€ Operations Center Tab Content â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

  const renderOperationsTab = () => {
    const assistList = opsRequests.assistance_requests || [];
    const itemList = opsRequests.item_requests || [];
    const currentList = opsTab === 'assistance' ? assistList : opsTab === 'items' ? itemList : [...assistList, ...itemList];
    const kind = opsTab === 'assistance' ? 'assistance' : opsTab === 'items' ? 'item' : null;

    return (
      <section className="panel" style={{ padding: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
          <div className="segmented" style={{ flexWrap: 'wrap' }}>
            <button type="button" className={`segment-btn ${opsTab === 'assistance' ? 'active' : ''}`} onClick={() => { setOpsTab('assistance'); setSelectedOpsRequest(null); }}>
              Assistance ({assistList.length})
            </button>
            <button type="button" className={`segment-btn ${opsTab === 'items' ? 'active' : ''}`} onClick={() => { setOpsTab('items'); setSelectedOpsRequest(null); }}>
              Items ({itemList.length})
            </button>
            <button type="button" className={`segment-btn ${opsTab === 'all' ? 'active' : ''}`} onClick={() => { setOpsTab('all'); setSelectedOpsRequest(null); }}>
              All ({assistList.length + itemList.length})
            </button>
          </div>

          {breachedCount > 0 && (
            <span style={{ padding: '4px 10px', borderRadius: '999px', fontSize: '0.76rem', fontWeight: 700, background: '#fef2f2', color: '#b91c1c', border: '1px solid #fecaca' }}>
              {breachedCount} SLA Breach{breachedCount > 1 ? 'es' : ''}
            </span>
          )}

          <button type="button" className="secondary-btn" onClick={fetchData}>
            Refresh
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '14px', minHeight: '520px' }}>
          <div style={{ display: 'grid', gap: '8px', alignContent: 'start', overflow: 'auto', maxHeight: '700px' }}>
            {currentList.length === 0 ? (
              <div className="panel-soft" style={{ padding: '32px', textAlign: 'center' }}>
                <h3 style={{ marginBottom: '6px', color: '#7f93aa' }}>No Open Requests</h3>
                <p style={{ margin: 0, color: '#a3b5c7' }}>All operations requests have been handled.</p>
              </div>
            ) : (
              currentList.map((request) => renderOpsRequestCard(request, kind || request.kind))
            )}
          </div>

          <div className="panel-soft" style={{ padding: '12px', borderRadius: '14px', overflow: 'auto', maxHeight: '700px' }}>
            {renderOpsDetailPanel()}
          </div>
        </div>
      </section>
    );
  };

  return (
    <div className="app-shell" style={{ position: 'relative' }}>
      <div className="ambient-grid" />
      <ProfileDropdown />
      <NotificationBell />

      <div className="page-container" style={{ position: 'relative', zIndex: 1 }}>
        <header className="panel" style={{ padding: '22px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '10px' }}>
            <div>
              <span className="eyebrow">Operations Control</span>
              <h1 className="page-heading" style={{ marginTop: '11px' }}>Field Staff</h1>
              <p className="page-subheading">Monitor incidents, manage field operations, dispatch teams, and handle requests.</p>
            </div>
            {user?.connector_scope && user.connector_scope.length > 0 && (
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '6px 14px', borderRadius: '999px',
                background: '#eff6ff', color: '#1d4ed8', fontSize: '0.78rem', fontWeight: 600,
                border: '1px solid #bfdbfe', marginTop: '10px',
              }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#3b82f6' }} />
                Scope: {user.connector_scope.map(s => s === 'portal' ? 'Portal' : s.toUpperCase()).join(', ')}
              </div>
            )}
          </div>
        </header>

        {/* Top-level tab bar */}
        <div className="segmented" style={{ marginBottom: '14px' }}>
          <button type="button" className={`segment-btn ${mainTab === 'home' ? 'active' : ''}`} onClick={() => setMainTab('home')}>
            Home
          </button>
          <button type="button" className={`segment-btn ${mainTab === 'incidents' ? 'active' : ''}`} onClick={() => setMainTab('incidents')}>
            Incidents
          </button>
          <button type="button" className={`segment-btn ${mainTab === 'operations' ? 'active' : ''}`} onClick={() => setMainTab('operations')}>
            Operations Center {totalOpsCount > 0 ? `(${totalOpsCount})` : ''}
          </button>
        </div>

        {mainTab === 'home' && renderHomeTab()}
        {mainTab === 'incidents' && renderIncidentsTab()}
        {mainTab === 'operations' && renderOperationsTab()}
      </div>

      {/* â”€â”€ Assign Agent Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {assigningAgentIncidentId && (
        <div className="modal-overlay" onClick={() => { setAssigningAgentIncidentId(null); setSelectedAgentId(''); }}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <h3 style={{ marginBottom: '6px' }}>Assign Field Agent</h3>
            <p style={{ margin: '0 0 12px', fontSize: '0.86rem' }}>Select an available agent for dispatch.</p>

            <div style={{ maxHeight: '340px', overflow: 'auto', display: 'grid', gap: '8px' }}>
              {availableAgents.length === 0 ? (
                <div className="panel-soft" style={{ padding: '14px', textAlign: 'center' }}>
                  <p style={{ margin: 0 }}>No available agents right now.</p>
                </div>
              ) : (
                availableAgents.map((agent) => {
                  const active = selectedAgentId === agent.agent_id;
                  return (
                    <button key={agent.agent_id} type="button" onClick={() => setSelectedAgentId(agent.agent_id)} style={{ border: active ? '2px solid #030304' : '1px solid #d2e1ee', background: active ? '#eef6fd' : '#fff', borderRadius: '12px', padding: '10px', textAlign: 'left', cursor: 'pointer', display: 'grid', gap: '3px' }}>
                      <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#11263c' }}>{agent.full_name}</span>
                      <span style={{ fontSize: '0.76rem', color: '#5f738a' }}>{agent.specialization || 'Field Engineer'}</span>
                      {agent.location && <span style={{ fontSize: '0.74rem', color: '#030304' }}>{agent.location}</span>}
                    </button>
                  );
                })
              )}
            </div>

            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" className="secondary-btn" onClick={() => { setAssigningAgentIncidentId(null); setSelectedAgentId(''); }}>Cancel</button>
              <button type="button" className="primary-btn" disabled={!selectedAgentId} style={{ opacity: selectedAgentId ? 1 : 0.55, cursor: selectedAgentId ? 'pointer' : 'not-allowed' }} onClick={handleAssignAgent}>Dispatch Agent</button>
            </div>
          </div>
        </div>
      )}

      {/* â”€â”€ Resolve Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {resolvingIncidentId && (
        <div className="modal-overlay" onClick={() => { setResolvingIncidentId(null); setResolutionNotes(''); }}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <h3 style={{ marginBottom: '6px' }}>Resolve Incident</h3>
            <p style={{ margin: '0 0 12px', fontSize: '0.86rem' }}>Add optional completion notes before closing this incident.</p>
            <textarea value={resolutionNotes} onChange={(event) => setResolutionNotes(event.target.value)} className="input-control" rows={4} placeholder="Resolution notes" style={{ resize: 'vertical' }} />
            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" className="secondary-btn" onClick={() => { setResolvingIncidentId(null); setResolutionNotes(''); }}>Cancel</button>
              <button type="button" className="primary-btn" onClick={handleResolveIncident}>Confirm Resolve</button>
            </div>
          </div>
        </div>
      )}

      {/* â”€â”€ Approve Resolution Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {approvingIncidentId && (
        <div className="modal-overlay" onClick={() => { setApprovingIncidentId(null); setApprovingIncident(null); setApprovalNotes(''); }}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()} style={{ width: 'min(560px, 100%)' }}>
            <h3 style={{ marginBottom: '6px' }}>Review & Approve Resolution</h3>
            <p style={{ margin: '0 0 12px', fontSize: '0.86rem', color: '#4d6178' }}>
              Review the agent&apos;s resolution and approve to mark incident as completed.
            </p>

            {approvingIncident && (
              <div className="panel-soft" style={{ padding: '12px', borderRadius: '12px', marginBottom: '12px', display: 'grid', gap: '6px', fontSize: '0.82rem' }}>
                {approvingIncident.resolved_by && (
                  <div><span style={{ color: '#64748b' }}>Resolved by:</span> <strong>{approvingIncident.resolved_by}</strong></div>
                )}
                {approvingIncident.resolution_notes && (
                  <div><span style={{ color: '#64748b' }}>Notes:</span> {approvingIncident.resolution_notes}</div>
                )}
                {approvingIncident.resolution_checklist && (
                  <>
                    {approvingIncident.resolution_checklist.root_cause && (
                      <div><span style={{ color: '#64748b' }}>Root Cause:</span> {approvingIncident.resolution_checklist.root_cause}</div>
                    )}
                    {approvingIncident.resolution_checklist.actions_taken?.length > 0 && (
                      <div><span style={{ color: '#64748b' }}>Actions:</span> {approvingIncident.resolution_checklist.actions_taken.join(', ')}</div>
                    )}
                    {approvingIncident.resolution_checklist.verification_result && (
                      <div><span style={{ color: '#64748b' }}>Verification:</span> <strong>{approvingIncident.resolution_checklist.verification_result}</strong></div>
                    )}
                  </>
                )}
                {approvingIncident.resolution_media?.length > 0 && (
                  <div>
                    <span style={{ color: '#64748b', display: 'block', marginBottom: '4px' }}>Proof of Fix:</span>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      {approvingIncident.resolution_media.map((m) => (
                        <a
                          key={m.media_id}
                          href={`${window.location.origin}/api/v1/incidents/${approvingIncident.incident_id}/resolution-media/${m.media_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{
                            display: 'inline-block', padding: '4px 8px', borderRadius: '8px',
                            background: '#e0f2fe', color: '#075985', fontSize: '0.76rem', fontWeight: 600,
                            textDecoration: 'none',
                          }}
                        >
                          {m.content_type?.startsWith('image/') ? 'ðŸ–¼ï¸' : 'ðŸ“„'} {m.filename}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <textarea
              value={approvalNotes}
              onChange={(event) => setApprovalNotes(event.target.value)}
              className="input-control" rows={3}
              placeholder="Optional approval notes"
              style={{ resize: 'vertical' }}
            />
            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" className="secondary-btn" onClick={() => { setApprovingIncidentId(null); setApprovingIncident(null); setApprovalNotes(''); }}>Cancel</button>
              <button type="button" className="primary-btn" onClick={handleApproveResolution}>Approve & Complete</button>
            </div>
          </div>
        </div>
      )}

      {/* â”€â”€ Assign Backup Engineer Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {assignBackupModal && (
        <div className="modal-overlay" onClick={() => { setAssignBackupModal(null); setSelectedBackupAgentId(''); }}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()} style={{ width: 'min(600px, 100%)' }}>
            <h3 style={{ marginBottom: '6px' }}>Assign Backup Engineer</h3>
            <p style={{ fontSize: '0.86rem', margin: '0 0 4px' }}>
              Incident: <strong>{assignBackupModal.incidentId}</strong>
            </p>
            <p style={{ fontSize: '0.82rem', color: '#5f738a', margin: '0 0 12px' }}>
              Request Type: <strong>{(assignBackupModal.requestType || '').replaceAll('_', ' ')}</strong> | Priority: <strong>{assignBackupModal.priority}</strong>
            </p>

            <div className="panel-soft" style={{ padding: '10px', marginBottom: '12px', borderRadius: '12px' }}>
              <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#030304' }}>Incident Context</div>
              <p style={{ fontSize: '0.8rem', margin: '4px 0 0', color: '#4d6178' }}>{assignBackupModal.incidentDescription || 'No description available'}</p>
              <div style={{ fontSize: '0.78rem', color: '#6e859d', marginTop: '4px' }}>
                Location: {assignBackupModal.incidentLocation || 'N/A'} | Primary Agent: {assignBackupModal.primaryAgent || 'N/A'}
              </div>
            </div>

            <div style={{ maxHeight: '300px', overflow: 'auto', display: 'grid', gap: '8px' }}>
              {availableAgents.filter((a) => a.agent_id !== assignBackupModal.primaryAgentId).length === 0 ? (
                <div className="panel-soft" style={{ padding: '14px', textAlign: 'center' }}>
                  <p style={{ margin: 0, color: '#b91c1c', fontWeight: 600 }}>
                    No available backup agents. All engineers are currently assigned.
                  </p>
                  <p style={{ margin: '6px 0 0', fontSize: '0.82rem', color: '#5f738a' }}>
                    Consider sending a customer notification about the delay.
                  </p>
                </div>
              ) : (
                availableAgents.filter((a) => a.agent_id !== assignBackupModal.primaryAgentId).map((agent) => {
                  const active = selectedBackupAgentId === agent.agent_id;
                  return (
                    <button key={agent.agent_id} type="button" onClick={() => setSelectedBackupAgentId(agent.agent_id)} style={{ border: active ? '2px solid #030304' : '1px solid #d2e1ee', background: active ? '#eef6fd' : '#fff', borderRadius: '12px', padding: '10px', textAlign: 'left', cursor: 'pointer', display: 'grid', gap: '3px' }}>
                      <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#11263c' }}>{agent.full_name}</span>
                      <span style={{ fontSize: '0.76rem', color: '#5f738a' }}>{agent.specialization || 'Field Engineer'} | {agent.experience_years || 0}y exp | Rating {agent.rating || 'N/A'}</span>
                      {agent.location && <span style={{ fontSize: '0.74rem', color: '#030304' }}>{agent.location}</span>}
                    </button>
                  );
                })
              )}
            </div>

            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'space-between' }}>
              <button type="button" className="secondary-btn" onClick={() => { setCustomerNotifModal({ incidentId: assignBackupModal.incidentId }); setAssignBackupModal(null); setSelectedBackupAgentId(''); }}>
                Notify Customer Instead
              </button>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button type="button" className="secondary-btn" onClick={() => { setAssignBackupModal(null); setSelectedBackupAgentId(''); }}>Cancel</button>
                <button type="button" className="primary-btn" disabled={!selectedBackupAgentId} style={{ opacity: selectedBackupAgentId ? 1 : 0.55 }} onClick={handleAssignBackup}>Assign Backup</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* â”€â”€ Item Dispatch with ETA Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {itemDispatchModal && (
        <div className="modal-overlay" onClick={() => { setItemDispatchModal(null); setDispatchEta(''); setWarehouseNotes(''); }}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <h3 style={{ marginBottom: '6px' }}>Dispatch Item</h3>
            <p style={{ fontSize: '0.86rem', margin: '0 0 12px' }}>
              <strong>{itemDispatchModal.itemName}</strong> x{itemDispatchModal.quantity} for <strong>{itemDispatchModal.incidentId}</strong>
            </p>

            <label style={{ fontSize: '0.82rem', fontWeight: 600, marginBottom: '4px', display: 'block', color: '#4d6178' }}>
              Estimated Delivery Time (minutes)
            </label>
            <input className="input-control" type="number" min={5} placeholder="e.g., 45" value={dispatchEta} onChange={(e) => setDispatchEta(e.target.value)} />

            <label style={{ fontSize: '0.82rem', fontWeight: 600, margin: '10px 0 4px', display: 'block', color: '#4d6178' }}>
              Warehouse / Logistics Notes
            </label>
            <textarea className="input-control" rows={3} placeholder="Dispatch details, stock notes, delivery instructions..." value={warehouseNotes} onChange={(e) => setWarehouseNotes(e.target.value)} />

            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" className="secondary-btn" onClick={() => { setItemDispatchModal(null); setDispatchEta(''); setWarehouseNotes(''); }}>Cancel</button>
              <button type="button" className="primary-btn" onClick={handleDispatchItem}>Dispatch Item</button>
            </div>
          </div>
        </div>
      )}

      {/* â”€â”€ Customer Notification Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {customerNotifModal && (
        <div className="modal-overlay" onClick={() => { setCustomerNotifModal(null); setNotifMessage(''); }}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <h3 style={{ marginBottom: '6px' }}>Send Customer Notification</h3>
            <p style={{ fontSize: '0.86rem', margin: '0 0 8px', color: '#5f738a' }}>
              This message will appear in the customer&apos;s incident detail page.
            </p>

            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '10px' }}>
              {[
                "We're experiencing a brief delay and appreciate your patience. Our team is working to resolve this.",
                "A backup engineer has been dispatched and is on the way to assist.",
                "The requested equipment is being prepared and will arrive shortly.",
                "We sincerely apologize for the extended delay. Your case has been escalated to senior management.",
              ].map((template, i) => (
                <button key={i} type="button" className="secondary-btn" style={{ fontSize: '0.72rem', padding: '4px 8px', minHeight: 'auto' }} onClick={() => setNotifMessage(template)}>
                  Template {i + 1}
                </button>
              ))}
            </div>

            <textarea className="input-control" rows={4} placeholder="Type the notification message for the customer..." value={notifMessage} onChange={(e) => setNotifMessage(e.target.value)} />

            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button type="button" className="secondary-btn" onClick={() => { setCustomerNotifModal(null); setNotifMessage(''); }}>Cancel</button>
              <button type="button" className="primary-btn" disabled={!notifMessage.trim()} onClick={handleSendCustomerNotification}>Send to Customer</button>
            </div>
          </div>
        </div>
      )}

      {/* â”€â”€ Incident Detail Modal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      {selectedOutcomeDrilldown && (
        <div className="modal-overlay" onClick={() => setSelectedOutcomeDrilldown(null)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()} style={{ width: 'min(920px, 96vw)', maxHeight: '84vh', overflow: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
              <div>
                <h3 style={{ margin: '0 0 4px' }}>{selectedOutcomeDrilldown}</h3>
                <p style={{ margin: 0, color: '#64748b', fontSize: '0.84rem' }}>
                  Workflow route, branch signal, and symptom intensity for incidents in the selected outcome bucket.
                </p>
              </div>
              <button type="button" className="secondary-btn" onClick={() => setSelectedOutcomeDrilldown(null)}>Close</button>
            </div>

            <div style={{ display: 'grid', gap: '10px' }}>
              {dashboardInsights.filteredIncidents
                .filter((incident) => formatCategoryLabel(incident.outcome || 'pending_decision') === selectedOutcomeDrilldown)
                .slice(0, 12)
                .map((incident) => {
                  const riskMeta = getRiskMeta(incident.risk_score ?? 0);
                  const symptomScore = countSymptomSignals(incident);
                  const workflowName = formatCategoryLabel(incident.incident_type || incident.classified_use_case || 'unclassified');
                  const branchName = formatCategoryLabel(incident.kb_match_type || 'model_path');
                  return (
                    <button
                      key={incident.incident_id}
                      type="button"
                      onClick={() => {
                        setSelectedOutcomeDrilldown(null);
                        handleIncidentRowClick(incident);
                      }}
                      style={{
                        border: '1px solid #d7e3ee',
                        background: '#fff',
                        borderRadius: '14px',
                        padding: '12px',
                        textAlign: 'left',
                        cursor: 'pointer',
                        display: 'grid',
                        gap: '8px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 800, color: '#345473' }}>
                          {formatIncidentId(incident.incident_id)}
                        </span>
                        <span style={{ padding: '3px 8px', borderRadius: '999px', background: riskMeta.bg, color: riskMeta.color, fontSize: '0.72rem', fontWeight: 800 }}>
                          {riskMeta.label} {Math.round((incident.risk_score ?? 0) * 100)}%
                        </span>
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '8px' }}>
                        <div>
                          <div style={{ color: '#64748b', fontSize: '0.72rem', fontWeight: 700 }}>Workflow</div>
                          <div style={{ color: '#0f172a', fontSize: '0.84rem', fontWeight: 800 }}>{workflowName}</div>
                        </div>
                        <div>
                          <div style={{ color: '#64748b', fontSize: '0.72rem', fontWeight: 700 }}>Branch</div>
                          <div style={{ color: '#0f172a', fontSize: '0.84rem', fontWeight: 800 }}>{branchName}</div>
                        </div>
                        <div>
                          <div style={{ color: '#64748b', fontSize: '0.72rem', fontWeight: 700 }}>Symptom Score</div>
                          <div style={{ color: '#0f172a', fontSize: '0.84rem', fontWeight: 800 }}>{symptomScore}/7</div>
                        </div>
                      </div>
                    </button>
                  );
                })}
            </div>
          </div>
        </div>
      )}

      {detailIncident && (() => {
        try {
          const inc = detailIncident;
          const sd = inc.structured_data || {};
          const kbVal = sd._kb_validation || inc.kb_validation_details || null;
          const statusMeta = getStatusMeta(inc.status);
          const riskMeta = getRiskMeta(inc.risk_score ?? 0);
          const assignedAgent = inc.assigned_agent_id
            ? allAgents.find((a) => a.agent_id === inc.assigned_agent_id)
            : null;

          const fmtVal = (v) => {
            if (typeof v === 'boolean') return v ? 'Yes' : 'No';
            if (typeof v === 'number') return v % 1 === 0 ? String(v) : v.toFixed(1);
            const str = String(v).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            return str.length > 120 ? str.slice(0, 120) + '...' : str;
          };

          const pickFirst = (...keys) => {
            for (const key of keys) {
              const value = sd[key];
              if (value !== null && value !== undefined && value !== '' && value !== 0) {
                return value;
              }
            }
            return null;
          };

          const pickBySuffix = (suffixes) => {
            const entries = Object.entries(sd);
            for (const [key, value] of entries) {
              if (value === null || value === undefined || value === '' || value === 0) continue;
              if (typeof value !== 'string') continue;
              const lowered = key.toLowerCase();
              if (lowered.endsWith('_score') || lowered.endsWith('_normalized_score')) continue;
              if (suffixes.some((suffix) => lowered.endsWith(`_${suffix}`) || lowered === suffix)) {
                return value;
              }
            }
            return null;
          };

          const reportType = inc.incident_type || inc.classified_use_case || sd.incident_type;
          const model = pickFirst(
            'kidde_model', 'fa_model', 'fh_model', 'aico_model', 'aico3030_model',
            'xs_model', 'nest_model', 'net_model', 'cav_model', 'other_model', 'model_number',
          );
          const summaryEntries = [
            ['Reference ID', inc.reference_id || sd.reference_id || sd.ref_id],
            ['Report Type', reportType],
            ['Alarm Type', pickFirst('alarm_type')],
            ['Manufacturer', pickFirst('alarm_manufacturer', 'manufacturer')],
            ['Model', model],
            ['Outcome', inc.outcome ? String(inc.outcome).replace(/_/g, ' ') : null],
          ].filter(([, value]) => value !== null && value !== undefined && value !== '' && value !== 0);

          const sectionTitle = (text) => (
            <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#030304', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px', paddingBottom: '4px', borderBottom: '1px solid #e2e8f0' }}>
              {text}
            </div>
          );

          return (
            <div className="modal-overlay">
              <div className="detail-modal-card" onClick={(e) => e.stopPropagation()} style={{ width: 'min(960px, 95vw)', maxHeight: '90vh', borderRadius: '16px', border: '1px solid #d4e2ef', background: '#fff', boxShadow: '0 24px 36px -24px rgba(15,31,51,0.66)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                {/* Header with Action Buttons */}
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                    <h2 style={{ margin: 0, fontSize: '1.05rem', color: '#0f172a' }}>Incident Details</h2>
                    <span style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.78rem', color: '#475569', background: '#f1f5f9', padding: '2px 8px', borderRadius: '6px' }}>
                      {formatIncidentId(inc.incident_id)}
                    </span>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', borderRadius: '999px', padding: '3px 10px', background: statusMeta.bg, color: statusMeta.text, fontSize: '0.74rem', fontWeight: 700 }}>
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: statusMeta.dot }} />
                      {statusMeta.label}
                    </span>
                    {detailLoading && <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Loading...</span>}
                  </div>

                  {/* Action Buttons on the right */}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    {inc.status === 'new' && inc.external_ref && !inc.kb_match_type && (
                      <button type="button" className="secondary-btn" style={{ fontSize: '0.82rem', borderColor: '#93c5fd', color: '#1d4ed8', background: '#eff6ff' }} onClick={() => handleValidate(inc.incident_id, { silent: true, keepModalOpen: true })}>
                        Validate with KB
                      </button>
                    )}
                    {(inc.status === 'pending_company_action' || (inc.status === 'new' && inc.external_ref && (!inc.kb_match_type || inc.kb_match_type === 'admin_confirmed'))) && (
                      <button type="button" className="primary-btn" style={{ fontSize: '0.82rem' }} onClick={() => { setDetailIncident(null); setSelectedAgentId(''); setAssigningAgentIncidentId(inc.incident_id); }}>
                        Assign Agent
                      </button>
                    )}
                    {inc.status === 'dispatched' && inc.agent_status === 'COMPLETED' && (
                      <button type="button" className="secondary-btn" style={{ fontSize: '0.82rem', borderColor: '#8bcfb8', color: '#047857', background: '#ecfdf5' }} onClick={() => { setDetailIncident(null); setResolvingIncidentId(inc.incident_id); }}>
                        Mark Resolved
                      </button>
                    )}
                    {inc.status === 'resolved' && (
                      <button type="button" className="secondary-btn" style={{ fontSize: '0.82rem', borderColor: '#86efac', color: '#047857', background: '#ecfdf5' }} onClick={() => { setDetailIncident(null); handleOpenApproval(inc); }}>
                        Review & Approve
                      </button>
                    )}
                    <button type="button" className="secondary-btn" style={{ fontSize: '0.82rem' }} onClick={() => { setDetailIncident(null); setExpandedKbEntry(null); }}>
                      Close
                    </button>
                  </div>
                </div>

                {/* Body - two column */}
                <div style={{ flex: 1, overflow: 'auto', padding: '16px 20px', display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '18px', alignContent: 'start' }}>
                  {/* â”€â”€ Left Column â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
                  <div style={{ display: 'grid', gap: '16px', alignContent: 'start' }}>

                    {/* User Details */}
                    <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                      {sectionTitle('Reported By')}
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', fontSize: '0.84rem' }}>
                        <div><span style={{ color: '#64748b' }}>Name:</span> <strong>{inc.user_name || 'N/A'}</strong></div>
                        <div><span style={{ color: '#64748b' }}>Phone:</span> <strong>{inc.user_phone || 'N/A'}</strong></div>
                        <div style={{ gridColumn: '1 / -1' }}><span style={{ color: '#64748b' }}>Address:</span> <strong>{inc.user_address || inc.location || 'N/A'}</strong></div>
                        {inc.user_geo_location && (
                          <div style={{ gridColumn: '1 / -1', fontSize: '0.78rem', color: '#94a3b8' }}>
                            GPS: {inc.user_geo_location.lat?.toFixed(5)}, {inc.user_geo_location.lng?.toFixed(5)}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* AI Description */}
                    {/* Incident Description & AI Assessment */}
                    <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                      {sectionTitle('Incident Description')}

                      {/* Description */}
                      <p style={{ fontSize: '0.88rem', color: '#334155', lineHeight: 1.65, margin: '0 0 10px 0' }}>
                        {inc.description || 'No description available'}
                      </p>



                      {/* Assessment Details */}
                      {summaryEntries.length > 0 && (
                        <>
                          <div style={{ display: 'grid', gap: '6px' }}>
                            {summaryEntries.map(([label, value]) => (
                              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontSize: '0.84rem', padding: '6px 8px', background: '#f8fafc', borderRadius: '6px', gap: '12px' }}>
                                <span style={{ color: '#64748b', fontWeight: 600 }}>{label}</span>
                                <strong style={{ color: '#1e293b', textAlign: 'right' }}>{fmtVal(value)}</strong>
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                    </div>

                    {/* User-Uploaded Evidence */}
                    {inc.media?.length > 0 && (
                      <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                        {sectionTitle('Uploaded Evidence')}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px' }}>
                          {inc.media.map((m) => (
                            <a
                              key={m.media_id}
                              href={`${window.location.origin}/api/v1/incidents/${inc.incident_id}/media/${m.media_id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={{ display: 'block', borderRadius: '8px', overflow: 'hidden', border: '1px solid #e2e8f0', transition: 'all 0.2s' }}
                            >
                              <img
                                src={`${window.location.origin}/api/v1/incidents/${inc.incident_id}/media/${m.media_id}`}
                                alt={m.metadata?.filename || 'Evidence'}
                                style={{ width: '100%', height: '100px', objectFit: 'cover', display: 'block' }}
                              />
                              <div style={{ padding: '4px 6px', fontSize: '0.7rem', color: '#64748b', fontWeight: 600, background: '#f8fafc' }}>
                                {m.metadata?.filename || 'Image'}
                              </div>
                            </a>
                          ))}
                        </div>
                      </div>
                    )}


                    {/* KB Validation */}
                    {kbVal && (() => {
                      const rawVerdict = (kbVal.verdict || kbVal.best_match_type || inc.kb_match_type || 'unknown').toString().toLowerCase();
                      const normalizedVerdict = ['true', 'false', 'admin_confirmed'].includes(rawVerdict) ? rawVerdict : 'unknown';
                      const trueMatches = kbVal.top_true_matches || [];
                      const falseMatches = kbVal.top_false_matches || [];
                      const avgTrueScore = (kbVal.true_kb_match ?? kbVal.true_kb_score) ?? (
                        trueMatches.length > 0
                          ? trueMatches.reduce((sum, match) => sum + (match.score || 0), 0) / trueMatches.length
                          : 0
                      );
                      const avgFalseScore = (kbVal.false_kb_match ?? kbVal.false_kb_score) ?? (
                        falseMatches.length > 0
                          ? falseMatches.reduce((sum, match) => sum + (match.score || 0), 0) / falseMatches.length
                          : 0
                      );
                      const badgeBg = normalizedVerdict === 'true' ? '#ecfdf5' : normalizedVerdict === 'false' ? '#fef2f2' : '#eff6ff';
                      const badgeColor = normalizedVerdict === 'true' ? '#047857' : normalizedVerdict === 'false' ? '#b91c1c' : '#1d4ed8';
                      const badgeBorder = normalizedVerdict === 'true' ? '#bbf7d0' : normalizedVerdict === 'false' ? '#fecaca' : '#bfdbfe';
                      const badgeLabel = normalizedVerdict === 'true'
                        ? 'TRUE INCIDENT'
                        : normalizedVerdict === 'false'
                          ? 'FALSE REPORT'
                          : normalizedVerdict === 'admin_confirmed'
                            ? 'ADMIN CONFIRMED'
                            : 'NO STRONG KB MATCH';

                      return (
                        <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                          {sectionTitle('KB Validation Result')}
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                            <span style={{
                              padding: '4px 12px', borderRadius: '999px', fontSize: '0.82rem', fontWeight: 700,
                              background: badgeBg,
                              color: badgeColor,
                              border: `1px solid ${badgeBorder}`,
                            }}>
                              {badgeLabel}
                            </span>
                            {kbVal.confidence != null && (
                              <span style={{ fontSize: '0.78rem', color: '#64748b' }}>
                                Confidence: <strong>{(kbVal.confidence * 100).toFixed(0)}%</strong>
                              </span>
                            )}
                          </div>
                          {(trueMatches.length > 0 || falseMatches.length > 0) && (
                            <div style={{ marginTop: '12px', display: 'grid', gap: '12px' }}>
                              {trueMatches.length > 0 && (
                                <details style={{ border: '1px solid #bbf7d0', borderRadius: '10px', background: '#f8fffb', padding: '8px 10px' }}>
                                  <summary style={{ cursor: 'pointer', listStyle: 'none', fontSize: '0.76rem', fontWeight: 700, color: '#047857', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                                    <span>Matched True Records ({trueMatches.length})</span>
                                    <span style={{ fontSize: '0.9rem', lineHeight: 1 }}>▼</span>
                                  </summary>
                                  <div style={{ display: 'grid', gap: '6px', marginTop: '10px' }}>
                                    {trueMatches.slice(0, 3).map((match, idx) => {
                                      const entryKey = `result-true-${match.kb_id || idx}`;
                                      const isExpanded = expandedKbEntry === entryKey;
                                      return (
                                        <button
                                          type="button"
                                          key={entryKey}
                                          onClick={() => setExpandedKbEntry(isExpanded ? null : entryKey)}
                                          style={{ border: '1px solid #bbf7d0', background: '#f0fdf4', borderRadius: '8px', padding: '8px 10px', textAlign: 'left', cursor: 'pointer', width: '100%' }}
                                        >
                                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginBottom: '3px' }}>
                                            <strong style={{ fontSize: '0.8rem', color: '#166534' }}>{formatKbDisplayId(match, match.incident_type || 'True incident')}</strong>
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                              <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#047857' }}>{Math.round((match.score || 0) * 100)}%</span>
                                              <span style={{ fontSize: '0.8rem', color: '#166534' }}>{isExpanded ? '▲' : '▼'}</span>
                                            </span>
                                          </div>
                                          {match.description && <div style={{ fontSize: '0.76rem', color: '#475569' }}>{match.description}</div>}
                                          {isExpanded && (
                                            <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #bbf7d0', display: 'grid', gap: '6px' }}>
                                              {match.resolution_summary && (
                                                <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                                                  <strong style={{ color: '#166534' }}>Summary:</strong> {match.resolution_summary}
                                                </div>
                                              )}
                                              {Array.isArray(match.matched_tags) && match.matched_tags.length > 0 && (
                                                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                                                  {match.matched_tags.map((tag) => (
                                                    <span key={tag} style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: '999px', background: '#dcfce7', color: '#166534', fontWeight: 700 }}>
                                                      {String(tag).replace(/_/g, ' ')}
                                                    </span>
                                                  ))}
                                                </div>
                                              )}
                                              {match.manufacturer && (
                                                <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                                                  <strong style={{ color: '#166534' }}>Manufacturer:</strong> {match.manufacturer}
                                                </div>
                                              )}
                                              {match.model && (
                                                <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                                                  <strong style={{ color: '#166534' }}>Model:</strong> {match.model}
                                                </div>
                                              )}
                                              {match.pattern_fields && Object.keys(match.pattern_fields).length > 0 && (
                                                <div style={{ display: 'grid', gap: '4px' }}>
                                                  {Object.entries(match.pattern_fields).map(([field, value]) => (
                                                    <div key={field} style={{ fontSize: '0.73rem', color: '#475569' }}>
                                                      <strong style={{ color: '#166534' }}>{field.replace(/_/g, ' ')}:</strong> {String(value)}
                                                    </div>
                                                  ))}
                                                </div>
                                              )}
                                            </div>
                                          )}
                                        </button>
                                      )
                                    })}
                                  </div>
                                </details>
                              )}
                              {falseMatches.length > 0 && (
                                <details style={{ border: '1px solid #fecaca', borderRadius: '10px', background: '#fffafa', padding: '8px 10px' }}>
                                  <summary style={{ cursor: 'pointer', listStyle: 'none', fontSize: '0.76rem', fontWeight: 700, color: '#b91c1c', textTransform: 'uppercase', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                                    <span>Matched False Records ({falseMatches.length})</span>
                                    <span style={{ fontSize: '0.9rem', lineHeight: 1 }}>▼</span>
                                  </summary>
                                  <div style={{ display: 'grid', gap: '6px', marginTop: '10px' }}>
                                    {falseMatches.slice(0, 3).map((match, idx) => {
                                      const entryKey = `result-false-${match.kb_id || idx}`;
                                      const isExpanded = expandedKbEntry === entryKey;
                                      return (
                                        <button
                                          type="button"
                                          key={entryKey}
                                          onClick={() => setExpandedKbEntry(isExpanded ? null : entryKey)}
                                          style={{ border: '1px solid #fecaca', background: '#fef2f2', borderRadius: '8px', padding: '8px 10px', textAlign: 'left', cursor: 'pointer', width: '100%' }}
                                        >
                                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginBottom: '3px' }}>
                                            <strong style={{ fontSize: '0.8rem', color: '#991b1b' }}>{formatKbDisplayId(match, match.incident_type || 'False report')}</strong>
                                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                              <span style={{ fontSize: '0.74rem', fontWeight: 700, color: '#b91c1c' }}>{Math.round((match.score || 0) * 100)}%</span>
                                              <span style={{ fontSize: '0.8rem', color: '#991b1b' }}>{isExpanded ? '▲' : '▼'}</span>
                                            </span>
                                          </div>
                                          {match.description && <div style={{ fontSize: '0.76rem', color: '#475569' }}>{match.description}</div>}
                                          {isExpanded && (
                                            <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #fecaca', display: 'grid', gap: '6px' }}>
                                              {match.resolution_summary && (
                                                <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                                                  <strong style={{ color: '#991b1b' }}>Summary:</strong> {match.resolution_summary}
                                                </div>
                                              )}
                                              {Array.isArray(match.matched_tags) && match.matched_tags.length > 0 && (
                                                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                                                  {match.matched_tags.map((tag) => (
                                                    <span key={tag} style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: '999px', background: '#fee2e2', color: '#991b1b', fontWeight: 700 }}>
                                                      {String(tag).replace(/_/g, ' ')}
                                                    </span>
                                                  ))}
                                                </div>
                                              )}
                                              {match.manufacturer && (
                                                <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                                                  <strong style={{ color: '#991b1b' }}>Manufacturer:</strong> {match.manufacturer}
                                                </div>
                                              )}
                                              {match.model && (
                                                <div style={{ fontSize: '0.74rem', color: '#475569' }}>
                                                  <strong style={{ color: '#991b1b' }}>Model:</strong> {match.model}
                                                </div>
                                              )}
                                              {match.pattern_fields && Object.keys(match.pattern_fields).length > 0 && (
                                                <div style={{ display: 'grid', gap: '4px' }}>
                                                  {Object.entries(match.pattern_fields).map(([field, value]) => (
                                                    <div key={field} style={{ fontSize: '0.73rem', color: '#475569' }}>
                                                      <strong style={{ color: '#991b1b' }}>{field.replace(/_/g, ' ')}:</strong> {String(value)}
                                                    </div>
                                                  ))}
                                                </div>
                                              )}
                                            </div>
                                          )}
                                        </button>
                                      )
                                    })}
                                  </div>
                                </details>
                              )}
                            </div>
                          )}

                        </div>
                      );
                    })()}

                    {/* Risk Breakdown */}
                    {/* Resolution Info */}
                    {(inc.resolution_notes || inc.items_used || inc.resolution_checklist) && (
                      <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                        {sectionTitle('Resolution')}
                        {inc.resolution_notes && (
                          <div style={{ fontSize: '0.84rem', marginBottom: '8px' }}>
                            <span style={{ color: '#64748b' }}>Notes:</span>
                            <p style={{ margin: '4px 0 0', color: '#334155', lineHeight: 1.5 }}>{inc.resolution_notes}</p>
                          </div>
                        )}
                        {inc.items_used && inc.items_used.length > 0 && (
                          <div style={{ fontSize: '0.84rem', marginBottom: '8px' }}>
                            <span style={{ color: '#64748b' }}>Items Used:</span>
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
                              {inc.items_used.map((item, i) => (
                                <span key={i} style={{ fontSize: '0.76rem', padding: '2px 8px', borderRadius: '999px', background: '#e0f2fe', color: '#075985', fontWeight: 600 }}>{item}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {inc.resolved_by && (
                          <div style={{ fontSize: '0.82rem' }}>
                            <span style={{ color: '#64748b' }}>Resolved by:</span> <strong>{inc.resolved_by}</strong>
                            {inc.resolved_at && <span style={{ color: '#94a3b8' }}> at {formatDateTime(inc.resolved_at)}</span>}
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* â”€â”€ Right Column â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
                  <div style={{ display: 'grid', gap: '16px', alignContent: 'start' }}>

                    {/* Status & Outcome */}
                    <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                      {sectionTitle('Status & Outcome')}
                      <div style={{ display: 'grid', gap: '6px', fontSize: '0.84rem' }}>
                        <div><span style={{ color: '#64748b' }}>Status:</span> <strong>{statusMeta.label}</strong></div>
                        {inc.outcome && (
                          <div>
                            <span style={{ color: '#64748b' }}>Outcome:</span>{' '}
                            <span style={{
                              padding: '2px 8px', borderRadius: '999px', fontSize: '0.76rem', fontWeight: 700,
                              background: inc.outcome === 'emergency_dispatch' ? '#fef2f2' : inc.outcome === 'false_report' ? '#fff7ed' : '#e0f2fe',
                              color: inc.outcome === 'emergency_dispatch' ? '#b91c1c' : inc.outcome === 'false_report' ? '#b45309' : '#075985',
                            }}>
                              {inc.outcome.replace(/_/g, ' ').toUpperCase()}
                            </span>
                          </div>
                        )}
                        {(inc.kb_match_type || kbVal?.verdict || kbVal?.best_match_type) && (() => {
                          const rawVerdict = (kbVal?.verdict || kbVal?.best_match_type || inc.kb_match_type || 'unknown').toString().toLowerCase();
                          const verdictLabel = rawVerdict === 'true'
                            ? 'True Incident'
                            : rawVerdict === 'false'
                              ? 'False Report'
                              : rawVerdict === 'admin_confirmed'
                                ? 'Admin Confirmed'
                                : 'Unknown / No strong match';
                          const verdictColor = rawVerdict === 'true'
                            ? '#047857'
                            : rawVerdict === 'false'
                              ? '#b91c1c'
                              : rawVerdict === 'admin_confirmed'
                                ? '#166534'
                                : '#1d4ed8';
                          return (
                            <div>
                              <span style={{ color: '#64748b' }}>KB Verdict:</span>{' '}
                              <strong style={{ color: verdictColor }}>
                                {verdictLabel}
                              </strong>
                            </div>
                          );
                        })()}
                        {inc.kb_similarity_score != null && (
                          <div><span style={{ color: '#64748b' }}>KB Similarity:</span> <strong>{(inc.kb_similarity_score * 100).toFixed(0)}%</strong></div>
                        )}
                        <div>
                          <span style={{ color: '#64748b' }}>Risk:</span>{' '}
                          <span style={{ fontSize: '0.76rem', fontWeight: 700, color: riskMeta.color }}>
                            {riskMeta.label}
                          </span>
                        </div>
                        {inc.sla_hours != null && (
                          <div><span style={{ color: '#64748b' }}>SLA:</span> <strong>{inc.sla_hours}h</strong></div>
                        )}
                        <div><span style={{ color: '#64748b' }}>Created:</span> <strong>{formatDateTime(inc.created_at)}</strong></div>
                      </div>
                    </div>

                    {/* Agent Details */}
                    {assignedAgent && (
                      <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                        {sectionTitle('Assigned Agent')}
                        <div style={{ display: 'grid', gap: '5px', fontSize: '0.84rem' }}>
                          <div><span style={{ color: '#64748b' }}>Name:</span> <strong>{assignedAgent.full_name}</strong></div>
                          <div><span style={{ color: '#64748b' }}>Specialization:</span> <strong>{assignedAgent.specialization || 'Field Engineer'}</strong></div>
                          {assignedAgent.phone && <div><span style={{ color: '#64748b' }}>Phone:</span> <strong>{assignedAgent.phone}</strong></div>}
                          {assignedAgent.email && <div><span style={{ color: '#64748b' }}>Email:</span> <strong>{assignedAgent.email}</strong></div>}
                          {inc.agent_status && (
                            <div>
                              <span style={{ color: '#64748b' }}>Agent Status:</span>{' '}
                              <span style={{
                                padding: '2px 8px', borderRadius: '999px', fontSize: '0.74rem', fontWeight: 700,
                                background: inc.agent_status === 'COMPLETED' ? '#ecfdf5' : inc.agent_status === 'ON_SITE' || inc.agent_status === 'IN_PROGRESS' ? '#fff7ed' : '#e0f2fe',
                                color: inc.agent_status === 'COMPLETED' ? '#047857' : inc.agent_status === 'ON_SITE' || inc.agent_status === 'IN_PROGRESS' ? '#b45309' : '#075985',
                              }}>
                                {inc.agent_status.replace(/_/g, ' ')}
                              </span>
                            </div>
                          )}
                          {inc.assigned_at && <div><span style={{ color: '#64748b' }}>Assigned:</span> <strong>{formatDateTime(inc.assigned_at)}</strong></div>}
                          {inc.estimated_arrival_at && <div><span style={{ color: '#64748b' }}>ETA:</span> <strong>{formatDateTime(inc.estimated_arrival_at)}</strong></div>}
                          {assignedAgent.experience_years > 0 && <div><span style={{ color: '#64748b' }}>Experience:</span> <strong>{assignedAgent.experience_years} years</strong></div>}
                          {assignedAgent.rating && <div><span style={{ color: '#64748b' }}>Rating:</span> <strong>{assignedAgent.rating}</strong></div>}
                        </div>
                      </div>
                    )}

                    {/* Backup Agents */}
                    {inc.backup_agents && inc.backup_agents.length > 0 && (
                      <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                        {sectionTitle(`Backup Agents (${inc.backup_agents.length})`)}
                        <div style={{ display: 'grid', gap: '6px' }}>
                          {inc.backup_agents.map((ba, i) => {
                            const baAgent = allAgents.find((a) => a.agent_id === ba.agent_id);
                            return (
                              <div key={i} style={{ fontSize: '0.82rem', padding: '6px 8px', background: '#f8fafc', borderRadius: '8px' }}>
                                <strong>{baAgent?.full_name || ba.agent_id}</strong>
                                <span style={{ fontSize: '0.74rem', color: '#64748b', marginLeft: '6px' }}>{ba.role || 'backup'}</span>
                                {ba.status && <span style={{ fontSize: '0.72rem', color: '#030304', marginLeft: '6px' }}>[{ba.status}]</span>}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Timeline */}
                    {/* Field Activity */}
                    {inc.field_activity && inc.field_activity.length > 0 && (
                      <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                        {sectionTitle(`Field Activity (${inc.field_activity.length})`)}
                        <div style={{ display: 'grid', gap: '4px' }}>
                          {[...inc.field_activity].reverse().slice(0, 10).map((entry, i) => (
                            <div key={i} style={{ fontSize: '0.78rem', padding: '4px 0', borderBottom: '1px solid #f1f5f9' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                                <strong style={{ color: '#030304' }}>{(entry.type || entry.activity || 'Activity').replace(/_/g, ' ')}</strong>
                                <span style={{ color: '#94a3b8', fontSize: '0.74rem', flexShrink: 0 }}>
                                  {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : ''}
                                </span>
                              </div>
                              {entry.notes && <div style={{ color: '#475569', marginTop: '2px' }}>{entry.notes}</div>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Customer Notifications */}
                    {inc.customer_notifications && inc.customer_notifications.length > 0 && (
                      <div className="panel-soft" style={{ padding: '12px 14px', borderRadius: '12px' }}>
                        {sectionTitle(`Customer Notifications (${inc.customer_notifications.length})`)}
                        <div style={{ display: 'grid', gap: '4px' }}>
                          {inc.customer_notifications.map((n, i) => (
                            <div key={i} style={{ fontSize: '0.78rem', padding: '6px 8px', background: '#f8fafc', borderRadius: '8px' }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                <strong style={{ color: '#030304' }}>{n.title || 'Notification'}</strong>
                                <span style={{ color: '#94a3b8', fontSize: '0.72rem' }}>
                                  {n.created_at ? new Date(n.created_at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
                                </span>
                              </div>
                              <div style={{ color: '#475569', marginTop: '2px' }}>{n.message}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* KB Validation Review Panel */}
                {(inc.kb_match_type || inc.kb_validation_details || kbVal) && (() => {
                  const kbDetails = kbVal || inc.kb_validation_details || {};
                  const rawVerdict = (kbDetails.verdict || kbDetails.best_match_type || inc.kb_match_type || 'unknown').toString().toLowerCase();
                  const normalizedVerdict = ['true', 'false', 'admin_confirmed'].includes(rawVerdict) ? rawVerdict : 'unknown';

                  const trueMatches = kbDetails.top_true_matches || [];
                  const falseMatches = kbDetails.top_false_matches || [];

                  let trueScore = Math.round((((kbDetails.true_kb_match ?? kbDetails.true_kb_score) ?? 0) || 0) * 100);
                  let falseScore = Math.round((((kbDetails.false_kb_match ?? kbDetails.false_kb_score) ?? 0) || 0) * 100);

                  trueScore = Math.max(0, Math.min(100, trueScore));
                  falseScore = Math.max(0, Math.min(100, falseScore));

                  const explanation = kbDetails.explanation || '';
                  const reviewerOverride = Boolean(kbDetails.reviewer_override);
                  const canReviewKb = ['new', 'in_progress', 'pending_company_action', 'false_report', 'completed'].includes(inc.status) && !reviewerOverride;
                  const panelBorder = normalizedVerdict === 'true' ? '#bbf7d0' : normalizedVerdict === 'false' ? '#fecaca' : '#bfdbfe';
                  const verdictColor = normalizedVerdict === 'true' ? '#047857' : normalizedVerdict === 'false' ? '#b91c1c' : '#1d4ed8';
                  const verdictLabel = normalizedVerdict === 'true'
                    ? 'Likely True Incident'
                    : normalizedVerdict === 'false'
                      ? 'Likely False Report'
                      : normalizedVerdict === 'admin_confirmed'
                        ? 'Admin Confirmed Valid'
                        : 'Validation Completed Without Strong Match';
                  const reviewPrompt = normalizedVerdict === 'true'
                    ? 'Do you want to mark this as a false report or re-validate it?'
                    : normalizedVerdict === 'false'
                      ? 'Do you want to confirm this as a true incident or re-validate it?'
                      : 'Do you want to review this verdict or run validation again?';

                  return (
                    <div style={{ padding: '12px 20px', borderTop: `2px solid ${panelBorder}`, background: '#ffffff' }}>
                      <div style={{ fontSize: '0.78rem', fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>
                        KB Validation Review
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', background: verdictColor, flexShrink: 0 }} />
                        <span style={{ fontSize: '0.86rem', fontWeight: 700, color: verdictColor }}>{verdictLabel}</span>
                      </div>
                      {/* Action buttons */}
                      {canReviewKb && normalizedVerdict !== 'admin_confirmed' && (
                        <div style={{ display: 'grid', gap: '10px' }}>
                          <div style={{ fontSize: '0.8rem', color: '#475569' }}>
                            {reviewPrompt}
                          </div>
                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            {normalizedVerdict !== 'true' && (
                              <button type="button" className="secondary-btn" disabled={Boolean(kbReviewBusy)} style={{ fontSize: '0.78rem', padding: '6px 14px', borderColor: '#86efac', color: '#047857', background: '#ecfdf5', fontWeight: 700, cursor: kbReviewBusy ? 'not-allowed' : 'pointer', opacity: kbReviewBusy && kbReviewBusy !== 'confirm' ? 0.65 : 1 }} onClick={() => handleConfirmValid(inc.incident_id)}>
                                Confirm True Incident
                              </button>
                            )}
                            {normalizedVerdict !== 'false' && (
                              <button type="button" className="secondary-btn" disabled={Boolean(kbReviewBusy)} style={{ fontSize: '0.78rem', padding: '6px 14px', borderColor: '#fca5a5', color: '#b91c1c', background: '#fff5f5', fontWeight: 700, cursor: kbReviewBusy ? 'not-allowed' : 'pointer', opacity: kbReviewBusy && kbReviewBusy !== 'false' ? 0.65 : 1 }} onClick={() => handleMarkFalse(inc.incident_id)}>
                                Mark as False Report
                              </button>
                            )}
                            <button type="button" className="secondary-btn" disabled={Boolean(kbReviewBusy)} style={{ fontSize: '0.78rem', padding: '6px 14px', borderColor: '#93c5fd', color: '#1d4ed8', background: '#eff6ff', fontWeight: 700, cursor: kbReviewBusy ? 'not-allowed' : 'pointer', opacity: kbReviewBusy && kbReviewBusy !== 'validate' ? 0.65 : 1 }} onClick={() => handleValidate(inc.incident_id, { silent: true, keepModalOpen: true })}>
                              Re-validate
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })()}
                {inc.kb_match_type === 'admin_confirmed' && (
                  <div style={{ padding: '8px 20px', borderTop: '2px solid #bbf7d0', background: '#f0fdf4' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem', fontWeight: 700, color: '#047857' }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#047857' }} />
                      Admin Confirmed Valid
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        } catch {
          return (
            <div className="modal-overlay">
              <div className="modal-card" onClick={(e) => e.stopPropagation()}>
                <h3>Error Loading Details</h3>
                <p style={{ fontSize: '0.86rem', color: '#b91c1c' }}>Could not render incident details. Please try again.</p>
                <button type="button" className="secondary-btn" onClick={() => setDetailIncident(null)}>Close</button>
              </div>
            </div>
          );
        }
      })()}

      {toast && (
        <div style={{ position: 'fixed', top: '22px', right: '22px', zIndex: 9999, borderRadius: '12px', border: `1px solid ${toast.type === 'error' ? '#fecaca' : '#bbf7d0'}`, background: toast.type === 'error' ? '#fef2f2' : '#ecfdf5', color: toast.type === 'error' ? '#b91c1c' : '#047857', padding: '10px 14px', boxShadow: '0 16px 24px -22px rgba(15,31,51,0.65)', fontWeight: 700, fontSize: '0.84rem', minWidth: '280px', animation: 'fadeSlideIn 0.25s ease' }}>
          {toast.message}
        </div>
      )}

      <style>{`
        .admin-ops-grid {
          grid-template-columns: 1.7fr 1fr;
        }

        .modal-overlay {
          position: fixed;
          inset: 0;
          z-index: 9998;
          background: rgba(7, 17, 29, 0.48);
          display: grid;
          place-items: center;
          padding: 16px;
        }

        .modal-card {
          width: min(520px, 100%);
          border-radius: 16px;
          border: 1px solid #d4e2ef;
          background: #fff;
          box-shadow: 0 24px 36px -24px rgba(15, 31, 51, 0.66);
          padding: 18px;
        }

        @media (max-width: 1200px) {
          .admin-ops-grid {
            grid-template-columns: 1fr;
          }
        }

        .detail-modal-card > div:nth-child(2) {
          scrollbar-width: thin;
        }

        @media (max-width: 900px) {
          .detail-modal-card > div:nth-child(2) {
            grid-template-columns: 1fr !important;
          }
          .page-container > section:first-of-type {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 640px) {
          .page-container > section:first-of-type {
            grid-template-columns: 1fr;
          }
        }

        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(-8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};

export default AdminDashboard;

