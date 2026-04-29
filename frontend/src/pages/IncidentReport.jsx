import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { reportIncident } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { formatUseCase } from '../utils/formatters';
import { formatReferenceId } from '../utils/incidentIds';
import ProfileDropdown from '../components/ProfileDropdown';

const SEVERITY_OPTIONS = [
  { value: 'low', label: 'Low', desc: 'Minor issue, no immediate risk', color: '#047857', bg: '#ecfdf5' },
  { value: 'medium', label: 'Medium', desc: 'Needs attention but not urgent', color: '#b45309', bg: '#fffbeb' },
  { value: 'high', label: 'High', desc: 'Significant risk, needs quick response', color: '#dc2626', bg: '#fef2f2' },
  { value: 'critical', label: 'Critical', desc: 'Immediate danger — evacuate if needed', color: '#7f1d1d', bg: '#fef2f2' },
];

const IncidentReport = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const routeLocation = useLocation();

  const manualMode = false;
  const prefillType = routeLocation.state?.classifiedUseCase || '';

  const [description, setDescription] = useState(routeLocation.state?.description || '');
  const [incidentType, setIncidentType] = useState(prefillType);
  const [location, setLocation] = useState('');
  const [userGeoLocation, setUserGeoLocation] = useState(null);
  const [geoStatus, setGeoStatus] = useState('Locating...');
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submittedId, setSubmittedId] = useState('');
  const [kbValidation, setKbValidation] = useState(null);
  const [classifiedUseCase, setClassifiedUseCase] = useState('');

  // Manual report extra fields
  const [userName, setUserName] = useState(user?.full_name || '');
  const [userPhone, setUserPhone] = useState(user?.phone || '');
  const [userAddress, setUserAddress] = useState('');
  const [severity, setSeverity] = useState('medium');

  const requestLocation = () => {
    if (!navigator.geolocation) {
      setGeoStatus('Location not supported in this browser');
      return;
    }

    setGeoStatus('Locating...');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const coords = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        };
        setUserGeoLocation(coords);
        setGeoStatus(`GPS captured (${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)})`);
      },
      () => {
        setGeoStatus('GPS unavailable. You can still continue with manual location.');
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 15000 },
    );
  };

  useEffect(() => {
    requestLocation();
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);

    try {
      if (manualMode) {
        // Submit as manual report
        const formData = new FormData();
        formData.append('tenant_id', user?.tenant_id);
        formData.append('user_id', user?.user_id);
        formData.append('description', description);
        formData.append('location', location);
        formData.append('severity', severity);
        if (incidentType) formData.append('incident_type', incidentType);
        if (userName) formData.append('user_name', userName);
        if (userPhone) formData.append('user_phone', userPhone);
        if (userAddress) formData.append('user_address', userAddress);
        if (userGeoLocation) {
          formData.append('user_geo_location', JSON.stringify(userGeoLocation));
        }
        if (existingIncidentId) {
          formData.append('existing_incident_id', existingIncidentId);
        }
        files.forEach((file) => formData.append('files', file));

        const response = await submitManualReport(formData);
        setSubmittedId(response.incident_id);
        if (response.kb_validation) setKbValidation(response.kb_validation);
        if (response.classified_use_case) setClassifiedUseCase(response.classified_use_case);
        setSubmitted(true);
      } else {
        // Normal flow: classify and go to chat
        const formData = new FormData();
        formData.append('tenant_id', user?.tenant_id);
        formData.append('user_id', user?.user_id);
        formData.append('description', description);
        formData.append('location', location);
        if (userGeoLocation) {
          formData.append('user_geo_location', JSON.stringify(userGeoLocation));
        }
        files.forEach((file) => formData.append('files', file));

        const response = await reportIncident(formData);
        navigate(`/chat/${response.incident_id}`, {
          state: {
            incidentId: response.incident_id,
            useCase: response.use_case,
            description,
            locationText: location,
            geoLocation: userGeoLocation || response.user_geo_location || null,
          },
        });
      }
    } catch (error) {
      alert(error.message || 'Failed to submit incident. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (event) => {
    if (event.target.files) {
      setFiles(Array.from(event.target.files));
    }
  };

  // formatUseCase imported from utils/formatters

  // KB match info - flat structure from backend: { match_type, similarity_score, description, ... }
  const kbMatch = kbValidation?.match_type ? kbValidation : null;
  const kbMatchType = kbMatch?.match_type; // "true" or "false"
  const kbScore = kbMatch?.similarity_score || 0;

  // Success screen after manual report submission
  if (submitted) {
    return (
      <main className="page-container">
        <ProfileDropdown />
        <section className="surface-card mx-auto max-w-3xl p-6 md:p-8" style={{ textAlign: 'center' }}>
          <div style={{
            width: '64px', height: '64px', borderRadius: '50%', background: '#ecfdf5',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 20px', border: '2px solid #a7f3d0',
          }}>
            <span style={{ fontSize: '28px' }}>&#10003;</span>
          </div>
          <h1 className="section-heading" style={{ fontSize: '1.6rem', marginBottom: '8px' }}>Report Submitted</h1>
          <p className="section-subheading" style={{ marginBottom: '20px' }}>
            Your manual incident report has been submitted for review.
            Our team will assess the situation and take appropriate action.
          </p>

          {/* Reference ID + Classified Use Case */}
          <div style={{
            background: '#f5f9fd', border: '1px solid #d7e3ee', borderRadius: '12px',
            padding: '14px', marginBottom: '24px', textAlign: 'left',
            display: 'flex', gap: '16px', alignItems: 'flex-start', flexWrap: 'wrap',
          }}>
            <div style={{ flex: 1, minWidth: '160px' }}>
              <div style={{ fontSize: '0.82rem', color: '#5f738a', fontWeight: 600, marginBottom: '6px' }}>Reference ID</div>
              <div style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontWeight: 700, fontSize: '0.95rem', color: '#030304' }}>
                {formatReferenceId(submittedId)}
              </div>
            </div>
            {classifiedUseCase && (
              <div style={{ flex: 1, minWidth: '160px' }}>
                <div style={{ fontSize: '0.82rem', color: '#5f738a', fontWeight: 600, marginBottom: '6px' }}>Classified As</div>
                <span style={{
                  display: 'inline-block', padding: '4px 12px', borderRadius: '8px',
                  background: '#ede9fe', color: '#5b21b6', fontWeight: 700, fontSize: '0.82rem',
                }}>
                  {formatUseCase(classifiedUseCase)}
                </span>
              </div>
            )}
          </div>

          {/* KB Validation Result */}
          {kbMatch && (
            <div style={{
              textAlign: 'left', marginBottom: '24px', borderRadius: '14px', overflow: 'hidden',
              border: kbMatchType === 'true' ? '1px solid #bbf7d0' : '1px solid #fde68a',
              background: '#fff',
            }}>
              {/* Header */}
              <div style={{
                padding: '14px 18px',
                background: kbMatchType === 'true'
                  ? 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)'
                  : 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)',
                borderBottom: kbMatchType === 'true' ? '1px solid #bbf7d0' : '1px solid #fde68a',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '1.2rem' }}>{kbMatchType === 'true' ? '\u26A0\uFE0F' : '\u2139\uFE0F'}</span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#1e293b' }}>
                      Knowledge Base Match Found
                    </div>
                    <div style={{ fontSize: '0.78rem', color: '#64748b' }}>
                      {kbMatchType === 'true' ? 'Similar known incident on record' : 'Similar false alarm on record'}
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{
                    padding: '3px 10px', borderRadius: '8px', fontSize: '0.76rem', fontWeight: 700,
                    background: kbMatchType === 'true' ? '#dcfce7' : '#fef3c7',
                    color: kbMatchType === 'true' ? '#166534' : '#92400e',
                    border: kbMatchType === 'true' ? '1px solid #86efac' : '1px solid #fcd34d',
                  }}>
                    {kbMatchType === 'true' ? 'True Incident' : 'False Alarm'}
                  </span>
                  <span style={{
                    padding: '3px 10px', borderRadius: '8px', fontSize: '0.76rem', fontWeight: 700,
                    background: kbScore >= 0.7 ? '#dcfce7' : kbScore >= 0.4 ? '#fef3c7' : '#fee2e2',
                    color: kbScore >= 0.7 ? '#166534' : kbScore >= 0.4 ? '#92400e' : '#991b1b',
                  }}>
                    {(kbScore * 100).toFixed(0)}% match
                  </span>
                </div>
              </div>

              {/* Body */}
              <div style={{ padding: '16px 18px' }}>
                {/* Description */}
                {kbMatch.description && (
                  <div style={{ marginBottom: '14px' }}>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      Description
                    </div>
                    <div style={{ fontSize: '0.88rem', color: '#334155', lineHeight: 1.5 }}>
                      {kbMatch.description}
                    </div>
                  </div>
                )}

                {/* True incident details */}
                {kbMatchType === 'true' && (
                  <>
                    {/* Outcome */}
                    {kbMatch.outcome && (
                      <div style={{ marginBottom: '14px' }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Expected Outcome
                        </div>
                        <span style={{
                          display: 'inline-block', padding: '4px 12px', borderRadius: '8px', fontSize: '0.82rem', fontWeight: 600,
                          background: kbMatch.outcome === 'emergency_dispatch' ? '#fee2e2'
                            : kbMatch.outcome === 'schedule_engineer' ? '#fef3c7'
                              : kbMatch.outcome === 'advisory_issued' ? '#e0f2fe'
                                : '#f1f5f9',
                          color: kbMatch.outcome === 'emergency_dispatch' ? '#991b1b'
                            : kbMatch.outcome === 'schedule_engineer' ? '#92400e'
                              : kbMatch.outcome === 'advisory_issued' ? '#030304'
                                : '#475569',
                        }}>
                          {kbMatch.outcome?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </span>
                      </div>
                    )}

                    {/* Root Cause */}
                    {kbMatch.root_cause && (
                      <div style={{
                        marginBottom: '14px', padding: '12px 14px', borderRadius: '10px',
                        background: '#fef2f2', borderLeft: '4px solid #f87171',
                      }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#991b1b', marginBottom: '4px' }}>
                          Root Cause (from similar incident)
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#7f1d1d', lineHeight: 1.5 }}>
                          {kbMatch.root_cause}
                        </div>
                      </div>
                    )}

                    {/* Actions Taken */}
                    {kbMatch.actions_taken && (
                      <div style={{
                        marginBottom: '14px', padding: '12px 14px', borderRadius: '10px',
                        background: '#eff6ff', borderLeft: '4px solid #60a5fa',
                      }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#1e40af', marginBottom: '4px' }}>
                          Recommended Actions (from similar incident)
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#1e3a5f', lineHeight: 1.5 }}>
                          {kbMatch.actions_taken}
                        </div>
                      </div>
                    )}

                    {/* Resolution Summary */}
                    {kbMatch.resolution_summary && (
                      <div style={{
                        marginBottom: '14px', padding: '12px 14px', borderRadius: '10px',
                        background: '#f0fdf4', borderLeft: '4px solid #4ade80',
                      }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#166534', marginBottom: '4px' }}>
                          Resolution Summary
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#14532d', lineHeight: 1.5 }}>
                          {kbMatch.resolution_summary}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* False alarm details */}
                {kbMatchType === 'false' && (
                  <>
                    {kbMatch.actual_issue && (
                      <div style={{
                        marginBottom: '14px', padding: '12px 14px', borderRadius: '10px',
                        background: '#fffbeb', borderLeft: '4px solid #fbbf24',
                      }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#92400e', marginBottom: '4px' }}>
                          Actual Issue (from similar past report)
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#78350f', lineHeight: 1.5 }}>
                          {kbMatch.actual_issue}
                        </div>
                      </div>
                    )}

                    {kbMatch.false_positive_reason && (
                      <div style={{
                        marginBottom: '14px', padding: '12px 14px', borderRadius: '10px',
                        background: '#f8fafc', borderLeft: '4px solid #94a3b8',
                      }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#475569', marginBottom: '4px' }}>
                          Why This Was a False Alarm
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#334155', lineHeight: 1.5 }}>
                          {kbMatch.false_positive_reason}
                        </div>
                      </div>
                    )}

                    {kbMatch.resolution && (
                      <div style={{
                        marginBottom: '14px', padding: '12px 14px', borderRadius: '10px',
                        background: '#f0fdf4', borderLeft: '4px solid #4ade80',
                      }}>
                        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#166534', marginBottom: '4px' }}>
                          Resolution
                        </div>
                        <div style={{ fontSize: '0.85rem', color: '#14532d', lineHeight: 1.5 }}>
                          {kbMatch.resolution}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {/* Tags */}
                {kbMatch.tags && kbMatch.tags.length > 0 && (
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#64748b', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      Tags
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {kbMatch.tags.map((tag) => (
                        <span key={tag} style={{
                          padding: '3px 10px', borderRadius: '6px', fontSize: '0.74rem', fontWeight: 600,
                          background: '#f1f5f9', color: '#475569',
                        }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* No KB match notice - show when backend returned no match (null kb_validation) but we did attempt validation */}
          {classifiedUseCase && !kbMatch && (
            <div style={{
              textAlign: 'left', marginBottom: '24px', borderRadius: '12px', padding: '14px 18px',
              background: '#f8fafc', border: '1px solid #e2e8f0',
              display: 'flex', alignItems: 'center', gap: '10px',
            }}>
              <span style={{ fontSize: '1.1rem' }}>&#128269;</span>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#334155' }}>No Knowledge Base Match</div>
                <div style={{ fontSize: '0.8rem', color: '#64748b' }}>
                  This incident doesn&apos;t closely match any known records. Our team will review it as a new case.
                </div>
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button type="button" className="btn-primary" onClick={() => navigate('/my-reports')}>
              View My Reports
            </button>
            <button type="button" className="secondary-btn" onClick={() => navigate('/dashboard')}>
              Back to Dashboard
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="page-container">
      <ProfileDropdown />
      <section className="surface-card mx-auto max-w-3xl p-6 md:p-8">
        <div className="mb-8">
          <button type="button" onClick={() => navigate('/dashboard')} className="btn-secondary mb-5">
            Back to Dashboard
          </button>
          <h1 className="section-heading text-3xl">
            {'Report Gas Incident'}
          </h1>
          <p className="section-subheading">
            {'Describe what you are experiencing and the assistant will guide next steps.'}
          </p>

          {manualMode && (
            <div style={{
              marginTop: '14px', padding: '12px 16px', borderRadius: '12px',
              background: '#eff6ff', border: '1px solid #bfdbfe',
              fontSize: '0.84rem', color: '#1e40af', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: '8px',
            }}>
              <span style={{ fontSize: '1.1rem' }}>&#9432;</span>
              This report will be sent directly to our team for manual review and action.
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Description */}
          <div>
            <label htmlFor="description" className="label-text">
              What is happening? *
            </label>
            <textarea
              id="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              required
              rows={5}
              className="input-control resize-none"
              placeholder="Describe the issue in detail — what you see, hear, or smell..."
            />
          </div>

          {/* Incident Type (manual mode) */}
          {manualMode && (
            <div>
              <label htmlFor="incidentType" className="label-text">
                Type of Issue
              </label>
              <input
                id="incidentType"
                type="text"
                value={incidentType}
                onChange={(event) => setIncidentType(event.target.value)}
                className="input-control"
                placeholder="e.g., Water leak, Electrical fault, Structural damage"
              />
              <p style={{ fontSize: '0.76rem', color: '#5f738a', marginTop: '4px' }}>
                Briefly categorize the issue type
              </p>
            </div>
          )}

          {/* Severity (manual mode) */}
          {manualMode && (
            <div>
              <label className="label-text">Severity *</label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px', marginTop: '6px' }}>
                {SEVERITY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setSeverity(opt.value)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '10px',
                      border: severity === opt.value ? `2px solid ${opt.color}` : '1px solid #d7e3ee',
                      background: severity === opt.value ? opt.bg : '#fff',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: '0.85rem', color: opt.color }}>{opt.label}</div>
                    <div style={{ fontSize: '0.74rem', color: '#5f738a', marginTop: '2px' }}>{opt.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Location */}
          <div>
            <label htmlFor="location" className="label-text">
              Location {manualMode && '*'}
            </label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              required={manualMode}
              className="input-control"
              placeholder="e.g., Kitchen, basement, outside meter, 123 Main St"
            />
            <div className="mt-2 flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50/90 px-3 py-2 text-xs text-slate-600">
              <span>{geoStatus}</span>
              <button
                type="button"
                className="secondary-btn"
                style={{ minHeight: '30px', padding: '4px 10px', fontSize: '0.75rem' }}
                onClick={requestLocation}
              >
                Retry GPS
              </button>
            </div>
          </div>

          {/* Contact Details (manual mode) */}
          {manualMode && (
            <fieldset style={{
              border: '1px solid #d7e3ee', borderRadius: '14px', padding: '16px 18px',
              background: '#f8fafc',
            }}>
              <legend style={{ fontWeight: 700, fontSize: '0.88rem', color: '#37526c', padding: '0 6px' }}>
                Contact Details
              </legend>
              <div style={{ display: 'grid', gap: '12px', marginTop: '8px' }}>
                <div>
                  <label htmlFor="userName" className="label-text">Full Name</label>
                  <input
                    id="userName"
                    type="text"
                    value={userName}
                    onChange={(event) => setUserName(event.target.value)}
                    className="input-control"
                    placeholder="Your full name"
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div>
                    <label htmlFor="userPhone" className="label-text">Phone Number</label>
                    <input
                      id="userPhone"
                      type="tel"
                      value={userPhone}
                      onChange={(event) => setUserPhone(event.target.value)}
                      className="input-control"
                      placeholder="+44 XXXX XXXXXX"
                    />
                  </div>
                  <div>
                    <label htmlFor="userAddress" className="label-text">Address</label>
                    <input
                      id="userAddress"
                      type="text"
                      value={userAddress}
                      onChange={(event) => setUserAddress(event.target.value)}
                      className="input-control"
                      placeholder="Street address or landmark"
                    />
                  </div>
                </div>
              </div>
            </fieldset>
          )}

          {/* File Upload */}
          <div>
            <label htmlFor="attachments" className="label-text">
              Upload Photos, Video, or Audio (Optional)
            </label>
            <input
              id="attachments"
              type="file"
              multiple
              accept="image/*,video/*,audio/*"
              onChange={handleFileChange}
              className="input-control"
            />
            {files.length > 0 && (
              <div className="mt-3 rounded-xl bg-slate-100/90 px-4 py-3 text-sm text-slate-700">
                {files.length} file(s) selected
              </div>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn-primary w-full py-3 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {loading
              ? 'Submitting...'
              : 'Submit Report'}
          </button>
        </form>

        <div className="mt-8 rounded-2xl border border-amber-300 bg-amber-50/90 p-4 text-sm text-amber-900">
          <span className="font-semibold">Emergency:</span> If you smell strong gas or suspect immediate danger,
          evacuate and call emergency services now.
        </div>
      </section>
    </main>
  );
};

export default IncidentReport;
