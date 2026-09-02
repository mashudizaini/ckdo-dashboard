import React, { useState, useCallback } from 'react';

export default function HotspotLayer({
  hotspots = [],
  pageWidth = 800,
  pageHeight = 1000,
  onHotspotClick = () => {},
}) {
  const [hoveredId, setHoveredId] = useState(null);

  const handleHotspotClick = useCallback(
    (e, hotspot) => {
      e.preventDefault();
      onHotspotClick(hotspot);
    },
    [onHotspotClick]
  );

  if (hotspots.length === 0) return null;

  return (
    <svg
      className="absolute inset-0 w-full h-full cursor-pointer"
      preserveAspectRatio="xMidYMid meet"
      viewBox={`0 0 ${pageWidth} ${pageHeight}`}
      style={{ pointerEvents: 'auto' }}
    >
      {hotspots.map((hotspot) => (
        <g key={hotspot.id}>
          {/* Invisible larger hitbox for easier clicking */}
          <rect
            x={hotspot.x_pos - 5}
            y={hotspot.y_pos - 5}
            width={hotspot.width + 10}
            height={hotspot.height + 10}
            fill="transparent"
            onMouseEnter={() => setHoveredId(hotspot.id)}
            onMouseLeave={() => setHoveredId(null)}
            onClick={(e) => handleHotspotClick(e, hotspot)}
            style={{ cursor: 'pointer' }}
          />

          {/* Visible hotspot box (shown on hover) */}
          {hoveredId === hotspot.id && (
            <>
              {/* Highlight rectangle */}
              <rect
                x={hotspot.x_pos}
                y={hotspot.y_pos}
                width={hotspot.width}
                height={hotspot.height}
                fill="rgba(59, 130, 246, 0.2)"
                stroke="rgb(59, 130, 246)"
                strokeWidth="2"
                rx="4"
                pointerEvents="none"
              />

              {/* Tooltip background */}
              {hotspot.tooltip && (
                <>
                  {/* Tooltip box */}
                  <rect
                    x={hotspot.x_pos}
                    y={Math.max(0, hotspot.y_pos - 40)}
                    width={Math.max(100, hotspot.tooltip.length * 6)}
                    height="32"
                    fill="rgb(0, 0, 0)"
                    rx="4"
                    pointerEvents="none"
                  />

                  {/* Tooltip text */}
                  <text
                    x={hotspot.x_pos + 8}
                    y={Math.max(0, hotspot.y_pos - 40) + 20}
                    fill="white"
                    fontSize="12"
                    fontWeight="500"
                    pointerEvents="none"
                  >
                    {hotspot.tooltip}
                  </text>
                </>
              )}

              {/* Action type indicator (small icon) */}
              <circle
                cx={hotspot.x_pos + hotspot.width - 8}
                cy={hotspot.y_pos + 8}
                r="6"
                fill={getActionColor(hotspot.action_type)}
                pointerEvents="none"
                opacity="0.8"
              />
            </>
          )}
        </g>
      ))}
    </svg>
  );
}

function getActionColor(actionType) {
  const colors = {
    link: 'rgb(59, 130, 246)', // blue
    contact: 'rgb(168, 85, 247)', // purple
    video: 'rgb(239, 68, 68)', // red
    form: 'rgb(34, 197, 94)', // green
    qrcode: 'rgb(249, 115, 22)', // orange
    profile: 'rgb(168, 85, 247)', // purple
  };
  return colors[actionType] || 'rgb(107, 114, 128)'; // gray default
}
