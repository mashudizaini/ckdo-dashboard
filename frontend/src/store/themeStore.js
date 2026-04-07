import { create } from "zustand";
import { THEMES } from "@/themes";

const SESSION_KEY = "ckdo_theme_id";

function applyVars(theme) {
  const root = document.documentElement;
  Object.entries(theme.vars).forEach(([k, v]) => root.style.setProperty(k, v));
  document.body.style.background = theme.bgMain;
  document.body.style.color = theme.vars["--text-primary"];
  // Flag CSS untuk light vs dark neumorphic
  if (theme.isNeomorphic) {
    root.setAttribute("data-theme", "light");
  } else {
    root.setAttribute("data-theme", "dark");
  }
}

// Terapkan theme awal saat modul dimuat
const savedId  = sessionStorage.getItem(SESSION_KEY);
const initial  = THEMES.find((t) => t.id === savedId) || THEMES[0];
applyVars(initial);

export const useThemeStore = create((set, get) => ({
  theme: initial,

  /** Dipanggil saat user klik CKDO Dashboard — pilih tema secara random */
  pickRandomTheme: () => {
    const current = get().theme;
    // Hindari tema yang sama dua kali berturut-turut
    const others  = THEMES.filter((t) => t.id !== current.id);
    const next    = others[Math.floor(Math.random() * others.length)];
    sessionStorage.setItem(SESSION_KEY, next.id);
    applyVars(next);
    set({ theme: next });
  },

  /** Terapkan ulang theme saat ini (misal setelah navigasi/reload) */
  applyCurrentTheme: () => applyVars(get().theme),
}));
