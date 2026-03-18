import { useState } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { sendOTP, verifyOTP, adminLogin } from '../services/api';
import OTPDisplay from '../components/OTPDisplay';

const ROLE_REDIRECTS = {
  user: '/dashboard',
  agent: '/agent/dashboard',
  company: '/company',
  super_user: '/super',
  admin: '/super',
};

const LoginPage = () => {
  // Tab: 'otp' or 'password'
  const [mode, setMode] = useState('otp');

  // OTP state
  const [step, setStep] = useState('phone');
  const [phone, setPhone] = useState('+44');
  const [otp, setOtp] = useState('');
  const [devOtp, setDevOtp] = useState(null);

  // Password state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // Shared state
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { login, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();

  // Redirect if already logged in — company users go to /dashboard (report on behalf)
  if (isAuthenticated && user) {
    const dest = user.role === 'company' ? '/dashboard' : (ROLE_REDIRECTS[user.role] || '/dashboard');
    return <Navigate to={dest} replace />;
  }

  const switchMode = (newMode) => {
    setMode(newMode);
    setError('');
    setStep('phone');
    setOtp('');
    setDevOtp(null);
  };

  /* ── OTP handlers ─────────────────────────────────────────────────── */

  const handleSendOTP = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await sendOTP(phone);
      setDevOtp(data.otp);
      setStep('otp');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOTP = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await verifyOTP(phone, otp);
      login(data);
      // Company users logging in via OTP go to user dashboard to report incidents
      const redirect = data.user.role === 'company' ? '/dashboard' : ROLE_REDIRECTS[data.user.role];
      navigate(redirect || '/dashboard');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /* ── Password handler ─────────────────────────────────────────────── */

  const handlePasswordLogin = async (event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await adminLogin(username, password);
      login(data);
      navigate(ROLE_REDIRECTS[data.user.role] || '/dashboard');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const canSendOtp = phone.trim().length >= 13;
  const canSubmitPassword = username.trim().length > 0 && password.length > 0;

  /* ── Left panel text adapts to mode ───────────────────────────────── */

  const leftPanelConfig = mode === 'otp'
    ? {
        gradient: 'linear-gradient(145deg, #030304 0%, #0d0d1a 52%, #0d0d1a 100%)',
        eyebrow: 'Secure Access',
        title: 'Gas Incident Intelligence Platform',
        desc: 'Sign in with your phone number to report incidents, monitor live updates, and coordinate response operations.',
        bullets: [
          'Role-aware routing for users, engineers, and administrators',
          'One-time password validation with tenant-linked access',
          'Session-protected workflows for incident lifecycle tracking',
        ],
        dotColor: '#8DE971',
      }
    : {
        gradient: 'linear-gradient(145deg, #1e1b4b 0%, #312e81 52%, #4338ca 100%)',
        eyebrow: 'Administrator Portal',
        title: 'Gas Incident Management Console',
        desc: 'Sign in with your credentials to manage operations, dispatch teams, and configure platform settings.',
        bullets: [
          'Manage incidents, agents, and tenant configurations',
          'Monitor real-time operations and dispatch field teams',
          'Configure workflows, knowledge base, and system settings',
        ],
        dotColor: '#a5b4fc',
      };

  /* ── Render ───────────────────────────────────────────────────────── */

  const formTitle =
    mode === 'password'
      ? 'Admin Sign In'
      : step === 'phone'
        ? 'Sign In'
        : 'Verify OTP';

  const formSubtitle =
    mode === 'password'
      ? 'Enter your username and password to continue.'
      : step === 'phone'
        ? 'Enter your registered phone number to continue.'
        : `Enter the 6-digit code sent to ${phone}.`;

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: '24px',
        background:
          'radial-gradient(circle at 0% 0%, rgba(3,3,4,0.18), transparent 40%), radial-gradient(circle at 100% 100%, rgba(141,233,113,0.15), transparent 42%), linear-gradient(165deg, #f6fbff 0%, #edf4fb 52%, #eaf2f9 100%)',
      }}
    >
      <div
        className="auth-layout"
        style={{
          width: '100%',
          maxWidth: '980px',
          borderRadius: '24px',
          border: '1px solid #d7e3ee',
          boxShadow: '0 30px 60px -35px rgba(15,31,51,0.7)',
          background: '#ffffff',
          overflow: 'hidden',
          display: 'grid',
          gridTemplateColumns: '1.1fr 1fr',
        }}
      >
        {/* ── Left panel ──────────────────────────────────────── */}
        <section
          style={{
            padding: '36px 34px',
            background: leftPanelConfig.gradient,
            color: '#ffffff',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            minHeight: '560px',
            transition: 'background 0.4s ease',
          }}
        >
          <div>
            <div
              style={{
                width: '50px',
                height: '50px',
                borderRadius: '14px',
                border: '1px solid rgba(255,255,255,0.24)',
                background: 'rgba(255,255,255,0.12)',
                display: 'grid',
                placeItems: 'center',
                fontSize: '1rem',
                fontWeight: 800,
                marginBottom: '18px',
              }}
            >
              GI
            </div>

            <p
              style={{
                margin: 0,
                fontSize: '0.72rem',
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                color: 'rgba(232,242,252,0.86)',
                fontWeight: 700,
              }}
            >
              {leftPanelConfig.eyebrow}
            </p>

            <h1
              style={{
                margin: '12px 0 10px',
                fontFamily: 'Playfair Display, Times New Roman, serif',
                lineHeight: 1.12,
                letterSpacing: '-0.03em',
                fontSize: '2.05rem',
                color: '#fff',
              }}
            >
              {leftPanelConfig.title}
            </h1>

            <p
              style={{
                margin: 0,
                color: 'rgba(233, 244, 255, 0.88)',
                fontSize: '0.96rem',
                maxWidth: '32ch',
                lineHeight: 1.6,
              }}
            >
              {leftPanelConfig.desc}
            </p>
          </div>

          <div style={{ marginTop: '26px', display: 'grid', gap: '10px' }}>
            {leftPanelConfig.bullets.map((item) => (
              <div
                key={item}
                style={{
                  display: 'flex',
                  gap: '10px',
                  alignItems: 'flex-start',
                  color: 'rgba(238,246,255,0.92)',
                  fontSize: '0.86rem',
                }}
              >
                <span
                  style={{
                    marginTop: '2px',
                    width: '7px',
                    height: '7px',
                    borderRadius: '999px',
                    background: leftPanelConfig.dotColor,
                    flexShrink: 0,
                  }}
                />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ── Right panel ─────────────────────────────────────── */}
        <section style={{ padding: '34px 32px', background: '#FAF8F9' }}>
          {/* Tab switcher */}
          <div
            style={{
              display: 'flex',
              borderRadius: '12px',
              background: '#F6F2F4',
              padding: '3px',
              marginBottom: '22px',
            }}
          >
            <button
              onClick={() => switchMode('otp')}
              style={{
                flex: 1,
                padding: '9px 14px',
                borderRadius: '10px',
                border: 'none',
                fontSize: '0.86rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                background: mode === 'otp' ? '#fff' : 'transparent',
                color: mode === 'otp' ? '#030304' : '#5c738c',
                boxShadow: mode === 'otp' ? '0 2px 8px -2px rgba(0,0,0,0.12)' : 'none',
              }}
            >
              Phone + OTP
            </button>
            <button
              onClick={() => switchMode('password')}
              style={{
                flex: 1,
                padding: '9px 14px',
                borderRadius: '10px',
                border: 'none',
                fontSize: '0.86rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                background: mode === 'password' ? '#fff' : 'transparent',
                color: mode === 'password' ? '#312e81' : '#5c738c',
                boxShadow: mode === 'password' ? '0 2px 8px -2px rgba(0,0,0,0.12)' : 'none',
              }}
            >
              Admin Login
            </button>
          </div>

          <h2
            style={{
              margin: 0,
              fontFamily: 'Playfair Display, Times New Roman, serif',
              fontSize: '1.5rem',
              color: '#11263c',
              letterSpacing: '-0.02em',
            }}
          >
            {formTitle}
          </h2>
          <p style={{ margin: '6px 0 20px', color: '#5c738c', fontSize: '0.92rem' }}>
            {formSubtitle}
          </p>

          {error && (
            <div
              style={{
                border: '1px solid #fecaca',
                background: '#fef2f2',
                color: '#b91c1c',
                borderRadius: '12px',
                padding: '10px 12px',
                fontSize: '0.86rem',
                marginBottom: '14px',
                fontWeight: 600,
              }}
            >
              {error}
            </div>
          )}

          {/* ── OTP Mode ────────────────────────────────────── */}
          {mode === 'otp' && step === 'phone' && (
            <form onSubmit={handleSendOTP}>
              <label htmlFor="phone" className="label-text">
                Phone Number
              </label>
              <input
                id="phone"
                type="tel"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="+447700900101"
                className="input-control"
                required
              />

              <button
                type="submit"
                disabled={loading || !canSendOtp}
                className="primary-btn"
                style={{
                  width: '100%',
                  marginTop: '16px',
                  opacity: loading || !canSendOtp ? 0.6 : 1,
                  cursor: loading || !canSendOtp ? 'not-allowed' : 'pointer',
                }}
              >
                {loading ? 'Sending OTP...' : 'Send OTP'}
              </button>

            </form>
          )}

          {mode === 'otp' && step === 'otp' && (
            <form onSubmit={handleVerifyOTP}>
              <label htmlFor="otp" className="label-text">
                Verification Code
              </label>
              <input
                id="otp"
                type="text"
                value={otp}
                onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                maxLength={6}
                autoFocus
                required
                className="input-control"
                style={{
                  fontSize: '1.75rem',
                  letterSpacing: '0.52rem',
                  textAlign: 'center',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                }}
              />

              <button
                type="submit"
                disabled={loading || otp.length !== 6}
                className="primary-btn"
                style={{
                  width: '100%',
                  marginTop: '16px',
                  opacity: loading || otp.length !== 6 ? 0.6 : 1,
                  cursor: loading || otp.length !== 6 ? 'not-allowed' : 'pointer',
                }}
              >
                {loading ? 'Verifying...' : 'Verify and Sign In'}
              </button>

              <button
                type="button"
                onClick={() => {
                  setStep('phone');
                  setOtp('');
                  setDevOtp(null);
                  setError('');
                }}
                className="secondary-btn"
                style={{ width: '100%', marginTop: '10px' }}
              >
                Use Different Phone Number
              </button>
            </form>
          )}

          {/* ── Password Mode ───────────────────────────────── */}
          {mode === 'password' && (
            <form onSubmit={handlePasswordLogin}>
              <label htmlFor="username" className="label-text">
                Username
              </label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                className="input-control"
                autoComplete="username"
                required
              />

              <label htmlFor="password" className="label-text" style={{ marginTop: '12px', display: 'block' }}>
                Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  className="input-control"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    border: 'none',
                    background: 'none',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    color: '#5c738c',
                    fontWeight: 600,
                    padding: '4px 6px',
                  }}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>

              <button
                type="submit"
                disabled={loading || !canSubmitPassword}
                className="primary-btn"
                style={{
                  width: '100%',
                  marginTop: '20px',
                  opacity: loading || !canSubmitPassword ? 0.6 : 1,
                  cursor: loading || !canSubmitPassword ? 'not-allowed' : 'pointer',
                }}
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>

            </form>
          )}
        </section>
      </div>

      {devOtp && <OTPDisplay otp={devOtp} phone={phone} />}

      <style>{`
        @media (max-width: 920px) {
          .auth-layout {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </div>
  );
};

export default LoginPage;
