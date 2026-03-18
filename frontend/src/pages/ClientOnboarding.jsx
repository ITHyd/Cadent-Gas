import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  activateConnector,
  configureConnector,
  createTenant,
  createTenantUser,
  storeConnectorCredentials,
  testConnector,
  updateTenantStatus,
} from '../services/api';
import CustomSelect from '../components/CustomSelect';

const STEPS = [
  'Tenant Details',
  'Company Admins',
  'Field Agents',
  'Users',
  'Connector',
  'Review & Activate',
];

const slugify = (value) =>
  (value || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-');

const emptyAdmin = () => ({ full_name: '', phone: '', use_password_login: false, username: '', password: '' });
const emptyPerson = () => ({ full_name: '', phone: '' });

export default function ClientOnboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [tenant, setTenant] = useState({
    company_name: '',
    display_name: '',
    contact_email: '',
    contact_phone: '',
  });

  const [admins, setAdmins] = useState([emptyAdmin()]);
  const [agents, setAgents] = useState([emptyPerson()]);
  const [users, setUsers] = useState([emptyPerson()]);

  const [connector, setConnector] = useState({
    mode: 'none',
    display_name: 'ServiceNow Connector',
    instance_url: '',
    username: '',
    password: '',
  });

  const [runtime, setRuntime] = useState({
    tenant_id: '',
    tenant_created: false,
    admins_created: 0,
    agents_created: 0,
    users_created: 0,
    connector_config_id: '',
    connector_active: false,
    tenant_activated: false,
  });

  const tenantId = useMemo(() => {
    if (runtime.tenant_id) return runtime.tenant_id;
    return tenant.company_name ? `tenant_${slugify(tenant.company_name)}` : '';
  }, [runtime.tenant_id, tenant.company_name]);

  const validateStep = () => {
    if (step === 0) {
      if (!tenant.company_name.trim()) return 'Company name is required';
      if (!tenantId) return 'Tenant ID could not be generated';
    }
    if (step === 1) {
      for (let i = 0; i < admins.length; i++) {
        const a = admins[i];
        if (!a.full_name.trim()) return `Admin ${i + 1}: full name is required`;
        if (!a.phone.trim()) return `Admin ${i + 1}: phone is required`;
        if (a.use_password_login && !a.username.trim()) return `Admin ${i + 1}: username is required`;
        if (a.use_password_login && !a.password.trim()) return `Admin ${i + 1}: password is required`;
      }
    }
    if (step === 2) {
      for (let i = 0; i < agents.length; i++) {
        if (agents[i].full_name.trim() && !agents[i].phone.trim()) return `Agent ${i + 1}: phone is required`;
      }
    }
    if (step === 3) {
      for (let i = 0; i < users.length; i++) {
        if (users[i].full_name.trim() && !users[i].phone.trim()) return `User ${i + 1}: phone is required`;
      }
    }
    if (step === 4 && connector.mode === 'servicenow') {
      if (!connector.instance_url.trim()) return 'ServiceNow instance URL is required';
      if (!connector.username.trim() || !connector.password.trim()) return 'ServiceNow credentials are required';
    }
    return '';
  };

  const runStep = async () => {
    setError('');
    setSuccess('');
    const validationError = validateStep();
    if (validationError) { setError(validationError); return; }

    setLoading(true);
    try {
      // Step 0: Create tenant
      if (step === 0) {
        if (!runtime.tenant_created) {
          await createTenant({
            tenant_id: tenantId,
            display_name: tenant.display_name || tenant.company_name,
            contact_email: tenant.contact_email || null,
            contact_phone: tenant.contact_phone || null,
            branding: { company_name: tenant.company_name },
          });
          setRuntime((p) => ({ ...p, tenant_id: tenantId, tenant_created: true }));
          setSuccess(`Tenant "${tenantId}" created`);
        }
        setStep(1);
        return;
      }

      // Step 1: Create company admins
      if (step === 1) {
        let created = runtime.admins_created;
        for (let i = created; i < admins.length; i++) {
          const a = admins[i];
          if (!a.full_name.trim()) continue;
          await createTenantUser(tenantId, {
            full_name: a.full_name,
            phone: a.phone,
            role: 'company',
            username: a.use_password_login ? a.username : null,
            password: a.use_password_login ? a.password : null,
          });
          created++;
          setRuntime((p) => ({ ...p, admins_created: created }));
        }
        setSuccess(`${created} company admin(s) created`);
        setStep(2);
        return;
      }

      // Step 2: Create field agents
      if (step === 2) {
        let created = runtime.agents_created;
        const valid = agents.filter((a) => a.full_name.trim() && a.phone.trim());
        for (let i = created; i < valid.length; i++) {
          await createTenantUser(tenantId, {
            full_name: valid[i].full_name,
            phone: valid[i].phone,
            role: 'agent',
          });
          created++;
          setRuntime((p) => ({ ...p, agents_created: created }));
        }
        setSuccess(created ? `${created} field agent(s) created` : 'Skipped — no agents added');
        setStep(3);
        return;
      }

      // Step 3: Create users
      if (step === 3) {
        let created = runtime.users_created;
        const valid = users.filter((u) => u.full_name.trim() && u.phone.trim());
        for (let i = created; i < valid.length; i++) {
          await createTenantUser(tenantId, {
            full_name: valid[i].full_name,
            phone: valid[i].phone,
            role: 'user',
          });
          created++;
          setRuntime((p) => ({ ...p, users_created: created }));
        }
        setSuccess(created ? `${created} user(s) created` : 'Skipped — no users added');
        setStep(4);
        return;
      }

      // Step 4: Connector
      if (step === 4) {
        if (connector.mode === 'none') {
          setStep(5);
          return;
        }
        if (!runtime.connector_config_id) {
          const slug = slugify(tenant.company_name);
          const config = await configureConnector({
            tenant_id: tenantId,
            connector_type: 'servicenow',
            display_name: connector.display_name || 'ServiceNow Connector',
            instance_url: connector.instance_url,
            auth_method: 'basic',
            settings: { table_name: 'incident', webhook_secret: `${slug}_webhook_secret` },
          });
          const configId = config.config_id;
          const credentials = { username: connector.username, password: connector.password };
          await storeConnectorCredentials(configId, { tenant_id: tenantId, credentials });
          await testConnector(configId, tenantId);
          await activateConnector(configId, tenantId);
          setRuntime((p) => ({ ...p, connector_config_id: configId, connector_active: true }));
          setSuccess('Connector configured and activated');
        }
        setStep(5);
        return;
      }

      // Step 5: Activate
      if (step === 5) {
        if (!runtime.tenant_activated) {
          await updateTenantStatus(tenantId, 'active');
          setRuntime((p) => ({ ...p, tenant_activated: true }));
        }
        navigate('/super/tenants');
      }
    } catch (err) {
      setError(err.message || 'Failed to complete onboarding step');
    } finally {
      setLoading(false);
    }
  };

  const back = () => { setError(''); setSuccess(''); setStep((p) => Math.max(0, p - 1)); };

  // List helpers
  const updateList = (setter, idx, field, value) =>
    setter((prev) => prev.map((item, i) => (i === idx ? { ...item, [field]: value } : item)));
  const addToList = (setter, factory) => setter((prev) => [...prev, factory()]);
  const removeFromList = (setter, idx) => setter((prev) => prev.filter((_, i) => i !== idx));

  return (
    <div style={S.page}>
      <div style={S.headerRow}>
        <div>
          <button style={S.backBtn} onClick={() => navigate('/super/tenants')}>Back to Tenants</button>
          <h1 style={S.title}>Client Onboarding</h1>
          <p style={S.subtitle}>Create a new tenant with users, agents, and admins.</p>
        </div>
      </div>

      <div style={S.stepper}>
        {STEPS.map((label, idx) => {
          const active = idx === step;
          const done = idx < step;
          return (
            <div key={label} style={S.stepNode}>
              <div style={{ ...S.stepCircle, ...(done ? S.stepCircleDone : active ? S.stepCircleActive : {}) }}>
                {done ? '\u2713' : idx + 1}
              </div>
              <div style={{ ...S.stepLabel, ...(active ? S.stepLabelActive : {}) }}>{label}</div>
            </div>
          );
        })}
      </div>

      {error && <div style={S.error}>{error}</div>}
      {success && <div style={S.success}>{success}</div>}

      <div style={S.card}>
        {/* Step 0: Tenant Details */}
        {step === 0 && (
          <div style={S.grid2}>
            <Field label="Company Name">
              <input
                value={tenant.company_name}
                onChange={(e) => {
                  const val = e.target.value;
                  setTenant((p) => ({ ...p, company_name: val, display_name: p.display_name || val }));
                }}
                style={S.input}
                placeholder="Cadent Gas Ltd"
              />
              <div style={S.hint}>Tenant ID: {tenantId || 'tenant_<company>'}</div>
            </Field>
            <Field label="Display Name">
              <input
                value={tenant.display_name}
                onChange={(e) => setTenant((p) => ({ ...p, display_name: e.target.value }))}
                style={S.input}
                placeholder="Cadent Gas Ltd"
              />
            </Field>
            <Field label="Contact Email">
              <input
                value={tenant.contact_email}
                onChange={(e) => setTenant((p) => ({ ...p, contact_email: e.target.value }))}
                style={S.input}
                placeholder="ops@cadent.example"
              />
            </Field>
            <Field label="Contact Phone">
              <input
                value={tenant.contact_phone}
                onChange={(e) => setTenant((p) => ({ ...p, contact_phone: e.target.value }))}
                style={S.input}
                placeholder="+447700900000"
              />
            </Field>
          </div>
        )}

        {/* Step 1: Company Admins */}
        {step === 1 && (
          <div>
            <div style={S.sectionHeader}>
              <span>Company Admins</span>
              <button style={S.addBtn} onClick={() => addToList(setAdmins, emptyAdmin)}>+ Add Admin</button>
            </div>
            {admins.map((a, i) => (
              <div key={i} style={S.personCard}>
                <div style={S.personHeader}>
                  <span style={S.personIndex}>Admin {i + 1}</span>
                  {admins.length > 1 && (
                    <button style={S.removeBtn} onClick={() => removeFromList(setAdmins, i)}>Remove</button>
                  )}
                </div>
                <div style={S.grid2}>
                  <Field label="Full Name">
                    <input value={a.full_name} onChange={(e) => updateList(setAdmins, i, 'full_name', e.target.value)} style={S.input} placeholder="Richard Bennett" />
                  </Field>
                  <Field label="Phone">
                    <input value={a.phone} onChange={(e) => updateList(setAdmins, i, 'phone', e.target.value)} style={S.input} placeholder="+447700900123" />
                  </Field>
                  <Field label="Password Login">
                    <label style={S.checkboxLabel}>
                      <input type="checkbox" checked={a.use_password_login} onChange={(e) => updateList(setAdmins, i, 'use_password_login', e.target.checked)} />
                      Enable username/password login
                    </label>
                  </Field>
                  {a.use_password_login && (
                    <>
                      <Field label="Username">
                        <input value={a.username} onChange={(e) => updateList(setAdmins, i, 'username', e.target.value)} style={S.input} placeholder="cadent_admin" />
                      </Field>
                      <Field label="Password">
                        <input type="password" value={a.password} onChange={(e) => updateList(setAdmins, i, 'password', e.target.value)} style={S.input} placeholder="admin123" />
                      </Field>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Step 2: Field Agents */}
        {step === 2 && (
          <div>
            <div style={S.sectionHeader}>
              <span>Field Agents</span>
              <button style={S.addBtn} onClick={() => addToList(setAgents, emptyPerson)}>+ Add Agent</button>
            </div>
            <div style={S.hint}>Field agents respond to dispatched incidents. You can skip this step.</div>
            {agents.map((a, i) => (
              <div key={i} style={S.personCard}>
                <div style={S.personHeader}>
                  <span style={S.personIndex}>Agent {i + 1}</span>
                  {agents.length > 1 && (
                    <button style={S.removeBtn} onClick={() => removeFromList(setAgents, i)}>Remove</button>
                  )}
                </div>
                <div style={S.grid2}>
                  <Field label="Full Name">
                    <input value={a.full_name} onChange={(e) => updateList(setAgents, i, 'full_name', e.target.value)} style={S.input} placeholder="Peter Watson" />
                  </Field>
                  <Field label="Phone">
                    <input value={a.phone} onChange={(e) => updateList(setAgents, i, 'phone', e.target.value)} style={S.input} placeholder="+447700900200" />
                  </Field>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Step 3: Users */}
        {step === 3 && (
          <div>
            <div style={S.sectionHeader}>
              <span>Users</span>
              <button style={S.addBtn} onClick={() => addToList(setUsers, emptyPerson)}>+ Add User</button>
            </div>
            <div style={S.hint}>Regular users who report incidents via the chatbot. You can skip this step.</div>
            {users.map((u, i) => (
              <div key={i} style={S.personCard}>
                <div style={S.personHeader}>
                  <span style={S.personIndex}>User {i + 1}</span>
                  {users.length > 1 && (
                    <button style={S.removeBtn} onClick={() => removeFromList(setUsers, i)}>Remove</button>
                  )}
                </div>
                <div style={S.grid2}>
                  <Field label="Full Name">
                    <input value={u.full_name} onChange={(e) => updateList(setUsers, i, 'full_name', e.target.value)} style={S.input} placeholder="Michael Green" />
                  </Field>
                  <Field label="Phone">
                    <input value={u.phone} onChange={(e) => updateList(setUsers, i, 'phone', e.target.value)} style={S.input} placeholder="+447700900300" />
                  </Field>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Step 4: Connector */}
        {step === 4 && (
          <div style={S.grid2}>
            <Field label="Connector Mode">
              <CustomSelect
                value={connector.mode}
                onChange={(v) => setConnector((p) => ({ ...p, mode: v }))}
                options={[
                  { value: 'none', label: 'Skip for now' },
                  { value: 'servicenow', label: 'ServiceNow' },
                ]}
              />
            </Field>
            <Field label="Display Name">
              <input value={connector.display_name} onChange={(e) => setConnector((p) => ({ ...p, display_name: e.target.value }))} style={S.input} />
            </Field>
            {connector.mode === 'servicenow' && (
              <>
                <Field label="Instance URL">
                  <input value={connector.instance_url} onChange={(e) => setConnector((p) => ({ ...p, instance_url: e.target.value }))} style={S.input} placeholder="https://your-instance.service-now.com" />
                </Field>
                <Field label="Username">
                  <input value={connector.username} onChange={(e) => setConnector((p) => ({ ...p, username: e.target.value }))} style={S.input} />
                </Field>
                <Field label="Password">
                  <input type="password" value={connector.password} onChange={(e) => setConnector((p) => ({ ...p, password: e.target.value }))} style={S.input} />
                </Field>
              </>
            )}
          </div>
        )}

        {/* Step 5: Review & Activate */}
        {step === 5 && (
          <div style={S.summary}>
            <SummaryRow label="Tenant ID" value={tenantId} />
            <SummaryRow label="Company" value={tenant.company_name} />
            <SummaryRow label="Contact" value={tenant.contact_email || tenant.contact_phone || 'Not set'} />
            <SummaryRow label="Company Admins" value={`${admins.filter((a) => a.full_name.trim()).length} admin(s)`} />
            <SummaryRow label="Field Agents" value={`${agents.filter((a) => a.full_name.trim() && a.phone.trim()).length} agent(s)`} />
            <SummaryRow label="Users" value={`${users.filter((u) => u.full_name.trim() && u.phone.trim()).length} user(s)`} />
            <SummaryRow label="Connector" value={connector.mode === 'none' ? 'Skipped' : connector.mode} />
            <SummaryRow label="Status" value="Ready to activate" />
          </div>
        )}
      </div>

      <div style={S.footerActions}>
        <button style={S.secondaryBtn} onClick={back} disabled={step === 0 || loading}>Back</button>
        <button style={S.primaryBtn} onClick={runStep} disabled={loading}>
          {loading ? 'Working...' : step === 5 ? 'Activate Tenant' : 'Continue'}
        </button>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={S.fieldLabel}>{label}</div>
      {children}
    </div>
  );
}

function SummaryRow({ label, value }) {
  return (
    <div style={S.summaryRow}>
      <span style={S.summaryLabel}>{label}</span>
      <span style={S.summaryValue}>{value || '-'}</span>
    </div>
  );
}

const S = {
  page: { minHeight: '100vh', background: '#f3f4f6', padding: '2rem 2.5rem' },
  headerRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap', marginBottom: '1.25rem' },
  backBtn: { border: 'none', background: 'transparent', color: '#475569', fontWeight: 600, cursor: 'pointer', padding: 0, marginBottom: '0.5rem' },
  title: { margin: 0, fontSize: '1.9rem', fontWeight: 800, color: '#0f172a' },
  subtitle: { margin: '0.3rem 0 0', color: '#64748b' },
  stepper: { display: 'grid', gridTemplateColumns: 'repeat(6, minmax(100px, 1fr))', gap: '0.5rem', marginBottom: '1rem' },
  stepNode: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.4rem' },
  stepCircle: { width: 32, height: 32, borderRadius: '50%', background: '#e2e8f0', color: '#475569', display: 'grid', placeItems: 'center', fontSize: '0.8rem', fontWeight: 700 },
  stepCircleActive: { background: '#030304', color: '#fff' },
  stepCircleDone: { background: '#8DE971', color: '#030304' },
  stepLabel: { fontSize: '0.74rem', color: '#64748b', fontWeight: 700, textAlign: 'center' },
  stepLabelActive: { color: '#0f172a' },
  card: { background: '#fff', border: '1px solid #e2e8f0', borderRadius: '0.9rem', padding: '1.25rem', boxShadow: '0 4px 14px -10px rgba(15, 23, 42, 0.25)' },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.9rem 1rem' },
  fieldLabel: { fontSize: '0.78rem', fontWeight: 700, color: '#475569', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' },
  input: { width: '100%', boxSizing: 'border-box', border: '1px solid #cbd5e1', borderRadius: '0.55rem', padding: '0.6rem 0.7rem', fontSize: '0.9rem', color: '#0f172a' },
  checkboxLabel: { display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.88rem', color: '#334155', fontWeight: 600 },
  hint: { marginTop: '0.3rem', fontSize: '0.74rem', color: '#64748b', marginBottom: '0.5rem' },
  infoBox: { gridColumn: '1 / -1', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '0.55rem', padding: '0.7rem 0.8rem', color: '#1e3a8a', fontSize: '0.84rem', fontWeight: 600 },
  sectionHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', fontSize: '1rem', fontWeight: 700, color: '#0f172a' },
  addBtn: { border: '1px solid #cbd5e1', background: '#fff', color: '#030304', borderRadius: '0.5rem', padding: '0.4rem 0.75rem', fontSize: '0.82rem', fontWeight: 700, cursor: 'pointer' },
  removeBtn: { border: 'none', background: 'transparent', color: '#b91c1c', fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer' },
  personCard: { background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '0.75rem', padding: '1rem', marginBottom: '0.75rem' },
  personHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' },
  personIndex: { fontSize: '0.82rem', fontWeight: 700, color: '#475569' },
  summary: { display: 'grid', gap: '0.6rem' },
  summaryRow: { display: 'flex', justifyContent: 'space-between', gap: '1rem', borderBottom: '1px dashed #e2e8f0', paddingBottom: '0.45rem' },
  summaryLabel: { color: '#64748b', fontSize: '0.82rem', fontWeight: 700 },
  summaryValue: { color: '#0f172a', fontSize: '0.86rem', fontWeight: 700 },
  footerActions: { display: 'flex', justifyContent: 'space-between', marginTop: '1rem' },
  secondaryBtn: { border: '1px solid #cbd5e1', background: '#fff', color: '#334155', borderRadius: '0.55rem', padding: '0.6rem 1rem', fontWeight: 700, cursor: 'pointer' },
  primaryBtn: { border: 'none', background: '#8DE971', color: '#030304', borderRadius: '0.55rem', padding: '0.6rem 1rem', fontWeight: 700, cursor: 'pointer' },
  error: { border: '1px solid #fecaca', background: '#fef2f2', color: '#991b1b', borderRadius: '0.55rem', padding: '0.55rem 0.7rem', marginBottom: '0.75rem', fontSize: '0.84rem', fontWeight: 600 },
  success: { border: '1px solid #bbf7d0', background: '#f0fdf4', color: '#166534', borderRadius: '0.55rem', padding: '0.55rem 0.7rem', marginBottom: '0.75rem', fontSize: '0.84rem', fontWeight: 600 },
};
