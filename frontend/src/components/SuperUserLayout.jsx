import  {useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const SIDEBAR_EXPANDED = 240;
const SIDEBAR_COLLAPSED = 64;

const SuperUserLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const sidebarWidth = collapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED;

  const menuItems = [
    {
      label: 'Dashboard',
      path: '/super',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
        </svg>
      ),
    },
    {
      label: 'Workflows',
      path: '/super/workflows',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      ),
    },
    {
      label: 'Knowledge Base',
      path: '/super/kb',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
      ),
    },
    {
      label: 'Tenants',
      path: '/super/tenants',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      ),
    },
    {
      label: 'Onboarding',
      path: '/super/tenants/onboard',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 6h18" /><path d="M7 12h10" /><path d="M10 18h4" />
        </svg>
      ),
    },
    {
      label: 'Connectors',
      path: '/super/connectors',
      icon: (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2v6m0 8v6M4.93 4.93l4.24 4.24m5.66 5.66l4.24 4.24M2 12h6m8 0h6M4.93 19.07l4.24-4.24m5.66-5.66l4.24-4.24" />
        </svg>
      ),
    },
  ];

  const isActive = (path) => {
    if (path === '/super') return location.pathname === '/super';
    if (path === '/super/tenants/onboard') {
      return location.pathname.startsWith('/super/tenants/onboard');
    }
    if (path === '/super/tenants') {
      return (
        location.pathname === '/super/tenants' ||
        (location.pathname.startsWith('/super/tenants/') &&
          !location.pathname.startsWith('/super/tenants/onboard'))
      );
    }
    return location.pathname.startsWith(path);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div style={styles.layout}>
      {/* Sidebar */}
      <aside style={{
        ...styles.sidebar,
        width: sidebarWidth,
        minWidth: sidebarWidth,
      }}>
        {/* Brand + Collapse toggle */}
        <div style={{ ...styles.brand, justifyContent: collapsed ? 'center' : 'flex-start' }}>
          {!collapsed && (
            <div style={styles.brandIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
          )}
          {!collapsed && (
            <div style={{ flex: 1 }}>
              <div style={styles.brandTitle}>Incident Handler</div>
              <div style={styles.brandSubtitle}>Super Admin</div>
            </div>
          )}
          <button
            onClick={() => setCollapsed((prev) => !prev)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 32, height: 32, borderRadius: '0.5rem', border: 'none',
              backgroundColor: 'transparent', cursor: 'pointer',
              color: '#94a3b8', transition: 'all 0.15s',
              position: collapsed ? 'static' : 'absolute', right: collapsed ? undefined : '10px',
              flexShrink: 0,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = '#fff'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; e.currentTarget.style.color = '#94a3b8'; }}
          >
            <img
              src="https://assets.streamlinehq.com/image/private/w_300,h_300,ar_1/f_auto/v1/icons/4/sidebar-collapse-wa8mq2uy2zwwo4sv7h6j8.png/sidebar-collapse-2w3re62ix0sjmbcj645cho.png?_a=DATAiZiuZAA0"
              alt={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
              style={{ width: 20, height: 20, display: 'block', filter: 'brightness(0) invert(1)' }}
            />
          </button>
        </div>

        {/* Navigation */}
        <nav style={styles.nav}>
          {menuItems.map((item) => {
            const active = isActive(item.path);
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                title={collapsed ? item.label : undefined}
                style={{
                  ...styles.navItem,
                  ...(active ? styles.navItemActive : {}),
                  justifyContent: collapsed ? 'center' : 'flex-start',
                  padding: collapsed ? '0.7rem 0' : '0.7rem 0.875rem',
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.08)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }
                }}
              >
                <span style={{ ...styles.navIcon, color: active ? '#fff' : '#94a3b8' }}>
                  {item.icon}
                </span>
                {!collapsed && (
                  <span style={{ ...styles.navLabel, color: active ? '#fff' : '#cbd5e1' }}>
                    {item.label}
                  </span>
                )}
                {active && <span style={styles.activeIndicator} />}
              </button>
            );
          })}
        </nav>

        {/* User section at bottom */}
        <div style={{ ...styles.userSection, justifyContent: collapsed ? 'center' : 'space-between', padding: collapsed ? '1rem 0.5rem' : '1rem' }}>
          {collapsed ? (
            <div style={styles.avatar}>
              {user?.full_name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'SU'}
            </div>
          ) : (
            <>
              <div style={styles.userInfo}>
                <div style={styles.avatar}>
                  {user?.full_name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'SU'}
                </div>
                <div style={styles.userDetails}>
                  <div style={styles.userName}>{user?.full_name || 'Super User'}</div>
                  <div style={styles.userRole}>{user?.role || 'super_user'}</div>
                </div>
              </div>
              <button
                onClick={handleLogout}
                style={styles.logoutButton}
                onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = 'rgba(239,68,68,0.15)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main style={{ ...styles.main, marginLeft: sidebarWidth, transition: 'margin-left 0.2s ease' }}>
        <Outlet />
      </main>
    </div>
  );
};

