import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const ProfileDropdown = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  if (!user) return null;

  const initials = (user.full_name || '')
    .split(' ')
    .map((n) => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase() || '?';

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const getRoleLabel = (role) => ({
    user: 'User',
    agent: 'Field Agent',
    company: 'Company Admin',
    super_user: 'Super User',
    admin: 'Administrator',
  }[role] || role);

  const getRoleColor = (role) => ({
    user: '#3b82f6',
    agent: '#8b5cf6',
    company: '#f59e0b',
    super_user: '#ef4444',
    admin: '#ef4444',
  }[role] || '#6b7280');

  return (
    <div ref={containerRef} style={styles.container}>
      {/* Avatar button */}
      <button
        onClick={() => setOpen((prev) => !prev)}
        style={styles.avatar}
        onMouseEnter={(e) => { e.currentTarget.style.boxShadow = '0 0 0 3px rgba(141,233,113,0.35)'; }}
        onMouseLeave={(e) => { e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.12)'; }}
      >
        {initials}
      </button>

      {/* Dropdown */}
      {open && (
        <div style={styles.dropdown}>
          {/* Header */}
          <div style={styles.header}>
            <div style={styles.largeAvatar}>{initials}</div>
            <div style={{ minWidth: 0 }}>
              <div style={styles.name}>{user.full_name || 'Unknown User'}</div>
            </div>
          </div>

          <div style={styles.divider} />

          {/* Info rows */}
          <div style={styles.infoSection}>
            {!['admin', 'super_user', 'company'].includes(user.role) && (
              <div style={styles.infoRow}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
                </svg>
                <span style={styles.infoValue}>{user.phone || 'N/A'}</span>
              </div>
            )}
            <div style={styles.infoRow}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
              </svg>
              <span style={styles.infoValue}>{user.tenant_id || 'N/A'}</span>
            </div>
          </div>

          <div style={styles.divider} />

          {/* Logout */}
          <button
            onClick={handleLogout}
            style={styles.logoutBtn}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = '#fef2f2'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>Sign Out</span>
          </button>
        </div>
      )}
    </div>
  );
};

const styles = {
  container: {
    position: 'fixed',
    top: 16,
    right: 16,
    zIndex: 9999,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: '50%',
    border: 'none',
    background: 'linear-gradient(135deg, #8DE971, #7AC75E)',
    color: 'white',
    fontSize: '0.8rem',
    fontWeight: 700,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
    transition: 'box-shadow 0.2s',
  },
  dropdown: {
    position: 'absolute',
    top: 'calc(100% + 8px)',
    right: 0,
    width: 260,
    backgroundColor: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 12px 30px -10px rgba(15,31,51,0.25)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '16px 16px 12px',
  },
  largeAvatar: {
    width: 44,
    height: 44,
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #8DE971, #7AC75E)',
    color: 'white',
    fontSize: '0.9rem',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  name: {
    fontSize: '0.95rem',
    fontWeight: 700,
    color: '#030304',
    marginBottom: 4,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  roleBadge: {
    fontSize: '0.68rem',
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: '6px',
    display: 'inline-block',
  },
  divider: {
    height: 1,
    backgroundColor: '#f1f5f9',
    margin: '0 12px',
  },
  infoSection: {
    padding: '10px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  infoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  infoValue: {
    fontSize: '0.82rem',
    color: 'rgba(3,3,4,0.7)',
    fontWeight: 500,
  },
  logoutBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    width: '100%',
    padding: '12px 16px',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    fontSize: '0.85rem',
    fontWeight: 600,
    color: '#ef4444',
    transition: 'background-color 0.15s',
  },
};

export default ProfileDropdown;
