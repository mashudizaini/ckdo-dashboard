import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import { useThemeStore } from "@/store/themeStore";

export default function Layout() {
  const { theme: T } = useThemeStore();

  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: T.bgMain, color: T.textPrimary }}
    >
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
