/**
 * API Client — Axios
 * ─────────────────────────────────────────
 * Otomatis inject Keycloak Bearer token ke setiap request.
 * Semua API call harus menggunakan instance ini.
 *
 * Cara pakai:
 *   import api from "@/api/client";
 *   const data = await api.get("/dashboard/it/summary");
 */
import axios from "axios";
import { useAuthStore } from "@/store/authStore";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "/api/v1",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// Request interceptor — inject token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — handle errors globally
api.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const original = error.config;

    // A single 401 can just mean the access token quietly expired between
    // requests — try a silent refresh and retry once before logging out.
    // Without this, any request made right after expiry (e.g. the first
    // fetch on a freshly opened tab) forces a full logout, which — since
    // this realm has Google as the default identity-provider redirector —
    // skips straight to the Google sign-in screen instead of just
    // reauthenticating quietly.
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      try {
        const kc = useAuthStore.getState().keycloak;
        await kc.updateToken(-1); // force refresh regardless of expiry
        useAuthStore.setState({ token: kc.token });
        original.headers.Authorization = `Bearer ${kc.token}`;
        return api(original);
      } catch (_) {
        // Refresh token itself is invalid/expired — session is genuinely over.
        useAuthStore.getState().logout();
      }
    }
    return Promise.reject(error.response?.data || error);
  }
);

export default api;
