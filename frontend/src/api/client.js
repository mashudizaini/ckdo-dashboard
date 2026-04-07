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
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
    }
    return Promise.reject(error.response?.data || error);
  }
);

export default api;
