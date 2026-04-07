/**
 * CKDO Dashboard Themes — Adminly 2 Dark Style
 * Satu visual style (dark gradient, rounded cards), 6 varian warna accent.
 * Dipilih random setiap klik CKDO Dashboard dari App Launcher.
 */

// Base dark bg yang sama untuk semua tema
const BASE = {
  dark: true,
  // Sidebar
  sidebarBorder: "rgba(255,255,255,0.06)",
  sidebarDivider: "rgba(255,255,255,0.06)",
  // Text
  textPrimary:   "#f1f5f9",
  textSecondary: "#cbd5e1",
  textMuted:     "#94a3b8",
  // Nav inactive
  navItemColor:  "#94a3b8",
  navHoverBg:    "rgba(255,255,255,0.06)",
  navHoverColor: "#f1f5f9",
  // Back button
  btnBackBg:     "rgba(255,255,255,0.08)",
  btnBackBorder: "rgba(255,255,255,0.12)",
  btnBackColor:  "#cbd5e1",
  // Logo
  logoFilter:    "brightness(1.1)",
};

// Helper — buat satu tema dari accent color
function mkTheme(id, name, accent, accentRgb, bgTint = "#0d0d1a") {
  return {
    ...BASE,
    id,
    name,
    accentColor:  accent,
    bgMain:    `linear-gradient(135deg, ${bgTint} 0%, #111122 60%, ${bgTint} 100%)`,
    bgSidebar: `linear-gradient(180deg, #0a0a16 0%, #0e0e1e 100%)`,
    borderSidebar: `rgba(${accentRgb}, 0.2)`,
    borderBottom:  `rgba(255,255,255,0.06)`,
    navActiveBg:     `rgba(${accentRgb}, 0.2)`,
    navActiveColor:  accent,
    navActiveBorder: "none",
    navActiveRadius: "8px",
    vars: {
      "--bg-main":        bgTint,
      "--bg-card":        "#1c1c2e",   // lebih terang dari bg-main → kontras jelas
      "--bg-card2":       "#242436",   // inner section
      "--bg-card3":       "#14141f",   // terdalam
      "--bg-card-hover":  "#222234",
      "--text-primary":   "#f1f5f9",
      "--text-secondary": "#cbd5e1",
      "--text-muted":     "#94a3b8",
      "--text-accent":    accent,
      "--border":         "rgba(255,255,255,0.08)",
      "--border2":        "rgba(255,255,255,0.13)",
      "--accent":         accent,
      "--accent-rgb":     accentRgb,
      // Shadow kuat — kunci efek 3D Adminly 2
      "--card-shadow":    `0 8px 32px rgba(0,0,0,0.55), 0 1px 0 rgba(255,255,255,0.07) inset`,
      "--scrollbar-track":"#0a0a16",
      "--scrollbar-thumb": accent,
    },
  };
}

// ── Light Neumorphic theme builder ────────────────────────────
function mkLightTheme(id, name, accent, accentRgb, bg = "#eae7df") {
  // Shadow dark & light untuk efek neumorphic
  const shadowDark  = "#c8c5be";
  const shadowLight = "#ffffff";
  return {
    id, name,
    dark: false,
    isNeomorphic: true,           // flag khusus untuk CSS light
    accentColor: accent,
    bgMain:    bg,
    bgSidebar: bg,
    borderSidebar: `rgba(${accentRgb}, 0.2)`,
    borderBottom:  `rgba(0,0,0,0.07)`,
    // Nav
    navActiveBg:     `rgba(${accentRgb}, 0.15)`,
    navActiveColor:  accent,
    navActiveBorder: "none",
    navItemColor:    "#4b5563",
    navHoverBg:      "rgba(0,0,0,0.05)",
    navHoverColor:   "#111827",
    // Teks
    textPrimary:   "#111827",
    textSecondary: "#374151",
    textMuted:     "#6b7280",
    sidebarBorder: `rgba(0,0,0,0.07)`,
    sidebarDivider:`rgba(0,0,0,0.07)`,
    // Tombol
    btnBackBg:     "rgba(0,0,0,0.06)",
    btnBackBorder: "rgba(0,0,0,0.1)",
    btnBackColor:  "#374151",
    logoFilter:    "none",
    vars: {
      "--bg-main":          bg,
      "--bg-card":          bg,          // sama dengan bg → neumorphic
      "--bg-card2":         "#f0ede5",
      "--bg-card3":         "#e2dfd7",
      "--bg-card-hover":    "#f2efe7",
      "--text-primary":     "#111827",
      "--text-secondary":   "#374151",
      "--text-muted":       "#6b7280",
      "--text-accent":      accent,
      "--border":           "rgba(0,0,0,0.06)",
      "--border2":          "rgba(0,0,0,0.10)",
      "--accent":           accent,
      "--accent-rgb":       accentRgb,
      "--shadow-dark":      shadowDark,
      "--shadow-light":     shadowLight,
      // Shadow neumorphic — raised
      "--card-shadow":      `6px 6px 16px ${shadowDark}, -6px -6px 16px ${shadowLight}`,
      "--card-shadow-in":   `inset 4px 4px 10px ${shadowDark}, inset -4px -4px 10px ${shadowLight}`,
      "--scrollbar-track":  bg,
      "--scrollbar-thumb":  accent,
    },
  };
}

export const THEMES = [
  mkTheme("indigo",  "Indigo Night",   "#6366f1", "99,102,241",  "#0e0e20"),
  mkTheme("emerald", "Emerald Night",  "#10b981", "16,185,129",  "#0a1a14"),
  mkTheme("rose",    "Rose Night",     "#f43f5e", "244,63,94",   "#1a0a10"),
  mkTheme("amber",   "Amber Night",    "#f59e0b", "245,158,11",  "#1a1408"),
  mkTheme("cyan",    "Cyan Night",     "#06b6d4", "6,182,212",   "#081820"),
  mkTheme("violet",  "Violet Night",   "#8b5cf6", "139,92,246",  "#110e20"),
  // ── Light Neumorphic ──────────────────────────────────────
  mkLightTheme("cream-teal",   "Cream Teal",   "#0d9488", "13,148,136",  "#eae7df"),
];
