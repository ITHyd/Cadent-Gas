/**
 * ProfessionalDashboard — main app landing page for authenticated users.
 *
 * Composes HeroSection + FloatingChatWidget with default (non-portal) branding.
 * Same components are reused by the portal with tenant-specific colors.
 */
import { useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import ProfileDropdown from "../components/ProfileDropdown";
import NotificationBell from "../components/NotificationBell";
import HeroSection from "../components/HeroSection";
import FloatingChatWidget from "../components/FloatingChatWidget";

const ProfessionalDashboard = () => {
  const { user } = useAuth();
  const chatRef = useRef(null);

  return (
    <>
      <ProfileDropdown />
      {user?.role !== 'company' && <NotificationBell />}
      <HeroSection onStartChat={() => chatRef.current?.open()} />
      <FloatingChatWidget
        ref={chatRef}
        tenantId={user?.tenant_id}
        userId={user?.user_id}
        userRole={user?.role}
        userDetails={{
          name: user?.full_name || null,
          phone: user?.phone || null,
          address: user?.address || null,
        }}
      />
    </>
  );
};

export default ProfessionalDashboard;
