/* ── Robot icon — square LED eyes, screen-panel look ──
   Shared between the AI Chatbot sidebar nav item and the floating ChatWidget,
   so both surfaces use the exact same brand icon. */
export default function RobotIcon({ size = 26, color = "#fff" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
      <line x1="15" y1="1" x2="15" y2="5.5" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="15" cy="1.5" r="2" fill={color} />
      <circle cx="15" cy="1.5" r="1" fill="rgba(99,102,241,0.6)" />
      <rect x="3.5" y="5.5" width="23" height="20" rx="5.5" fill="rgba(255,255,255,0.13)" stroke={color} strokeWidth="1.7" />
      <rect x="7" y="10" width="6" height="6" rx="2" fill={color} />
      <rect x="8.2" y="11.2" width="3.6" height="3.6" rx="1" fill="#4f46e5" />
      <circle cx="9" cy="12" r="0.6" fill="rgba(255,255,255,0.9)" />
      <rect x="17" y="10" width="6" height="6" rx="2" fill={color} />
      <rect x="18.2" y="11.2" width="3.6" height="3.6" rx="1" fill="#4f46e5" />
      <circle cx="19" cy="12" r="0.6" fill="rgba(255,255,255,0.9)" />
      <rect x="8.5"  y="19.5" width="2.5" height="2" rx="0.8" fill={color} />
      <rect x="12"   y="19.5" width="2.5" height="2" rx="0.8" fill={color} />
      <rect x="15.5" y="19.5" width="2.5" height="2" rx="0.8" fill={color} />
      <rect x="19"   y="19.5" width="2.5" height="2" rx="0.8" fill={color} opacity="0.55" />
      <rect x="1.2" y="11" width="2.5" height="5.5" rx="1.2" fill={color} />
      <rect x="26.3" y="11" width="2.5" height="5.5" rx="1.2" fill={color} />
    </svg>
  );
}
