import React, { useState, useCallback } from 'react';

/**
 * Reader-facing hotspot overlay — plain percentage-positioned <div>s over
 * the page image, not SVG viewBox math. x_pos/y_pos/width/height are all
 * 0-100 percentages of the page container, matching HotspotEditor.jsx's
 * (the admin placement tool) convention exactly, so a hotspot placed there
 * lands in the same spot here. Percentages track the actual rendered
 * <img> size automatically regardless of viewport/zoom, sidestepping the
 * SVG viewBox/aspect-ratio class of bug entirely.
 */
export default function HotspotLayer({ hotspots = [], onHotspotClick = () => {} }) {
  const [hoveredId, setHoveredId] = useState(null);

  const handleClick = useCallback(
    (e, hotspot) => {
      e.preventDefault();
      onHotspotClick(hotspot);
    },
    [onHotspotClick]
  );

  if (hotspots.length === 0) return null;

  return (
    <div className="absolute inset-0">
      {hotspots.map((hotspot) => {
        const hovered = hoveredId === hotspot.id;
        return (
          <div
            key={hotspot.id}
            onMouseEnter={() => setHoveredId(hotspot.id)}
            onMouseLeave={() => setHoveredId(null)}
            onClick={(e) => handleClick(e, hotspot)}
            style={{
              position: 'absolute',
              left: `${hotspot.x_pos}%`,
              top: `${hotspot.y_pos}%`,
              width: `${hotspot.width}%`,
              height: `${hotspot.height}%`,
              cursor: 'pointer',
              borderRadius: 4,
              background: hovered ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
              border: hovered ? '2px solid rgb(59, 130, 246)' : '2px solid transparent',
              transition: 'background 0.1s, border-color 0.1s',
            }}
          >
            {hovered && (
              <>
                <span
                  style={{
                    position: 'absolute',
                    top: -8,
                    right: -8,
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    background: getActionColor(hotspot.action_type),
                    opacity: 0.9,
                  }}
                />
                {hotspot.tooltip && (
                  <span
                    style={{
                      position: 'absolute',
                      bottom: '100%',
                      left: 0,
                      marginBottom: 6,
                      background: 'rgb(0, 0, 0)',
                      color: 'white',
                      fontSize: 12,
                      fontWeight: 500,
                      padding: '6px 10px',
                      borderRadius: 4,
                      whiteSpace: 'nowrap',
                      pointerEvents: 'none',
                    }}
                  >
                    {hotspot.tooltip}
                  </span>
                )}
              </>
            )}
          </div>
        );
      })}
    </div>
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
