import { useState } from "react";
import Upload  from "./pages/Upload.jsx";
import Review  from "./pages/Review.jsx";
import Tracker from "./pages/Tracker.jsx";

const NAV_TABS = [
  { id: "upload",  label: "📤 Upload PDF" },
  { id: "tracker", label: "📊 Tracker"    },
];

export default function App() {
  const [tab,        setTab]        = useState("upload");
  const [reviewData, setReviewData] = useState(null);
  const [reviewMode, setReviewMode] = useState(false);

  const handleUploaded = (result) => {
    setReviewData(result);
    setReviewMode(true);
    setTab("review");
  };

  const handleReviewById = (stgId) => {
    setReviewData({ stg_id: stgId, _fetchById: true });
    setReviewMode(true);
    setTab("review");
  };

  const handleDone = () => {
    setReviewMode(false);
    setReviewData(null);
    setTab("tracker");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f1f5f9", fontFamily: "Inter, sans-serif" }}>
      <div style={{
        background: "linear-gradient(135deg, #1e3a5f, #1d4ed8)",
        padding: "0 32px", display: "flex", alignItems: "center", gap: 32,
        boxShadow: "0 2px 8px #0002",
      }}>
        <div style={{ padding: "16px 0", color: "#fff" }}>
          <div style={{ fontWeight: 700, fontSize: 18 }}>CKDO AP Invoice Import</div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>Oracle EBS 12.2.8 — AP Module</div>
        </div>
        <nav style={{ display: "flex", gap: 4 }}>
          {NAV_TABS.map(({ id, label }) => (
            <button key={id} onClick={() => { setTab(id); setReviewMode(false); }} style={{
              padding: "6px 18px",
              background: tab === id ? "rgba(255,255,255,0.2)" : "transparent",
              border: "none",
              borderBottom: tab === id ? "3px solid #fff" : "3px solid transparent",
              color: "#fff", cursor: "pointer",
              fontWeight: tab === id ? 600 : 400, fontSize: 14,
            }}>{label}</button>
          ))}
          {reviewMode && (
            <button style={{
              padding: "6px 18px", background: "rgba(255,255,255,0.2)",
              border: "none", borderBottom: "3px solid #fbbf24",
              color: "#fbbf24", cursor: "default", fontWeight: 600, fontSize: 14,
            }}>✏️ Review Invoice</button>
          )}
        </nav>
      </div>

      <div style={{ padding: "24px 32px" }}>
        {tab === "upload" && !reviewMode && <Upload onUploaded={handleUploaded} />}
        {(tab === "review" || reviewMode) && reviewData && <Review invoice={reviewData} onDone={handleDone} />}
        {tab === "tracker" && !reviewMode && <Tracker onReview={handleReviewById} />}
      </div>
    </div>
  );
}
