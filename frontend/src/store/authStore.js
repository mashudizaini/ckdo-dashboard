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
//
// Rewritten from a single `setTimeout(fn, 10*60*1000)` to a periodic
// elapsed-wall-clock-time check. Two real bugs with the old version:
//
// 1. A 10-minute setTimeout is exactly the kind of long timer a
//    backgrounded tab gets throttled on — but throttling only ever DELAYS
//    firing, it can't explain a logout that happens within seconds of
//    switching away. The actual fast-logout mechanism was almost certainly
//    this: Keycloak's SSO session is ONE shared cookie for the whole
//    browser, but kc.logout() (called by whichever tab's idle timer fires
//    first) kills that cookie for every tab/window at once. If the
//    dashboard was open in more than one tab/window, an idle one sitting
//    in the background — completely unrelated to "switching to another
//    app" in the tab actually being used — could cross the 10-minute mark
//    and log out the shared session out from under the active tab.
// 2. Checking "how long has it actually been" on a timer that re-arms
//    itself only fires get().logout() at all once genuinely >= 10 minutes
//    have elapsed since the last recorded activity — it can never fire
//    early, since it's driven by a Date.now() diff rather than trusting a
//    scheduled deadline.
//
// LAST_ACTIVITY_KEY is written to localStorage (shared across same-origin
// tabs) instead of only an in-memory variable, so activity in ANY open
// dashboard tab counts as activity for ALL of them — fixing #1 directly.
const IDLE_TIMEOUT_MS = 10 * 60 * 1000;
const IDLE_CHECK_INTERVAL_MS = 15 * 1000;
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "scroll", "touchstart"];
const LAST_ACTIVITY_KEY = "ckdo_last_activity_at";

const markActivity = () => {
  try { localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now())); } catch (_) {}
};

const getLastActivity = () => {
  try {
    const stored = Number(localStorage.getItem(LAST_ACTIVITY_KEY));
    if (stored) return stored;
  } catch (_) {}
  return Date.now();
};

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
        markActivity();
        ACTIVITY_EVENTS.forEach((evt) => window.addEventListener(evt, markActivity, { passive: true }));
        const idleCheck = setInterval(() => {
          if (Date.now() - getLastActivity() >= IDLE_TIMEOUT_MS) {
            clearInterval(idleCheck);
            get().logout();
          }
        }, IDLE_CHECK_INTERVAL_MS);
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

  // Explicit "this counts as activity too" for pages with a long
  // unattended-but-legitimately-busy operation (e.g. Meeting Notes recording
  // a 1-2h meeting, or waiting on transcription) — without this, such a page
  // hits the idle timeout above and gets logged out mid-operation even
  // though nothing is actually idle. Deliberately separate from the
  // token-refresh loop (which does NOT call this) so genuine tab-left-open
  // idleness is still caught everywhere else.
  keepAlive: () => { markActivity(); },

  hasRole: (role) => {
    const { roles } = get();
    return roles.includes(role) || roles.includes("admin");
  },

  hasAnyRole: (...checkRoles) => {
    const { roles } = get();
    return roles.includes("admin") || checkRoles.some((r) => roles.includes(r));
  },
}));
