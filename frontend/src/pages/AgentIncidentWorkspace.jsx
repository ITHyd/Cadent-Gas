import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MapContainer, Marker, Popup, Polyline, TileLayer } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useAuth } from '../contexts/AuthContext';
import ProfileDropdown from '../components/ProfileDropdown';
import NotificationBell from '../components/NotificationBell';
import {
  addFieldMilestone,
  createAssistanceRequest,
  createItemRequest,
  getIncident,
  resolveIncident,
  updateAgentLocation,
  updateItemRequest,
} from '../services/api';
import CustomSelect from '../components/CustomSelect';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const USER_ICON = L.divIcon({
  className: 'user-pin',
  html: '<div style="width:20px;height:20px;border-radius:999px;background:#ef4444;border:3px solid #fff;box-shadow:0 6px 14px rgba(239,68,68,.45)"></div>',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

const AGENT_ICON = L.divIcon({
  className: 'agent-pin',
  html: '<div style="width:22px;height:22px;border-radius:999px;background:linear-gradient(135deg,#030304,#0d0d1a);border:3px solid #fff;box-shadow:0 8px 16px rgba(3,3,4,.45)"></div>',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const MILESTONES = [
  { key: 'depart', label: 'Depart Base' },
  { key: 'arrived_perimeter', label: 'Arrived Nearby' },
  { key: 'on_site', label: 'On Site' },
  { key: 'diagnosis_started', label: 'Diagnosis Started' },
  { key: 'repair_started', label: 'Repair Started' },
  { key: 'verification_passed', label: 'Verification Passed' },
  { key: 'handoff_done', label: 'Handoff Complete' },
];

const OPEN_ASSISTANCE_STATUSES = new Set(['PENDING', 'ACKNOWLEDGED', 'IN_PROGRESS']);
const OPEN_ITEM_STATUSES = new Set(['REQUESTED', 'APPROVED', 'DISPATCHED', 'DELIVERED']);

const AgentIncidentWorkspace = () => {
  const { incidentId } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [trackingEnabled, setTrackingEnabled] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [assistForm, setAssistForm] = useState({ request_type: 'backup', priority: 'MEDIUM', reason: '', details: '' });
  const [itemForm, setItemForm] = useState({ item_name: '', quantity: 1, urgency: 'NORMAL', notes: '' });
  const [resolutionForm, setResolutionForm] = useState({
    resolutionNotes: '',
    rootCause: '',
    actionsTaken: '',
    verificationEvidence: '',
    verificationEvidenceNote: '',
    verificationResult: 'PASS',
    safetyChecksCompleted: false,
    handoffConfirmed: false,
    itemsUsed: '',
  });
  const [validationErrors, setValidationErrors] = useState({});

  // Resolution file upload state
  const [resolutionFiles, setResolutionFiles] = useState([]);
  const fileInputRef = useRef(null);

  // Speech-to-text state
  const [isRecording, setIsRecording] = useState(false);
  const recognitionRef = useRef(null);

  const trackerTimerRef = useRef(null);

  const agentId = user?.user_id;

  const fetchIncident = async (showLoading = false) => {
    try {
      if (showLoading) setLoading(true);
      const data = await getIncident(incidentId);
      setIncident(data);
      setError('');
    } catch {
      setError('Failed to load incident workspace');
    } finally {
      if (showLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncident(true);
  }, [incidentId]);

  useEffect(() => {
    const timer = setInterval(() => fetchIncident(false), 15000);
    return () => clearInterval(timer);
  }, [incidentId]);

  useEffect(() => () => {
    if (trackerTimerRef.current) {
      clearInterval(trackerTimerRef.current);
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
  }, []);

  // ── Resolution file upload handlers ──
  const handleResolutionFileSelect = (event) => {
    const newFiles = Array.from(event.target.files);
    setResolutionFiles((prev) => [...prev, ...newFiles]);
    event.target.value = '';
  };

  const removeResolutionFile = (index) => {
    setResolutionFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // ── Speech-to-text for resolution notes ──
  const startSpeechRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Speech recognition is not supported in this browser. Please use Chrome or Edge.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        }
      }
      if (finalTranscript) {
        setResolutionForm((current) => ({
          ...current,
          resolutionNotes: current.resolutionNotes
            ? current.resolutionNotes + ' ' + finalTranscript
            : finalTranscript,
        }));
        if (validationErrors.resolutionNotes) {
          setValidationErrors((prev) => ({ ...prev, resolutionNotes: undefined }));
        }
      }
    };

    recognition.onerror = () => setIsRecording(false);
    recognition.onend = () => setIsRecording(false);

    recognitionRef.current = recognition;
    recognition.start();
    setIsRecording(true);
  };

  const stopSpeechRecognition = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsRecording(false);
  };

  const toggleSpeechRecognition = () => {
    if (isRecording) stopSpeechRecognition();
    else startSpeechRecognition();
  };

  const getRiskMeta = (riskScore) => {
    if (!riskScore) return { label: 'Unknown', bg: '#f1f5f9', color: '#475569' };
    if (riskScore >= 0.8) return { label: 'Critical', bg: '#fef2f2', color: '#b91c1c' };
    if (riskScore >= 0.5) return { label: 'High', bg: '#fff7ed', color: '#b45309' };
    if (riskScore >= 0.3) return { label: 'Medium', bg: '#fef9c3', color: '#a16207' };
    return { label: 'Low', bg: '#ecfdf5', color: '#047857' };
  };

  const parseCoords = (obj) => {
    if (!obj || typeof obj !== 'object') return null;
    const lat = Number(obj.lat ?? obj.latitude);
    const lng = Number(obj.lng ?? obj.longitude ?? obj.lon);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return null;
    return [lat, lng];
  };

  const userCoords = useMemo(
    () => parseCoords(incident?.user_geo_location) || parseCoords(incident?.geo_location),
    [incident],
  );

  const agentCoords = useMemo(
    () => parseCoords(incident?.agent_live_location) || parseCoords(incident?.assigned_agent?.geo_coordinates),
    [incident],
  );

  const mapCenter = userCoords || agentCoords || [28.6139, 77.209];

  const timelineEvents = useMemo(() => {
    if (!incident) return [];

    const field = (incident.field_activity || []).map((entry) => ({
      id: entry.activity_id || `field-${entry.timestamp}`,
      title: entry.label || entry.milestone || 'Field Activity',
      message: entry.notes || entry.message || '',
      timestamp: entry.timestamp,
      type: 'field',
    }));

    const status = (incident.status_history || []).map((entry, index) => ({
      id: `status-${index}-${entry.timestamp}`,
      title: (entry.status || 'status').replaceAll('_', ' '),
      message: entry.message || '',
      timestamp: entry.timestamp,
      type: 'status',
    }));

    return [...field, ...status].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [incident]);

  const openAssistanceCount = useMemo(
    () => (incident?.assistance_requests || []).filter((req) => OPEN_ASSISTANCE_STATUSES.has((req.status || '').toUpperCase())).length,
    [incident],
  );

  const openItemCount = useMemo(
    () => (incident?.item_requests || []).filter((req) => OPEN_ITEM_STATUSES.has((req.status || '').toUpperCase())).length,
    [incident],
  );

  const sendLocationPing = () => {
    if (!navigator.geolocation) {
      alert('Geolocation is not available in this browser.');
      return;
    }

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const payload = {
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            source: trackingEnabled ? 'gps_interval' : 'manual',
            accuracy: position.coords.accuracy,
            updated_by: agentId,
          };
          await updateAgentLocation(incidentId, payload);
          setIncident((current) => (
            current
              ? {
                ...current,
                agent_live_location: {
                  ...payload,
                  timestamp: new Date().toISOString(),
                },
              }
              : current
          ));
        } catch {
        }
      },
      () => {
        alert('Unable to fetch GPS location. Use manual milestones as fallback.');
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 5000 },
    );
  };

  const startTracking = () => {
    if (trackerTimerRef.current) clearInterval(trackerTimerRef.current);
    setTrackingEnabled(true);
    sendLocationPing();
    trackerTimerRef.current = setInterval(() => {
      sendLocationPing();
    }, 30000);
  };

  const stopTracking = () => {
    if (trackerTimerRef.current) {
      clearInterval(trackerTimerRef.current);
      trackerTimerRef.current = null;
    }
    setTrackingEnabled(false);
  };

  const submitMilestone = async (milestone, notes = '') => {
    try {
      setSubmitting(true);
      await addFieldMilestone(incidentId, {
        milestone,
        created_by: agentId,
        notes,
        metadata: { source: 'workspace' },
      });
      await fetchIncident(false);
    } catch {
      alert('Failed to add milestone');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateAssistance = async (event) => {
    event.preventDefault();
    if (!assistForm.reason.trim()) return;

    try {
      setSubmitting(true);
      await createAssistanceRequest(incidentId, { ...assistForm, created_by: agentId });
      setAssistForm((current) => ({ ...current, reason: '', details: '' }));
      await fetchIncident(false);
    } catch {
      alert('Failed to request assistance');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateItemRequest = async (event) => {
    event.preventDefault();
    if (!itemForm.item_name.trim()) return;

    try {
      setSubmitting(true);
      await createItemRequest(incidentId, {
        ...itemForm,
        quantity: Number(itemForm.quantity),
        created_by: agentId,
      });
      setItemForm({ item_name: '', quantity: 1, urgency: 'NORMAL', notes: '' });
      await fetchIncident(false);
    } catch {
      alert('Failed to request item');
    } finally {
      setSubmitting(false);
    }
  };

  const markItemAsUsed = async (requestId) => {
    try {
      setSubmitting(true);
      await updateItemRequest(incidentId, requestId, {
        status: 'USED',
        updated_by: agentId,
        note: 'Marked as consumed on site',
      });
      await fetchIncident(false);
    } catch {
      alert('Failed to update item request status');
    } finally {
      setSubmitting(false);
    }
  };

  const handleResolve = async (event) => {
    event.preventDefault();
    setValidationErrors({});

    // Client-side validation: require minimum word count for text fields
    const errors = {};
    const notesWords = resolutionForm.resolutionNotes.trim().split(/\s+/).filter(Boolean);
    const causeWords = resolutionForm.rootCause.trim().split(/\s+/).filter(Boolean);
    const actionsWords = resolutionForm.actionsTaken.trim().split(/\s+/).filter(Boolean);

    if (notesWords.length === 0) {
      errors.resolutionNotes = 'Resolution notes are required.';
    } else if (notesWords.length < 3) {
      errors.resolutionNotes = 'Resolution notes must contain at least 3 descriptive words.';
    }

    if (causeWords.length === 0) {
      errors.rootCause = 'Root cause is required.';
    } else if (causeWords.length < 3) {
      errors.rootCause = 'Root cause must contain at least 3 descriptive words.';
    }

    if (actionsWords.length === 0) {
      errors.actionsTaken = 'Actions taken is required.';
    } else if (actionsWords.length < 3) {
      errors.actionsTaken = 'Actions taken must contain at least 3 descriptive words.';
    }

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      return;
    }

    const checklist = {
      rootCause: resolutionForm.rootCause,
      actionsTaken: resolutionForm.actionsTaken.split(',').map((item) => item.trim()).filter(Boolean),
      verificationEvidence: resolutionForm.verificationEvidence,
      verificationEvidenceNote: resolutionForm.verificationEvidenceNote,
      verificationResult: resolutionForm.verificationResult,
      safetyChecksCompleted: resolutionForm.safetyChecksCompleted,
      handoffConfirmed: resolutionForm.handoffConfirmed,
    };

    try {
      setSubmitting(true);
      await resolveIncident(incidentId, agentId, resolutionForm.resolutionNotes, {
        checklist,
        itemsUsed: resolutionForm.itemsUsed.split(',').map((item) => item.trim()).filter(Boolean),
        files: resolutionFiles,
      });
      await fetchIncident(false);
      alert('Resolution submitted for company review.');
    } catch (err) {
      const errMsg = err.message || 'Failed to resolve incident';
      // Parse server-side text validation errors
      if (errMsg.includes('Text validation failed')) {
        const serverErrors = {};
        if (errMsg.includes('resolution_notes:')) serverErrors.resolutionNotes = 'Resolution notes contain invalid text. Please write clear English.';
        if (errMsg.includes('root_cause:')) serverErrors.rootCause = 'Root cause contains invalid text. Please write clear English.';
        if (errMsg.includes('actions_taken:')) serverErrors.actionsTaken = 'Actions taken contains invalid text. Please write clear English.';
        setValidationErrors(serverErrors);
      } else {
        alert(errMsg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="app-shell" style={{ display: 'grid', placeItems: 'center' }}>
        <div className="panel" style={{ padding: '28px', maxWidth: '460px', textAlign: 'center' }}>
          <h3 style={{ marginBottom: '6px' }}>Loading Workspace</h3>
          <p style={{ margin: 0 }}>Preparing field controls and incident context...</p>
        </div>
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="app-shell" style={{ display: 'grid', placeItems: 'center' }}>
        <div className="panel" style={{ padding: '28px', maxWidth: '520px', textAlign: 'center' }}>
          <h3 style={{ marginBottom: '6px' }}>Unable to open workspace</h3>
          <p style={{ marginBottom: '12px' }}>{error || 'Incident not found'}</p>
          <button type="button" className="secondary-btn" onClick={() => navigate('/agent/dashboard')}>
            Back to Agent Dashboard
          </button>
        </div>
      </div>
    );
  }

  const riskMeta = getRiskMeta(incident.risk_score);

  // Detect if current agent is primary or backup/support
  const isPrimary = incident.assigned_agent_id === agentId;
  const backupEntry = !isPrimary
    ? (incident.backup_agents || []).find((b) => b.agent_id === agentId)
    : null;
  const agentRole = backupEntry ? (backupEntry.role || 'backup') : 'primary';
  const linkedRequest = backupEntry
    ? (incident.assistance_requests || []).find((r) => r.request_id === backupEntry.request_id)
    : null;

  const ROLE_BANNER = {
    backup: { label: 'Backup Engineer', bg: '#fef3c7', color: '#92400e', border: '#fcd34d' },
    supervisor: { label: 'Supervisor', bg: '#ede9fe', color: '#5b21b6', border: '#c4b5fd' },
    safety_support: { label: 'Safety Support', bg: '#fce7f3', color: '#9d174d', border: '#f9a8d4' },
  };
  const roleBanner = ROLE_BANNER[agentRole];

  // Primary agent details (for backup agents to see)
  const primaryAgent = incident.assigned_agent
    || (incident.assigned_agent_id ? { agent_id: incident.assigned_agent_id } : null);

  return (
    <div className="app-shell" style={{ position: 'relative' }}>
      <div className="ambient-grid" />
      <ProfileDropdown />
      <NotificationBell />

      <div className="page-container" style={{ position: 'relative', zIndex: 1 }}>
        {/* Backup/Support Role Banner */}
        {roleBanner && (
          <div style={{
            background: roleBanner.bg,
            border: `2px solid ${roleBanner.border}`,
            borderRadius: '14px',
            padding: '14px 20px',
            marginBottom: '12px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '14px',
            flexWrap: 'wrap',
          }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <span style={{
                  padding: '4px 12px', borderRadius: '999px', fontSize: '0.72rem',
                  fontWeight: 800, letterSpacing: '0.05em',
                  background: roleBanner.color, color: '#fff',
                }}>
                  {roleBanner.label.toUpperCase()}
                </span>
                <span style={{ fontSize: '0.88rem', fontWeight: 700, color: roleBanner.color }}>
                  You are assigned as {roleBanner.label.toLowerCase()} for this incident
                </span>
              </div>
              {linkedRequest && (
                <div style={{ fontSize: '0.84rem', color: '#4d6178', marginBottom: '4px' }}>
                  <strong>Reason:</strong> {linkedRequest.reason || 'N/A'}
                  {linkedRequest.priority && <span style={{ marginLeft: '10px' }}><strong>Priority:</strong> {linkedRequest.priority}</span>}
                </div>
              )}
            </div>
            {primaryAgent && (
              <div style={{
                background: '#fff',
                borderRadius: '12px',
                padding: '10px 14px',
                border: '1px solid #d7e0ea',
                minWidth: '200px',
              }}>
                <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#7f93aa', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>
                  Primary Agent
                </div>
                <div style={{ fontSize: '0.9rem', fontWeight: 700, color: '#0f1f33' }}>
                  {primaryAgent.full_name || primaryAgent.agent_id}
                </div>
                {primaryAgent.specialization && (
                  <div style={{ fontSize: '0.78rem', color: '#5f738a' }}>{primaryAgent.specialization}</div>
                )}
                {primaryAgent.phone && (
                  <a href={`tel:${primaryAgent.phone}`} style={{
                    fontSize: '0.78rem', color: '#030304', fontWeight: 600, textDecoration: 'none',
                    display: 'inline-flex', alignItems: 'center', gap: '4px', marginTop: '4px',
                  }}>
                    Call: {primaryAgent.phone}
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        <header className="panel" style={{ padding: '20px', marginBottom: '14px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
            <div>
              <span className="eyebrow">{roleBanner ? `${roleBanner.label} Workspace` : 'Agent Workspace'}</span>
              <h1 className="page-heading" style={{ marginTop: '10px' }}>{incident.incident_id}</h1>
              <p className="page-subheading">
                {(incident.classified_use_case || incident.incident_type || 'Incident').replaceAll('_', ' ')} &mdash; {incident.user_address || incident.location || 'Location unavailable'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'start', flexWrap: 'wrap' }}>
              <span className="status-pill" style={{ background: riskMeta.bg, color: riskMeta.color, borderColor: `${riskMeta.color}2f` }}>
                {riskMeta.label} {(incident.risk_score ? incident.risk_score * 100 : 0).toFixed(0)}%
              </span>
              <span className="status-pill" style={{ background: '#e0f2fe', color: '#075985', borderColor: '#bae6fd' }}>
                Agent Status: {incident.agent_status || 'ASSIGNED'}
              </span>
              <button type="button" className="secondary-btn" onClick={() => navigate('/agent/dashboard')}>
                Back
              </button>
            </div>
          </div>
        </header>

        <div className="workspace-grid" style={{ display: 'grid', gridTemplateColumns: '1.25fr 1fr', gap: '14px' }}>
          <div style={{ display: 'grid', gap: '12px' }}>
            <section className="panel" style={{ padding: '14px' }}>
              <h3 style={{ marginBottom: '6px' }}>Incident Briefing</h3>
              <p style={{ marginBottom: '8px' }}>{incident.description || 'No description available.'}</p>
              <div style={{ display: 'grid', gap: '6px', fontSize: '0.85rem', color: '#5f738a', fontWeight: 600 }}>
                <span>User: {incident.user_name || 'N/A'} ({incident.user_phone || 'N/A'})</span>
                <span>SLA ETA: {incident.sla?.estimated_resolution_at ? new Date(incident.sla.estimated_resolution_at).toLocaleString() : 'N/A'}</span>
                <span>Open Requests: Assistance {openAssistanceCount} &middot; Items {openItemCount}</span>
              </div>
            </section>

            {/* User-Uploaded Evidence */}
            {incident.media?.length > 0 && (
              <section className="panel" style={{ padding: '14px' }}>
                <h3 style={{ marginBottom: '8px' }}>User Evidence</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '8px' }}>
                  {incident.media.map((m) => (
                    <a
                      key={m.media_id}
                      href={`${window.location.origin}/api/v1/incidents/${incident.incident_id}/media/${m.media_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ display: 'block', borderRadius: '10px', overflow: 'hidden', border: '1px solid #d4e2ef', transition: 'all 0.2s' }}
                    >
                      <img
                        src={`${window.location.origin}/api/v1/incidents/${incident.incident_id}/media/${m.media_id}`}
                        alt={m.metadata?.filename || 'Evidence'}
                        style={{ width: '100%', height: '100px', objectFit: 'cover', display: 'block' }}
                      />
                      <div style={{ padding: '4px 6px', fontSize: '0.7rem', color: '#5f738a', fontWeight: 600, background: '#f8fafc' }}>
                        {m.metadata?.filename || 'Image'}
                      </div>
                    </a>
                  ))}
                </div>
              </section>
            )}

            {/* Backup Support Section */}
            {(incident.backup_agents || []).length > 0 && (
              <section className="panel" style={{ padding: '14px' }}>
                <h3 style={{ marginBottom: '8px' }}>Backup Support</h3>
                <div style={{ display: 'grid', gap: '8px' }}>
                  {incident.backup_agents.map((backup) => {
                    const statusMap = {
                      ASSIGNED: { label: 'Assigned', bg: '#e0f2fe', color: '#075985' },
                      EN_ROUTE: { label: 'En Route', bg: '#fff7ed', color: '#b45309' },
                      ON_SITE: { label: 'On Site', bg: '#ede9fe', color: '#5b21b6' },
                      IN_PROGRESS: { label: 'In Progress', bg: '#e5f4f1', color: '#030304' },
                      COMPLETED: { label: 'Completed', bg: '#dcfce7', color: '#047857' },
                    };
                    const roleLabelMap = {
                      backup: 'Backup Engineer',
                      supervisor: 'Supervisor',
                      safety_support: 'Safety Support',
                    };
                    const sMeta = statusMap[(backup.status || '').toUpperCase()] || { label: backup.status || 'Unknown', bg: '#f1f5f9', color: '#475569' };
                    const roleLabel = roleLabelMap[backup.role] || backup.role || 'Backup';
                    const agentDetail = backup.agent_details || {};

                    return (
                      <div key={backup.agent_id} className="panel-soft" style={{ padding: '10px', borderRadius: '12px', border: '1px solid #d4e2ef' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{
                              width: '32px', height: '32px', borderRadius: '10px',
                              background: 'linear-gradient(135deg, #030304, #0d0d1a)',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              color: '#fff', fontSize: '0.75rem', fontWeight: 800, flexShrink: 0,
                            }}>
                              {(agentDetail.full_name || backup.agent_id || '??').split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)}
                            </div>
                            <div>
                              <div style={{ fontSize: '0.88rem', fontWeight: 700, color: '#11263c' }}>
                                {agentDetail.full_name || backup.agent_id}
                              </div>
                              {agentDetail.specialization && (
                                <div style={{ fontSize: '0.76rem', color: '#6e859d' }}>{agentDetail.specialization}</div>
                              )}
                            </div>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{
                              padding: '3px 8px', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700,
                              background: '#fef3c7', color: '#92400e',
                            }}>
                              {roleLabel}
                            </span>
                            <span style={{
                              padding: '3px 8px', borderRadius: '999px', fontSize: '0.7rem', fontWeight: 700,
                              background: sMeta.bg, color: sMeta.color,
                            }}>
                              {sMeta.label}
                            </span>
                          </div>
                        </div>
                        {agentDetail.phone && (
                          <div style={{ fontSize: '0.78rem', color: '#587089', marginTop: '2px' }}>
                            Phone: {agentDetail.phone}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            <section className="panel" style={{ padding: '14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
                <h3 style={{ margin: 0 }}>Live Location</h3>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {!trackingEnabled ? (
                    <button type="button" className="primary-btn" onClick={startTracking}>Start GPS Tracking</button>
                  ) : (
                    <button type="button" className="secondary-btn" onClick={stopTracking}>Stop GPS Tracking</button>
                  )}
                  <button type="button" className="secondary-btn" onClick={sendLocationPing}>Manual Check-In</button>
                </div>
              </div>

              <div style={{ height: '300px', borderRadius: '14px', overflow: 'hidden', border: '1px solid #d5e3ef' }}>
                <MapContainer center={mapCenter} zoom={13} style={{ height: '100%', width: '100%' }}>
                  <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                  {userCoords && (
                    <Marker position={userCoords} icon={USER_ICON}>
                      <Popup>User reported location</Popup>
                    </Marker>
                  )}
                  {agentCoords && (
                    <Marker position={agentCoords} icon={AGENT_ICON}>
                      <Popup>Agent current location</Popup>
                    </Marker>
                  )}
                  {userCoords && agentCoords && (
                    <Polyline positions={[agentCoords, userCoords]} pathOptions={{ color: '#030304', dashArray: '8 8', weight: 3 }} />
                  )}
                </MapContainer>
              </div>
            </section>

            <section className="panel" style={{ padding: '14px' }}>
              <h3 style={{ marginBottom: '10px' }}>Milestones</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: '8px' }}>
                {MILESTONES.map((milestone) => (
                  <button
                    key={milestone.key}
                    type="button"
                    className="secondary-btn"
                    disabled={submitting}
                    onClick={() => submitMilestone(milestone.key)}
                    style={{ justifyContent: 'flex-start' }}
                  >
                    {milestone.label}
                  </button>
                ))}
              </div>
            </section>
          </div>

          <div style={{ display: 'grid', gap: '12px' }}>
            <section className="panel" style={{ padding: '14px' }}>
              <h3 style={{ marginBottom: '8px' }}>Field Timeline</h3>
              <div style={{ maxHeight: '240px', overflow: 'auto', display: 'grid', gap: '8px' }}>
                {timelineEvents.length === 0 && <p style={{ margin: 0 }}>No timeline entries yet.</p>}
                {timelineEvents.map((event) => (
                  <div key={event.id} className="panel-soft" style={{ padding: '10px', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                      <strong style={{ fontSize: '0.85rem' }}>{event.title}</strong>
                      <span style={{ fontSize: '0.75rem', color: '#7890a9' }}>{event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : ''}</span>
                    </div>
                    {event.message && <p style={{ margin: '4px 0 0', fontSize: '0.82rem' }}>{event.message}</p>}
                  </div>
                ))}
              </div>
            </section>

            {/* Request Assistance - only visible to primary agent */}
            {isPrimary && (
              <section className="panel" style={{ padding: '14px' }}>
                <h3 style={{ marginBottom: '8px' }}>Request Assistance</h3>
                <form onSubmit={handleCreateAssistance} style={{ display: 'grid', gap: '8px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    <CustomSelect
                      value={assistForm.request_type}
                      onChange={(v) => setAssistForm((current) => ({ ...current, request_type: v }))}
                      options={[
                        { value: 'backup', label: 'Backup Engineer' },
                        { value: 'safety_support', label: 'Safety Support' },
                        { value: 'supervisor', label: 'Supervisor' },
                      ]}
                    />
                    <CustomSelect
                      value={assistForm.priority}
                      onChange={(v) => setAssistForm((current) => ({ ...current, priority: v }))}
                      options={[
                        { value: 'LOW', label: 'Low' },
                        { value: 'MEDIUM', label: 'Medium' },
                        { value: 'HIGH', label: 'High' },
                        { value: 'CRITICAL', label: 'Critical' },
                      ]}
                    />
                  </div>
                  <textarea
                    className="input-control"
                    rows={2}
                    placeholder="Reason"
                    value={assistForm.reason}
                    onChange={(event) => setAssistForm((current) => ({ ...current, reason: event.target.value }))}
                  />
                  <input
                    className="input-control"
                    placeholder="Details"
                    value={assistForm.details}
                    onChange={(event) => setAssistForm((current) => ({ ...current, details: event.target.value }))}
                  />
                  <button type="submit" className="primary-btn" disabled={submitting || !assistForm.reason.trim()}>
                    Submit Assistance Request
                  </button>
                </form>
                <div style={{ marginTop: '8px', display: 'grid', gap: '6px' }}>
                  {(incident.assistance_requests || []).slice().reverse().slice(0, 4).map((req) => (
                    <div key={req.request_id} className="panel-soft" style={{ padding: '8px', borderRadius: '10px' }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 700 }}>{req.type} — {req.priority}</div>
                      <div style={{ fontSize: '0.78rem', color: '#587089' }}>{req.status}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section className="panel" style={{ padding: '14px' }}>
              <h3 style={{ marginBottom: '8px' }}>Request Items</h3>
              <form onSubmit={handleCreateItemRequest} style={{ display: 'grid', gap: '8px' }}>
                <input
                  className="input-control"
                  placeholder="Item name"
                  value={itemForm.item_name}
                  onChange={(event) => setItemForm((current) => ({ ...current, item_name: event.target.value }))}
                />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                  <input
                    className="input-control"
                    type="number"
                    min={1}
                    value={itemForm.quantity}
                    onChange={(event) => setItemForm((current) => ({ ...current, quantity: event.target.value }))}
                  />
                  <CustomSelect
                    value={itemForm.urgency}
                    onChange={(v) => setItemForm((current) => ({ ...current, urgency: v }))}
                    options={[
                      { value: 'LOW', label: 'Low' },
                      { value: 'NORMAL', label: 'Normal' },
                      { value: 'HIGH', label: 'High' },
                      { value: 'URGENT', label: 'Urgent' },
                    ]}
                  />
                </div>
                <input
                  className="input-control"
                  placeholder="Notes"
                  value={itemForm.notes}
                  onChange={(event) => setItemForm((current) => ({ ...current, notes: event.target.value }))}
                />
                <button type="submit" className="primary-btn" disabled={submitting || !itemForm.item_name.trim()}>
                  Submit Item Request
                </button>
              </form>
              <div style={{ marginTop: '8px', display: 'grid', gap: '6px' }}>
                {(incident.item_requests || []).slice().reverse().slice(0, 5).map((req) => (
                  <div key={req.request_id} className="panel-soft" style={{ padding: '8px', borderRadius: '10px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: 700 }}>{req.item_name} x{req.quantity}</span>
                      <span style={{ fontSize: '0.78rem', color: '#587089' }}>{req.status}</span>
                    </div>
                    {req.status === 'DELIVERED' && (
                      <button
                        type="button"
                        className="secondary-btn"
                        style={{ marginTop: '6px', minHeight: '30px', fontSize: '0.74rem' }}
                        onClick={() => markItemAsUsed(req.request_id)}
                      >
                        Mark Used
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>

            {/* Closure Checklist - only visible to primary agent, editable only after work started */}
            {isPrimary && (() => {
              const workStartedStatuses = new Set(['IN_PROGRESS', 'COMPLETED']);
              const hasStartedWork = workStartedStatuses.has((incident.agent_status || '').toUpperCase());
              const formDisabled = !hasStartedWork;

              return (
                <section className="panel" style={{ padding: '14px', opacity: formDisabled ? 0.7 : 1 }}>
                  <h3 style={{ marginBottom: '8px' }}>Closure Checklist</h3>

                  {formDisabled && (
                    <div style={{
                      padding: '10px 14px', borderRadius: '10px', marginBottom: '10px',
                      background: '#fffbeb', border: '1px solid #fde68a',
                      fontSize: '0.82rem', fontWeight: 600, color: '#92400e',
                      display: 'flex', alignItems: 'center', gap: '8px',
                    }}>
                      <span style={{ fontSize: '1rem' }}>&#9888;</span>
                      Resolution fields unlock after you start diagnosis. Click <strong style={{ margin: '0 3px' }}>Diagnosis Started</strong> milestone first.
                    </div>
                  )}

                  <form onSubmit={handleResolve} style={{ display: 'grid', gap: '8px' }}>
                    <div>
                      <div style={{ position: 'relative' }}>
                        <textarea
                          className="input-control"
                          rows={2}
                          placeholder="Resolution summary — describe what was found and how it was fixed"
                          disabled={formDisabled}
                          value={resolutionForm.resolutionNotes}
                          onChange={(event) => {
                            setResolutionForm((current) => ({ ...current, resolutionNotes: event.target.value }));
                            if (validationErrors.resolutionNotes) setValidationErrors((prev) => ({ ...prev, resolutionNotes: undefined }));
                          }}
                          style={{
                            ...(validationErrors.resolutionNotes ? { borderColor: '#dc2626', boxShadow: '0 0 0 1px #dc2626' } : {}),
                            paddingRight: '44px',
                          }}
                        />
                        <button
                          type="button"
                          onClick={toggleSpeechRecognition}
                          disabled={formDisabled}
                          title={isRecording ? 'Stop dictation' : 'Start dictation'}
                          style={{
                            position: 'absolute', right: '8px', top: '8px',
                            width: '32px', height: '32px', borderRadius: '50%',
                            border: 'none', cursor: formDisabled ? 'not-allowed' : 'pointer',
                            background: isRecording ? '#ef4444' : '#e2e8f0',
                            color: isRecording ? 'white' : '#475569',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '1rem', transition: 'all 0.2s',
                            animation: isRecording ? 'micPulse 1.5s ease-in-out infinite' : 'none',
                          }}
                        >
                          🎤
                        </button>
                      </div>
                      {isRecording && (
                        <span style={{ fontSize: '0.76rem', color: '#ef4444', fontWeight: 600 }}>
                          🔴 Listening... speak now
                        </span>
                      )}
                      {validationErrors.resolutionNotes && (
                        <span style={{ fontSize: '0.76rem', color: '#dc2626', fontWeight: 600 }}>{validationErrors.resolutionNotes}</span>
                      )}
                    </div>
                    <div>
                      <input
                        className="input-control"
                        placeholder="Root cause — e.g. corroded pipe joint, faulty regulator"
                        disabled={formDisabled}
                        value={resolutionForm.rootCause}
                        onChange={(event) => {
                          setResolutionForm((current) => ({ ...current, rootCause: event.target.value }));
                          if (validationErrors.rootCause) setValidationErrors((prev) => ({ ...prev, rootCause: undefined }));
                        }}
                        style={validationErrors.rootCause ? { borderColor: '#dc2626', boxShadow: '0 0 0 1px #dc2626' } : {}}
                      />
                      {validationErrors.rootCause && (
                        <span style={{ fontSize: '0.76rem', color: '#dc2626', fontWeight: 600 }}>{validationErrors.rootCause}</span>
                      )}
                    </div>
                    <div>
                      <input
                        className="input-control"
                        placeholder="Actions taken — e.g. isolated supply, replaced connector, tested"
                        disabled={formDisabled}
                        value={resolutionForm.actionsTaken}
                        onChange={(event) => {
                          setResolutionForm((current) => ({ ...current, actionsTaken: event.target.value }));
                          if (validationErrors.actionsTaken) setValidationErrors((prev) => ({ ...prev, actionsTaken: undefined }));
                        }}
                        style={validationErrors.actionsTaken ? { borderColor: '#dc2626', boxShadow: '0 0 0 1px #dc2626' } : {}}
                      />
                      {validationErrors.actionsTaken && (
                        <span style={{ fontSize: '0.76rem', color: '#dc2626', fontWeight: 600 }}>{validationErrors.actionsTaken}</span>
                      )}
                    </div>
                    <input
                      className="input-control"
                      placeholder="Verification evidence — e.g. tightness test passed, CO reading 0 ppm"
                      disabled={formDisabled}
                      value={resolutionForm.verificationEvidence}
                      onChange={(event) => setResolutionForm((current) => ({ ...current, verificationEvidence: event.target.value }))}
                    />
                    <CustomSelect
                      disabled={formDisabled}
                      value={resolutionForm.verificationResult}
                      onChange={(v) => setResolutionForm((current) => ({ ...current, verificationResult: v }))}
                      options={[
                        { value: 'PASS', label: 'PASS' },
                        { value: 'FAIL', label: 'FAIL' },
                      ]}
                    />
                    <input
                      className="input-control"
                      placeholder="Items used — e.g. flexible connector, PTFE tape, pressure gauge"
                      disabled={formDisabled}
                      value={resolutionForm.itemsUsed}
                      onChange={(event) => setResolutionForm((current) => ({ ...current, itemsUsed: event.target.value }))}
                    />
                    {/* Resolution Media Upload */}
                    <div>
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept="image/*,.pdf,.doc,.docx"
                        style={{ display: 'none' }}
                        onChange={handleResolutionFileSelect}
                        disabled={formDisabled}
                      />
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={formDisabled}
                        style={{
                          width: '100%', padding: '10px', borderRadius: '10px',
                          border: '2px dashed #cbd5e1', background: '#f8fafc',
                          cursor: formDisabled ? 'not-allowed' : 'pointer',
                          fontSize: '0.82rem', fontWeight: 600, color: '#64748b',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                        }}
                      >
                        📎 Attach Proof of Fix (photos, documents)
                      </button>
                      {resolutionFiles.length > 0 && (
                        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '6px' }}>
                          {resolutionFiles.map((file, idx) => (
                            <div key={idx} style={{
                              fontSize: '0.76rem', padding: '4px 8px', borderRadius: '8px',
                              background: '#e0f2fe', color: '#075985', fontWeight: 600,
                              display: 'flex', alignItems: 'center', gap: '4px',
                            }}>
                              {file.type?.startsWith('image/') ? '🖼️' : '📄'}{' '}
                              {file.name.length > 20 ? file.name.slice(0, 20) + '...' : file.name}
                              <span
                                onClick={() => removeResolutionFile(idx)}
                                style={{ cursor: 'pointer', color: '#b91c1c', marginLeft: '4px', fontWeight: 800 }}
                              >
                                ✕
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <label style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '0.82rem', fontWeight: 600, color: formDisabled ? '#94a3b8' : '#4d6178' }}>
                      <input
                        type="checkbox"
                        disabled={formDisabled}
                        checked={resolutionForm.safetyChecksCompleted}
                        onChange={(event) => setResolutionForm((current) => ({ ...current, safetyChecksCompleted: event.target.checked }))}
                      />
                      Safety checks completed
                    </label>
                    <label style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '0.82rem', fontWeight: 600, color: formDisabled ? '#94a3b8' : '#4d6178' }}>
                      <input
                        type="checkbox"
                        disabled={formDisabled}
                        checked={resolutionForm.handoffConfirmed}
                        onChange={(event) => setResolutionForm((current) => ({ ...current, handoffConfirmed: event.target.checked }))}
                      />
                      Customer handoff confirmed
                    </label>
                    <button type="submit" className="primary-btn" disabled={submitting || formDisabled}>
                      {submitting ? 'Submitting...' : 'Submit for Review'}
                    </button>
                  </form>
                </section>
              );
            })()}
          </div>
        </div>
      </div>

      <style>{`
        @keyframes micPulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.1); opacity: 0.8; }
        }
        @media (max-width: 1160px) {
          .workspace-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </div>
  );
};

export default AgentIncidentWorkspace;