const styles = {
  layout: {
    display: 'flex',
    minHeight: '100vh',
  },
  sidebar: {
    backgroundColor: '#0f172a',
    display: 'flex',
    flexDirection: 'column',
    position: 'fixed',
    top: 0,
    left: 0,
    bottom: 0,
    zIndex: 100,
    overflowY: 'auto',
    overflowX: 'hidden',
    transition: 'width 0.2s ease, min-width 0.2s ease',
  },
  brand: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '1.25rem 0.75rem 1.5rem',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    position: 'relative',
  },
  brandIcon: {
    width: 40,
    height: 40,
    borderRadius: '0.625rem',
    background: 'linear-gradient(135deg, #8DE971 0%, #7AC75E 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  brandTitle: {
    fontSize: '0.95rem',
    fontWeight: 700,
    color: '#f1f5f9',
    lineHeight: 1.2,
  },
  brandSubtitle: {
    fontSize: '0.7rem',
    fontWeight: 600,
    color: '#8DE971',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  nav: {
    flex: 1,
    padding: '1rem 0.75rem',
    display: 'flex',
    flexDirection: 'column',
    gap: '0.25rem',
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.75rem',
    padding: '0.7rem 0.875rem',
    borderRadius: '0.5rem',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    position: 'relative',
    width: '100%',
    textAlign: 'left',
  },
  navItemActive: {
    backgroundColor: 'rgba(102, 126, 234, 0.18)',
  },
  navIcon: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  navLabel: {
    fontSize: '0.875rem',
    fontWeight: 600,
  },
  activeIndicator: {
    position: 'absolute',
    left: 0,
    top: '50%',
    transform: 'translateY(-50%)',
    width: 3,
    height: 20,
    borderRadius: '0 3px 3px 0',
    background: 'linear-gradient(180deg, #8DE971, #7AC75E)',
  },
  userSection: {
    borderTop: '1px solid rgba(255,255,255,0.08)',
    padding: '1rem 1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '0.5rem',
  },
  userInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '0.625rem',
    minWidth: 0,
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: '50%',
    background: 'linear-gradient(135deg, #8DE971, #7AC75E)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: 'white',
    fontSize: '0.7rem',
    fontWeight: 700,
    flexShrink: 0,
  },
  userDetails: {
    minWidth: 0,
  },
  userName: {
    fontSize: '0.8rem',
    fontWeight: 600,
    color: '#e2e8f0',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  userRole: {
    fontSize: '0.65rem',
    color: '#64748b',
    fontWeight: 500,
  },
  logoutButton: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 34,
    height: 34,
    borderRadius: '0.5rem',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    transition: 'background-color 0.15s',
    flexShrink: 0,
  },
  main: {
    flex: 1,
    minHeight: '100vh',
    backgroundColor: '#f3f4f6',
    position: 'relative',
  },
};

export default SuperUserLayout;
