/**
 * Auth Store — Zustand
 * ─────────────────────────────────────────
 * Manages Keycloak authentication state.
 * Token disimpan di memory (bukan localStorage).
 */
import { create } from "zustand";
import Keycloak from "keycloak-js";

// VITE_KEYCLOAK_URL is a fixed build-time string (currently "http://...").
// The app is reachable over both http:// and https:// (nginx serves both,
// no forced redirect), but Keycloak's token/auth XHR calls must match the
// PAGE's own scheme — an https:// page calling out to a hardcoded http://
// endpoint gets blocked outright as mixed content (no user-facing error
// beyond a silent "Keycloak init failed" and a bounce back to the login
// page). Swap in whichever scheme the page actually loaded with, so login
// works consistently under either.
const keycloakUrl = (import.meta.env.VITE_KEYCLOAK_URL || "").replace(/^https?:/, window.location.protocol);

const kc = new Keycloak({
  url: keycloakUrl,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
});

let kcInitialized = false;

// Auto-logout setelah 10 menit tanpa aktivitas (mouse/keyboard/touch/scroll).
const IDLE_TIMEOUT_MS = 10 * 60 * 1000;
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart"];

export const useAuthStore = create((set, get) => ({
  keycloak: kc,
  isAuthenticated: false,
  isLoading: true,
  user: null,
  token: null,
  roles: [],

  init: async () => {
    if (kcInitialized) return;
    kcInitialized = true;
    try {
      const authenticated = await kc.init({
        checkLoginIframe: false,
        pkceMethod: "S256",
      });

      if (!authenticated) {
        set({ isLoading: false });
        return;
      }

      if (authenticated) {
        // loadUserProfile bisa gagal jika endpoint profile tidak aktif
        let profile = {};
        try {
          profile = await kc.loadUserProfile();
        } catch (_) {
          // fallback ke tokenParsed
        }

        const roles =
          kc.realmAccess?.roles ||
          kc.tokenParsed?.realm_access?.roles ||
          [];

        set({
          isAuthenticated: true,
          isLoading: false,
          token: kc.token,
          roles,
          user: {
            id: kc.subject,
            username: kc.tokenParsed?.preferred_username,
            email: profile.email ?? kc.tokenParsed?.email ?? "",
            fullName: (
              `${profile.firstName ?? kc.tokenParsed?.given_name ?? ""} ` +
              `${profile.lastName ?? kc.tokenParsed?.family_name ?? ""}`
            ).trim(),
          },
        });

        // Auto-refresh token 60s sebelum expire
        setInterval(() => {
          kc.updateToken(60).then((refreshed) => {
            if (refreshed) {
              set({ token: kc.token });
            }
          });
        }, 30000);

        // Auto-logout setelah 10 menit tanpa aktivitas — refresh loop di atas
        // sengaja tidak dijadikan sinyal aktivitas, supaya idle beneran (tab
        // dibiarkan terbuka tanpa disentuh) tetap ter-logout meski token
        // masih terus di-refresh di background.
        let idleTimer;
        const resetIdleTimer = () => {
          clearTimeout(idleTimer);
          idleTimer = setTimeout(() => get().logout(), IDLE_TIMEOUT_MS);
        };
        ACTIVITY_EVENTS.forEach((evt) => window.addEventListener(evt, resetIdleTimer, { passive: true }));
        resetIdleTimer();
      }
    } catch (error) {
      console.error("Keycloak init failed:", error);
      set({ isLoading: false });
    }
  },

  logout: () => {
    kc.logout({ redirectUri: window.location.origin });
    set({ isAuthenticated: false, user: null, token: null, roles: [] });
  },

  hasRole: (role) => {
    const { roles } = get();
    return roles.includes(role) || roles.includes("admin");
  },

  hasAnyRole: (...checkRoles) => {
    const { roles } = get();
    return roles.includes("admin") || checkRoles.some((r) => roles.includes(r));
  },
}));
