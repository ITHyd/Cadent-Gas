import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import SuperUserLayout from './components/SuperUserLayout';

const ROLE_HOME = {
  user: '/dashboard',
  company: '/dashboard',
  agent: '/agent/dashboard',
  super_user: '/super',
  admin: '/super',
};

const RoleRedirect = () => {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Navigate to={ROLE_HOME[user?.role] || '/dashboard'} replace />;
};
import LoginPage from './pages/LoginPage';
import IncidentReport from './pages/IncidentReport';
import AgentChat from './pages/AgentChat';
import ProfessionalDashboard from './pages/ProfessionalDashboard';
import MyReports from './pages/MyReports';
import IncidentDetail from './pages/IncidentDetail';
import AdminDashboard from './pages/AdminDashboard';
import SuperUserDashboard from './pages/SuperUserDashboard';
import WorkflowManagement from './pages/WorkflowManagement';
import FieldAgentDashboard from './pages/FieldAgentDashboard';
import AgentIncidentWorkspace from './pages/AgentIncidentWorkspace';
import KnowledgeBase from './pages/KnowledgeBase';
import TenantManagement from './pages/TenantManagement';
import ConnectorStatus from './pages/ConnectorStatus';
import ClientOnboarding from './pages/ClientOnboarding';
import ConnectorSetup from './pages/ConnectorSetup';
import TenantMappingEditor from './pages/TenantMappingEditor';

function App() {
  return (
    <Router>
        <AuthProvider>
          <div style={{ margin: 0, padding: 0, minHeight: '100vh', overflow: 'auto' }}>
            <Routes>
            {/* Public */}
            <Route path="/login" element={<LoginPage />} />
            <Route path="/admin-login" element={<Navigate to="/login" replace />} />

            {/* User Routes */}
            <Route path="/" element={<RoleRedirect />} />
            <Route path="/dashboard" element={
              <ProtectedRoute allowedRoles={['user', 'company']}>
                <ProfessionalDashboard />
              </ProtectedRoute>
            } />
            <Route path="/my-reports" element={
              <ProtectedRoute allowedRoles={['user', 'company']}>
                <MyReports />
              </ProtectedRoute>
            } />
            <Route path="/my-reports/:incidentId" element={
              <ProtectedRoute allowedRoles={['user', 'company']}>
                <IncidentDetail />
              </ProtectedRoute>
            } />
            <Route path="/report" element={
              <ProtectedRoute allowedRoles={['user']}>
                <IncidentReport />
              </ProtectedRoute>
            } />
            <Route path="/chat/:incidentId" element={
              <ProtectedRoute allowedRoles={['user']}>
                <AgentChat />
              </ProtectedRoute>
            } />

            {/* Field Agent Routes */}
            <Route path="/agent/dashboard" element={
              <ProtectedRoute allowedRoles={['agent']}>
                <FieldAgentDashboard />
              </ProtectedRoute>
            } />
            <Route path="/agent/incidents/:incidentId" element={
              <ProtectedRoute allowedRoles={['agent']}>
                <AgentIncidentWorkspace />
              </ProtectedRoute>
            } />

            {/* Company Admin Routes */}
            <Route path="/company" element={
              <ProtectedRoute allowedRoles={['company', 'super_user', 'admin']}>
                <AdminDashboard />
              </ProtectedRoute>
            } />
            {/* Super User Routes — wrapped in sidebar layout */}
            <Route element={
              <ProtectedRoute allowedRoles={['super_user', 'admin']}>
                <SuperUserLayout />
              </ProtectedRoute>
            }>
              <Route path="/super" element={<SuperUserDashboard />} />
              <Route path="/super/workflows" element={<WorkflowManagement />} />
              <Route path="/super/workflows/:workflowName" element={<WorkflowManagement />} />
              <Route path="/super/kb" element={<KnowledgeBase />} />
              <Route path="/super/tenants" element={<TenantManagement />} />
              <Route path="/super/tenants/onboard" element={<ClientOnboarding />} />
              <Route path="/super/tenants/:tenantId/mappings" element={<TenantMappingEditor />} />
              <Route path="/super/connectors" element={<ConnectorStatus />} />
              <Route path="/super/connectors/setup" element={<ConnectorSetup />} />
            </Route>

            {/* Catch-all: unknown routes → role-based home */}
            <Route path="*" element={<RoleRedirect />} />
            </Routes>
          </div>
        </AuthProvider>
    </Router>
  );
}

export default App;
