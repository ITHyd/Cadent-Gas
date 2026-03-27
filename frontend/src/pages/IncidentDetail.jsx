import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { formatUseCase } from '../utils/formatters';
import { formatIncidentId, formatReferenceId } from '../utils/incidentIds';
import {
  getIncident,
  addUserNote,
  updateUserNote,
  deleteUserNote,
  updateSmsPreference,
  validateIncident,
  confirmIncidentValid,
  markIncidentFalse,
} from '../services/api';

/* ═══════════════════════════════════════════════════════════════════
   DESIGN TOKENS
   ═══════════════════════════════════════════════════════════════════ */
const T = {
  bg: '#eaf2f9',
  card: '#ffffff',
  primary: '#030304',
  primaryLight: '#edf5fc',
  primaryBorder: '#c8dceb',
  text: '#102842',
  textMuted: '#4d6178',
  textFaint: '#7f93aa',
  border: '#d7e3ee',
  borderLight: '#e9f0f7',
  green: '#047857',
  red: '#b91c1c',
  orange: '#f59e0b',
  purple: '#8DE971',
  radius: '16px',
  radiusSm: '12px',
  radiusPill: '999px',
  shadow: '0 14px 24px -22px rgba(15,31,51,0.54)',
  shadowLg: '0 24px 40px -30px rgba(15,31,51,0.68)',
  shadowHover: '0 28px 42px -30px rgba(15,31,51,0.78)',
  font: "'Nunito', 'Calibri', -apple-system, BlinkMacSystemFont, sans-serif",
};

