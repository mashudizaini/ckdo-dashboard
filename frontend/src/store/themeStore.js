import { create } from "zustand";
import { THEME } from "@/themes";

function applyVars(theme) {
  const root = document.documentElement;
  Object.entries(theme.vars).forEach(([k, v]) => root.style.setProperty(k, v));
  document.body.style.background = theme.bgMain;
  document.body.style.color = theme.vars["--text-primary"];
  root.setAttribute("data-theme", "light");
}

applyVars(THEME);

export const useThemeStore = create(() => ({
  theme: THEME,
  pickRandomTheme: () => {},
  applyCurrentTheme: () => applyVars(THEME),
}));
