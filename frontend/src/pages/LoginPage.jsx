import { useAuthStore } from "@/store/authStore";
import logo from "@/assets/LOGO-ONLY.png";

export default function LoginPage() {
  const { keycloak } = useAuthStore();

  const handleGoogleLogin = () => {
    keycloak.login({ idpHint: "google", prompt: "select_account" });
  };

  const handleAccountLogin = () => {
    keycloak.login({ prompt: "login" });
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes floatUp {
          0%   { transform: translateY(0px)   translateX(0px);  opacity: 0; }
          10%  { opacity: 0.6; }
          90%  { opacity: 0.3; }
          100% { transform: translateY(-100vh) translateX(30px); opacity: 0; }
        }
        @keyframes rotateSlow {
          from { transform: translate(-50%,-50%) rotate(0deg); }
          to   { transform: translate(-50%,-50%) rotate(360deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.5; }
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        .google-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
          width: 100%;
          padding: 13px 20px;
          border-radius: 12px;
          border: 1.5px solid #dadce0;
          background: #ffffff;
          color: #3c4043;
          font-family: 'Inter', sans-serif;
          font-size: 15px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          box-shadow: 0 1px 4px rgba(0,0,0,0.08);
          letter-spacing: 0.01em;
        }
        .google-btn:hover {
          background: #f8faff;
          border-color: #1a73e8;
          box-shadow: 0 2px 12px rgba(26,115,232,0.2);
          transform: translateY(-1px);
        }
        .google-btn:active {
          transform: translateY(0);
          box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        }

        .account-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          width: 100%;
          padding: 12px 20px;
          border-radius: 12px;
          border: 1.5px solid #e2e8f0;
          background: #f8fafc;
          color: #475569;
          font-family: 'Inter', sans-serif;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          letter-spacing: 0.01em;
        }
        .account-btn:hover {
          background: #f1f5f9;
          border-color: #94a3b8;
          color: #1e293b;
          transform: translateY(-1px);
          box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .account-btn:active {
          transform: translateY(0);
        }
      `}</style>

      <div style={{
        minHeight: "100vh",
        background: "linear-gradient(160deg, #0e3460 0%, #134074 40%, #1a4d8a 70%, #0e3460 100%)",
        fontFamily: "'Inter', sans-serif",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        overflow: "hidden",
      }}>

        {/* ── Dot pattern ── */}
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.06, pointerEvents: "none" }}
          xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id="dots" x="0" y="0" width="32" height="32" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1.5" fill="#60a5fa" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#dots)" />
        </svg>

        {/* ── Rotating ring ── */}
        <div style={{
          position: "absolute",
          top: "50%", left: "50%",
          width: 700, height: 700,
          borderRadius: "50%",
          border: "1px solid rgba(96,165,250,0.15)",
          animation: "rotateSlow 40s linear infinite",
          pointerEvents: "none",
        }}>
          <div style={{
            position: "absolute",
            top: "12%", left: "12%", right: "12%", bottom: "12%",
            borderRadius: "50%",
            border: "1px solid rgba(96,165,250,0.08)",
          }} />
        </div>

        {/* ── Glow blobs ── */}
        <div style={{
          position: "absolute", top: -100, right: -80,
          width: 400, height: 400, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(96,165,250,0.15) 0%, transparent 70%)",
          pointerEvents: "none",
        }} />
        <div style={{
          position: "absolute", bottom: -80, left: -60,
          width: 360, height: 360, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(16,185,129,0.1) 0%, transparent 70%)",
          pointerEvents: "none",
        }} />

        {/* ── Floating particles ── */}
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} style={{
            position: "absolute",
            left: `${8 + i * 8}%`,
            bottom: `-${5 + (i % 4) * 5}%`,
            width: i % 3 === 0 ? 5 : 3,
            height: i % 3 === 0 ? 5 : 3,
            borderRadius: "50%",
            background: "rgba(147,197,253,0.5)",
            animation: `floatUp ${14 + i * 2}s linear ${i * 1.2}s infinite`,
            pointerEvents: "none",
          }} />
        ))}

        {/* ── Header bar ── */}
        <header style={{
          position: "relative", zIndex: 10,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "16px 40px",
          background: "rgba(255,255,255,0.07)",
          backdropFilter: "blur(10px)",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          animation: "fadeIn 0.6s ease forwards",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <img src={logo} alt="CKD Otto" style={{ height: 42, width: 42, objectFit: "contain" }} />
            <div>
              <p style={{ fontSize: 14, fontWeight: 700, color: "#f1f5f9", letterSpacing: "0.06em" }}>
                CKD OTTO PHARMACEUTICALS
              </p>
              <p style={{ fontSize: 9.5, color: "#93c5fd", letterSpacing: "0.1em", fontWeight: 600, marginTop: 1 }}>
                INTERNAL APPLICATION PORTAL
              </p>
            </div>
          </div>
          <p style={{ fontSize: 11, color: "#93c5fd", fontWeight: 600, letterSpacing: "0.08em" }}>
            BETTER LIFE THROUGH BETTER MEDICINE
          </p>
        </header>

        {/* ── Center login card ── */}
        <div style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "40px 20px",
          position: "relative", zIndex: 10,
        }}>
          <div style={{
            width: "100%",
            maxWidth: 420,
            background: "rgba(255,255,255,0.97)",
            borderRadius: 20,
            padding: "44px 40px 36px",
            boxShadow: "0 24px 80px rgba(0,0,0,0.25), 0 0 0 1px rgba(255,255,255,0.1)",
            animation: "fadeIn 0.7s ease 0.15s both",
          }}>
            {/* Logo + company in card */}
            <div style={{ textAlign: "center", marginBottom: 28 }}>
              <div style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 80, height: 80,
                borderRadius: "50%",
                background: "linear-gradient(135deg, #eff6ff, #dbeafe)",
                border: "2px solid #bfdbfe",
                marginBottom: 16,
                boxShadow: "0 4px 16px rgba(37,99,235,0.15)",
              }}>
                <img src={logo} alt="CKD Otto" style={{ height: 60, width: 60, objectFit: "contain" }} />
              </div>
              <h1 style={{ fontSize: 20, fontWeight: 700, color: "#0f172a", letterSpacing: "0.02em", marginBottom: 4 }}>
                Welcome Back
              </h1>
              <p style={{ fontSize: 12.5, color: "#64748b" }}>
                Sign in to access the internal portal
              </p>
            </div>

            {/* Divider */}
            <div style={{
              height: 1, background: "linear-gradient(to right, transparent, #e2e8f0, transparent)",
              marginBottom: 24,
            }} />

            {/* Google Sign In Button */}
            <button className="google-btn" onClick={handleGoogleLogin}>
              <svg width="20" height="20" viewBox="0 0 48 48">
                <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.35-8.16 2.35-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                <path fill="none" d="M0 0h48v48H0z"/>
              </svg>
              Sign in with Google
            </button>

            <p style={{ textAlign: "center", fontSize: 11, color: "#94a3b8", marginTop: 10 }}>
              Use your <strong style={{ color: "#2563eb" }}>@ckd-otto.com</strong> Google Workspace account
            </p>

            {/* Divider */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "18px 0" }}>
              <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
              <span style={{ fontSize: 11, color: "#cbd5e1", fontWeight: 600, letterSpacing: "0.05em" }}>OR</span>
              <div style={{ flex: 1, height: 1, background: "#e2e8f0" }} />
            </div>

            {/* Account Login Button */}
            <button className="account-btn" onClick={handleAccountLogin}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              Sign in with Account
            </button>

            <p style={{ textAlign: "center", fontSize: 11, color: "#94a3b8", marginTop: 10 }}>
              For admin access using Keycloak credentials
            </p>

            {/* Divider */}
            <div style={{
              height: 1, background: "linear-gradient(to right, transparent, #e2e8f0, transparent)",
              margin: "18px 0 14px",
            }} />

            {/* Footer inside card */}
            <p style={{ textAlign: "center", fontSize: 10.5, color: "#cbd5e1" }}>
              Protected by Keycloak SSO · CKD Otto Pharmaceuticals
            </p>
          </div>
        </div>

        {/* ── Footer ── */}
        <footer style={{
          position: "relative", zIndex: 10,
          textAlign: "center",
          padding: "14px",
          borderTop: "1px solid rgba(255,255,255,0.07)",
          animation: "fadeIn 0.7s ease 0.4s both",
        }}>
          <p style={{ fontSize: 10.5, color: "rgba(148,163,184,0.6)", letterSpacing: "0.05em" }}>
            © {new Date().getFullYear()} CKD Otto Pharmaceuticals · All rights reserved
          </p>
        </footer>
      </div>
    </>
  );
}