const Card = ({ children, style, hoverable, ...props }) => {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      onMouseEnter={hoverable ? () => setHovered(true) : undefined}
      onMouseLeave={hoverable ? () => setHovered(false) : undefined}
      style={{
        background: T.card,
        borderRadius: T.radius,
        boxShadow: hovered ? T.shadowHover : T.shadow,
        transition: 'all 0.25s cubic-bezier(.4,0,.2,1)',
        transform: hovered ? 'translateY(-2px)' : 'translateY(0)',
        overflow: 'hidden',
        ...style,
      }}
      {...props}
    >
      {children}
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

/* ═══════════════════════════════════════════════════════════════════
   LEAFLET ICONS
   ═══════════════════════════════════════════════════════════════════ */
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const incidentPinIcon = L.divIcon({
  className: 'incident-pin',
  html: `<div style="display:flex;flex-direction:column;align-items:center;">
    <div style="width:32px;height:32px;background:#ef4444;border:3px solid white;border-radius:50%;
      box-shadow:0 3px 12px rgba(239,68,68,0.5);display:flex;align-items:center;justify-content:center;
      font-size:14px;animation:pinPulse 2s ease-in-out infinite;">📍</div>
    <div style="margin-top:3px;padding:1px 8px;background:#ef4444;border-radius:8px;color:white;
      font-size:9px;font-weight:700;white-space:nowrap;box-shadow:0 2px 6px rgba(239,68,68,0.4);
      font-family:-apple-system,BlinkMacSystemFont,sans-serif;">Incident</div>
  </div>`,
  iconSize: [70, 56], iconAnchor: [35, 28], popupAnchor: [0, -28],
});

const createAgentVehicleIcon = (name, etaMins) => L.divIcon({
  className: 'agent-vehicle-pin',
  html: `<div style="display:flex;flex-direction:column;align-items:center;">
    <div style="position:relative;">
      <div style="width:40px;height:40px;background:linear-gradient(135deg,#030304,#0d0d1a);
        border:3px solid white;border-radius:50%;box-shadow:0 3px 12px rgba(3,3,4,0.5);
        display:flex;align-items:center;justify-content:center;font-size:18px;
        animation:vehicleBounce 2s ease-in-out infinite;">🚗</div>
      ${etaMins ? `<div style="position:absolute;top:-8px;right:-16px;background:#030304;color:white;
        font-size:8px;font-weight:800;padding:2px 5px;border-radius:6px;white-space:nowrap;
        box-shadow:0 2px 6px rgba(79,70,229,0.4);font-family:-apple-system,sans-serif;">~${etaMins}m</div>` : ''}
    </div>
    <div style="margin-top:3px;padding:1px 8px;background:linear-gradient(135deg,#030304,#0d0d1a);
      border-radius:8px;color:white;font-size:9px;font-weight:700;white-space:nowrap;
      box-shadow:0 2px 6px rgba(3,3,4,0.4);font-family:-apple-system,sans-serif;">${name}</div>
  </div>`,
  iconSize: [80, 60], iconAnchor: [40, 30], popupAnchor: [0, -30],
});

const MapBoundsController = ({ points }) => {
  const map = useMap();
  useEffect(() => {
    if (points.length > 0) {
      if (points.length === 1) map.setView(points[0], 14);
      else map.fitBounds(L.latLngBounds(points), { padding: [50, 50], maxZoom: 14 });
    }
  }, [points, map]);
  return null;
};

/* ═══════════════════════════════════════════════════════════════════
   SKELETON LOADER
   ═══════════════════════════════════════════════════════════════════ */
const SkeletonBlock = ({ w, h, r, style }) => (
  <div style={{
    width: w || '100%', height: h || '16px', borderRadius: r || '8px',
    background: 'linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%)',
    backgroundSize: '200% 100%', animation: 'skeletonShimmer 1.5s ease-in-out infinite',
    ...style,
  }} />
);

const SkeletonCard = ({ h, children }) => (
  <div style={{
    background: T.card, borderRadius: T.radius, boxShadow: T.shadow,
    padding: '24px', height: h,
  }}>
    {children || (
      <>
        <SkeletonBlock w="40%" h="14px" style={{ marginBottom: '16px' }} />
        <SkeletonBlock h="12px" style={{ marginBottom: '10px' }} />
        <SkeletonBlock w="80%" h="12px" style={{ marginBottom: '10px' }} />
        <SkeletonBlock w="60%" h="12px" />
      </>
    )}
  </div>
);

const SkeletonPage = () => (
  <div style={{ minHeight: '100vh', background: T.bg, fontFamily: T.font }}>
    {/* Top bar skeleton */}
    <div style={{ background: T.card, padding: '16px 24px', boxShadow: T.shadow }}>
      <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', justifyContent: 'space-between' }}>
        <SkeletonBlock w="140px" h="20px" />
        <SkeletonBlock w="100px" h="20px" />
      </div>
    </div>
    {/* Hero skeleton */}
    <div style={{ background: T.card, padding: '28px 24px', marginBottom: '24px', boxShadow: T.shadow }}>
      <div style={{ maxWidth: '1280px', margin: '0 auto' }}>
        <SkeletonBlock w="280px" h="28px" style={{ marginBottom: '12px' }} />
        <SkeletonBlock w="200px" h="16px" />
      </div>
    </div>
    {/* Grid skeleton */}
    <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px', display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        <SkeletonCard h="180px" />
        <SkeletonCard h="140px" />
        <SkeletonCard h="200px" />
      </div>
      <div>
        <div style={{ background: T.card, borderRadius: T.radius, boxShadow: T.shadow, padding: '24px' }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
              <SkeletonBlock w="28px" h="28px" r="50%" />
              <div style={{ flex: 1 }}>
                <SkeletonBlock w="70%" h="12px" style={{ marginBottom: '6px' }} />
                <SkeletonBlock w="50%" h="10px" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

/* ═══════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════ */
const IncidentDetail = () => {
  const { incidentId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const isReporterView = location.pathname.startsWith('/my-reports/');
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [showActivityLog, setShowActivityLog] = useState(false);
  const [commTab, setCommTab] = useState('messages');
  const [showComm, setShowComm] = useState(false);
  const printRef = useRef(null);

  // Add Details modal
  const [showAddDetails, setShowAddDetails] = useState(false);
  const [userNote, setUserNote] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  // Edit/Delete notes
  const [editingNote, setEditingNote] = useState(null); // { note_id, note }
  const [editNoteText, setEditNoteText] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [deletingNoteId, setDeletingNoteId] = useState(null);

  // SMS preference
  const [smsUpdating, setSmsUpdating] = useState(false);
  const [kbReviewBusy, setKbReviewBusy] = useState('');
  const [expandedKbMatch, setExpandedKbMatch] = useState(null);

  // Toast
  const [toast, setToast] = useState(null);

  /* ── Data Fetching ───────────────────────────────────────────── */
  const fetchIncidentDetail = async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      const data = await getIncident(incidentId);
      setIncident(data);
      setError(null);
    } catch {
      setError('Failed to load incident details');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchIncidentDetail();
    const interval = setInterval(() => fetchIncidentDetail(true), 30000);
    return () => clearInterval(interval);
  }, [incidentId]);

  const handleKbRevalidate = async () => {
    try {
      setKbReviewBusy('validate');
      await validateIncident(incidentId);
      await fetchIncidentDetail(true);
      showToastMsg('KB validation refreshed');
    } catch (err) {
      showToastMsg(err.message || 'Failed to re-validate incident', 'error');
    } finally {
      setKbReviewBusy('');
    }
  };

  const handleKbConfirmValid = async () => {
    try {
      setKbReviewBusy('confirm');
      await confirmIncidentValid(incidentId);
      await fetchIncidentDetail(true);
      showToastMsg('Incident marked as true incident');
    } catch (err) {
      showToastMsg(err.message || 'Failed to confirm incident', 'error');
    } finally {
      setKbReviewBusy('');
    }
  };

  const handleKbMarkFalse = async () => {
    try {
      setKbReviewBusy('false');
      await markIncidentFalse(incidentId, 'Marked as false report from incident review');
      await fetchIncidentDetail(true);
      showToastMsg('Incident marked as false report');
    } catch (err) {
      showToastMsg(err.message || 'Failed to mark incident as false', 'error');
    } finally {
      setKbReviewBusy('');
    }
  };


  /* ── Format Helpers ──────────────────────────────────────────── */
  const formatDate = (ds) => {
    if (!ds) return '';
    return new Date(ds).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const formatTimeAgo = (ds) => {
    if (!ds) return '';
    const diff = Date.now() - new Date(ds).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return 'Just now';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  };

  const formatAbsTime = (ds) => {
    if (!ds) return '';
    return new Date(ds).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  };

  /* ── Status / Outcome Helpers ────────────────────────────────── */
  const statusColors = {
    new: '#030304', submitted: '#0e7490', classifying: '#8DE971',
    in_progress: '#f59e0b', paused: '#f59e0b', analyzing: '#f59e0b',
    pending_company_action: '#ef4444', dispatched: '#8DE971',
    resolved: '#f59e0b', completed: '#10b981', emergency: '#ef4444',
    false_report: '#6b7280', closed: '#6b7280',
  };
  const statusLabels = {
    new: 'New', submitted: 'Submitted', classifying: 'Classifying',
    in_progress: 'In Progress', paused: 'Paused', analyzing: 'Analyzing',
    pending_company_action: 'Pending Action', dispatched: 'Engineer Dispatched',
    resolved: 'Under Review', completed: 'Completed', emergency: 'Emergency',
    false_report: 'False Report', closed: 'Closed',
  };
  const outcomeLabels = {
    emergency_dispatch: 'Emergency Dispatch', schedule_engineer: 'Engineer Scheduled',
    monitor: 'Monitoring', close_with_guidance: 'Closed with Guidance', false_report: 'No Action Required',
  };
  const getStatusColor = (s) => statusColors[s] || '#6b7280';
  const getStatusLabel = (s) => statusLabels[s] || s;
  const getOutcomeLabel = (o) => outcomeLabels[o] || o?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || '';
  const isActive = (s) => ['new', 'submitted', 'in_progress', 'analyzing', 'pending_company_action', 'dispatched', 'emergency'].includes(s);

  /* ── Agent Helpers ───────────────────────────────────────────── */
  const getInitials = (n) => n ? n.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) : '👤';

  const agentStatusStyles = {
    ASSIGNED: { bg: '#ebf4fb', text: '#030304', dot: '#030304' },
    EN_ROUTE: { bg: '#fef3c7', text: '#92400e', dot: '#f59e0b' },
    ON_SITE: { bg: '#e0e7ff', text: '#3730a3', dot: '#8DE971' },
    IN_PROGRESS: { bg: '#fce7f3', text: '#9d174d', dot: '#8DE971' },
    COMPLETED: { bg: '#d1fae5', text: '#065f46', dot: '#10b981' },
  };
  const getAgentStatusStyle = (s) => agentStatusStyles[s] || { bg: '#f3f4f6', text: '#374151', dot: '#9ca3af' };
  const isAgentActive = (s) => ['ASSIGNED', 'EN_ROUTE', 'ON_SITE', 'IN_PROGRESS'].includes(s);


  const getAgentETA = (a) => {
    if (!a || !a.geo_coordinates) return null;
    const dists = {
      'Westminster, London': { km: 8.2, mins: 25 },
      'Canary Wharf, London': { km: 6.5, mins: 22 },
      'Deansgate, Manchester': { km: 11.3, mins: 35 },
      'Headingley, Leeds': { km: 7.8, mins: 24 },
      'Clifton, Bristol': { km: 9.6, mins: 28 },
    };
    return dists[a.location] || { km: 10.0, mins: 30 };
  };

  /* ── Timeline Helpers ────────────────────────────────────────── */
  const getTimelineAvatar = (step) => {
    const cat = step.category || 'system';
    if (step.completed) return { icon: '✓', bg: '#d1fae5', border: '#6ee7b7', color: '#059669' };
    if (step.in_progress) {
      const m = {
        system: { icon: '⚙️', bg: '#ebf4fb', border: '#b4ccdf', color: '#030304' },
        engineer: { icon: '👷', bg: '#ebf4fb', border: '#c4b5fd', color: '#8DE971' },
        ai: { icon: '🤖', bg: '#e5f4f1', border: '#8ec7bf', color: '#8DE971' }
      };
      return m[cat] || m.system;
    }
    return { icon: '○', bg: '#f9fafb', border: '#d7e3ee', color: '#d1d5db' };
  };

  const getActionTag = (step) => {
    if (!step.completed && !step.in_progress) return null;
    const auto = ['received', 'validated', 'closed'];
    return auto.includes(step.step) ? { label: 'Auto', bg: '#f1f5f9', color: '#64748b' } : { label: 'Manual', bg: '#ebf4fb', color: '#030304' };
  };

  /* ── Communication Helpers ───────────────────────────────────── */
  const getCommAvatar = (entry) => {
    const msg = (entry.message || '').toLowerCase();
    if (msg.includes('ai') || msg.includes('assess') || msg.includes('classif') || msg.includes('outcome')) return { icon: '🤖', label: 'System', bg: '#f1f5f9', color: '#475569' };
    if (msg.includes('engineer') || msg.includes('agent') || msg.includes('assign') || msg.includes('dispatch')) return { icon: '👷', label: 'Engineer', bg: '#ebf4fb', color: '#8DE971' };
    return { icon: '⚙️', label: 'System', bg: '#f1f5f9', color: '#475569' };
  };

  /* -- Toast Helper ---------------------------------------------------- */
  const showToastMsg = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3200);
  };

  /* -- Add Note Handler ------------------------------------------------ */
  const handleAddNote = async () => {
    if (!userNote.trim()) return;
    try {
      setAddingNote(true);
      await addUserNote(incidentId, userNote.trim());
      showToastMsg('Note added successfully');
      setUserNote('');
      setShowAddDetails(false);
      fetchIncidentDetail(true);
    } catch {
      showToastMsg('Failed to add note', 'error');
    } finally {
      setAddingNote(false);
    }
  };

  /* -- Edit Note Handler ----------------------------------------------- */
  const handleEditNote = async () => {
    if (!editNoteText.trim() || !editingNote) return;
    try {
      setSavingEdit(true);
      await updateUserNote(incidentId, editingNote.note_id, editNoteText.trim());
      showToastMsg('Note updated successfully');
      setEditingNote(null);
      setEditNoteText('');
      fetchIncidentDetail(true);
    } catch {
      showToastMsg('Failed to update note', 'error');
    } finally {
      setSavingEdit(false);
    }
  };

  /* -- Delete Note Handler ---------------------------------------------- */
  const handleDeleteNote = async (noteId) => {
    try {
      setDeletingNoteId(noteId);
      await deleteUserNote(incidentId, noteId);
      showToastMsg('Note deleted successfully');
      fetchIncidentDetail(true);
    } catch {
      showToastMsg('Failed to delete note', 'error');
    } finally {
      setDeletingNoteId(null);
    }
  };

  /* -- SMS Preference Handler ------------------------------------------ */
  const handleToggleSms = async () => {
    if (!incident) return;
    const currentPref = incident.structured_data?._sms_preference;
    const newEnabled = !(currentPref?.enabled);
    try {
      setSmsUpdating(true);
      await updateSmsPreference(incidentId, newEnabled);
      showToastMsg(newEnabled ? 'SMS notifications enabled' : 'SMS notifications disabled');
      fetchIncidentDetail(true);
    } catch {
      showToastMsg('Failed to update SMS preference', 'error');
    } finally {
      setSmsUpdating(false);
    }
  };

  /* -- Download Report Handler ----------------------------------------- */
  const handleDownloadReport = () => {
    if (!incident) return;

    const lines = [];
    const hr = '-'.repeat(60);
    const addSection = (title) => { lines.push(''); lines.push(hr); lines.push(`  ${title.toUpperCase()}`); lines.push(hr); };

    lines.push('-'.repeat(60));
    lines.push('  INCIDENT REPORT');
    lines.push('-'.repeat(60));
    lines.push(`  Reference: ${shortRef}`);
    lines.push(`  Incident ID: ${formatIncidentId(incident.incident_id)}`);
    lines.push(`  Generated: ${new Date().toLocaleString('en-GB')}`);

    addSection('Incident Overview');
    lines.push(`  Type: ${incidentType}`);
    lines.push(`  Status: ${getStatusLabel(incident.status)}`);
    if (incident.outcome) lines.push(`  Outcome: ${getOutcomeLabel(incident.outcome)}`);
    lines.push(`  Reported: ${formatDate(incident.created_at)}`);
    if (incident.location) lines.push(`  Location: ${incident.location}`);
    if (incident.risk_score != null) lines.push(`  Risk Score: ${(incident.risk_score * 100).toFixed(0)}%`);
    if (incident.confidence_score != null) lines.push(`  Confidence: ${(incident.confidence_score * 100).toFixed(0)}%`);

    addSection('Description');
    lines.push(`  ${incident.description || 'No description available'}`);

    if (incident.user_name || incident.user_phone || incident.user_address) {
      addSection('Reporter Information');
      if (incident.user_name) lines.push(`  Name: ${incident.user_name}`);
      if (incident.user_phone) lines.push(`  Phone: ${incident.user_phone}`);
      if (incident.user_address) lines.push(`  Address: ${incident.user_address}`);
    }

    if (sla.sla_hours || sla.estimated_resolution_at) {
      addSection('SLA Information');
      if (sla.sla_hours) lines.push(`  SLA Window: ${sla.sla_hours} hours`);
      if (sla.estimated_resolution_at) lines.push(`  Est. Resolution: ${formatDate(sla.estimated_resolution_at)}`);
    }

    if (agent) {
      addSection('Assigned Engineer');
      lines.push(`  Name: ${agent.full_name}`);
      lines.push(`  Specialization: ${agent.specialization}`);
      if (agent.phone) lines.push(`  Phone: ${agent.phone}`);
      if (agent.email) lines.push(`  Email: ${agent.email}`);
      lines.push(`  Jobs Completed: ${agent.total_jobs_completed}`);
      if (incident.agent_status) lines.push(`  Current Status: ${incident.agent_status_label || incident.agent_status}`);
      if (incident.assigned_at) lines.push(`  Assigned At: ${formatDate(incident.assigned_at)}`);
    }

    if (timeline.length > 0) {
      addSection('Incident Timeline');
      timeline.forEach((step) => {
        const status = step.completed ? '[DONE]' : step.in_progress ? '[IN PROGRESS]' : '[PENDING]';
        const ts = step.timestamp ? formatDate(step.timestamp) : '';
        lines.push(`  ${status} ${step.label}`);
        if (ts) lines.push(`         ${ts}`);
        lines.push(`         ${step.message}`);
      });
    }

    if (statusHistory.length > 0) {
      addSection('Activity Log');
      [...statusHistory].reverse().forEach((entry) => {
        const status = (entry.status || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        lines.push(`  [${formatDate(entry.timestamp)}] ${status}`);
        if (entry.message) lines.push(`    ${entry.message}`);
      });
    }

    const notifs = incident.customer_notifications || [];
    if (notifs.length > 0) {
      addSection('Customer Notifications');
      [...notifs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).forEach((n) => {
        lines.push(`  [${formatDate(n.created_at)}] ${n.title}`);
        lines.push(`    ${n.message}`);
      });
    }

    const userNotes = incident.structured_data?._user_notes || [];
    if (userNotes.length > 0) {
      addSection('User Notes');
      userNotes.forEach((n) => {
        lines.push(`  [${formatDate(n.created_at)}] ${n.note}`);
      });
    }

    if (incident.resolution_notes || incident.items_used?.length > 0) {
      addSection('Resolution');
      if (incident.resolution_notes) lines.push(`  Notes: ${incident.resolution_notes}`);
      if (incident.resolved_by) lines.push(`  Resolved By: ${incident.resolved_by}`);
      if (incident.resolved_at) lines.push(`  Resolved At: ${formatDate(incident.resolved_at)}`);
      if (incident.items_used?.length > 0) lines.push(`  Equipment Used: ${incident.items_used.join(', ')}`);
    }

    const chatHistory = incident.conversation_history || [];
    if (chatHistory.length > 0) {
      addSection('Chat History');
      chatHistory.forEach((msg) => {
        const role = (msg.role === 'agent' || msg.role === 'system') ? 'AI Agent' : 'Customer';
        const text = typeof msg.content === 'string' ? msg.content : (msg.content?.message || msg.content?.question || JSON.stringify(msg.content));
        if (!text) return;
        const ts = msg.timestamp ? new Date(msg.timestamp).toLocaleString('en-GB') : '';
        lines.push(`  [${role}]${ts ? ` ${ts}` : ''}`);
        lines.push(`    ${text}`);
        lines.push('');
      });
    }

    lines.push('');
    lines.push('-'.repeat(60));
    lines.push('  END OF REPORT');
    lines.push('-'.repeat(60));

    const content = lines.join('\n');
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Incident-Report-${shortRef}-${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  /* ── Loading & Error ─────────────────────────────────────────── */
  if (loading) return <SkeletonPage />;

  if (error || !incident) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: T.bg, fontFamily: T.font }}>
        <Card style={{ textAlign: 'center', maxWidth: '380px', padding: '48px 32px' }}>
          <div style={{ fontSize: '3.5rem', marginBottom: '16px' }}>⚠️</div>
          <div style={{ fontSize: '1.25rem', fontWeight: '700', color: T.text, marginBottom: '8px' }}>{error || 'Incident not found'}</div>
          <p style={{ fontSize: '1rem', color: T.textMuted, marginBottom: '24px', lineHeight: 1.5 }}>Please try again or go back to your reports.</p>
          <button onClick={() => navigate('/my-reports', { replace: true })} style={{
            padding: '10px 24px', background: T.primary, color: 'white', border: 'none',
            borderRadius: T.radiusSm, cursor: 'pointer', fontSize: '0.95rem', fontWeight: '600',
          }}>Back to My Reports</button>
        </Card>
      </div>
    );
  }

  /* ═══════════════════════════════════════════════════════════════
     DERIVED STATE
     ═══════════════════════════════════════════════════════════════ */
  const timeline = incident.timeline || [];
  const sla = incident.sla || {};
  const active = isActive(incident.status);
  const incidentType = formatUseCase(incident.incident_type || incident.classified_use_case || 'Incident');
  const shortRef = formatReferenceId(incident.incident_id);
  const agent = incident.assigned_agent;
  const statusHistory = incident.status_history || [];
  const statusColor = getStatusColor(incident.status);
  const eta = agent ? getAgentETA(agent) : null;
  const hasMapData = (incident.latitude && incident.longitude) || (agent && agent.geo_coordinates);
  const agentCoords = agent?.geo_coordinates ? [agent.geo_coordinates.lat, agent.geo_coordinates.lng] : null;
  const incidentCoords = incident.latitude ? [incident.latitude, incident.longitude] : null;

  /* ═══════════════════════════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════════════════════════ */
  return (
    <div ref={printRef} className="incident-detail-page" style={{ minHeight: '100vh', background: T.bg, fontFamily: T.font }}>

      {/* ═══ STICKY TOP BAR ═══════════════════════════════════════ */}
      <div className="no-print" style={{
        background: 'rgba(255,255,255,0.88)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid rgba(229,231,235,0.6)',
        padding: '12px 0', position: 'sticky', top: 0, zIndex: 50,
      }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', minWidth: 0 }}>
            <button onClick={() => navigate('/my-reports', { replace: true })} style={{
              background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.95rem',
              color: T.primary, fontWeight: '600', display: 'flex', alignItems: 'center', gap: '4px', padding: '6px 0',
            }}>← My Reports</button>
            <div style={{ width: '1px', height: '20px', background: T.border }} />
            <span style={{
              fontFamily: 'monospace', fontSize: '0.9rem', color: T.primary,
              background: T.primaryLight, padding: '4px 10px', borderRadius: '6px', fontWeight: '600',
              whiteSpace: 'nowrap', overflow: 'visible', flexShrink: 0,
            }}>{shortRef}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Live indicator */}
            {active && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '4px 12px', borderRadius: T.radiusPill,
                background: '#fef2f2', border: '1px solid #fecaca',
              }}>
                <div style={{ position: 'relative', width: '8px', height: '8px' }}>
                  <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: T.red }} />
                  <div style={{ position: 'absolute', inset: '-3px', borderRadius: '50%', border: `2px solid ${T.red}`, opacity: 0.4, animation: 'liveRing 2s ease-out infinite' }} />
                </div>
                <span style={{ fontSize: '0.8rem', fontWeight: '800', color: '#dc2626', letterSpacing: '0.08em' }}>LIVE</span>
              </div>
            )}
            {/* Refresh */}
            <button onClick={() => fetchIncidentDetail(true)} disabled={refreshing} style={{
              background: refreshing ? T.primaryLight : '#f8fafc',
              border: `1px solid ${refreshing ? T.primaryBorder : T.border}`, borderRadius: '8px',
              padding: '6px 14px', fontSize: '0.9rem', fontWeight: '600',
              color: refreshing ? T.primary : T.textMuted, cursor: refreshing ? 'default' : 'pointer',
              transition: 'all 0.2s',
            }}>
              <span style={{ display: 'inline-block', animation: refreshing ? 'spin 1s linear infinite' : 'none' }}>🔄</span>
              {' '}{refreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      {/* ═══ HERO SECTION ════════════════════════════════════════ */}
      <div style={{ background: T.card, boxShadow: '0 1px 3px rgba(0,0,0,0.04)', padding: '28px 0' }}>
        <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '24px', flexWrap: 'wrap' }}>
            <div>
              <h1 style={{ fontSize: '1.85rem', fontWeight: '800', color: T.text, margin: '0 0 10px', letterSpacing: '-0.025em' }}>
                {incidentType}
              </h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <div style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  padding: '4px 14px', borderRadius: T.radiusPill,
                  background: statusColor + '14', border: `1px solid ${statusColor}30`,
                }}>
                  <div style={{
                    width: '7px', height: '7px', borderRadius: '50%', background: statusColor,
                    ...(active ? { animation: 'pulse 2s infinite' } : {}),
                  }} />
                  <span style={{ fontSize: '0.9rem', fontWeight: '700', color: statusColor }}>{getStatusLabel(incident.status)}</span>
                </div>
                <span style={{ fontSize: '0.9rem', color: T.textFaint }}>Reported {formatTimeAgo(incident.created_at)}</span>
                {incident.location && (
                  <span style={{ fontSize: '0.9rem', color: T.textMuted }}>📍 {incident.location}</span>
                )}
              </div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              {incident.status === 'resolved' || incident.status === 'completed' ? (
                <div>
                  <div style={{ fontSize: '0.8rem', color: T.green, fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Resolved</div>
                  <div style={{ fontSize: '1.15rem', fontWeight: '700', color: '#059669' }}>{formatDate(incident.resolved_at)}</div>
                </div>
              ) : sla.estimated_resolution_at && active ? (
                <div>
                  <div style={{ fontSize: '0.8rem', color: T.purple, fontWeight: '700', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Est. Resolution
                  </div>
                  <div style={{ fontSize: '1.15rem', fontWeight: '700', color: '#8DE971' }}>
                    {formatDate(sla.estimated_resolution_at)}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {/* ═══ MAIN GRID ═══════════════════════════════════════════ */}
      <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px', alignItems: 'start' }}>

          {/* ═══ LEFT COLUMN ═══════════════════════════════════════ */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

            {/* ── Engineer Card ────────────────────────────────────── */}
            {agent ? (
              <Card hoverable>
                {/* ETA Banner */}
                {isAgentActive(incident.agent_status) && eta && (
                  <div style={{
                    background: 'linear-gradient(135deg, #030304 0%, #0d0d1a 100%)',
                    padding: '16px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div>
                      <div style={{ fontSize: '0.75rem', fontWeight: '700', color: 'rgba(255,255,255,0.65)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        Estimated Arrival
                      </div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '2px' }}>
                        <span style={{ fontSize: '1.35rem', fontWeight: '800', color: 'white' }}>~{eta.mins} mins</span>
                        <span style={{ fontSize: '0.85rem', fontWeight: '600', color: 'rgba(255,255,255,0.55)' }}>({eta.km} km away)</span>
                      </div>
                    </div>
                    <div style={{ fontSize: '2rem', animation: 'vehicleBounce 2s ease-in-out infinite' }}>🚗</div>
                  </div>
                )}
                <div style={{ padding: '24px' }}>
                  {/* Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Assigned Engineer</span>
                    <div style={{
                      display: 'inline-flex', alignItems: 'center', gap: '5px',
                      padding: '3px 10px', borderRadius: T.radiusPill, fontSize: '0.8rem', fontWeight: '700',
                      background: getAgentStatusStyle(incident.agent_status).bg,
                      color: getAgentStatusStyle(incident.agent_status).text,
                    }}>
                      <div style={{
                        width: '6px', height: '6px', borderRadius: '50%',
                        background: getAgentStatusStyle(incident.agent_status).dot,
                        ...(isAgentActive(incident.agent_status) ? { animation: 'pulse 2s infinite' } : {}),
                      }} />
                      {incident.agent_status_label || incident.agent_status || 'Assigned'}
                    </div>
                  </div>
                  {/* Profile */}
                  <div style={{ display: 'flex', gap: '14px', alignItems: 'center', marginBottom: '16px' }}>
                    <div style={{
                      width: '48px', height: '48px', borderRadius: '14px',
                      background: 'linear-gradient(135deg, #030304, #0d0d1a)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'white', fontSize: '1rem', fontWeight: '800', flexShrink: 0,
                    }}>{getInitials(agent.full_name)}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '1.1rem', fontWeight: '700', color: T.text }}>{agent.full_name}</div>
                      <div style={{ fontSize: '0.9rem', color: T.textMuted }}>{agent.specialization}</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '3px' }}>
                        <span style={{ fontSize: '0.85rem', color: T.textFaint }}>{agent.total_jobs_completed} jobs</span>
                      </div>
                    </div>
                  </div>
                  {/* Chips */}
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
                    {agent.location && (
                      <span style={{ fontSize: '0.82rem', color: T.primary, fontWeight: '600', background: T.primaryLight, padding: '4px 10px', borderRadius: '8px' }}>📍 {agent.location}</span>
                    )}
                    {agent.experience_years && (
                      <span style={{ fontSize: '0.82rem', color: T.textMuted, fontWeight: '500', background: '#f8fafc', padding: '4px 10px', borderRadius: '8px', border: `1px solid ${T.border}` }}>{agent.experience_years}y exp</span>
                    )}
                  </div>
                  {/* Contact */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <a href={`tel:${agent.phone}`} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                      padding: '10px', background: '#f0fdf4', borderRadius: T.radiusSm,
                      border: '1px solid #bbf7d0', textDecoration: 'none', color: '#15803d',
                      fontSize: '0.9rem', fontWeight: '700', transition: 'transform 0.15s',
                    }}>📞 Call</a>
                    {agent.email && (
                      <a href={`mailto:${agent.email}`} style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        padding: '10px', background: T.primaryLight, borderRadius: T.radiusSm,
                        border: `1px solid ${T.primaryBorder}`, textDecoration: 'none', color: '#030304',
                        fontSize: '0.9rem', fontWeight: '700', transition: 'transform 0.15s',
                      }}>✉️ Email</a>
                    )}
                  </div>
                </div>
              </Card>
            ) : incident.assigned_agent_id ? (
              <Card hoverable>
                {isAgentActive(incident.agent_status) && (
                  <div style={{
                    background: 'linear-gradient(135deg, #030304, #0d0d1a)',
                    padding: '14px 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div>
                      <div style={{ fontSize: '0.75rem', fontWeight: '700', color: 'rgba(255,255,255,0.65)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Estimated Arrival</div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px' }}>
                        <span style={{ fontSize: '1.25rem', fontWeight: '800', color: 'white' }}>~30 mins</span>
                        <span style={{ fontSize: '0.85rem', fontWeight: '600', color: 'rgba(255,255,255,0.55)' }}>(calculating...)</span>
                      </div>
                    </div>
                    <div style={{ fontSize: '1.75rem', animation: 'vehicleBounce 2s ease-in-out infinite' }}>🚗</div>
                  </div>
                )}
                <div style={{ padding: '24px', display: 'flex', gap: '14px', alignItems: 'center' }}>
                  <div style={{
                    width: '48px', height: '48px', borderRadius: '14px',
                    background: 'linear-gradient(135deg, #030304, #0d0d1a)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'white', fontSize: '1.25rem', flexShrink: 0,
                  }}>✓</div>
                  <div>
                    <div style={{ fontSize: '1rem', fontWeight: '700', color: T.text }}>Engineer Dispatched</div>
                    <div style={{ fontSize: '0.9rem', color: T.textMuted }}>A qualified engineer is on the way.</div>
                    <div style={{ fontSize: '0.85rem', color: T.textFaint, fontFamily: 'monospace', marginTop: '3px' }}>ID: {incident.assigned_agent_id}</div>
                  </div>
                </div>
              </Card>
            ) : (
              incident.outcome && ['emergency_dispatch', 'schedule_engineer'].includes(incident.outcome) && (
                <Card>
                  <div style={{ height: '3px', background: 'linear-gradient(90deg, #030304, #8DE971, #030304)', backgroundSize: '200% 100%', animation: 'shimmer 2s linear infinite' }} />
                  <div style={{ padding: '32px', textAlign: 'center' }}>
                    <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>🔍</div>
                    <div style={{ fontSize: '1.15rem', fontWeight: '700', color: T.text, marginBottom: '6px' }}>Finding an Engineer</div>
                    <p style={{ fontSize: '0.9rem', color: T.textMuted, margin: '0 0 16px', lineHeight: 1.6 }}>We&apos;re matching you with the best available engineer nearby.</p>
                    <div style={{
                      display: 'inline-flex', alignItems: 'center', gap: '6px',
                      padding: '4px 12px', background: '#edf5fc', borderRadius: T.radiusPill,
                      border: '1px solid #cde0ef', fontSize: '0.8rem', color: '#8DE971', fontWeight: '700',
                    }}>
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: T.purple, animation: 'pulse 2s infinite' }} />
                      Searching
                    </div>
                  </div>
                </Card>
              )
            )}

            {/* ── Customer Notifications Card ──────────────────────── */}
            {(incident.customer_notifications || []).length > 0 && (() => {
              const notifications = [...incident.customer_notifications].sort(
                (a, b) => new Date(b.created_at) - new Date(a.created_at)
              );
              const severityStyles = {
                info: { bg: '#edf5fc', border: '#b4ccdf', color: '#030304', icon: 'ℹ️' },
                warning: { bg: '#fff7ed', border: '#fed7aa', color: '#b45309', icon: '⚠️' },
                critical: { bg: '#fef2f2', border: '#fecaca', color: '#b91c1c', icon: '🚨' },
              };

              return (
                <Card hoverable style={{ overflow: 'hidden' }}>
                  <div style={{
                    padding: '18px 24px',
                    borderBottom: `1px solid ${T.borderLight}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                        Updates & Notifications
                      </span>
                      <span style={{
                        fontSize: '0.75rem', fontWeight: '700', color: T.primary,
                        background: T.primaryLight, padding: '2px 8px', borderRadius: T.radiusPill,
                      }}>
                        {notifications.length}
                      </span>
                    </div>
                  </div>
                  <div style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {notifications.map((notif) => {
                      const sev = severityStyles[notif.severity] || severityStyles.info;
                      return (
                        <div
                          key={notif.notification_id}
                          style={{
                            padding: '12px 14px',
                            borderRadius: T.radiusSm,
                            background: sev.bg,
                            border: `1px solid ${sev.border}`,
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '4px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <span style={{ fontSize: '0.95rem' }}>{sev.icon}</span>
                              <span style={{ fontSize: '0.88rem', fontWeight: '700', color: sev.color }}>
                                {notif.title}
                              </span>
                            </div>
                            <span style={{ fontSize: '0.75rem', color: T.textFaint, whiteSpace: 'nowrap' }}>
                              {formatTimeAgo(notif.created_at)}
                            </span>
                          </div>
                          <p style={{ margin: 0, fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>
                            {notif.message}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              );
            })()}

            {/* Manual Report Banner */}
            {incident.structured_data?.manual_report && (
              <Card style={{ padding: '16px', background: '#ede9fe', border: '1px solid #c4b5fd' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <span style={{
                    fontSize: '0.78rem', fontWeight: 700, color: '#5b21b6',
                    background: '#fff', padding: '4px 12px', borderRadius: T.radiusPill,
                    border: '1px solid #c4b5fd',
                  }}>
                    Manual Report
                  </span>
                  <span style={{ fontSize: '0.84rem', color: '#5b21b6', fontWeight: 600 }}>
                    This incident was submitted as a manual report (no automated workflow available).
                  </span>
                  {incident.structured_data?.severity && (
                    <span style={{
                      marginLeft: 'auto',
                      fontSize: '0.76rem', fontWeight: 700,
                      padding: '4px 12px', borderRadius: T.radiusPill,
                      background: incident.structured_data.severity === 'critical' ? '#fef2f2'
                        : incident.structured_data.severity === 'high' ? '#fef2f2'
                          : incident.structured_data.severity === 'medium' ? '#fffbeb' : '#ecfdf5',
                      color: incident.structured_data.severity === 'critical' ? '#7f1d1d'
                        : incident.structured_data.severity === 'high' ? '#dc2626'
                          : incident.structured_data.severity === 'medium' ? '#b45309' : '#047857',
                      border: `1px solid ${incident.structured_data.severity === 'critical' ? '#fca5a5'
                        : incident.structured_data.severity === 'high' ? '#fca5a5'
                          : incident.structured_data.severity === 'medium' ? '#fde68a' : '#a7f3d0'
                        }`,
                    }}>
                      Severity: {incident.structured_data.severity.charAt(0).toUpperCase() + incident.structured_data.severity.slice(1)}
                    </span>
                  )}
                </div>
              </Card>
            )}

            {/* ── Description & Assessment Card ─────────────────────── */}
            <Card hoverable style={{ padding: '24px' }}>
              <h3 style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 12px' }}>Description</h3>
              <p style={{ fontSize: '0.95rem', color: '#334155', lineHeight: 1.7, margin: 0 }}>
                {incident.description || (() => {
                  const sd = incident.structured_data || {};
                  const useCase = (incident.classified_use_case || incident.incident_type || 'gas incident').replace(/_/g, ' ');
                  const parts = [`A ${useCase} incident was reported`];
                  if (incident.user_name) parts[0] += ` by ${incident.user_name}`;
                  if (incident.location || sd.location || incident.user_address) parts[0] += ` at ${incident.location || sd.location || incident.user_address}`;
                  parts[0] += '.';
                  if (sd.smell_intensity) parts.push(`Smell intensity was reported as ${sd.smell_intensity.toLowerCase()}.`);
                  if (sd.co_alarm_triggered) parts.push(`CO alarm triggered: ${sd.co_alarm_triggered}.`);
                  if (sd.co_symptoms) parts.push(`CO symptoms reported: ${sd.co_symptoms}.`);
                  if (sd.visible_damage) parts.push(`Visible damage: ${sd.visible_damage}.`);
                  if (incident.structured_data?.severity) parts.push(`Severity assessed as ${incident.structured_data.severity}.`);
                  const outcome = incident.structured_data?.outcome || incident.status;
                  if (outcome) parts.push(`Outcome: ${outcome.replace(/_/g, ' ')}.`);
                  return parts.join(' ');
                })()}
              </p>

              {/* ── Chatbot-Extracted Assessment ─────────────────────── */}
              {false && incident.structured_data && Object.keys(incident.structured_data).length > 0 && (() => {
                const sd = incident.structured_data;
                // Labels for known structured_data keys
                const labelMap = {
                  incident_type: 'Incident Type', smell_intensity: 'Smell Intensity', smell_location: 'Smell Location',
                  smell_time: 'Time of Smell', smell_duration: 'Smell Duration', appliance_age: 'Appliance Age',
                  other_appliances_affected: 'Other Appliances Affected', recent_area_changes: 'Recent Area Changes',
                  visible_damage: 'Visible Damage', outdoor_smell_strength: 'Outdoor Smell Strength',
                  recent_excavation: 'Recent Excavation Nearby', hissing_location: 'Hissing Location',
                  sound_type: 'Sound Type', meter_spinning: 'Meter Spinning', recent_gas_work: 'Recent Gas Work',
                  is_evacuated: 'Evacuated', co_symptoms: 'CO Symptoms', co_alarm_triggered: 'CO Alarm Triggered',
                  outage_time: 'Outage Time', neighbors_affected: 'Neighbors Affected', valve_position: 'Valve Position',
                  has_night_heating: 'Night Heating', night_smell_location: 'Night Smell Location',
                  nearby_gas_users: 'Nearby Gas Users', tampering_reason: 'Tampering Reason',
                  seal_status: 'Seal Status', consumption_change: 'Consumption Change',
                  symptoms: 'Health Symptoms', appliances_off: 'Appliances Turned Off',
                  meter_moving: 'Meter Moving (Appliances Off)', hissing_sound: 'Hissing Sound Detected',
                  co_alarm: 'CO Alarm Active', property_type: 'Property Type',
                  consumption_delta_pct: 'Consumption Delta', nearby_reports_count: 'Nearby Reports',
                };
                // Skip internal/binary/photo keys
                const skipKeys = ['flame_photo', 'area_photo', 'audio_recording', 'valve_photo', 'meter_photo',
                  'audio_provided', 'image_provided', 'video_provided', 'audio_leak_confidence',
                  'visual_damage_confidence', 'user_trust_score'];

                const entries = Object.entries(sd).filter(([k, v]) =>
                  !skipKeys.includes(k) && v !== null && v !== undefined && v !== '' && v !== 0
                );
                if (entries.length === 0) return null;

                // Separate critical indicators from regular details
                const criticalKeys = ['symptoms', 'co_alarm', 'co_alarm_triggered', 'co_symptoms', 'is_evacuated', 'hissing_sound', 'meter_moving'];
                const critical = entries.filter(([k]) => criticalKeys.includes(k) && (sd[k] === true || sd[k] === 'yes' || sd[k] === 'Yes'));
                const regular = entries.filter(([k]) => !criticalKeys.includes(k) || !(sd[k] === true || sd[k] === 'yes' || sd[k] === 'Yes'));

                const formatValue = (v) => {
                  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
                  if (typeof v === 'number') return v % 1 === 0 ? String(v) : v.toFixed(1);
                  return String(v).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                };

                const formatKey = (k) => labelMap[k] || k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

                return (
                  <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: `1px solid ${T.borderLight}` }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
                      <h4 style={{ fontSize: '0.75rem', fontWeight: '700', color: T.primary, textTransform: 'uppercase', letterSpacing: '0.05em', margin: 0 }}>
                        Assessment Details
                      </h4>
                      <span style={{ fontSize: '0.7rem', fontWeight: '600', color: T.textFaint, background: '#f8fafc', padding: '2px 8px', borderRadius: '4px' }}>
                        Extracted from chatbot
                      </span>
                    </div>

                    {/* Critical alerts */}
                    {critical.length > 0 && (
                      <div style={{
                        display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '14px',
                        padding: '10px 12px', background: '#fef2f2', borderRadius: '10px', border: '1px solid #fecaca',
                      }}>
                        <span style={{ fontSize: '0.8rem', fontWeight: '700', color: '#dc2626', marginRight: '4px' }}>⚠️ Alerts:</span>
                        {critical.map(([k], i) => (
                          <span key={i} style={{
                            padding: '2px 8px', background: '#fee2e2', borderRadius: '6px',
                            fontSize: '0.78rem', fontWeight: '700', color: '#b91c1c',
                          }}>{formatKey(k)}</span>
                        ))}
                      </div>
                    )}

                    {/* Regular extracted details */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0' }}>
                      {regular.map(([k, v], i) => (
                        <div key={k} style={{
                          padding: '8px 12px', borderRadius: '8px',
                          background: i % 2 === 0 ? '#f8fafc' : 'transparent',
                        }}>
                          <div style={{ fontSize: '0.72rem', color: T.textFaint, fontWeight: '600', marginBottom: '1px' }}>{formatKey(k)}</div>
                          <div style={{ fontSize: '0.88rem', fontWeight: '600', color: T.text }}>{formatValue(v)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {incident.resolution_notes && (
                <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: `1px solid ${T.borderLight}` }}>
                  <div style={{ borderLeft: '3px solid #10b981', paddingLeft: '12px' }}>
                    <h4 style={{ fontSize: '0.75rem', fontWeight: '700', color: T.green, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 6px' }}>Resolution Notes</h4>
                    <p style={{ fontSize: '0.95rem', color: '#334155', lineHeight: 1.7, margin: 0 }}>{incident.resolution_notes}</p>
                  </div>
                </div>
              )}
              {incident.items_used?.length > 0 && (
                <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: `1px solid ${T.borderLight}` }}>
                  <h4 style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 8px' }}>Equipment Used</h4>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {incident.items_used.map((item, i) => (
                      <span key={i} style={{
                        padding: '4px 10px', background: '#edf5fc', border: '1px solid #cde0ef',
                        borderRadius: '8px', fontSize: '0.85rem', color: '#030304', fontWeight: '600',
                      }}>{item}</span>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            {/* ── Live Map ─────────────────────────────────────────── */}
            {hasMapData && (
              <>
                <button onClick={() => setShowMap(!showMap)} className="no-print" style={{
                  width: '100%', padding: '14px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  background: showMap ? T.primary : T.card,
                  color: showMap ? '#fff' : T.primary,
                  border: showMap ? 'none' : `1px solid ${T.primaryBorder}`,
                  borderRadius: T.radius, fontSize: '0.95rem', fontWeight: '700',
                  cursor: 'pointer', transition: 'all 0.25s',
                  boxShadow: showMap ? '0 4px 16px rgba(79,70,229,0.3)' : T.shadow,
                }}>
                  📍 {showMap ? 'Hide Live Location' : 'View Live Location'}
                </button>
                {showMap && (
                  <Card style={{ animation: 'fadeSlideIn 0.35s ease' }}>
                    {/* Map Legend */}
                    <div style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '12px 20px', borderBottom: `1px solid ${T.borderLight}`,
                    }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: '700', color: T.text }}>Live Tracking</span>
                      <div style={{ display: 'flex', gap: '14px', fontSize: '0.8rem' }}>
                        {incidentCoords && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', color: T.red, fontWeight: '600' }}>
                            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: T.red, display: 'inline-block' }} />Incident
                          </span>
                        )}
                        {agentCoords && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', color: T.primary, fontWeight: '600' }}>
                            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: T.primary, display: 'inline-block' }} />Engineer
                          </span>
                        )}
                        {incidentCoords && agentCoords && (
                          <span style={{ display: 'flex', alignItems: 'center', gap: '5px', color: T.textFaint, fontWeight: '600' }}>
                            <span style={{ width: '16px', height: '2px', borderTop: '2px dashed #94a3b8', display: 'inline-block' }} />Route
                          </span>
                        )}
                      </div>
                    </div>
                    <div style={{ height: '320px' }}>
                      <MapContainer
                        center={incidentCoords || agentCoords}
                        zoom={13} style={{ height: '100%', width: '100%' }}
                        zoomControl={true} attributionControl={false}
                      >
                        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                        <MapBoundsController points={[...(incidentCoords ? [incidentCoords] : []), ...(agentCoords ? [agentCoords] : [])]} />
                        {/* Route polyline */}
                        {incidentCoords && agentCoords && (
                          <Polyline
                            positions={[agentCoords, incidentCoords]}
                            pathOptions={{ color: '#030304', weight: 3, dashArray: '10, 8', opacity: 0.7 }}
                          />
                        )}
                        {/* Incident marker */}
                        {incidentCoords && (
                          <Marker position={incidentCoords} icon={incidentPinIcon}>
                            <Popup>
                              <div style={{ padding: '8px', minWidth: '160px' }}>
                                <div style={{ fontSize: '13px', fontWeight: '700', color: T.text, marginBottom: '4px' }}>📍 Incident Location</div>
                                {incident.location && <div style={{ fontSize: '11px', color: T.textMuted }}>{incident.location}</div>}
                              </div>
                            </Popup>
                          </Marker>
                        )}
                        {/* Agent vehicle marker */}
                        {agentCoords && agent && (
                          <Marker position={agentCoords} icon={createAgentVehicleIcon(agent.full_name, eta?.mins)}>
                            <Popup>
                              <div style={{ padding: '8px', minWidth: '180px' }}>
                                <div style={{ fontSize: '13px', fontWeight: '700', color: T.text, marginBottom: '2px' }}>{agent.full_name}</div>
                                <div style={{ fontSize: '11px', color: T.textMuted, marginBottom: '2px' }}>{agent.specialization}</div>
                                {agent.location && <div style={{ fontSize: '11px', color: T.primary }}>📍 {agent.location}</div>}
                                {eta && <div style={{ fontSize: '11px', color: '#059669', fontWeight: '600', marginTop: '4px' }}>~{eta.mins} min · {eta.km} km away</div>}
                              </div>
                            </Popup>
                          </Marker>
                        )}
                      </MapContainer>
                    </div>
                  </Card>
                )}
              </>
            )}

            {/* ── Incident Details ─────────────────────────────────── */}
            <Card hoverable style={{ padding: '24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                <h3 style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0' }}>Incident Details</h3>
                {(() => {
                  const kbValidation = incident.structured_data?._kb_validation || incident.kb_validation_details;
                  const rawVerdict = (kbValidation?.verdict || kbValidation?.best_match_type || incident.kb_match_type || 'unknown').toString().toLowerCase();
                  if (!kbValidation && !incident.kb_match_type) return null;

                  const isTrue = rawVerdict === 'true';
                  const isFalse = rawVerdict === 'false';
                  const isAdminConfirmed = rawVerdict === 'admin_confirmed';
                  const confidence = kbValidation?.confidence ?? incident.kb_similarity_score ?? 0;
                  const percentage = Math.round(confidence * 100);
                  const trueOverall = Math.round(((((kbValidation?.true_kb_match ?? kbValidation?.true_kb_score) ?? 0) || 0)) * 100);
                  const falseOverall = Math.round(((((kbValidation?.false_kb_match ?? kbValidation?.false_kb_score) ?? 0) || 0)) * 100);
                  const reviewerOverride = Boolean(kbValidation?.reviewer_override);
                  const label = isTrue
                    ? 'Likely True Incident'
                    : isFalse
                      ? 'Likely False Report'
                      : isAdminConfirmed
                        ? 'Admin Confirmed'
                        : 'No strong KB match';
                  const reviewPrompt = isTrue
                    ? 'Do you want to mark this as a false report or re-validate it?'
                    : isFalse
                      ? 'Do you want to confirm this as a true incident or re-validate it?'
                      : 'Do you want to review this verdict or run validation again?';
                  const bg = isReporterView
                    ? (isTrue ? '#fef2f2' : isFalse ? '#ecfdf5' : '#eff6ff')
                    : (isTrue ? '#dcfce7' : isFalse ? '#fef3c7' : '#eff6ff');
                  const color = isReporterView
                    ? (isTrue ? '#b91c1c' : isFalse ? '#047857' : '#1d4ed8')
                    : (isTrue ? '#166534' : isFalse ? '#92400e' : '#1d4ed8');
                  const border = isReporterView
                    ? (isTrue ? '#fecaca' : isFalse ? '#86efac' : '#bfdbfe')
                    : (isTrue ? '#86efac' : isFalse ? '#fcd34d' : '#bfdbfe');

                  return (
                    <div style={{ display: 'grid', gap: '10px' }}>
                      <span style={isReporterView ? {
                        fontSize: '0.92rem',
                        fontWeight: '700',
                        color,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '8px',
                        width: 'fit-content',
                      } : {
                        padding: '6px 14px',
                        borderRadius: '8px',
                        fontSize: '0.85rem',
                        fontWeight: '700',
                        background: bg,
                        color,
                        border: `1px solid ${border}`,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        width: 'fit-content'
                      }}>
                        {isReporterView && (
                          <span style={{
                            width: '10px',
                            height: '10px',
                            borderRadius: '50%',
                            background: color,
                            display: 'inline-block',
                            flexShrink: 0,
                          }} />
                        )}
                        {label}{!isReporterView && (kbValidation?.confidence != null || incident.kb_similarity_score != null) ? ` - ${percentage}%` : ''}
                      </span>
                      {!isReporterView && (() => {
                        const trueMatches = kbValidation?.top_true_matches || [];
                        const falseMatches = kbValidation?.top_false_matches || [];
                        const canReviewKb = ['new', 'in_progress', 'pending_company_action', 'false_report', 'completed'].includes(incident.status) && !reviewerOverride;
                        if (!trueMatches.length && !falseMatches.length && !canReviewKb) return null;
                        return (
                          <div style={{ display: 'grid', gap: '10px' }}>
                            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                              <div style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid #bbf7d0', background: '#ecfdf5', color: '#166534', fontSize: '0.8rem', fontWeight: 700 }}>
                                Overall True Similarity {trueOverall}%
                              </div>
                              <div style={{ padding: '7px 12px', borderRadius: '8px', border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', fontSize: '0.8rem', fontWeight: 700 }}>
                                Overall False Similarity {falseOverall}%
                              </div>
                            </div>
                            {trueMatches.length > 0 && (
                              <details style={{ border: '1px solid #bbf7d0', borderRadius: '10px', background: '#f8fffb', padding: '8px 10px' }}>
                                <summary style={{ cursor: 'pointer', fontSize: '0.74rem', color: '#166534', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                                  <span>Matched True Records ({trueMatches.length})</span>
                                  <span style={{ fontSize: '0.9rem', lineHeight: 1 }}>▼</span>
                                </summary>
                                <div style={{ display: 'grid', gap: '6px', marginTop: '10px' }}>
                                  {trueMatches.slice(0, 3).map((match, idx) => {
                                    const entryKey = `true-${match.kb_id || idx}`;
                                    const isExpanded = expandedKbMatch === entryKey;
                                    return (
                                    <button
                                      type="button"
                                      key={entryKey}
                                      onClick={() => setExpandedKbMatch(isExpanded ? null : entryKey)}
                                      style={{ padding: '8px 10px', borderRadius: '8px', border: '1px solid #bbf7d0', background: '#f0fdf4', textAlign: 'left', width: '100%', cursor: 'pointer' }}
                                    >
                                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                                        <strong style={{ fontSize: '0.8rem', color: '#166534' }}>{formatKbDisplayId(match, match.incident_type || 'True incident')}</strong>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                          <span style={{ fontSize: '0.75rem', color: '#047857', fontWeight: 700 }}>{Math.round((match.score || 0) * 100)}%</span>
                                          <span style={{ fontSize: '0.8rem', color: '#166534' }}>{isExpanded ? '▲' : '▼'}</span>
                                        </span>
                                      </div>
                                      {match.description && <div style={{ fontSize: '0.76rem', color: T.textMuted, marginTop: '3px' }}>{match.description}</div>}
                                      {isExpanded && (
                                        <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #bbf7d0', display: 'grid', gap: '6px' }}>
                                          {match.resolution_summary && (
                                            <div style={{ fontSize: '0.74rem', color: T.textMuted }}>
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
                                            <div style={{ fontSize: '0.74rem', color: T.textMuted }}>
                                              <strong style={{ color: '#166534' }}>Manufacturer:</strong> {match.manufacturer}
                                            </div>
                                          )}
                                          {match.model && (
                                            <div style={{ fontSize: '0.74rem', color: T.textMuted }}>
                                              <strong style={{ color: '#166534' }}>Model:</strong> {match.model}
                                            </div>
                                          )}
                                          {match.pattern_fields && Object.keys(match.pattern_fields).length > 0 && (
                                            <div style={{ display: 'grid', gap: '4px' }}>
                                              {Object.entries(match.pattern_fields).map(([field, value]) => (
                                                <div key={field} style={{ fontSize: '0.73rem', color: T.textMuted }}>
                                                  <strong style={{ color: '#166534' }}>{field.replace(/_/g, ' ')}:</strong> {String(value)}
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </button>
                                  )})}
                                </div>
                              </details>
                            )}
                            {falseMatches.length > 0 && (
                              <details style={{ border: '1px solid #fecaca', borderRadius: '10px', background: '#fffafa', padding: '8px 10px' }}>
                                <summary style={{ cursor: 'pointer', fontSize: '0.74rem', color: '#991b1b', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}>
                                  <span>Matched False Records ({falseMatches.length})</span>
                                  <span style={{ fontSize: '0.9rem', lineHeight: 1 }}>▼</span>
                                </summary>
                                <div style={{ display: 'grid', gap: '6px', marginTop: '10px' }}>
                                  {falseMatches.slice(0, 3).map((match, idx) => {
                                    const entryKey = `false-${match.kb_id || idx}`;
                                    const isExpanded = expandedKbMatch === entryKey;
                                    return (
                                    <button
                                      type="button"
                                      key={entryKey}
                                      onClick={() => setExpandedKbMatch(isExpanded ? null : entryKey)}
                                      style={{ padding: '8px 10px', borderRadius: '8px', border: '1px solid #fecaca', background: '#fef2f2', textAlign: 'left', width: '100%', cursor: 'pointer' }}
                                    >
                                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                                        <strong style={{ fontSize: '0.8rem', color: '#991b1b' }}>{formatKbDisplayId(match, match.incident_type || 'False report')}</strong>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                                          <span style={{ fontSize: '0.75rem', color: '#b91c1c', fontWeight: 700 }}>{Math.round((match.score || 0) * 100)}%</span>
                                          <span style={{ fontSize: '0.8rem', color: '#991b1b' }}>{isExpanded ? '▲' : '▼'}</span>
                                        </span>
                                      </div>
                                      {match.description && <div style={{ fontSize: '0.76rem', color: T.textMuted, marginTop: '3px' }}>{match.description}</div>}
                                      {isExpanded && (
                                        <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #fecaca', display: 'grid', gap: '6px' }}>
                                          {match.resolution_summary && (
                                            <div style={{ fontSize: '0.74rem', color: T.textMuted }}>
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
                                            <div style={{ fontSize: '0.74rem', color: T.textMuted }}>
                                              <strong style={{ color: '#991b1b' }}>Manufacturer:</strong> {match.manufacturer}
                                            </div>
                                          )}
                                          {match.model && (
                                            <div style={{ fontSize: '0.74rem', color: T.textMuted }}>
                                              <strong style={{ color: '#991b1b' }}>Model:</strong> {match.model}
                                            </div>
                                          )}
                                          {match.pattern_fields && Object.keys(match.pattern_fields).length > 0 && (
                                            <div style={{ display: 'grid', gap: '4px' }}>
                                              {Object.entries(match.pattern_fields).map(([field, value]) => (
                                                <div key={field} style={{ fontSize: '0.73rem', color: T.textMuted }}>
                                                  <strong style={{ color: '#991b1b' }}>{field.replace(/_/g, ' ')}:</strong> {String(value)}
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </button>
                                  )})}
                                </div>
                              </details>
                            )}
                            {canReviewKb && (
                              <div style={{ display: 'grid', gap: '8px' }}>
                                <div style={{ fontSize: '0.8rem', color: T.textMuted }}>
                                  {reviewPrompt}
                                </div>
                                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                                {!isTrue && (
                                  <button
                                    type="button"
                                    onClick={handleKbConfirmValid}
                                    disabled={Boolean(kbReviewBusy)}
                                    style={{
                                      minHeight: '34px',
                                      padding: '7px 12px',
                                      borderRadius: '8px',
                                      border: '1px solid #86efac',
                                      background: '#ecfdf5',
                                      color: '#047857',
                                      fontSize: '0.78rem',
                                      fontWeight: '700',
                                      cursor: kbReviewBusy ? 'not-allowed' : 'pointer',
                                      opacity: kbReviewBusy && kbReviewBusy !== 'confirm' ? 0.65 : 1,
                                    }}
                                  >
                                    Confirm True Incident
                                  </button>
                                )}
                                {!isFalse && (
                                  <button
                                    type="button"
                                    onClick={handleKbMarkFalse}
                                    disabled={Boolean(kbReviewBusy)}
                                    style={{
                                      minHeight: '34px',
                                      padding: '7px 12px',
                                      borderRadius: '8px',
                                      border: '1px solid #fca5a5',
                                      background: '#fef2f2',
                                      color: '#b91c1c',
                                      fontSize: '0.78rem',
                                      fontWeight: '700',
                                      cursor: kbReviewBusy ? 'not-allowed' : 'pointer',
                                      opacity: kbReviewBusy && kbReviewBusy !== 'false' ? 0.65 : 1,
                                    }}
                                  >
                                    Mark False Report
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={handleKbRevalidate}
                                  disabled={Boolean(kbReviewBusy)}
                                  style={{
                                    minHeight: '34px',
                                    padding: '7px 12px',
                                    borderRadius: '8px',
                                    border: '1px solid #bfdbfe',
                                    background: '#eff6ff',
                                    color: '#1d4ed8',
                                    fontSize: '0.78rem',
                                    fontWeight: '700',
                                    cursor: kbReviewBusy ? 'not-allowed' : 'pointer',
                                    opacity: kbReviewBusy && kbReviewBusy !== 'validate' ? 0.65 : 1,
                                  }}
                                  >
                                    Re-validate
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  );
                })()}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0' }}>
                {[
                  { label: 'Reference', value: shortRef, mono: true, fullWidth: false },
                  { label: 'Type', value: incidentType },
                  { label: 'Status', value: getStatusLabel(incident.status) },
                  { label: 'Outcome', value: getOutcomeLabel(incident.outcome) || 'Pending' },
                  { label: 'Reported', value: formatDate(incident.created_at) },
                  ...(incident.location ? [{ label: 'Location', value: incident.location }] : []),
                  ...(agent ? [{ label: 'Engineer', value: agent.full_name }]
                    : incident.assigned_agent_id ? [{ label: 'Engineer', value: incident.assigned_agent_id }] : []),
                  ...(incident.resolved_at ? [{ label: 'Resolved At', value: formatDate(incident.resolved_at) }] : []),
                ].map((row, i) => (
                  <div key={i} style={{
                    padding: '10px 12px', borderRadius: '8px',
                    background: i % 2 === 0 ? '#f8fafc' : 'transparent',
                  }}>
                    <div style={{ fontSize: '0.75rem', color: T.textFaint, fontWeight: '600', marginBottom: '2px' }}>{row.label}</div>
                    <div style={{
                      fontSize: '0.9rem', fontWeight: '600', color: T.text,
                      whiteSpace: 'normal',
                      wordWrap: 'break-word',
                      overflowWrap: 'anywhere',
                      ...(row.mono ? { fontFamily: 'monospace', letterSpacing: '0.02em', fontSize: '0.85rem' } : {}),
                    }}>{row.value}</div>
                  </div>
                ))}
              </div>
            </Card>

            {/* ── Communication Panel ──────────────────────────────── */}
            {statusHistory.length > 0 && (
              <Card hoverable>
                <button onClick={() => setShowComm(!showComm)} style={{
                  width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '18px 24px', background: 'none', border: 'none', cursor: 'pointer',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Communication</span>
                    <span style={{
                      fontSize: '0.75rem', fontWeight: '700', color: T.primary,
                      background: T.primaryLight, padding: '2px 8px', borderRadius: T.radiusPill,
                    }}>{statusHistory.length}</span>
                  </div>
                  <span style={{
                    fontSize: '0.9rem', color: T.textFaint, fontWeight: '600',
                    transform: showComm ? 'rotate(180deg)' : 'rotate(0)',
                    transition: 'transform 0.25s', display: 'inline-block',
                  }}>▼</span>
                </button>
                {showComm && (
                  <div style={{ animation: 'fadeSlideIn 0.25s ease' }}>
                    {/* Tabs */}
                    <div style={{ display: 'flex', gap: '0', padding: '0 24px', borderBottom: `1px solid ${T.borderLight}` }}>
                      {['messages', 'chat history', 'attachments'].map(tab => (
                        <button key={tab} onClick={() => setCommTab(tab)} style={{
                          padding: '10px 18px', fontSize: '0.82rem', fontWeight: '700', cursor: 'pointer',
                          background: 'none', border: 'none',
                          color: commTab === tab ? T.primary : T.textFaint,
                          borderBottom: commTab === tab ? `2px solid ${T.primary}` : '2px solid transparent',
                          textTransform: 'capitalize', transition: 'all 0.2s',
                        }}>{tab}</button>
                      ))}
                    </div>
                    <div style={{ padding: '16px 24px 24px' }}>
                      {commTab === 'messages' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          {[...statusHistory].reverse().map((entry, i) => {
                            const avatar = getCommAvatar(entry);
                            return (
                              <div key={i} style={{
                                padding: '12px 14px', borderRadius: T.radiusSm, background: '#f8fafc',
                                border: `1px solid ${T.borderLight}`, display: 'flex', gap: '10px',
                              }}>
                                <div style={{
                                  width: '32px', height: '32px', borderRadius: '10px', flexShrink: 0,
                                  background: avatar.bg, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  fontSize: '0.9rem',
                                }}>{avatar.icon}</div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', marginBottom: '3px' }}>
                                    <span style={{ fontSize: '0.82rem', fontWeight: '700', color: avatar.color }}>{avatar.label}</span>
                                    <span style={{
                                      fontSize: '0.7rem', fontWeight: '700', padding: '1px 6px', borderRadius: '4px',
                                      background: entry.message?.toLowerCase().includes('auto') || ['new', 'submitted', 'classifying', 'analyzing'].includes(entry.status) ? '#f1f5f9' : '#ebf4fb',
                                      color: entry.message?.toLowerCase().includes('auto') || ['new', 'submitted', 'classifying', 'analyzing'].includes(entry.status) ? '#64748b' : '#030304',
                                    }}>{['new', 'submitted', 'classifying', 'analyzing'].includes(entry.status) ? 'Auto' : 'Manual'}</span>
                                    <span style={{ fontSize: '0.78rem', color: T.textFaint, marginLeft: 'auto' }}>
                                      {formatAbsTime(entry.timestamp)} · {formatTimeAgo(entry.timestamp)}
                                    </span>
                                  </div>
                                  <div style={{ fontSize: '0.85rem', fontWeight: '600', color: T.text }}>
                                    {entry.status?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                                  </div>
                                  {entry.message && (
                                    <p style={{ fontSize: '0.85rem', color: T.textMuted, margin: '3px 0 0', lineHeight: 1.5 }}>{entry.message}</p>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {commTab === 'chat history' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '420px', overflowY: 'auto' }}>
                          {incident.conversation_history?.length > 0 ? (
                            incident.conversation_history.map((msg, i) => {
                              const isAgent = msg.role === 'agent' || msg.role === 'system';
                              const text = typeof msg.content === 'string' ? msg.content : (msg.content?.message || msg.content?.question || JSON.stringify(msg.content));
                              if (!text) return null;
                              return (
                                <div key={i} style={{
                                  display: 'flex',
                                  justifyContent: isAgent ? 'flex-start' : 'flex-end',
                                }}>
                                  <div style={{
                                    maxWidth: '80%',
                                    padding: '10px 14px',
                                    borderRadius: isAgent ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
                                    background: '#f1f5f9',
                                    color: '#1e293b',
                                    fontSize: '0.84rem',
                                    lineHeight: 1.55,
                                    wordBreak: 'break-word',
                                  }}>
                                    <div style={{ fontSize: '0.68rem', fontWeight: '700', marginBottom: '3px', opacity: 0.6 }}>
                                      {isAgent ? 'AI Agent' : 'Customer'}
                                      {msg.timestamp && <span style={{ marginLeft: '8px', fontWeight: '500' }}>{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>}
                                    </div>
                                    {text}
                                  </div>
                                </div>
                              );
                            })
                          ) : (
                            <div style={{ textAlign: 'center', padding: '32px 16px', color: T.textFaint, fontSize: '0.85rem' }}>
                              No chat history available for this incident.
                            </div>
                          )}
                        </div>
                      )}
                      {commTab === 'attachments' && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                          {incident.media?.length > 0 && (
                            <div>
                              <div style={{ fontSize: '0.82rem', fontWeight: '700', color: T.text, marginBottom: '8px' }}>Incident Evidence</div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '10px' }}>
                                {incident.media.map((m) => (
                                  <a
                                    key={m.media_id}
                                    href={`${window.location.origin}/api/v1/incidents/${incident.incident_id}/media/${m.media_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ display: 'block', borderRadius: '10px', overflow: 'hidden', border: `1px solid ${T.border}`, transition: 'all 0.2s' }}
                                  >
                                    <img
                                      src={`${window.location.origin}/api/v1/incidents/${incident.incident_id}/media/${m.media_id}`}
                                      alt={m.metadata?.filename || 'Evidence'}
                                      style={{ width: '100%', height: '120px', objectFit: 'cover', display: 'block' }}
                                    />
                                    <div style={{ padding: '6px 8px', fontSize: '0.72rem', color: T.textMuted, fontWeight: '600', background: '#f8fafc' }}>
                                      {m.metadata?.filename || 'Image'}
                                    </div>
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                          {incident.resolution_media?.length > 0 && (
                            <div>
                              <div style={{ fontSize: '0.82rem', fontWeight: '700', color: T.text, marginBottom: '8px' }}>Proof of Fix</div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '10px' }}>
                                {incident.resolution_media.map((m) => (
                                  <a
                                    key={m.media_id}
                                    href={`${window.location.origin}/api/v1/incidents/${incident.incident_id}/resolution-media/${m.media_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ display: 'block', borderRadius: '10px', overflow: 'hidden', border: `1px solid ${T.border}`, transition: 'all 0.2s' }}
                                  >
                                    {m.content_type?.startsWith('image/') ? (
                                      <img
                                        src={`${window.location.origin}/api/v1/incidents/${incident.incident_id}/resolution-media/${m.media_id}`}
                                        alt={m.filename || 'Proof of fix'}
                                        style={{ width: '100%', height: '120px', objectFit: 'cover', display: 'block' }}
                                      />
                                    ) : (
                                      <div style={{ width: '100%', height: '120px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f1f5f9', fontSize: '2rem' }}>📎</div>
                                    )}
                                    <div style={{ padding: '6px 8px', fontSize: '0.72rem', color: T.textMuted, fontWeight: '600', background: '#f8fafc' }}>
                                      {m.filename || 'Document'}
                                    </div>
                                  </a>
                                ))}
                              </div>
                            </div>
                          )}
                          {!incident.media?.length && !incident.resolution_media?.length && (
                            <div style={{ textAlign: 'center', padding: '32px 0' }}>
                              <div style={{ fontSize: '2rem', marginBottom: '8px' }}>📎</div>
                              <div style={{ fontSize: '0.9rem', color: T.textFaint, fontWeight: '600' }}>No attachments yet</div>
                              <p style={{ fontSize: '0.82rem', color: T.textFaint, margin: '4px 0 0' }}>Files and evidence will appear here</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </Card>
            )}

            {/* ── Quick Actions ─────────────────────────────────────── */}
            <div className="no-print" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
              <Card hoverable style={{ cursor: 'pointer' }}>
                <button onClick={() => setShowAddDetails(true)} style={{
                  width: '100%', padding: '16px', background: 'none', border: 'none', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
                }}>
                  <span style={{ fontSize: '1.4rem' }}>➕</span>
                  <span style={{ fontSize: '0.82rem', fontWeight: '700', color: T.text }}>Add Details</span>
                </button>
              </Card>
              <Card hoverable style={{ cursor: 'pointer' }}>
                <button onClick={handleDownloadReport} style={{
                  width: '100%', padding: '16px', background: 'none', border: 'none', cursor: 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
                }}>
                  <span style={{ fontSize: '1.4rem' }}>📥</span>
                  <span style={{ fontSize: '0.82rem', fontWeight: '700', color: T.text }}>Download Report</span>
                </button>
              </Card>
              <Card hoverable style={{ cursor: 'pointer' }}>
                <button onClick={handleToggleSms} disabled={smsUpdating} style={{
                  width: '100%', padding: '16px', background: 'none', border: 'none', cursor: smsUpdating ? 'default' : 'pointer',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
                  opacity: smsUpdating ? 0.6 : 1,
                }}>
                  <span style={{ fontSize: '1.4rem' }}>{incident.structured_data?._sms_preference?.enabled ? '🔔' : '🔕'}</span>
                  <span style={{ fontSize: '0.82rem', fontWeight: '700', color: incident.structured_data?._sms_preference?.enabled ? T.green : T.text }}>
                    {smsUpdating ? 'Updating...' : incident.structured_data?._sms_preference?.enabled ? 'SMS On' : 'SMS Updates'}
                  </span>
                </button>
              </Card>
            </div>

            {/* -- SMS Notification Banner -------------------------------- */}
            {incident.structured_data?._sms_preference?.enabled && (
              <div className="no-print" style={{
                padding: '12px 16px', borderRadius: T.radiusSm,
                background: '#ecfdf5', border: '1px solid #bbf7d0',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '1.1rem' }}>✅</span>
                  <div>
                    <div style={{ fontSize: '0.84rem', fontWeight: '700', color: '#047857' }}>SMS Notifications Active</div>
                    <div style={{ fontSize: '0.78rem', color: '#059669' }}>
                      Updates will be sent to {incident.structured_data._sms_preference.phone || incident.user_phone || 'your registered number'}
                    </div>
                  </div>
                </div>
                <button onClick={handleToggleSms} disabled={smsUpdating} style={{
                  background: 'none', border: '1px solid #86efac', borderRadius: '8px',
                  padding: '4px 10px', fontSize: '0.78rem', fontWeight: '600', color: '#047857',
                  cursor: 'pointer',
                }}>Turn Off</button>
              </div>
            )}

            {/* -- User Notes -------------------------------------------- */}
            {(incident.structured_data?._user_notes || []).length > 0 && (
              <Card hoverable style={{ padding: '20px 24px' }}>
                <h3 style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 12px' }}>
                  Your Notes ({incident.structured_data._user_notes.length})
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {[...incident.structured_data._user_notes].reverse().map((n, i) => (
                    <div key={n.note_id || i} style={{
                      padding: '10px 12px', borderRadius: '10px', background: '#f8fafc',
                      border: `1px solid ${T.borderLight}`,
                    }}>
                      {editingNote?.note_id === n.note_id ? (
                        /* -- Inline Edit Mode -- */
                        <div>
                          <textarea
                            value={editNoteText}
                            onChange={e => setEditNoteText(e.target.value)}
                            maxLength={500}
                            style={{
                              width: '100%', minHeight: '60px', padding: '8px', fontSize: '0.88rem',
                              borderRadius: '8px', border: `1px solid ${T.borderLight}`, resize: 'vertical',
                              fontFamily: 'inherit', color: '#334155', background: '#fff',
                            }}
                          />
                          <div style={{ display: 'flex', gap: '6px', marginTop: '6px', justifyContent: 'flex-end' }}>
                            <button onClick={() => { setEditingNote(null); setEditNoteText(''); }}
                              style={{
                                padding: '4px 12px', fontSize: '0.75rem', fontWeight: '600',
                                borderRadius: '6px', border: `1px solid ${T.borderLight}`,
                                background: '#fff', color: T.textMuted, cursor: 'pointer',
                              }}>Cancel</button>
                            <button onClick={handleEditNote} disabled={savingEdit || !editNoteText.trim()}
                              style={{
                                padding: '4px 12px', fontSize: '0.75rem', fontWeight: '600',
                                borderRadius: '6px', border: 'none',
                                background: T.primary, color: '#fff', cursor: 'pointer',
                                opacity: savingEdit || !editNoteText.trim() ? 0.5 : 1,
                              }}>{savingEdit ? 'Saving...' : 'Save'}</button>
                          </div>
                        </div>
                      ) : (
                        /* -- Display Mode -- */
                        <div>
                          <p style={{ margin: '0 0 4px', fontSize: '0.88rem', color: '#334155', lineHeight: 1.5 }}>{n.note}</p>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '0.75rem', color: T.textFaint }}>{formatDate(n.created_at)}</span>
                            <div style={{ display: 'flex', gap: '6px' }}>
                              <button
                                onClick={() => { setEditingNote(n); setEditNoteText(n.note); }}
                                title="Edit note"
                                style={{
                                  background: 'none', border: 'none', cursor: 'pointer',
                                  padding: '5px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: '600',
                                  color: '#3b82f6', display: 'flex', alignItems: 'center', gap: '4px',
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = '#eff6ff'; }}
                                onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
                              ><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>Edit</button>
                              <button
                                onClick={() => handleDeleteNote(n.note_id)}
                                disabled={deletingNoteId === n.note_id}
                                title="Delete note"
                                style={{
                                  background: 'none', border: 'none', cursor: 'pointer',
                                  padding: '5px 10px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: '600',
                                  color: '#ef4444', display: 'flex', alignItems: 'center', gap: '4px',
                                  opacity: deletingNoteId === n.note_id ? 0.5 : 1,
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = '#fef2f2'; }}
                                onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
                              ><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>Delete</button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>

          {/* ═══ RIGHT COLUMN — Lifecycle Timeline ════════════════ */}
          <div style={{ position: 'sticky', top: '5rem' }}>
            <Card>
              {/* Header */}
              <div style={{ padding: '18px 24px', borderBottom: `1px solid ${T.borderLight}` }}>
                <span style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Incident Lifecycle</span>
              </div>

              {/* Timeline */}
              <div style={{ padding: '20px 24px' }}>
                {timeline.map((step, index) => {
                  const isLast = index === timeline.length - 1;
                  const av = getTimelineAvatar(step);
                  const tag = getActionTag(step);

                  return (
                    <div key={index} style={{ display: 'flex', gap: '12px' }}>
                      {/* Icon + line */}
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '32px', flexShrink: 0 }}>
                        <div style={{
                          width: '32px', height: '32px', borderRadius: '50%',
                          background: av.bg, border: `2px solid ${av.border}`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: step.completed ? '0.7rem' : '0.85rem',
                          color: av.color, fontWeight: '700', flexShrink: 0, zIndex: 1,
                          ...(step.in_progress ? { animation: 'ringPulse 2s infinite', boxShadow: `0 0 0 4px ${av.border}20` } : {}),
                        }}>{av.icon}</div>
                        {!isLast && (
                          <div style={{
                            width: '2px', flex: 1, minHeight: '24px',
                            background: step.completed ? '#86efac' : T.border,
                            ...(step.completed ? {} : { backgroundImage: 'repeating-linear-gradient(0deg, #e5e7eb, #e5e7eb 4px, transparent 4px, transparent 8px)' }),
                          }} />
                        )}
                      </div>
                      {/* Content */}
                      <div style={{ paddingBottom: isLast ? '0' : '16px', flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px', flexWrap: 'wrap' }}>
                          <span style={{
                            fontSize: '0.9rem', fontWeight: '700',
                            color: step.completed ? T.text : step.in_progress ? av.color : T.textFaint,
                          }}>{step.label}</span>
                          {step.in_progress && (
                            <span style={{
                              fontSize: '0.65rem', fontWeight: '800', color: av.color, background: av.bg,
                              padding: '1px 6px', borderRadius: '4px', border: `1px solid ${av.border}`,
                              textTransform: 'uppercase', letterSpacing: '0.05em',
                            }}>Active</span>
                          )}
                          {tag && (
                            <span style={{
                              fontSize: '0.65rem', fontWeight: '700', padding: '1px 6px', borderRadius: '4px',
                              background: tag.bg, color: tag.color,
                            }}>{tag.label}</span>
                          )}
                          {step.timestamp && (
                            <span style={{ fontSize: '0.78rem', color: T.textFaint, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                              {formatAbsTime(step.timestamp)} · {formatTimeAgo(step.timestamp)}
                            </span>
                          )}
                        </div>
                        <p style={{
                          fontSize: '0.82rem', lineHeight: 1.5, margin: 0,
                          color: step.completed ? T.textMuted : step.in_progress ? '#475569' : '#c0c7d0',
                          fontStyle: !step.completed && !step.in_progress ? 'italic' : 'normal',
                        }}>{step.message}</p>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Activity Log */}
              {statusHistory.length > 0 && (
                <div style={{ borderTop: `1px solid ${T.borderLight}` }}>
                  <button onClick={() => setShowActivityLog(!showActivityLog)} style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '14px 24px', background: 'none', border: 'none', cursor: 'pointer',
                  }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: '700', color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      Activity Log ({statusHistory.length})
                    </span>
                    <span style={{
                      fontSize: '0.8rem', color: T.textFaint, fontWeight: '600',
                      transform: showActivityLog ? 'rotate(180deg)' : 'rotate(0)',
                      transition: 'transform 0.25s', display: 'inline-block',
                    }}>▼</span>
                  </button>
                  {showActivityLog && (
                    <div style={{ padding: '0 24px 20px', animation: 'fadeSlideIn 0.25s ease' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {[...statusHistory].reverse().map((entry, i) => (
                          <div key={i} style={{
                            padding: '10px 12px', borderRadius: '10px', background: '#f8fafc',
                            border: `1px solid ${T.borderLight}`, display: 'flex', gap: '8px',
                          }}>
                            <div style={{
                              width: '6px', height: '6px', borderRadius: '50%',
                              background: '#cbd5e1', marginTop: '6px', flexShrink: 0,
                            }} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontSize: '0.82rem', fontWeight: '700', color: '#374151' }}>
                                  {entry.status?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                                </span>
                                <span style={{ fontSize: '0.78rem', color: T.textFaint, whiteSpace: 'nowrap', marginLeft: '8px' }}>
                                  {formatTimeAgo(entry.timestamp)}
                                </span>
                              </div>
                              {entry.message && (
                                <p style={{ fontSize: '0.82rem', color: T.textMuted, margin: '2px 0 0', lineHeight: 1.4 }}>{entry.message}</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </Card>
          </div>
        </div>
      </div>

      {/* ═══ ANIMATIONS + PRINT STYLES ═══════════════════════════ */}
      {/* -- Add Details Modal ---------------------------------------- */}
      {showAddDetails && (
        <div onClick={() => { setShowAddDetails(false); setUserNote(''); }} style={{
          position: 'fixed', inset: 0, zIndex: 9998,
          background: 'rgba(7, 17, 29, 0.48)',
          display: 'grid', placeItems: 'center', padding: '16px',
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            width: 'min(480px, 100%)', borderRadius: '16px', border: `1px solid ${T.border}`,
            background: '#fff', boxShadow: T.shadowLg, padding: '20px',
          }}>
            <h3 style={{ margin: '0 0 4px', fontSize: '1.05rem', color: T.text }}>Add Details</h3>
            <p style={{ margin: '0 0 14px', fontSize: '0.86rem', color: T.textMuted }}>
              Add additional information, observations, or notes to this incident.
            </p>
            <textarea
              value={userNote}
              onChange={(e) => setUserNote(e.target.value)}
              placeholder="Describe any additional details, updates, or observations..."
              rows={5}
              style={{
                width: '100%', padding: '12px', borderRadius: '10px', border: `1px solid ${T.border}`,
                fontSize: '0.9rem', fontFamily: T.font, resize: 'vertical', outline: 'none',
                transition: 'border-color 0.2s', boxSizing: 'border-box',
              }}
              onFocus={(e) => e.target.style.borderColor = T.primary}
              onBlur={(e) => e.target.style.borderColor = T.border}
              autoFocus
            />
            <div style={{ fontSize: '0.78rem', color: T.textFaint, marginTop: '6px' }}>
              {userNote.length}/500 characters
            </div>
            <div style={{ marginTop: '14px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => { setShowAddDetails(false); setUserNote(''); }} style={{
                padding: '8px 16px', borderRadius: '10px', border: `1px solid ${T.border}`,
                background: '#fff', fontSize: '0.86rem', fontWeight: '600', color: T.textMuted,
                cursor: 'pointer',
              }}>Cancel</button>
              <button onClick={handleAddNote} disabled={!userNote.trim() || addingNote} style={{
                padding: '8px 16px', borderRadius: '10px', border: 'none',
                background: !userNote.trim() || addingNote ? '#94a3b8' : T.primary,
                fontSize: '0.86rem', fontWeight: '600', color: '#fff',
                cursor: !userNote.trim() || addingNote ? 'not-allowed' : 'pointer',
              }}>{addingNote ? 'Adding...' : 'Add Note'}</button>
            </div>
          </div>
        </div>
      )}

      {/* -- Toast ---------------------------------------------------- */}
      {toast && (
        <div style={{
          position: 'fixed', right: '22px', bottom: '22px', zIndex: 9999,
          borderRadius: '12px',
          border: `1px solid ${toast.type === 'error' ? '#fecaca' : '#bbf7d0'}`,
          background: toast.type === 'error' ? '#fef2f2' : '#ecfdf5',
          color: toast.type === 'error' ? '#b91c1c' : '#047857',
          padding: '10px 14px', boxShadow: T.shadowLg,
          fontWeight: 700, fontSize: '0.84rem',
          animation: 'fadeSlideIn 0.25s ease',
        }}>
          {toast.message}
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        @keyframes pulse {
          0%, 100% { opacity: 1; } 50% { opacity: 0.5; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes ringPulse {
          0%, 100% { box-shadow: 0 0 0 4px rgba(99,102,241,0.12); }
          50% { box-shadow: 0 0 0 8px rgba(99,102,241,0.04); }
        }
        @keyframes shimmer {
          0% { background-position: 200% 0; } 100% { background-position: -200% 0; }
        }
        @keyframes skeletonShimmer {
          0% { background-position: -200% 0; } 100% { background-position: 200% 0; }
        }
        @keyframes pinPulse {
          0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); }
        }
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); }
        }
        @keyframes liveRing {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(2.2); opacity: 0; }
        }
        @keyframes vehicleBounce {
          0%, 100% { transform: translateY(0); } 50% { transform: translateY(-3px); }
        }
        .leaflet-popup-content-wrapper { border-radius: 12px !important; box-shadow: 0 4px 20px rgba(0,0,0,0.12) !important; }
        .leaflet-popup-tip { display: none !important; }
        .leaflet-popup-content { margin: 0 !important; }

        @media print {
          .no-print { display: none !important; }
          .incident-detail-page { background: white !important; }
          div[style*="sticky"] { position: relative !important; top: 0 !important; }
          div[style*="grid-template-columns"] { display: block !important; }
          div[style*="box-shadow"] { box-shadow: none !important; border: 1px solid #e5e7eb !important; }
        }
      `}</style>
    </div>
  );
};

export default IncidentDetail;



