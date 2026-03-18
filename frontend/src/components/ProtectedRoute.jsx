import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const ROLE_REDIRECTS = {
  user: '/dashboard',
  agent: '/agent/dashboard',
  company: '/company',
  super_user: '/super',
  admin: '/super',
};

const ProtectedRoute = ({ children, allowedRoles = [] }) => {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (isLoading) {
    return (
      <div style={{
        height: '100vh', display: 'flex', alignItems: 'center',
        justifyContent: 'center', background: '#f0f4f8',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            width: '40px', height: '40px', border: '3px solid #e5e7eb',
            borderTopColor: '#2563eb', borderRadius: '50%',
            animation: 'spin 0.8s linear infinite', margin: '0 auto 1rem',
          }} />
          <p style={{ color: '#6b7280' }}>Loading...</p>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles.length > 0 && !allowedRoles.includes(user?.role)) {
    return <Navigate to={ROLE_REDIRECTS[user?.role] || '/dashboard'} replace />;
  }

  return children;
};

export default ProtectedRoute;
