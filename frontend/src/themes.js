/**
 * CKDO Dashboard — Single Flat White Theme
 * White cards on a soft light-gray page, thin borders + conventional
 * elevation shadows for depth (not neumorphic blend), accent blue.
 * Chosen 2026-08-03 for text clarity over the previous neumorphic look —
 * see THEME_NEUMORPHIC_LEGACY below to revert if it doesn't work out
 * (just change the `export const THEME = ...` line at the bottom).
 */

const PAGE_BG     = "#f1f4f8";
const ACCENT      = "#2563eb";
const ACCENT_RGB  = "37,99,235";

export const THEME_FLAT_WHITE = {
  id: "flat-white",
  name: "Flat White",
  dark: false,
  isNeomorphic: false,
  accentColor: ACCENT,
  bgMain: PAGE_BG,
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
  textPrimary: "#0f172a",
  textSecondary: "#475569",
  textMuted: "#94a3b8",
  btnBackBg: "rgba(37,99,235,0.06)",
  btnBackBorder: "rgba(37,99,235,0.12)",
  btnBackColor: "#475569",
  logoFilter: "none",
  vars: {
    "--bg-main": PAGE_BG,
    "--bg-card": "#ffffff",
    "--bg-card2": "#f8fafc",
    "--bg-card3": "#f1f5f9",
    "--bg-card-hover": "#f8fafc",
    "--text-primary": "#0f172a",
    "--text-secondary": "#475569",
    "--text-muted": "#94a3b8",
    "--text-accent": ACCENT,
    "--border": "rgba(15,23,42,0.09)",
    "--border2": "rgba(15,23,42,0.14)",
    "--accent": ACCENT,
    "--accent-rgb": ACCENT_RGB,
    "--shadow-dark": "rgba(15,23,42,0.10)",
    "--shadow-light": "#ffffff",
    "--card-shadow": "0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
    "--card-shadow-hover": "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.06)",
    "--card-shadow-in": "inset 0 1px 3px rgba(15,23,42,0.08)",
    "--scrollbar-track": "#f1f5f9",
    "--scrollbar-thumb": ACCENT,
  },
};

/**
 * Legacy neumorphic theme — kept complete and unused so a revert is a
 * one-line swap of the `THEME` export below instead of digging through git
 * history. Background putih susu (#e8edf5), efek 3D neumorphic cembung.
 */
const NEU_BG      = "#e8edf5";
const NEU_SHADOW_DARK = "#c5cad8";
const NEU_SHADOW_LIGHT= "#ffffff";

export const THEME_NEUMORPHIC_LEGACY = {
  id: "portal-light",
  name: "Portal Light (neumorphic)",
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
    "--shadow-dark": NEU_SHADOW_DARK,
    "--shadow-light": NEU_SHADOW_LIGHT,
    "--card-shadow": `6px 6px 14px ${NEU_SHADOW_DARK}, -6px -6px 14px ${NEU_SHADOW_LIGHT}`,
    "--card-shadow-hover": `8px 8px 18px ${NEU_SHADOW_DARK}, -8px -8px 18px ${NEU_SHADOW_LIGHT}`,
    "--card-shadow-in": `inset 4px 4px 10px ${NEU_SHADOW_DARK}, inset -4px -4px 10px ${NEU_SHADOW_LIGHT}`,
    "--scrollbar-track": "#f1f5f9",
    "--scrollbar-thumb": ACCENT,
  },
};

export const THEME = THEME_FLAT_WHITE;
export const THEMES = [THEME];
