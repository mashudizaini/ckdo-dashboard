import React, { useState, useRef, useEffect } from 'react';
import { X, Move } from 'lucide-react';

const ACTION_TYPES = [
  { value: 'contact', label: 'Contact' },
  { value: 'link', label: 'Link' },
  { value: 'video', label: 'Video' },
  { value: 'form', label: 'Form' },
  { value: 'qrcode', label: 'QR Code' },
];

export default function HotspotEditor({
  hotspots = [],
  editionId,
  pageNumber,
  onCreateHotspot,
  onUpdateHotspot,
  onDeleteHotspot,
  disabled = false
}) {
  const svgRef = useRef(null);
  const [isCreating, setIsCreating] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [draggingId, setDraggingId] = useState(null);
  const [draggingCorner, setDraggingCorner] = useState(null);
  const [dragStart, setDragStart] = useState(null);
  const [editingId, setEditingId] = useState(null);

  const handleSvgMouseDown = (e) => {
    if (disabled) return;

    const svg = svgRef.current;
    if (!svg) return;

    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;

    setIsCreating(true);
    setStartPos({ x, y });
    setEditingId(null);
  };

  const handleSvgMouseMove = (e) => {
    if (!svgRef.current) return;

    const svg = svgRef.current;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;

    if (isCreating && startPos) {
      // Visual feedback for creating hotspot - handled by canvas
    }

    if (draggingId && dragStart) {
      const deltaX = x - dragStart.x;
      const deltaY = y - dragStart.y;
      const hotspot = hotspots.find(h => h.id === draggingId);

      if (draggingCorner === 'resize') {
        // Resize mode - only update for SE corner
        const newWidth = Math.max(5, hotspot.width + deltaX);
        const newHeight = Math.max(5, hotspot.height + deltaY);
        updateHotspotPosition(draggingId, {
          ...hotspot,
          width: newWidth,
          height: newHeight,
        });
      } else {
        // Move mode
        const newX = Math.max(0, Math.min(100, hotspot.x_pos + deltaX));
        const newY = Math.max(0, Math.min(100, hotspot.y_pos + deltaY));
        updateHotspotPosition(draggingId, {
          ...hotspot,
          x_pos: newX,
          y_pos: newY,
        });
      }

      setDragStart({ x, y });
    }
  };

  const handleSvgMouseUp = (e) => {
    if (isCreating && startPos) {
      const svg = svgRef.current;
      if (!svg) return;

      const rect = svg.getBoundingClientRect();
      const endX = ((e.clientX - rect.left) / rect.width) * 100;
      const endY = ((e.clientY - rect.top) / rect.height) * 100;

      const width = Math.abs(endX - startPos.x);
      const height = Math.abs(endY - startPos.y);

      // Only create if hotspot is large enough
      if (width > 2 && height > 2) {
        const x = Math.min(startPos.x, endX);
        const y = Math.min(startPos.y, endY);

        const newHotspot = {
          edition_id: editionId,
          page_number: pageNumber,
          x_pos: x,
          y_pos: y,
          width: width,
          height: height,
          action_type: 'contact',
          action_data: {},
          tooltip: 'New hotspot',
        };

        onCreateHotspot(newHotspot);
      }

      setIsCreating(false);
      setStartPos(null);
    }

    if (draggingId) {
      setDraggingId(null);
      setDraggingCorner(null);
      setDragStart(null);
    }
  };

  const updateHotspotPosition = (hotspotId, updatedHotspot) => {
    if (onUpdateHotspot) {
      onUpdateHotspot(hotspotId, updatedHotspot);
    }
  };

  const handleHotspotMouseDown = (e, hotspotId, corner = null) => {
    if (disabled) return;
    e.stopPropagation();

    const svg = svgRef.current;
    if (!svg) return;

    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;

    setDraggingId(hotspotId);
    setDraggingCorner(corner);
    setDragStart({ x, y });
    setEditingId(hotspotId);
  };

  const handleDeleteHotspot = (e, hotspotId) => {
    e.stopPropagation();
    if (onDeleteHotspot) {
      onDeleteHotspot(hotspotId);
    }
  };

  // Calculate bounding box for creation preview
  const getBoundingBox = () => {
    if (!isCreating || !startPos) return null;

    const svg = svgRef.current;
    if (!svg) return null;

    const rect = svg.getBoundingClientRect();

    // Get current mouse position from SVG by finding it from event
    // For now, we'll use startPos to show a preview
    return startPos;
  };

  return (
    <div className="space-y-4">
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
        <p className="text-sm text-yellow-800">
          <strong>Hotspot Editor:</strong> Click and drag on the page to create hotspots.
          Click on existing hotspots to edit or drag to move them.
        </p>
      </div>

      <div className="relative border border-gray-300 rounded-lg overflow-hidden bg-white">
        <svg
          ref={svgRef}
          viewBox="0 0 100 140"
          className="w-full aspect-video bg-gray-50 cursor-crosshair"
          onMouseDown={handleSvgMouseDown}
          onMouseMove={handleSvgMouseMove}
          onMouseUp={handleSvgMouseUp}
          onMouseLeave={handleSvgMouseUp}
          style={{ minHeight: '300px' }}
        >
          {/* Page background */}
          <rect width="100" height="140" fill="white" stroke="#ddd" strokeWidth="0.5" />

          {/* Hotspots */}
          {hotspots.map((hotspot) => (
            <g key={hotspot.id}>
              {/* Main hotspot rectangle */}
              <rect
                x={hotspot.x_pos}
                y={hotspot.y_pos}
                width={hotspot.width}
                height={hotspot.height}
                fill={editingId === hotspot.id ? '#3b82f6' : '#60a5fa'}
                opacity={editingId === hotspot.id ? 0.3 : 0.15}
                stroke={editingId === hotspot.id ? '#1e40af' : '#3b82f6'}
                strokeWidth="0.3"
                className="cursor-move"
                onMouseDown={(e) => handleHotspotMouseDown(e, hotspot.id)}
              />

              {/* Show resize handle and close button only when editing */}
              {editingId === hotspot.id && (
                <>
                  {/* Resize handle (bottom-right corner) */}
                  <circle
                    cx={hotspot.x_pos + hotspot.width}
                    cy={hotspot.y_pos + hotspot.height}
                    r="1"
                    fill="#ef4444"
                    className="cursor-se-resize"
                    onMouseDown={(e) => handleHotspotMouseDown(e, hotspot.id, 'resize')}
                  />

                  {/* Delete button (top-right corner) */}
                  <g
                    className="cursor-pointer"
                    onMouseDown={(e) => handleDeleteHotspot(e, hotspot.id)}
                  >
                    <circle
                      cx={hotspot.x_pos + hotspot.width}
                      cy={hotspot.y_pos}
                      r="1.2"
                      fill="#ef4444"
                    />
                    <text
                      x={hotspot.x_pos + hotspot.width}
                      y={hotspot.y_pos + 0.4}
                      fontSize="1"
                      fill="white"
                      textAnchor="middle"
                      pointerEvents="none"
                    >
                      ✕
                    </text>
                  </g>

                  {/* Tooltip text */}
                  <text
                    x={hotspot.x_pos}
                    y={hotspot.y_pos - 0.5}
                    fontSize="0.8"
                    fill="#1e40af"
                    className="pointer-events-none"
                  >
                    {hotspot.tooltip || 'Hotspot'}
                  </text>
                </>
              )}
            </g>
          ))}

          {/* Creation preview */}
          {isCreating && startPos && (
            <rect
              x={startPos.x}
              y={startPos.y}
              width="5"
              height="5"
              fill="#10b981"
              opacity="0.3"
              stroke="#059669"
              strokeWidth="0.3"
              strokeDasharray="1,1"
            />
          )}
        </svg>
      </div>

      {/* Hotspot list */}
      {hotspots.length > 0 && (
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="font-semibold text-sm text-gray-900 mb-2">
            Active Hotspots ({hotspots.length})
          </h4>
          <div className="space-y-2">
            {hotspots.map((hotspot) => (
              <div
                key={hotspot.id}
                className={`flex items-center justify-between px-3 py-2 rounded text-sm ${
                  editingId === hotspot.id
                    ? 'bg-blue-100 border border-blue-300'
                    : 'bg-white border border-gray-200'
                }`}
                onClick={() => setEditingId(hotspot.id)}
              >
                <div>
                  <span className="font-medium">{hotspot.tooltip || 'Untitled'}</span>
                  <span className="text-xs text-gray-500 ml-2">
                    ({hotspot.x_pos.toFixed(1)}, {hotspot.y_pos.toFixed(1)})
                  </span>
                </div>
                <span className="text-xs bg-gray-200 px-2 py-1 rounded">
                  {ACTION_TYPES.find(t => t.value === hotspot.action_type)?.label || hotspot.action_type}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
