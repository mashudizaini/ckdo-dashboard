/**
 * CKDO Dashboard — Single Light Neumorphic Theme
 * Mengikuti style Application Center / App Portal.
 * Background putih susu, efek 3D neumorphic, aksen biru.
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
    "--bg-card": NEU_BG,
    "--bg-card2": "#f1f5f9",
    "--bg-card3": "#e2e8f0",
    "--bg-card-hover": "#edf1f8",
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
    "--card-shadow": `6px 6px 14px ${SHADOW_DARK}, -6px -6px 14px ${SHADOW_LIGHT}`,
    "--card-shadow-hover": `8px 8px 18px ${SHADOW_DARK}, -8px -8px 18px ${SHADOW_LIGHT}`,
    "--card-shadow-in": `inset 4px 4px 10px ${SHADOW_DARK}, inset -4px -4px 10px ${SHADOW_LIGHT}`,
    "--scrollbar-track": "#f1f5f9",
    "--scrollbar-thumb": ACCENT,
  },
};

export const THEMES = [THEME];
