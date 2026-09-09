/**
 * Site map E — Notification inbox.
 * Approval, rejection and adjustment (revision) notices raised by the
 * approval chain, filtered by whatever HRGA has switched on under
 * System Setting > Notification Setting.
 */
import { useCallback, useEffect, useState } from "react";
import { Bell, BellOff, CheckCheck, Eye, RefreshCw } from "lucide-react";

import { overtimeApi } from "@/api/overtime";
import RequestDetail from "./RequestDetail";
import {
  Alert, Btn, Card, Empty, SectionTitle, Spinner, TEXT, errMsg, fmtDateTime,
} from "./ui";

const EVENT_CFG = {
  need_approval: { label: "Needs approval", bg: "#fef3c7", color: "#b45309" },
  approval:      { label: "Approved",       bg: "#dcfce7", color: "#15803d" },
  rejection:     { label: "Rejected",       bg: "#fee2e2", color: "#b91c1c" },
  adjustment:    { label: "Adjustment",     bg: "#ffedd5", color: "#c2410c" },
};

export default function OvertimeNotifications({ refreshBadges }) {
  const [data, setData] = useState({ notifications: [], unread: 0 });
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detailId, setDetailId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await overtimeApi.getNotifications({ unread_only: unreadOnly }));
      setError("");
    } catch (e) {
      setError(errMsg(e, "Could not load your notifications."));
    } finally {
      setLoading(false);
    }
  }, [unreadOnly]);

  useEffect(() => { load(); }, [load]);

  const open = async (n) => {
    if (!n.is_read) {
      try {
        await overtimeApi.markRead(n.id);
        setData((p) => ({
          ...p,
          unread: Math.max(0, p.unread - 1),
          notifications: p.notifications.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)),
        }));
        refreshBadges?.();
      } catch (_) { /* opening the request matters more than the read flag */ }
    }
    if (n.request_id) setDetailId(n.request_id);
  };

  const markAll = async () => {
    try {
      await overtimeApi.markAllRead();
      load();
      refreshBadges?.();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {error && <Alert kind="error" onClose={() => setError("")}>{error}</Alert>}

      <Card>
        <SectionTitle
          icon={Bell}
          title="Notification"
          subtitle={data.unread > 0 ? `${data.unread} unread` : "You are all caught up"}
          right={
            <div style={{ display: "flex", gap: 7 }}>
              <Btn icon={unreadOnly ? Bell : BellOff} onClick={() => setUnreadOnly((v) => !v)}>
                {unreadOnly ? "Show all" : "Unread only"}
              </Btn>
              <Btn icon={RefreshCw} onClick={load} loading={loading}>Refresh</Btn>
              <Btn icon={CheckCheck} variant="primary" onClick={markAll} disabled={data.unread === 0}>
                Mark all read
              </Btn>
            </div>
          }
        />

        {loading && !data.notifications.length ? <Spinner /> : data.notifications.length === 0 ? (
          <Empty
            icon={Bell}
            title={unreadOnly ? "No unread notifications" : "No notifications yet"}
            hint="Approvals, rejections and revision requests on your overtime appear here."
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {data.notifications.map((n) => {
              const cfg = EVENT_CFG[n.event_key] || { label: n.event_key, bg: "#e2e8f0", color: "#64748b" };
              return (
                <div
                  key={n.id}
                  onClick={() => open(n)}
                  style={{
                    display: "flex", gap: 11, padding: "12px 14px", borderRadius: 12, cursor: "pointer",
                    background: n.is_read ? "#ffffff" : "#eff6ff",
                    boxShadow: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
                    borderLeft: `3px solid ${n.is_read ? "#e2e8f0" : "#2563eb"}`,
                  }}
                >
                  <span style={{
                    padding: "2px 9px", borderRadius: 20, fontSize: 10.5, fontWeight: 700, height: "fit-content",
                    background: cfg.bg, color: cfg.color, whiteSpace: "nowrap",
                  }}>
                    {cfg.label}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{
                      fontSize: 12.5, fontWeight: n.is_read ? 600 : 800, color: TEXT.strong, margin: 0,
                    }}>
                      {n.title}
                    </p>
                    <p style={{ fontSize: 11.5, color: TEXT.body, margin: "3px 0 0", lineHeight: 1.5 }}>{n.body}</p>
                    <p style={{ fontSize: 10.5, color: TEXT.muted, margin: "5px 0 0" }}>{fmtDateTime(n.created_at)}</p>
                  </div>
                  {n.request_id && (
                    <span style={{ color: TEXT.muted, alignSelf: "center", display: "flex" }}>
                      <Eye size={14} />
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <RequestDetail
        requestId={detailId}
        open={!!detailId}
        onClose={() => setDetailId(null)}
        footer={<Btn onClick={() => setDetailId(null)}>Close</Btn>}
      />
    </div>
  );
}
