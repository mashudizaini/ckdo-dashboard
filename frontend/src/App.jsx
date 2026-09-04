import { useEffect } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import Layout from "@/components/layout/Layout";
import ProtectedRoute from "@/components/layout/ProtectedRoute";
import AppLauncher from "@/pages/AppLauncher";
import LoginPage from "@/pages/LoginPage";

// Dashboard Pages
import ITDashboard from "@/pages/dashboard/IT";
import HRDashboard from "@/pages/dashboard/HR";
import PACDashboard from "@/pages/dashboard/PAC";
import AccountingDashboard from "@/pages/dashboard/Accounting";
import PurchasingDashboard from "@/pages/dashboard/Purchasing";
import SalesMarketingDashboard from "@/pages/dashboard/SalesMarketing";
import PPWHDashboard from "@/pages/dashboard/PPWH";
import GeneralDashboard from "@/pages/dashboard/General";
import EISDashboard from "@/pages/dashboard/EIS";

// Setup Pages — one per team, same names as the DASHBOARD section
import SetupPage from "@/pages/setup/SetupPage";
import HRSetupPage from "@/pages/setup/HRSetupPage";
import GeneralSetupPage from "@/pages/setup/general/GeneralSetupPage";
import AiSetupPage from "@/pages/setup/ai/AiSetupPage";

// AI Tools Pages
import Chatbot from "@/pages/ai-tools/Chatbot";
import MeetingNotes from "@/pages/ai-tools/MeetingNotes";
import MeetingTranscriptView from "@/pages/ai-tools/MeetingTranscriptView";

// E-Magazine Pages
import EMagazinePage from "@/pages/EMagazinePage";
import EMagazineAdminPage from "@/pages/admin/EMagazineAdminPage";

export default function App() {
  const { init, isLoading, isAuthenticated, returnPath, clearReturnPath } = useAuthStore();
  const navigate = useNavigate();

  useEffect(() => {
    init();
  }, []);

  // After a fresh login, jump back to whatever page the user was on right
  // before the logout that preceded it (idle timeout, a failed token
  // refresh, or a manual logout) — see authStore.js's logout()/returnPath.
  useEffect(() => {
    if (isAuthenticated && returnPath) {
      navigate(returnPath, { replace: true });
      clearReturnPath();
    }
  }, [isAuthenticated, returnPath]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isLoading) {
    return (
      <div style={{
        display: "flex", height: "100vh",
        alignItems: "center", justifyContent: "center",
        background: "linear-gradient(160deg, #0e3460 0%, #134074 40%, #1a4d8a 70%, #0e3460 100%)",
        flexDirection: "column", gap: 16,
      }}>
        <div style={{
          width: 32, height: 32,
          border: "2px solid #60a5fa",
          borderTopColor: "transparent",
          borderRadius: "50%",
          animation: "spin 0.8s linear infinite",
        }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); }}`}</style>
        <p style={{ color: "#93c5fd", fontSize: 12, letterSpacing: "0.1em", fontWeight: 600 }}>
          CONNECTING TO SERVER...
        </p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <Routes>
      {/* App Launcher — halaman utama setelah login */}
      <Route path="/" element={<AppLauncher />} />

      {/* Dashboard dengan sidebar layout */}
      <Route path="/dashboard" element={<Layout />}>
        <Route
          path="it/*"
          element={
            <ProtectedRoute roles={["it_staff", "admin"]}>
              <ITDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="hr/*"
          element={
            <ProtectedRoute roles={["hr_staff", "admin"]}>
              <HRDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="pac/*"
          element={
            <ProtectedRoute roles={["pac_staff", "admin"]}>
              <PACDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="accounting/*"
          element={
            <ProtectedRoute roles={["accounting_staff", "admin"]}>
              <AccountingDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="purchasing/*"
          element={
            <ProtectedRoute roles={["purchasing_staff", "admin"]}>
              <PurchasingDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="sales/*"
          element={
            // No dedicated role yet — see Sidebar.jsx's NAV_ITEMS comment.
            <ProtectedRoute>
              <SalesMarketingDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="ppwh/*"
          element={
            // No dedicated role yet — see Sidebar.jsx's NAV_ITEMS comment.
            <ProtectedRoute>
              <PPWHDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="general/*"
          element={
            // No roles — reachable by any authenticated user. Sub-modules
            // (Budget Monitoring) apply their own finer-grained access
            // control server-side instead of a Keycloak role gate.
            <ProtectedRoute>
              <GeneralDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="eis/*"
          element={
            <ProtectedRoute roles={["management", "admin"]}>
              <EISDashboard />
            </ProtectedRoute>
          }
        />
      </Route>

      {/* SETUP — same team names as DASHBOARD, one placeholder page each
          (no per-team role gate yet — reachable by any authenticated
          user, matching SETUP_ITEMS' roles: [] in Sidebar.jsx). Setup > IT
          is now the generic placeholder — its 3 modules (HikCentral/ZKTeco/
          ETL Admin) moved to Setup > General (2026-09-01), which is now
          where the actual content lives; see GeneralSetupPage.jsx. */}
      <Route path="/setup" element={<Layout />}>
        <Route index             element={<Navigate to="/setup/general" replace />} />
        <Route path="it"          element={<ProtectedRoute><SetupPage team="IT" /></ProtectedRoute>} />
        <Route path="hr"          element={<ProtectedRoute><HRSetupPage /></ProtectedRoute>} />
        <Route path="pac"         element={<ProtectedRoute><SetupPage team="PAC" /></ProtectedRoute>} />
        <Route path="accounting"  element={<ProtectedRoute><SetupPage team="Accounting & Tax" /></ProtectedRoute>} />
        <Route path="purchasing"  element={<ProtectedRoute><SetupPage team="Purchasing" /></ProtectedRoute>} />
        <Route path="general"     element={<ProtectedRoute><GeneralSetupPage /></ProtectedRoute>} />
        <Route path="ai"          element={<ProtectedRoute><AiSetupPage /></ProtectedRoute>} />
      </Route>

      {/* Bare new-tab view (no sidebar chrome) — opened via window.open() after transcribing */}
      <Route path="/ai/meeting-notes/view/:id" element={<MeetingTranscriptView />} />

      {/* AI Tools */}
      <Route path="/ai" element={<Layout />}>
        <Route path="chatbot" element={<Chatbot />} />
        {/* Moved to Setup > AI (2026-09-03) alongside Knowledge Base — kept
            as a redirect so any existing bookmark/link still lands somewhere. */}
        <Route path="document-converter" element={<Navigate to="/setup/ai" replace />} />
        <Route path="oracle-data" element={<Navigate to="/ai/chatbot" replace />} />
        <Route path="meeting-notes" element={<MeetingNotes />} />
      </Route>

      {/* E-Magazine (new dynamic viewer) — deliberately NOT /e-magazine: nginx
          already serves the old static PDF-based e-magazine directly from
          disk at that exact prefix (location /e-magazine/ in nginx.dev.conf),
          which wins over this SPA route since it's a more specific prefix
          match. Temporary path while both versions coexist during testing. */}
      <Route path="/e-magazine-viewer" element={<EMagazinePage />} />
      <Route path="/e-magazine-viewer/admin" element={<EMagazineAdminPage />} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
