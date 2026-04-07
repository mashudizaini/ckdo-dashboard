import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/store/authStore";

/**
 * ProtectedRoute
 * ─────────────────────────────────────────
 * Wrap page component dengan role check.
 *
 * Props:
 *   roles: string[]  — list role yang diizinkan (admin selalu lolos)
 *   children: ReactNode
 *
 * Usage:
 *   <ProtectedRoute roles={["it_staff", "admin"]}>
 *     <ITDashboard />
 *   </ProtectedRoute>
 */
export default function ProtectedRoute({ roles = [], children }) {
  const { isAuthenticated, hasAnyRole } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  if (roles.length > 0 && !hasAnyRole(...roles)) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center p-8">
          <div className="text-6xl mb-4">🔒</div>
          <h2 className="text-xl font-semibold text-gray-200 mb-2">Access Denied</h2>
          <p className="text-gray-500 text-sm">
            You do not have permission to access this page.
          </p>
        </div>
      </div>
    );
  }

  return children;
}
