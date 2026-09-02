import React, { useState, useEffect } from 'react';
import { Trash2, Edit, Plus, X, ChevronDown, ChevronUp, Paintbrush } from 'lucide-react';
import emagazineAPI from '../../utils/emagazineApi';
import HotspotEditor from '../emagazine/HotspotEditor';

const ACTION_TYPES = [
  { value: 'contact', label: 'Contact', color: 'bg-purple-100 text-purple-700' },
  { value: 'link', label: 'Link', color: 'bg-blue-100 text-blue-700' },
  { value: 'video', label: 'Video', color: 'bg-red-100 text-red-700' },
  { value: 'form', label: 'Form', color: 'bg-green-100 text-green-700' },
  { value: 'qrcode', label: 'QR Code', color: 'bg-orange-100 text-orange-700' },
];

export default function HotspotManager({ editionId }) {
  const [hotspots, setHotspots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [expandedPages, setExpandedPages] = useState({});
  const [formData, setFormData] = useState(null);
  const [editorMode, setEditorMode] = useState('list'); // 'list' or 'visual'
  const [editorPage, setEditorPage] = useState(1);
  const [editorImageUrl, setEditorImageUrl] = useState(null);

  useEffect(() => {
    loadHotspots();
  }, [editionId]);

  // Visual editor needs the actual page image as its background — fetch
  // it whenever the edition or the page being edited changes.
  useEffect(() => {
    if (editorMode !== 'visual' || !editionId) return;
    setEditorImageUrl(null);
    emagazineAPI
      .getPage(editionId, editorPage)
      .then((page) => setEditorImageUrl(page?.image_path || null))
      .catch((error) => console.error('Error loading page image:', error));
  }, [editorMode, editionId, editorPage]);

  const loadHotspots = async () => {
    if (!editionId) return;
    setLoading(true);
    try {
      const data = await emagazineAPI.getEditionHotspots(editionId);
      setHotspots(data || []);
    } catch (error) {
      console.error('Error loading hotspots:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleNewHotspot = () => {
    setFormData({
      edition_id: editionId,
      page_number: 1,
      x_pos: 0,
      y_pos: 0,
      width: 100,
      height: 50,
      action_type: 'contact',
      action_data: {},
      tooltip: '',
    });
    setEditingId('new');
  };

  const handleEdit = (hotspot) => {
    setFormData({ ...hotspot });
    setEditingId(hotspot.id);
  };

  const handleSave = async () => {
    try {
      if (editingId === 'new') {
        await emagazineAPI.createHotspot(editionId, formData);
      } else {
        await emagazineAPI.updateHotspot(editingId, formData);
      }
      setFormData(null);
      setEditingId(null);
      await loadHotspots();
    } catch (error) {
      console.error('Error saving hotspot:', error);
      alert('Failed to save hotspot');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this hotspot?')) return;
    try {
      await emagazineAPI.deleteHotspot(id);
      await loadHotspots();
    } catch (error) {
      console.error('Error deleting hotspot:', error);
      alert('Failed to delete hotspot');
    }
  };

  const togglePage = (pageNum) => {
    setExpandedPages((prev) => ({
      ...prev,
      [pageNum]: !prev[pageNum],
    }));
  };

  const groupedByPage = hotspots.reduce((acc, hs) => {
    if (!acc[hs.page_number]) acc[hs.page_number] = [];
    acc[hs.page_number].push(hs);
    return acc;
  }, {});

  const sortedPages = Object.keys(groupedByPage).sort((a, b) => a - b);

  if (loading) {
    return <div className="text-center py-8">Loading hotspots...</div>;
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Hotspots</h2>
          <p className="text-sm text-gray-600 mt-1">
            {hotspots.length} total hotspot{hotspots.length !== 1 ? 's' : ''}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setEditorMode(editorMode === 'list' ? 'visual' : 'list')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition font-medium ${
              editorMode === 'visual'
                ? 'bg-purple-600 text-white hover:bg-purple-700'
                : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
            }`}
          >
            <Paintbrush size={18} />
            {editorMode === 'visual' ? 'Visual Editor' : 'Edit List'}
          </button>
          {editorMode === 'list' && (
            <button
              onClick={handleNewHotspot}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
            >
              <Plus size={18} />
              New Hotspot
            </button>
          )}
        </div>
      </div>

      {/* Visual Editor Mode */}
      {editorMode === 'visual' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input
              type="number"
              min="1"
              value={editorPage}
              onChange={(e) => setEditorPage(parseInt(e.target.value) || 1)}
              className="w-20 px-3 py-2 border border-gray-300 rounded-lg text-sm"
              placeholder="Page #"
            />
            <span className="py-2 text-sm text-gray-600">
              Page {editorPage}
            </span>
          </div>
          <HotspotEditor
            hotspots={hotspots.filter(h => h.page_number === editorPage)}
            editionId={editionId}
            pageNumber={editorPage}
            imageUrl={editorImageUrl}
            onCreateHotspot={(hotspotData) => {
              setFormData(hotspotData);
              setEditingId('new');
              setEditorMode('list');
            }}
            onUpdateHotspot={(hotspotId, hotspotData) => {
              setFormData(hotspotData);
              setEditingId(hotspotId);
              setEditorMode('list');
            }}
            onDeleteHotspot={handleDelete}
          />
        </div>
      )}

      {/* Form */}
      {editingId && editorMode === 'list' && (
        <HotspotForm
          data={formData}
          setData={setFormData}
          onSave={handleSave}
          onCancel={() => {
            setFormData(null);
            setEditingId(null);
          }}
        />
      )}

      {/* Hotspots by Page */}
      {editorMode === 'list' && (
      <div className="space-y-3">
        {sortedPages.length === 0 ? (
          <div className="text-center py-8 bg-gray-50 rounded-lg">
            <p className="text-gray-600">No hotspots yet. Create one to get started!</p>
          </div>
        ) : (
          sortedPages.map((pageNum) => (
            <div key={pageNum} className="border border-gray-200 rounded-lg overflow-hidden">
              {/* Page Header */}
              <button
                onClick={() => togglePage(pageNum)}
                className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition"
              >
                <div>
                  <h3 className="font-semibold text-gray-900">Page {pageNum}</h3>
                  <p className="text-sm text-gray-600">
                    {groupedByPage[pageNum].length} hotspot{groupedByPage[pageNum].length !== 1 ? 's' : ''}
                  </p>
                </div>
                {expandedPages[pageNum] ? (
                  <ChevronUp size={20} />
                ) : (
                  <ChevronDown size={20} />
                )}
              </button>

              {/* Hotspots List */}
              {expandedPages[pageNum] && (
                <div className="divide-y divide-gray-200">
                  {groupedByPage[pageNum].map((hs) => (
                    <HotspotRow
                      key={hs.id}
                      hotspot={hs}
                      onEdit={handleEdit}
                      onDelete={handleDelete}
                    />
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
      )}
    </div>
  );
}

function HotspotRow({ hotspot, onEdit, onDelete }) {
  const actionType = ACTION_TYPES.find((a) => a.value === hotspot.action_type);

  return (
    <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-50">
      <div className="flex-1">
        <div className="flex items-center gap-3">
          {actionType && <span className={`px-2 py-1 rounded text-xs font-semibold ${actionType.color}`}>
            {actionType.label}
          </span>}
          <span className="text-sm font-medium text-gray-900">{hotspot.tooltip || 'No tooltip'}</span>
        </div>
        <div className="text-xs text-gray-500 mt-1">
          Position: ({hotspot.x_pos}, {hotspot.y_pos}) • Size: {hotspot.width}×{hotspot.height}
        </div>
      </div>

      <div className="flex items-center gap-2 ml-4">
        <button
          onClick={() => onEdit(hotspot)}
          className="p-2 text-blue-600 hover:bg-blue-50 rounded transition"
          title="Edit"
        >
          <Edit size={18} />
        </button>
        <button
          onClick={() => onDelete(hotspot.id)}
          className="p-2 text-red-600 hover:bg-red-50 rounded transition"
          title="Delete"
        >
          <Trash2 size={18} />
        </button>
      </div>
    </div>
  );
}

function HotspotForm({ data, setData, onSave, onCancel }) {
  if (!data) return null;

  const handleActionDataChange = (key, value) => {
    setData({
      ...data,
      action_data: {
        ...data.action_data,
        [key]: value,
      },
    });
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-6">
      <h3 className="text-lg font-bold text-gray-900">
        {data.id ? 'Edit Hotspot' : 'New Hotspot'}
      </h3>

      {/* Position & Size */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Page
          </label>
          <input
            type="number"
            min="1"
            value={data.page_number}
            onChange={(e) => setData({ ...data, page_number: parseInt(e.target.value) })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">X</label>
          <input
            type="number"
            value={data.x_pos}
            onChange={(e) => setData({ ...data, x_pos: parseFloat(e.target.value) })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Y</label>
          <input
            type="number"
            value={data.y_pos}
            onChange={(e) => setData({ ...data, y_pos: parseFloat(e.target.value) })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Width</label>
          <input
            type="number"
            value={data.width}
            onChange={(e) => setData({ ...data, width: parseFloat(e.target.value) })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
        <div className="md:col-span-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">Height</label>
          <input
            type="number"
            value={data.height}
            onChange={(e) => setData({ ...data, height: parseFloat(e.target.value) })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
      </div>

      {/* Action Type & Tooltip */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Action Type
          </label>
          <select
            value={data.action_type}
            onChange={(e) => setData({ ...data, action_type: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          >
            {ACTION_TYPES.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Tooltip
          </label>
          <input
            type="text"
            placeholder="Hover text"
            value={data.tooltip}
            onChange={(e) => setData({ ...data, tooltip: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
      </div>

      {/* Action Data (Dynamic based on type) */}
      <div>
        <h4 className="font-semibold text-gray-900 mb-3">Action Data</h4>
        {data.action_type === 'contact' && (
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Name"
              value={data.action_data.name || ''}
              onChange={(e) => handleActionDataChange('name', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              type="email"
              placeholder="Email"
              value={data.action_data.email || ''}
              onChange={(e) => handleActionDataChange('email', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              type="tel"
              placeholder="Phone"
              value={data.action_data.phone || ''}
              onChange={(e) => handleActionDataChange('phone', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <textarea
              placeholder="Bio"
              value={data.action_data.bio || ''}
              onChange={(e) => handleActionDataChange('bio', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              rows="2"
            />
          </div>
        )}
        {data.action_type === 'link' && (
          <div className="space-y-3">
            <input
              type="url"
              placeholder="URL"
              value={data.action_data.url || ''}
              onChange={(e) => handleActionDataChange('url', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <textarea
              placeholder="Description"
              value={data.action_data.description || ''}
              onChange={(e) => handleActionDataChange('description', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              rows="2"
            />
          </div>
        )}
        {data.action_type === 'video' && (
          <div className="space-y-3">
            <select
              value={data.action_data.provider || 'youtube'}
              onChange={(e) => handleActionDataChange('provider', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              <option value="youtube">YouTube</option>
              <option value="vimeo">Vimeo</option>
            </select>
            <input
              type="text"
              placeholder="Video ID (e.g., dQw4w9WgXcQ)"
              value={data.action_data.videoId || ''}
              onChange={(e) => handleActionDataChange('videoId', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <textarea
              placeholder="Description"
              value={data.action_data.description || ''}
              onChange={(e) => handleActionDataChange('description', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              rows="2"
            />
          </div>
        )}
        {data.action_type === 'qrcode' && (
          <div className="space-y-3">
            <input
              type="text"
              placeholder="Value to encode (URL or text)"
              value={data.action_data.value || ''}
              onChange={(e) => handleActionDataChange('value', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <input
              type="text"
              placeholder="Label (modal title)"
              value={data.action_data.label || ''}
              onChange={(e) => handleActionDataChange('label', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            />
            <textarea
              placeholder="Description"
              value={data.action_data.description || ''}
              onChange={(e) => handleActionDataChange('description', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              rows="2"
            />
          </div>
        )}
      </div>

      {/* Buttons */}
      <div className="flex gap-3 pt-4 border-t border-gray-200">
        <button
          onClick={onSave}
          className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
        >
          Save
        </button>
        <button
          onClick={onCancel}
          className="flex-1 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition font-medium"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
