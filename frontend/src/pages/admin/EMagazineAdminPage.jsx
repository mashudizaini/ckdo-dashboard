import React, { useState, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/Tabs';
import { BarChart3, Zap, BookOpen, Upload, Trash2 } from 'lucide-react';
import emagazineAPI from '../../utils/emagazineApi';
import HotspotManager from '../../components/admin/HotspotManager';
import AnalyticsDashboard from '../../components/admin/AnalyticsDashboard';
import EditionUploader from '../../components/admin/EditionUploader';

export default function EMagazineAdminPage() {
  const [editions, setEditions] = useState([]);
  const [selectedEditionId, setSelectedEditionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('hotspots');

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
      await loadEditions();
    } catch (error) {
      alert(`Failed to delete edition: ${error.response?.data?.detail || error.message}`);
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
                  {ed.title} (Edition {ed.edition_number}) - {ed.total_pages} pages
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
                      className="flex items-center justify-between px-4 py-3 bg-gray-50 border border-gray-200 rounded-lg"
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {ed.title} <span className="text-gray-500">(Edition {ed.edition_number})</span>
                        </p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          {ed.total_pages} pages • Published {ed.published_date}
                        </p>
                      </div>
                      <button
                        onClick={() => handleDeleteEdition(ed)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded transition"
                        title="Delete edition"
                      >
                        <Trash2 size={18} />
                      </button>
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
