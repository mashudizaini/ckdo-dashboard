/**
 * CKDO Dashboard — Single Light Neumorphic Theme
 * Mengikuti style Application Center / App Portal.
 * Background putih susu, efek 3D, aksen biru.
 * Tidak ada random theme switching.
 */

const NEU_BG      = "#e8edf5";
const SHADOW_DARK = "#c5cad8";
const SHADOW_LIGHT= "#ffffff";
const ACCENT      = "#2563eb";
const ACCENT_RGB  = "37,99,235";

export const THEME = {
  id: "portal-light",
  name: "Portal Light",
  dark: false,
  isNeomorphic: true,
  accentColor: ACCENT,
  bgMain: NEU_BG,
  bgSidebar: "#ffffff",
  borderSidebar: "rgba(0,0,0,0.06)",
  borderBottom: "rgba(0,0,0,0.06)",
  sidebarBorder: "rgba(0,0,0,0.06)",
  sidebarDivider: "rgba(0,0,0,0.06)",
  navActiveBg: `rgba(${ACCENT_RGB}, 0.08)`,
  navActiveColor: ACCENT,
  navActiveBorder: "none",
  navActiveRadius: "10px",
  navItemColor: "#64748b",
  navHoverBg: "rgba(0,0,0,0.03)",
  navHoverColor: "#1e293b",
  textPrimary: "#1e293b",
  textSecondary: "#475569",
  textMuted: "#94a3b8",
  btnBackBg: "rgba(37,99,235,0.06)",
  btnBackBorder: "rgba(37,99,235,0.12)",
  btnBackColor: "#475569",
  logoFilter: "none",
  vars: {
    "--bg-main": NEU_BG,
    "--bg-card": "#ffffff",
    "--bg-card2": "#f1f5f9",
    "--bg-card3": "#e2e8f0",
    "--bg-card-hover": "#f8fafc",
    "--text-primary": "#1e293b",
    "--text-secondary": "#475569",
    "--text-muted": "#94a3b8",
    "--text-accent": ACCENT,
    "--border": "rgba(0,0,0,0.06)",
    "--border2": "rgba(0,0,0,0.10)",
    "--accent": ACCENT,
    "--accent-rgb": ACCENT_RGB,
    "--shadow-dark": SHADOW_DARK,
    "--shadow-light": SHADOW_LIGHT,
    "--card-shadow": `0 2px 8px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.04)`,
    "--card-shadow-hover": `0 4px 12px rgba(0,0,0,0.08), 0 12px 32px rgba(0,0,0,0.06)`,
    "--card-shadow-in": `inset 3px 3px 8px ${SHADOW_DARK}, inset -3px -3px 8px ${SHADOW_LIGHT}`,
    "--scrollbar-track": "#f1f5f9",
    "--scrollbar-thumb": ACCENT,
  },
};

// Keep THEMES array for backward compatibility but with single theme
export const THEMES = [THEME];
