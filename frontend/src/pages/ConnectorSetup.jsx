import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  activateConnector,
  backfillConnector,
  configureConnector,
  getAvailableConnectors,
  getTenantConnectors,
  getTenants,
  storeConnectorCredentials,
  testConnector,
  updateConnector,
} from '../services/api';
import CustomSelect from '../components/CustomSelect';

const STEPS = [
  'Connector Type',
  'Connection Details',
  'Credentials',
  'Test',
  'Activate',
];

export default function ConnectorSetup() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();

  const editConfigId = searchParams.get('config_id') || '';
  const [isEditMode] = useState(!!editConfigId);

  const [tenantOptions, setTenantOptions] = useState([]);
  const [tenantId, setTenantId] = useState(searchParams.get('tenant_id') || user?.tenant_id || '');
  const [types, setTypes] = useState([]);

  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const [connectorType, setConnectorType] = useState('servicenow');
  const [displayName, setDisplayName] = useState('ServiceNow Connector');
  const [instanceUrl, setInstanceUrl] = useState('');
  const [authMethod, setAuthMethod] = useState('basic');

  // Basic auth credentials
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  // OAuth2 credentials
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [tokenUrl, setTokenUrl] = useState('');
  // API key credentials
  const [apiKey, setApiKey] = useState('');
  const [apiKeyHeader, setApiKeyHeader] = useState('X-API-Key');

  const [webhookSecret, setWebhookSecret] = useState(`${searchParams.get('tenant_id') || user?.tenant_id || 'tenant'}_webhook_secret`);

  const [configId, setConfigId] = useState(editConfigId);
  const [testResult, setTestResult] = useState(null);
  const [activated, setActivated] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);
  const [backfillLoading, setBackfillLoading] = useState(false);

  const selectedTenant = useMemo(
    () => tenantOptions.find((t) => t.tenant_id === tenantId),
    [tenantOptions, tenantId],
  );

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [typesRes, tenantsRes] = await Promise.all([
          getAvailableConnectors(),
          getTenants(),
        ]);

        if (cancelled) return;

        const available = typesRes.connectors || [];
        setTypes(available);
        if (available.length && !available.find((c) => c.type === connectorType)) {
          setConnectorType(available[0].type);
        }

        const tenants = tenantsRes.tenants || [];
        setTenantOptions(tenants);

        if (!tenantId && tenants.length) {
          setTenantId(tenants[0].tenant_id);
        }

        // Edit mode: load existing config and pre-populate
        if (editConfigId && tenantId) {
          try {
            const connRes = await getTenantConnectors(tenantId);
            const existing = (connRes.connectors || []).find((c) => c.config_id === editConfigId);
            if (existing && !cancelled) {
              setConnectorType(existing.connector_type);
              setDisplayName(existing.display_name);
              setInstanceUrl(existing.instance_url || '');
              setAuthMethod(existing.auth_method || 'basic');
              if (existing.settings?.webhook_secret) setWebhookSecret(existing.settings.webhook_secret);
              setConfigId(editConfigId);
              setStep(1); // Skip type selection, go to Connection Details
            }
          } catch {
          }
        }
      } catch {
        if (!cancelled) setError('Failed to load connector setup metadata');
      }
    };

    load();
    return () => { cancelled = true; };
  }, []);

  const validateStep = () => {
    if (step === 0) {
      if (!tenantId) return 'Tenant is required';
      if (!connectorType) return 'Connector type is required';
      return '';
    }

    if (step === 1) {
      if (!displayName.trim()) return 'Display name is required';
      if (!instanceUrl.trim()) return 'Instance URL is required';
      return '';
    }

    if (step === 2) {
      if (authMethod === 'basic') {
        if (!username.trim()) return 'Username is required';
        if (!password.trim()) return 'Password is required';
      } else if (authMethod === 'oauth2') {
        if (!clientId.trim()) return 'Client ID is required';
        if (!clientSecret.trim()) return 'Client Secret is required';
        if (!tokenUrl.trim()) return 'Token URL is required';
      } else if (authMethod === 'api_key') {
        if (!apiKey.trim()) return 'API Key is required';
      }
      return '';
    }

    return '';
  };

  const continueFlow = async () => {
    setError('');
    setMessage('');

    const validation = validateStep();
    if (validation) {
      setError(validation);
      return;
    }

    setLoading(true);
    try {
      if (step === 0) {
        setStep(1);
        return;
      }

      if (step === 1) {
        if (isEditMode && configId) {
          // Update existing config
          await updateConnector(configId, {
            tenant_id: tenantId,
            display_name: displayName,
            instance_url: instanceUrl,
            auth_method: authMethod,
            settings: {
              table_name: 'incident',
              webhook_secret: webhookSecret,
            },
          });
          setMessage('Connector config updated');
        } else {
          // Create new config
          const payload = {
            tenant_id: tenantId,
            connector_type: connectorType,
            display_name: displayName,
            instance_url: instanceUrl,
            auth_method: authMethod,
            settings: {
              table_name: 'incident',
              webhook_secret: webhookSecret,
            },
          };
          const data = await configureConnector(payload);
          setConfigId(data.config_id);
          setMessage(`Connector config created: ${data.config_id}`);
        }
        setStep(2);
        return;
      }

      if (step === 2) {
        let credentials = {};
        if (authMethod === 'basic') {
          credentials = { username, password };
        } else if (authMethod === 'oauth2') {
          credentials = { client_id: clientId, client_secret: clientSecret, token_url: tokenUrl };
        } else if (authMethod === 'api_key') {
          credentials = { api_key: apiKey };
          if (apiKeyHeader.trim()) credentials.api_key_header = apiKeyHeader;
        }

        await storeConnectorCredentials(configId, {
          tenant_id: tenantId,
          credentials,
        });
        setMessage('Credentials stored');
        setStep(3);
        return;
      }

      if (step === 3) {
        const result = await testConnector(configId, tenantId);
        setTestResult(result);
        if (result.status === 'ok') {
          setMessage('Connection test passed');
          setStep(4);
        } else {
          setError(result.message || 'Connection test failed');
        }
        return;
      }

      if (step === 4) {
        await activateConnector(configId, tenantId);
        setActivated(true);
        setMessage('Connector activated — pulling initial data...');

        // Auto-backfill after activation
        setBackfillLoading(true);
        try {
          const result = await backfillConnector(tenantId, connectorType, 50);
          setBackfillResult(result);
          const f = result.failed ?? 0;
          setMessage(f > 0
            ? `Activated! ${result.imported ?? 0} imported, ${f} failed — see details below.`
            : `Activated! Imported ${result.imported ?? 0} records, ${result.skipped ?? 0} skipped.`,
          );
        } catch (bfErr) {
          setBackfillResult({ imported: 0, skipped: 0, failed: 0, error: bfErr.message });
          setMessage('Connector activated. Initial data pull failed — you can retry from Connector Status.');
        } finally {
          setBackfillLoading(false);
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to continue connector setup');
    } finally {
      setLoading(false);
    }
  };

  const goBack = () => {
    setError('');
    setMessage('');
    if (isEditMode && step === 1) {
      // In edit mode step 1 is the first step — go back to connectors page
      navigate('/super/connectors');
      return;
    }
    setStep((prev) => Math.max(0, prev - 1));
  };

  return (
    <div style={S.page}>
      <div style={S.header}>
        <div>
          <button style={S.backLink} onClick={() => navigate('/super/connectors')}>
            Back to Connectors
          </button>
          <h1 style={S.title}>{isEditMode ? 'Edit Connector' : 'Connector Setup'}</h1>
          <p style={S.subtitle}>
            {isEditMode
              ? 'Update configuration, re-enter credentials, test, and re-activate.'
              : 'Configure, test, and activate a tenant connector.'}
          </p>
        </div>
      </div>

      <div style={S.stepRow}>
        {STEPS.map((label, idx) => (
          <div key={label} style={S.stepItem}>
            <div style={{ ...S.stepDot, ...(idx < step ? S.stepDone : idx === step ? S.stepActive : {}) }}>{idx + 1}</div>
            <div style={{ ...S.stepLabel, ...(idx === step ? S.stepLabelActive : {}) }}>{label}</div>
          </div>
        ))}
      </div>

      {error && <div style={S.error}>{error}</div>}
      {message && <div style={S.success}>{message}</div>}

      <div style={S.card}>
        {step === 0 && (
          <div style={S.grid}>
            <Field label="Tenant">
              <CustomSelect
                value={tenantId}
                onChange={(v) => { setTenantId(v); setWebhookSecret(`${v}_webhook_secret`); }}
                options={tenantOptions.map((t) => ({
                  value: t.tenant_id,
                  label: t.display_name ? `${t.display_name} (${t.tenant_id})` : t.tenant_id,
                }))}
                placeholder="Select tenant"
              />
            </Field>

            <Field label="Connector Type">
              <CustomSelect
                value={connectorType}
                onChange={setConnectorType}
                options={(types.length === 0 ? [{ type: 'servicenow' }] : types).map((t) => ({
                  value: t.type,
                  label: t.type,
                }))}
              />
            </Field>

          </div>
        )}

        {step === 1 && (
          <div style={S.grid}>
            <Field label="Display Name">
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} style={S.input} />
            </Field>

            <Field label="Auth Method">
              <CustomSelect
                value={authMethod}
                onChange={setAuthMethod}
                options={[
                  { value: 'basic', label: 'basic' },
                  { value: 'oauth2', label: 'oauth2' },
                  { value: 'api_key', label: 'api_key' },
                ]}
              />
            </Field>

            <Field label="Instance URL">
              <input
                value={instanceUrl}
                onChange={(e) => setInstanceUrl(e.target.value)}
                style={S.input}
                placeholder="https://your-instance.service-now.com"
              />
            </Field>

            <Field label="Webhook Secret">
              <input
                value={webhookSecret}
                onChange={(e) => setWebhookSecret(e.target.value)}
                style={S.input}
                placeholder={`${tenantId}_webhook_secret`}
              />
              <div style={{ fontSize: '0.72rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                Must match the secret configured in the external system's webhook sender.
              </div>
            </Field>

            <Field label="Selected Tenant">
              <div style={S.readonlyBox}>{selectedTenant?.display_name || tenantId || '-'}</div>
            </Field>

            {isEditMode && (
              <div style={S.info}>
                Editing connector <strong>{configId}</strong>. Saving will deactivate the connector — you must re-test and re-activate.
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div style={S.grid}>
            {authMethod === 'basic' && (
              <>
                <Field label="Username">
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    style={S.input}
                    placeholder="integration_user"
                  />
                </Field>
                <Field label="Password">
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={S.input}
                    placeholder="connector password"
                  />
                </Field>
              </>
            )}
            {authMethod === 'oauth2' && (
              <>
                <Field label="Client ID">
                  <input
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    style={S.input}
                    placeholder="e.g. cadent-client"
                  />
                </Field>
                <Field label="Client Secret">
                  <input
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    style={S.input}
                    placeholder="e.g. cadent-secret"
                  />
                </Field>
                <Field label="Token URL">
                  <input
                    value={tokenUrl}
                    onChange={(e) => setTokenUrl(e.target.value)}
                    style={S.input}
                    placeholder="e.g. http://localhost:9000/oauth/token"
                  />
                </Field>
              </>
            )}
            {authMethod === 'api_key' && (
              <>
                <Field label="API Key">
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    style={S.input}
                    placeholder="your-api-key"
                  />
                </Field>
                <Field label="API Key Header (optional)">
                  <input
                    value={apiKeyHeader}
                    onChange={(e) => setApiKeyHeader(e.target.value)}
                    style={S.input}
                    placeholder="X-API-Key"
                  />
                </Field>
              </>
            )}
          </div>
        )}

        {step === 3 && (
          <div>
            <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
              <div style={{ fontSize: '0.82rem', color: '#64748b', marginBottom: '0.5rem' }}>Config: <strong>{configId}</strong></div>

              {!testResult && !loading && (
                <>
                  <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>&#128268;</div>
                  <p style={{ color: '#475569', fontWeight: 600, margin: '0 0 1rem' }}>
                    Ready to test connectivity to your external system.
                  </p>
                  <button
                    onClick={continueFlow}
                    style={{ ...S.primaryBtn, padding: '0.7rem 2rem', fontSize: '0.9rem' }}
                  >
                    Run Connection Test
                  </button>
                </>
              )}

              {loading && (
                <>
                  <div style={{ fontSize: '2.5rem', marginBottom: '0.5rem', animation: 'spin 1s linear infinite' }}>&#9881;&#65039;</div>
                  <p style={{ color: '#475569', fontWeight: 600, margin: 0 }}>Testing connection...</p>
                </>
              )}

              {testResult && !loading && (
                <>
                  <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>
                    {testResult.status === 'ok' ? '\u2705' : '\u274C'}
                  </div>
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: '6px',
                    padding: '6px 16px', borderRadius: '999px', fontSize: '0.88rem', fontWeight: 700,
                    background: testResult.status === 'ok' ? '#f0fdf4' : '#fef2f2',
                    color: testResult.status === 'ok' ? '#047857' : '#b91c1c',
                    border: `1px solid ${testResult.status === 'ok' ? '#bbf7d0' : '#fecaca'}`,
                  }}>
                    {testResult.status === 'ok' ? 'Connection Successful' : 'Connection Failed'}
                  </div>
                  {testResult.message && (
                    <p style={{ color: '#475569', fontSize: '0.84rem', margin: '0.75rem 0 0', fontWeight: 600 }}>
                      {testResult.message}
                    </p>
                  )}
                  {testResult.latency_ms != null && (
                    <p style={{ color: '#64748b', fontSize: '0.78rem', margin: '0.35rem 0 0' }}>
                      Latency: {testResult.latency_ms}ms
                    </p>
                  )}
                  {testResult.status !== 'ok' && (
                    <button
                      onClick={() => { setTestResult(null); setError(''); }}
                      style={{ ...S.secondaryBtn, marginTop: '1rem' }}
                    >
                      Retry Test
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        {step === 4 && (
          <div style={S.grid}>
            <Field label="Config ID">
              <div style={S.readonlyBox}>{configId || '-'}</div>
            </Field>
            <Field label="Tenant">
              <div style={S.readonlyBox}>{tenantId || '-'}</div>
            </Field>
            <Field label="Activation">
              <div style={S.readonlyBox}>{activated ? 'Active' : 'Ready to activate'}</div>
            </Field>
            {activated && (
              <div style={{ gridColumn: '1 / -1', marginTop: '0.75rem' }}>
                {backfillLoading && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0.6rem 0.75rem', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '0.55rem', marginBottom: '0.75rem' }}>
                    <span style={{ animation: 'spin 1s linear infinite' }}>&#9881;&#65039;</span>
                    <span style={{ fontSize: '0.84rem', fontWeight: 600, color: '#1e40af' }}>Pulling initial data from external system...</span>
                  </div>
                )}
                {backfillResult && !backfillLoading && (
                  <BackfillResultPanel result={backfillResult} />
                )}
                <button
                  onClick={() => navigate('/super/connectors')}
                  style={{ ...S.secondaryBtn, fontSize: '0.82rem', padding: '0.5rem 1rem' }}
                >
                  Return to Connector Status
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <div style={S.footer}>
        <button onClick={goBack} disabled={(step === 0 && !isEditMode) || loading} style={S.secondaryBtn}>Back</button>
        {step === 3 ? (
          <button
            onClick={() => { setStep(4); setError(''); setMessage('Connection test passed'); }}
            disabled={!testResult || testResult.status !== 'ok'}
            style={{
              ...S.primaryBtn,
              opacity: (!testResult || testResult.status !== 'ok') ? 0.5 : 1,
              cursor: (!testResult || testResult.status !== 'ok') ? 'not-allowed' : 'pointer',
            }}
          >
            Continue to Activate
          </button>
        ) : (
          <button onClick={continueFlow} disabled={loading || (step === 4 && activated)} style={S.primaryBtn}>
            {loading ? 'Working...' : step === 4 ? (activated ? 'Activated' : 'Activate') : 'Continue'}
          </button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={S.label}>{label}</div>
      {children}
    </div>
  );
}

function BackfillResultPanel({ result }) {
  const [showErrors, setShowErrors] = useState(false);

  const failed = result.failed ?? 0;
  const imported = result.imported ?? 0;
  const skipped = result.skipped ?? 0;
  const errors = result.errors ?? [];
  const hasCriticalFailure = result.error; // HTTP-level failure
  const hasPartialFailures = failed > 0 && errors.length > 0;
  const allFailed = failed > 0 && imported === 0 && skipped === 0;

  // Determine panel color
  const isError = hasCriticalFailure || allFailed;
  const isWarning = hasPartialFailures && !allFailed;

  const panelBg = isError ? '#fef2f2' : isWarning ? '#fffbeb' : '#f0fdf4';
  const panelBorder = isError ? '#fecaca' : isWarning ? '#fde68a' : '#bbf7d0';
  const titleColor = isError ? '#991b1b' : isWarning ? '#92400e' : '#166534';

  // Deduplicate errors by message and count occurrences
  const errorSummary = [];
  if (errors.length > 0) {
    const counts = {};
    for (const e of errors) {
      const msg = typeof e === 'string' ? e : (e.error || 'Unknown error');
      counts[msg] = (counts[msg] || 0) + 1;
    }
    for (const [msg, count] of Object.entries(counts)) {
      errorSummary.push({ message: msg, count });
    }
    errorSummary.sort((a, b) => b.count - a.count);
  }

  // Determine actionable advice based on error patterns
  const advice = [];
  const errorText = errors.map((e) => typeof e === 'string' ? e : (e.error || '')).join(' ').toLowerCase();
  if (errorText.includes('auth') || errorText.includes('401') || errorText.includes('credential')) {
    advice.push('Check your connector credentials — they may be expired or incorrect.');
  }
  if (errorText.includes('timeout') || errorText.includes('timed out')) {
    advice.push('The external system is slow to respond. Try again with a smaller batch size.');
  }
  if (errorText.includes('rate') || errorText.includes('429') || errorText.includes('throttl')) {
    advice.push('You are being rate-limited by the external system. Wait a few minutes and retry.');
  }
  if (errorText.includes('mapping') || errorText.includes('field') || errorText.includes('transform')) {
    advice.push('Some records have fields that could not be mapped. Check your field mappings.');
  }
  if (errorText.includes('duplicate') || errorText.includes('already exists')) {
    advice.push('Some records already exist in the platform. These were skipped.');
  }
  if (errorText.includes('validation') || errorText.includes('required') || errorText.includes('invalid')) {
    advice.push('Some external records are missing required fields or contain invalid data.');
  }
  if (advice.length === 0 && hasPartialFailures) {
    advice.push('Some records could not be imported. Expand the error details below for more information.');
  }

  return (
    <div style={{ padding: '0.75rem', borderRadius: '0.55rem', marginBottom: '0.75rem', background: panelBg, border: `1px solid ${panelBorder}` }}>
      {/* Title */}
      <div style={{ fontSize: '0.84rem', fontWeight: 700, color: titleColor, marginBottom: '0.4rem' }}>
        {hasCriticalFailure ? 'Initial Pull Failed'
          : allFailed ? 'All Records Failed to Import'
          : isWarning ? 'Imported With Errors'
          : 'Initial Data Pull Complete'}
      </div>

      {/* Counters */}
      <div style={{ display: 'flex', gap: '1rem', fontSize: '0.82rem', color: '#374151' }}>
        <span><strong>{imported}</strong> imported</span>
        <span><strong>{skipped}</strong> skipped</span>
        {failed > 0 && (
          <span style={{ color: '#b91c1c' }}><strong>{failed}</strong> failed</span>
        )}
      </div>

      {/* Critical HTTP error */}
      {hasCriticalFailure && (
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem', color: '#991b1b', fontWeight: 600 }}>
          {result.error}
        </p>
      )}

      {/* Actionable advice */}
      {advice.length > 0 && (
        <div style={{ marginTop: '0.5rem', padding: '0.5rem 0.6rem', background: 'rgba(255,255,255,0.6)', borderRadius: '0.4rem', border: `1px solid ${panelBorder}` }}>
          <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#475569', marginBottom: '0.25rem', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
            What to do
          </div>
          {advice.map((a, i) => (
            <div key={i} style={{ fontSize: '0.8rem', color: '#334155', lineHeight: 1.5 }}>
              &bull; {a}
            </div>
          ))}
        </div>
      )}

      {/* Expandable error details */}
      {hasPartialFailures && (
        <div style={{ marginTop: '0.5rem' }}>
          <button
            type="button"
            onClick={() => setShowErrors((p) => !p)}
            style={{
              border: 'none', background: 'transparent', cursor: 'pointer', padding: 0,
              fontSize: '0.78rem', fontWeight: 700, color: '#6b7280',
              display: 'flex', alignItems: 'center', gap: '4px',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 20 20" fill="none" style={{ transform: showErrors ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.2s' }}>
              <path d="M5 7.5L10 12.5L15 7.5" stroke="#6b7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {showErrors ? 'Hide' : 'Show'} error details ({errors.length})
          </button>

          {showErrors && (
            <div style={{ marginTop: '0.4rem', maxHeight: 240, overflowY: 'auto', borderRadius: '0.4rem', border: '1px solid #e5e7eb', background: '#fff' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.76rem' }}>
                <thead>
                  <tr style={{ background: '#f9fafb', position: 'sticky', top: 0 }}>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 700, borderBottom: '1px solid #e5e7eb' }}>Ticket</th>
                    <th style={{ padding: '6px 10px', textAlign: 'left', color: '#6b7280', fontWeight: 700, borderBottom: '1px solid #e5e7eb' }}>Error</th>
                    {errorSummary.length !== errors.length && (
                      <th style={{ padding: '6px 10px', textAlign: 'center', color: '#6b7280', fontWeight: 700, borderBottom: '1px solid #e5e7eb', width: 50 }}>Count</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {/* Show individual errors if structured, otherwise show deduplicated summary */}
                  {errors.length > 0 && typeof errors[0] === 'object' ? (
                    errors.map((e, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '5px 10px', color: '#374151', fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {e.external_number || e.external_id || `Record ${i + 1}`}
                        </td>
                        <td style={{ padding: '5px 10px', color: '#991b1b', wordBreak: 'break-word' }}>
                          {e.error || 'Unknown error'}
                        </td>
                      </tr>
                    ))
                  ) : (
                    errorSummary.map((e, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                        <td style={{ padding: '5px 10px', color: '#374151', fontWeight: 600 }}>—</td>
                        <td style={{ padding: '5px 10px', color: '#991b1b', wordBreak: 'break-word' }}>{e.message}</td>
                        <td style={{ padding: '5px 10px', textAlign: 'center', color: '#6b7280', fontWeight: 600 }}>{e.count > 1 ? `x${e.count}` : ''}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const S = {
  page: {
    minHeight: '100vh',
    background: '#f3f4f6',
    padding: '2rem 2.5rem',
  },
  header: {
    marginBottom: '1rem',
  },
  backLink: {
    border: 'none',
    background: 'transparent',
    color: '#475569',
    fontWeight: 600,
    cursor: 'pointer',
    padding: 0,
    marginBottom: '0.5rem',
  },
  title: {
    margin: 0,
    fontSize: '1.9rem',
    fontWeight: 800,
    color: '#0f172a',
  },
  subtitle: {
    margin: '0.35rem 0 0',
    color: '#64748b',
  },
  stepRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(5, minmax(110px, 1fr))',
    gap: '0.5rem',
    marginBottom: '1rem',
  },
  stepItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '0.3rem',
  },
  stepDot: {
    width: 30,
    height: 30,
    borderRadius: '50%',
    background: '#e2e8f0',
    color: '#334155',
    fontSize: '0.8rem',
    fontWeight: 700,
    display: 'grid',
    placeItems: 'center',
  },
  stepActive: {
    background: '#030304',
    color: '#fff',
  },
  stepDone: {
    background: '#8DE971',
    color: '#030304',
  },
  stepLabel: {
    fontSize: '0.72rem',
    color: '#64748b',
    fontWeight: 700,
    textAlign: 'center',
  },
  stepLabelActive: {
    color: '#0f172a',
  },
  card: {
    background: '#fff',
    border: '1px solid #e2e8f0',
    borderRadius: '0.9rem',
    padding: '1.25rem',
    boxShadow: '0 4px 14px -10px rgba(15, 23, 42, 0.25)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: '0.75rem 0.9rem',
  },
  label: {
    fontSize: '0.78rem',
    fontWeight: 700,
    color: '#475569',
    marginBottom: '0.35rem',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  input: {
    width: '100%',
    boxSizing: 'border-box',
    border: '1px solid #cbd5e1',
    borderRadius: '0.55rem',
    padding: '0.6rem 0.7rem',
    fontSize: '0.9rem',
    color: '#0f172a',
    background: '#fff',
  },
  readonlyBox: {
    border: '1px solid #e2e8f0',
    borderRadius: '0.55rem',
    padding: '0.6rem 0.7rem',
    background: '#f8fafc',
    fontSize: '0.9rem',
    color: '#0f172a',
    fontWeight: 600,
  },
  footer: {
    marginTop: '1rem',
    display: 'flex',
    justifyContent: 'space-between',
  },
  secondaryBtn: {
    border: '1px solid #cbd5e1',
    background: '#fff',
    color: '#334155',
    borderRadius: '0.55rem',
    padding: '0.6rem 1rem',
    fontWeight: 700,
    cursor: 'pointer',
  },
  primaryBtn: {
    border: 'none',
    background: '#8DE971',
    color: '#030304',
    borderRadius: '0.55rem',
    padding: '0.6rem 1rem',
    fontWeight: 700,
    cursor: 'pointer',
  },
  error: {
    border: '1px solid #fecaca',
    background: '#fef2f2',
    color: '#991b1b',
    borderRadius: '0.55rem',
    padding: '0.55rem 0.7rem',
    marginBottom: '0.75rem',
    fontSize: '0.84rem',
    fontWeight: 600,
  },
  success: {
    border: '1px solid #bbf7d0',
    background: '#f0fdf4',
    color: '#166534',
    borderRadius: '0.55rem',
    padding: '0.55rem 0.7rem',
    marginBottom: '0.75rem',
    fontSize: '0.84rem',
    fontWeight: 600,
  },
};
