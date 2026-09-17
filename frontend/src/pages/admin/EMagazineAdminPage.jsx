import React, { useState, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/Tabs';
import { BarChart3, Zap, BookOpen, Upload, Trash2, Images, Pencil } from 'lucide-react';
import emagazineAPI from '../../utils/emagazineApi';
import HotspotManager from '../../components/admin/HotspotManager';
import AnalyticsDashboard from '../../components/admin/AnalyticsDashboard';
import EditionUploader from '../../components/admin/EditionUploader';

export default function EMagazineAdminPage() {
  const [editions, setEditions] = useState([]);
  const [selectedEditionId, setSelectedEditionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('hotspots');
  const [editingEdition, setEditingEdition] = useState(null); // {id, title, edition_number, published_date}
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState('');

  useEffect(() => {
    loadEditions();
  }, []);

  const loadEditions = async () => {
    setLoading(true);
    try {
      const data = await emagazineAPI.getEditions();
      setEditions(data || []);
      if (data && data.length > 0) {
        // Keep the current selection if it still exists (e.g. after
        // uploading a second edition, don't yank focus away from what the
        // admin was editing) — only fall back to the first edition if the
        // previously-selected one is gone (deleted) or nothing was
        // selected yet.
        setSelectedEditionId((prev) => (data.some((e) => e.id === prev) ? prev : data[0].id));
      } else {
        setSelectedEditionId(null);
      }
    } catch (error) {
      console.error('Error loading editions:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleEditionUpload = async () => {
    await loadEditions();
  };

  const handleDeleteEdition = async (edition) => {
    if (!confirm(`Delete "${edition.title}" (Edition ${edition.edition_number})? This removes its pages, hotspots, and analytics too — this cannot be undone.`)) return;
    try {
      await emagazineAPI.deleteEdition(edition.id);
      if (editingEdition?.id === edition.id) setEditingEdition(null);
      await loadEditions();
    } catch (error) {
      alert(`Failed to delete edition: ${error.response?.data?.detail || error.message}`);
    }
  };

  const openEditEdition = (edition) => {
    setEditError('');
    setEditingEdition({
      id: edition.id,
      title: edition.title,
      edition_number: edition.edition_number,
      published_date: edition.published_date,
    });
  };

  const handleSaveEdition = async () => {
    if (!editingEdition) return;
    if (!editingEdition.title.trim()) { setEditError('Title cannot be empty.'); return; }
    setSavingEdit(true);
    setEditError('');
    try {
      await emagazineAPI.updateEdition(editingEdition.id, {
        title: editingEdition.title.trim(),
        edition_number: parseInt(editingEdition.edition_number, 10),
        published_date: editingEdition.published_date,
      });
      setEditingEdition(null);
      await loadEditions();
    } catch (error) {
      setEditError(error.response?.data?.detail || error.message || 'Failed to update edition.');
    } finally {
      setSavingEdit(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
            <BookOpen size={32} className="text-blue-600" />
            E-Magazine Admin
          </h1>
          <p className="text-gray-600 mt-2">Manage editions, hotspots, and analytics</p>
        </div>

        {/* Edition Selector */}
        {editions.length > 0 && (
          <div className="mb-6 bg-white border border-gray-200 rounded-lg p-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Select Edition
            </label>
            <select
              value={selectedEditionId || ''}
              onChange={(e) => setSelectedEditionId(parseInt(e.target.value))}
              className="w-full md:w-1/3 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              {editions.map((ed) => (
                <option key={ed.id} value={ed.id}>
                  {ed.edition_type === 'album' ? '[Album] ' : ''}
                  {ed.title} (Edition {ed.edition_number}) - {ed.total_pages} {ed.edition_type === 'album' ? 'photos' : 'pages'}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="bg-white border border-gray-200 rounded-lg">
          <TabsList className="border-b border-gray-200 px-6">
            <TabsTrigger value="hotspots" className="flex items-center gap-2">
              <Zap size={18} />
              Hotspots
            </TabsTrigger>
            <TabsTrigger value="analytics" className="flex items-center gap-2">
              <BarChart3 size={18} />
              Analytics
            </TabsTrigger>
            <TabsTrigger value="editions" className="flex items-center gap-2">
              <Upload size={18} />
              Editions
            </TabsTrigger>
          </TabsList>

          {/* Hotspots Tab */}
          <TabsContent value="hotspots" className="p-6">
            {selectedEditionId ? (
              <HotspotManager editionId={selectedEditionId} />
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-600">No editions available. Create one first.</p>
              </div>
            )}
          </TabsContent>

          {/* Analytics Tab */}
          <TabsContent value="analytics" className="p-6">
            {selectedEditionId ? (
              <AnalyticsDashboard editionId={selectedEditionId} />
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-600">No editions available.</p>
              </div>
            )}
          </TabsContent>

          {/* Editions Tab */}
          <TabsContent value="editions" className="p-6 space-y-8">
            {editions.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-3">Uploaded Editions</h3>
                <div className="space-y-2">
                  {editions.map((ed) => (
                    <div
                      key={ed.id}
                      className="bg-gray-50 border border-gray-200 rounded-lg"
                    >
                      <div className="flex items-center justify-between px-4 py-3">
                        <div>
                          <p className="text-sm font-medium text-gray-900 flex items-center gap-2">
                            {ed.edition_type === 'album' ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 text-purple-700 px-2 py-0.5 text-[10px] font-semibold">
                                <Images size={10} /> Album
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 text-blue-700 px-2 py-0.5 text-[10px] font-semibold">
                                <BookOpen size={10} /> Magazine
                              </span>
                            )}
                            {ed.title} <span className="text-gray-500">(Edition {ed.edition_number})</span>
                          </p>
                          <p className="text-xs text-gray-500 mt-0.5">
                            {ed.total_pages} {ed.edition_type === 'album' ? 'photos' : 'pages'} • Published {ed.published_date}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => editingEdition?.id === ed.id ? setEditingEdition(null) : openEditEdition(ed)}
                            className={`p-2 rounded transition ${
                              editingEdition?.id === ed.id ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-200'
                            }`}
                            title="Edit edition"
                          >
                            <Pencil size={18} />
                          </button>
                          <button
                            onClick={() => handleDeleteEdition(ed)}
                            className="p-2 text-red-600 hover:bg-red-50 rounded transition"
                            title="Delete edition"
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      </div>

                      {editingEdition?.id === ed.id && (
                        <div className="border-t border-gray-200 px-4 py-4 bg-white rounded-b-lg">
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <div className="md:col-span-2">
                              <label className="block text-xs font-medium text-gray-700 mb-1">Title</label>
                              <input
                                type="text"
                                value={editingEdition.title}
                                onChange={(e) => setEditingEdition((prev) => ({ ...prev, title: e.target.value }))}
                                className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-700 mb-1">Edition Number</label>
                              <input
                                type="number"
                                min="1"
                                value={editingEdition.edition_number}
                                onChange={(e) => setEditingEdition((prev) => ({ ...prev, edition_number: e.target.value }))}
                                className="w-full px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              />
                            </div>
                            <div className="md:col-span-3">
                              <label className="block text-xs font-medium text-gray-700 mb-1">
                                {ed.edition_type === 'album' ? 'Event Date' : 'Published Date'}
                              </label>
                              <input
                                type="date"
                                value={editingEdition.published_date}
                                onChange={(e) => setEditingEdition((prev) => ({ ...prev, published_date: e.target.value }))}
                                className="w-full md:w-1/3 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                              />
                            </div>
                          </div>

                          {editError && <p className="text-xs text-red-600 mt-2">{editError}</p>}

                          <div className="flex items-center gap-2 mt-3">
                            <button
                              onClick={handleSaveEdition}
                              disabled={savingEdit}
                              className="px-4 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition"
                            >
                              {savingEdit ? 'Saving…' : 'Save'}
                            </button>
                            <button
                              onClick={() => setEditingEdition(null)}
                              className="px-4 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 transition"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Upload New Edition</h3>
              <EditionUploader onUploadSuccess={handleEditionUpload} />
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
