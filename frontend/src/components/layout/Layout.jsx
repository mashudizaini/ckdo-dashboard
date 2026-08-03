import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import ChatWidget from "./ChatWidget";

export default function Layout() {
  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: "var(--bg-main)", color: "var(--text-primary)" }}
    >
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <ChatWidget />
    </div>
  );
}
