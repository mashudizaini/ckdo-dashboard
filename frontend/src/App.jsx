import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
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

// AI Tools Pages
import Chatbot from "@/pages/ai-tools/Chatbot";
import MeetingNotes from "@/pages/ai-tools/MeetingNotes";

export default function App() {
  const { init, isLoading, isAuthenticated } = useAuthStore();

  useEffect(() => {
    init();
  }, []);

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

  // DEBUG — hapus setelah masalah roles terselesaikan
  console.log("[AUTH DEBUG] roles:", useAuthStore.getState().roles);
  console.log("[AUTH DEBUG] token parsed:", useAuthStore.getState().keycloak?.tokenParsed);

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
          path="hr"
          element={
            <ProtectedRoute roles={["hr_staff", "admin"]}>
              <HRDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="pac"
          element={
            <ProtectedRoute roles={["pac_staff", "admin"]}>
              <PACDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="accounting"
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
      </Route>

      {/* AI Tools */}
      <Route path="/ai" element={<Layout />}>
        <Route path="chatbot" element={<Chatbot />} />
        <Route path="meeting-notes" element={<MeetingNotes />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
