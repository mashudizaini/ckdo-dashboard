import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useEMagazineStore } from '../stores/emagazineStore';
import emagazineAPI from '../utils/emagazineApi';
import NavigationBar from '../components/emagazine/NavigationBar';
import SearchBar from '../components/emagazine/SearchBar';
import TableOfContents from '../components/emagazine/TableOfContents';
import PageViewer from '../components/emagazine/PageViewer';

export default function EMagazinePage() {
  const [searchParams] = useSearchParams();
  const {
    editions,
    currentEditionId,
    setEditions,
    setCurrentEdition,
    setTableOfContents,
    setLoading,
    showSidebar,
    showSearch,
    error,
  } = useEMagazineStore();

  // Load editions on mount
  useEffect(() => {
    const loadEditions = async () => {
      setLoading(true);
      try {
        const data = await emagazineAPI.getEditions();
        setEditions(data);

        // Get edition from URL params or use first edition
        const editionParam = searchParams.get('edition');
        const edition = data.find((e) => e.id === parseInt(editionParam)) || data[0];

        if (edition) {
          setCurrentEdition(edition.id, edition.total_pages);

          // Load table of contents
          const toc = await emagazineAPI.getTableOfContents(edition.id);
          setTableOfContents(toc);
        }
      } catch (err) {
        console.error('Failed to load editions:', err);
      } finally {
        setLoading(false);
      }
    };

    loadEditions();
  }, []);

  if (!currentEditionId) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900 mb-4">E-Magazine</h1>
          <p className="text-gray-600">No editions available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* Navigation Bar */}
      <NavigationBar />

      {/* Search Bar (conditional) */}
      {showSearch && <SearchBar />}

      {/* Main Content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar - Table of Contents */}
        {showSidebar && (
          <div className="w-64 border-r border-gray-200 hidden md:block">
            <TableOfContents />
          </div>
        )}

        {/* Page Viewer */}
        <PageViewer />
      </div>

      {/* Error Message */}
      {error && (
        <div className="fixed bottom-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded shadow-lg">
          {error}
        </div>
      )}
    </div>
  );
}
