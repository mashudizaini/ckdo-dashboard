import React, { useState, useRef } from 'react';

const ACTION_TYPES = [
  { value: 'contact', label: 'Contact' },
  { value: 'link', label: 'Link' },
  { value: 'video', label: 'Video' },
  { value: 'form', label: 'Form' },
  { value: 'qrcode', label: 'QR Code' },
];

const ACTION_COLORS = {
  contact: '#a855f7',
  link: '#3b82f6',
  video: '#ef4444',
  form: '#22c55e',
  qrcode: '#f97316',
};

/**
 * Admin visual hotspot placement tool. Shows the actual rendered page image
 * as the background so placement is WYSIWYG, and positions/creates
 * hotspots as plain percentage-based <div>s (not SVG viewBox shapes) — the
 * same x_pos/y_pos/width/height-as-percent convention HotspotLayer.jsx (the
 * reader-facing overlay) uses, so a hotspot placed here lands in the exact
 * same spot there. The container's aspect ratio comes from the image's own
 * natural size (no forced CSS ratio), which is what a fixed viewBox used to
 * silently disagree with.
 */
export default function HotspotEditor({
  hotspots = [],
  editionId,
  pageNumber,
  imageUrl,
  onCreateHotspot,
  onUpdateHotspot,
  onDeleteHotspot,
  disabled = false,
}) {
  const containerRef = useRef(null);
  const [isCreating, setIsCreating] = useState(false);
  const [startPos, setStartPos] = useState(null);
  const [previewPos, setPreviewPos] = useState(null);
  const [draggingId, setDraggingId] = useState(null);
  const [draggingCorner, setDraggingCorner] = useState(null);
  const [dragStart, setDragStart] = useState(null);
  const [editingId, setEditingId] = useState(null);

  const posFromEvent = (e) => {
    const rect = containerRef.current.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100)),
      y: Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100)),
    };
  };

  const handleContainerMouseDown = (e) => {
    if (disabled || !containerRef.current) return;
    setIsCreating(true);
    const pos = posFromEvent(e);
    setStartPos(pos);
    setPreviewPos(pos);
    setEditingId(null);
  };

  const handleContainerMouseMove = (e) => {
    if (!containerRef.current) return;
    const pos = posFromEvent(e);

    if (isCreating && startPos) {
      setPreviewPos(pos);
    }

    if (draggingId && dragStart) {
      const deltaX = pos.x - dragStart.x;
      const deltaY = pos.y - dragStart.y;
      const hotspot = hotspots.find((h) => h.id === draggingId);
      if (!hotspot) return;

      if (draggingCorner === 'resize') {
        const newWidth = Math.max(2, Math.min(100 - hotspot.x_pos, hotspot.width + deltaX));
        const newHeight = Math.max(2, Math.min(100 - hotspot.y_pos, hotspot.height + deltaY));
        onUpdateHotspot(draggingId, { ...hotspot, width: newWidth, height: newHeight });
      } else {
        const newX = Math.max(0, Math.min(100 - hotspot.width, hotspot.x_pos + deltaX));
        const newY = Math.max(0, Math.min(100 - hotspot.height, hotspot.y_pos + deltaY));
        onUpdateHotspot(draggingId, { ...hotspot, x_pos: newX, y_pos: newY });
      }

      setDragStart(pos);
    }
  };

  const handleContainerMouseUp = (e) => {
    if (isCreating && startPos) {
      const pos = posFromEvent(e);
      const width = Math.abs(pos.x - startPos.x);
      const height = Math.abs(pos.y - startPos.y);

      if (width > 1.5 && height > 1.5) {
        const x = Math.min(startPos.x, pos.x);
        const y = Math.min(startPos.y, pos.y);

        onCreateHotspot({
          edition_id: editionId,
          page_number: pageNumber,
          x_pos: x,
          y_pos: y,
          width,
          height,
          action_type: 'contact',
          action_data: {},
          tooltip: 'New hotspot',
        });
      }

      setIsCreating(false);
      setStartPos(null);
      setPreviewPos(null);
    }

    if (draggingId) {
      setDraggingId(null);
      setDraggingCorner(null);
      setDragStart(null);
    }
  };

  const handleHotspotMouseDown = (e, hotspotId, corner = null) => {
    if (disabled) return;
    e.stopPropagation();
    setDraggingId(hotspotId);
    setDraggingCorner(corner);
    setDragStart(posFromEvent(e));
    setEditingId(hotspotId);
  };

  const handleDeleteHotspot = (e, hotspotId) => {
    e.stopPropagation();
    onDeleteHotspot?.(hotspotId);
  };

  const previewBox = isCreating && startPos && previewPos
    ? {
        left: Math.min(startPos.x, previewPos.x),
        top: Math.min(startPos.y, previewPos.y),
        width: Math.abs(previewPos.x - startPos.x),
        height: Math.abs(previewPos.y - startPos.y),
      }
    : null;

  return (
    <div className="space-y-4">
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
        <p className="text-sm text-yellow-800">
          <strong>Hotspot Editor:</strong> Click and drag on the page to create hotspots.
          Click on existing hotspots to edit or drag to move them.
        </p>
      </div>

      <div
        ref={containerRef}
        onMouseDown={handleContainerMouseDown}
        onMouseMove={handleContainerMouseMove}
        onMouseUp={handleContainerMouseUp}
        onMouseLeave={handleContainerMouseUp}
        className="relative border border-gray-300 rounded-lg overflow-hidden bg-gray-100"
        style={{ cursor: disabled ? 'default' : 'crosshair', userSelect: 'none' }}
      >
        {imageUrl ? (
          <img src={imageUrl} alt={`Page ${pageNumber}`} className="w-full h-auto block pointer-events-none" draggable={false} />
        ) : (
          <div className="flex items-center justify-center text-gray-400 text-sm" style={{ minHeight: 300 }}>
            Loading page image...
          </div>
        )}

        {hotspots.map((hotspot) => {
          const isEditing = editingId === hotspot.id;
          return (
            <div
              key={hotspot.id}
              onMouseDown={(e) => handleHotspotMouseDown(e, hotspot.id)}
              style={{
                position: 'absolute',
                left: `${hotspot.x_pos}%`,
                top: `${hotspot.y_pos}%`,
                width: `${hotspot.width}%`,
                height: `${hotspot.height}%`,
                background: ACTION_COLORS[hotspot.action_type] || '#60a5fa',
                opacity: isEditing ? 0.35 : 0.18,
                border: `2px solid ${isEditing ? '#1e40af' : ACTION_COLORS[hotspot.action_type] || '#3b82f6'}`,
                borderRadius: 4,
                cursor: 'move',
              }}
            >
              {isEditing && (
                <>
                  <div
                    onMouseDown={(e) => handleHotspotMouseDown(e, hotspot.id, 'resize')}
                    style={{
                      position: 'absolute', right: -6, bottom: -6, width: 12, height: 12,
                      borderRadius: '50%', background: '#ef4444', cursor: 'se-resize',
                    }}
                  />
                  <div
                    onMouseDown={(e) => handleDeleteHotspot(e, hotspot.id)}
                    style={{
                      position: 'absolute', right: -8, top: -8, width: 18, height: 18,
                      borderRadius: '50%', background: '#ef4444', color: 'white',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11, cursor: 'pointer', lineHeight: 1,
                    }}
                  >
                    ✕
                  </div>
                  {hotspot.tooltip && (
                    <span
                      style={{
                        position: 'absolute', bottom: '100%', left: 0, marginBottom: 4,
                        fontSize: 11, fontWeight: 600, color: '#1e40af',
                        background: 'white', padding: '1px 4px', borderRadius: 3,
                        whiteSpace: 'nowrap',
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

        {previewBox && (
          <div
            style={{
              position: 'absolute',
              left: `${previewBox.left}%`,
              top: `${previewBox.top}%`,
              width: `${previewBox.width}%`,
              height: `${previewBox.height}%`,
              background: 'rgba(16, 185, 129, 0.25)',
              border: '2px dashed #059669',
              pointerEvents: 'none',
            }}
          />
        )}
      </div>

      {hotspots.length > 0 && (
        <div className="bg-gray-50 rounded-lg p-4">
          <h4 className="font-semibold text-sm text-gray-900 mb-2">
            Active Hotspots ({hotspots.length})
          </h4>
          <div className="space-y-2">
            {hotspots.map((hotspot) => (
              <div
                key={hotspot.id}
                className={`flex items-center justify-between px-3 py-2 rounded text-sm cursor-pointer ${
                  editingId === hotspot.id
                    ? 'bg-blue-100 border border-blue-300'
                    : 'bg-white border border-gray-200'
                }`}
                onClick={() => setEditingId(hotspot.id)}
              >
                <div>
                  <span className="font-medium">{hotspot.tooltip || 'Untitled'}</span>
                  <span className="text-xs text-gray-500 ml-2">
                    ({hotspot.x_pos.toFixed(1)}%, {hotspot.y_pos.toFixed(1)}%)
                  </span>
                </div>
                <span className="text-xs bg-gray-200 px-2 py-1 rounded">
                  {ACTION_TYPES.find((t) => t.value === hotspot.action_type)?.label || hotspot.action_type}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
