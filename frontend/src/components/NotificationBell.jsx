import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { getUserNotifications, markNotificationRead, markAllNotificationsRead } from '../services/api';

const NOTIF_TYPE_STYLES = {
  info: { bg: '#edf5fc', border: '#b4ccdf', color: '#030304', icon: 'ℹ️' },
  warning: { bg: '#fff7ed', border: '#fed7aa', color: '#b45309', icon: '⚠️' },
  success: { bg: '#ecfdf5', border: '#a7f3d0', color: '#047857', icon: '✓' },
  critical: { bg: '#fef2f2', border: '#fecaca', color: '#b91c1c', icon: '🚨' },
  assignment: { bg: '#ede9fe', border: '#c4b5fd', color: '#5b21b6', icon: '📋' },
};

const NotificationBell = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loginToast, setLoginToast] = useState(null);
  const containerRef = useRef(null);
  const hasShownToast = useRef(false);

  const userId = user?.user_id;

  const fetchNotifications = useCallback(async () => {
    if (!userId) return;
    try {
      const data = await getUserNotifications(userId);
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
      return data;
    } catch {
      return null;
    }
  }, [userId]);

  // Fetch on mount and poll every 15s
  useEffect(() => {
    fetchNotifications().then((data) => {
      // Show login toast once on first mount
      if (data && !hasShownToast.current) {
        hasShownToast.current = true;
        const count = data.unread_count || 0;
        if (count > 0) {
          setLoginToast(`You have ${count} unread notification${count !== 1 ? 's' : ''}`);
          setTimeout(() => setLoginToast(null), 5000);
        }
      }
    });
    const timer = setInterval(fetchNotifications, 15000);
    return () => clearInterval(timer);
  }, [fetchNotifications]);

  // Close on click outside
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleOpen = () => {
    setOpen((prev) => !prev);
    if (!open) fetchNotifications();
  };

  const handleMarkRead = async (notifId) => {
    try {
      await markNotificationRead(userId, notifId);
      setNotifications((prev) =>
        prev.map((n) => (n.notification_id === notifId ? { ...n, read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      return;
    }
  };

  const handleMarkAllRead = async () => {
    try {
      setLoading(true);
      await markAllNotificationsRead(userId);
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch {
      return;
    } finally {
      setLoading(false);
    }
  };

  const handleNotifClick = (notif) => {
    if (!notif.read) handleMarkRead(notif.notification_id);
    if (notif.link) {
      navigate(notif.link);
      setOpen(false);
    }
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

  if (!user) return null;

  return (
    <div ref={containerRef} style={styles.container}>
      <button onClick={handleOpen} style={styles.bellBtn} title="Notifications">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#030304" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span style={styles.badge}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div style={styles.dropdown}>
          <div style={styles.dropdownHeader}>
            <span style={styles.dropdownTitle}>Notifications</span>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                disabled={loading}
                style={styles.markAllBtn}
              >
                {loading ? '...' : 'Mark all read'}
              </button>
            )}
          </div>

          <div style={styles.notifList}>
            {notifications.length === 0 ? (
              <div style={styles.emptyState}>
                <span style={{ fontSize: '1.5rem', marginBottom: '6px' }}>🔔</span>
                <span style={{ fontSize: '0.85rem', color: '#7f93aa' }}>No notifications yet</span>
              </div>
            ) : (
              notifications.slice(0, 20).map((notif) => {
                const typeMeta = NOTIF_TYPE_STYLES[notif.type] || NOTIF_TYPE_STYLES.info;
                return (
                  <div
                    key={notif.notification_id}
                    onClick={() => handleNotifClick(notif)}
                    style={{
                      ...styles.notifItem,
                      background: notif.read ? '#fff' : typeMeta.bg,
                      borderLeft: `3px solid ${notif.read ? '#e2e8f0' : typeMeta.color}`,
                      cursor: notif.link ? 'pointer' : 'default',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: 1, minWidth: 0 }}>
                        <span style={{ fontSize: '0.85rem', flexShrink: 0 }}>{typeMeta.icon}</span>
                        <span style={{
                          fontSize: '0.82rem',
                          fontWeight: notif.read ? 600 : 700,
                          color: notif.read ? '#4d6178' : '#0f1f33',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {notif.title}
                        </span>
                      </div>
                      <span style={{ fontSize: '0.68rem', color: '#7f93aa', whiteSpace: 'nowrap', flexShrink: 0 }}>
                        {formatTimeAgo(notif.created_at)}
                      </span>
                    </div>
                    <p style={{
                      margin: '3px 0 0',
                      fontSize: '0.78rem',
                      color: notif.read ? '#7f93aa' : '#4d6178',
                      lineHeight: 1.4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                    }}>
                      {notif.message}
                    </p>
                    {!notif.read && (
                      <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: typeMeta.color, position: 'absolute', top: '10px', right: '10px' }} />
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Login toast popup */}
      {loginToast && (
        <div
          style={{
            position: 'fixed',
            top: 68,
            right: 16,
            background: '#fff',
            border: '1px solid #d7e0ea',
            borderRadius: '14px',
            boxShadow: '0 12px 30px -10px rgba(15,31,51,0.25)',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            zIndex: 9999,
            animation: 'notifToastIn 0.3s ease-out',
            maxWidth: '320px',
          }}
          onClick={() => { setLoginToast(null); setOpen(true); }}
          role="button"
          tabIndex={0}
        >
          <div style={{
            width: '36px', height: '36px', borderRadius: '10px',
            background: '#030304',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
              <path d="M13.73 21a2 2 0 0 1-3.46 0" />
            </svg>
          </div>
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#0f1f33', marginBottom: '2px' }}>
              Welcome back!
            </div>
            <div style={{ fontSize: '0.78rem', color: '#4d6178' }}>{loginToast}</div>
          </div>
          <button
            onClick={(e) => { e.stopPropagation(); setLoginToast(null); }}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: '#94a3b8', fontSize: '1rem', padding: '4px', marginLeft: 'auto',
            }}
          >
            &times;
          </button>
        </div>
      )}

      <style>{`
        @keyframes notifToastIn {
          from { opacity: 0; transform: translateY(-12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};

const styles = {
  container: {
    position: 'fixed',
    top: 16,
    right: 64,
    zIndex: 9998,
  },
  bellBtn: {
    width: 40,
    height: 40,
    borderRadius: '50%',
    border: '1px solid #d7e0ea',
    background: '#fff',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
    transition: 'all 0.2s',
    position: 'relative',
  },
  badge: {
    position: 'absolute',
    top: -4,
    right: -4,
    minWidth: '18px',
    height: '18px',
    borderRadius: '999px',
    background: '#ef4444',
    color: '#fff',
    fontSize: '0.65rem',
    fontWeight: 800,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 4px',
    border: '2px solid #fff',
    lineHeight: 1,
  },
  dropdown: {
    position: 'absolute',
    top: 'calc(100% + 8px)',
    right: 0,
    width: 340,
    backgroundColor: '#ffffff',
    borderRadius: '16px',
    border: '1px solid #e2e8f0',
    boxShadow: '0 16px 40px -12px rgba(15,31,51,0.3)',
    overflow: 'hidden',
    maxHeight: '480px',
    display: 'flex',
    flexDirection: 'column',
  },
  dropdownHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 16px',
    borderBottom: '1px solid #f1f5f9',
  },
  dropdownTitle: {
    fontSize: '0.92rem',
    fontWeight: 700,
    color: '#0f1f33',
  },
  markAllBtn: {
    background: 'none',
    border: 'none',
    color: '#030304',
    fontSize: '0.78rem',
    fontWeight: 600,
    cursor: 'pointer',
    padding: '4px 8px',
    borderRadius: '6px',
    transition: 'background 0.15s',
  },
  notifList: {
    overflowY: 'auto',
    flex: 1,
  },
  notifItem: {
    padding: '10px 14px',
    borderBottom: '1px solid #f1f5f9',
    transition: 'background 0.15s',
    position: 'relative',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '32px 16px',
  },
};

export default NotificationBell;
