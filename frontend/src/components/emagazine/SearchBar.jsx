import React, { useState } from 'react';
import { Search, X } from 'lucide-react';
import { useEMagazineStore } from '../../stores/emagazineStore';
import emagazineAPI from '../../utils/emagazineApi';

export default function SearchBar() {
  const { searchQuery, setSearchQuery, setSearchResults, setCurrentPage, currentEditionId } =
    useEMagazineStore();
  const [isSearching, setIsSearching] = useState(false);

  const handleSearch = async (e) => {
    e.preventDefault();

    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }

    setIsSearching(true);
    try {
      const results = await emagazineAPI.search(searchQuery, currentEditionId);
      setSearchResults(results);
    } catch (error) {
      console.error('Search failed:', error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleResultClick = (pageNumber) => {
    setCurrentPage(pageNumber);
    setSearchResults([]);
    setSearchQuery('');
  };

  const handleClearSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
  };

  return (
    <div className="bg-white border-b border-gray-200 px-4 py-3">
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="flex-1 relative">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <Search size={18} />
          </div>
          <input
            type="text"
            placeholder="Search content..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
          />
          {searchQuery && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X size={18} />
            </button>
          )}
        </div>
        <button
          type="submit"
          disabled={isSearching}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
        >
          {isSearching ? 'Searching...' : 'Search'}
        </button>
      </form>

      {/* Search Results */}
      <div className="mt-3 space-y-2 max-h-96 overflow-y-auto">
        {useEMagazineStore((state) => state.searchResults).map((result) => (
          <button
            key={result.content_id}
            onClick={() => handleResultClick(result.page_number)}
            className="w-full text-left p-3 bg-gray-50 hover:bg-blue-50 rounded border border-gray-200 hover:border-blue-300 transition group"
          >
            <div className="flex justify-between items-start gap-2">
              <div className="flex-1">
                <p className="font-semibold text-sm group-hover:text-blue-600">
                  {result.title}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {result.section_name} • Page {result.page_number}
                </p>
              </div>
            </div>
            <p className="text-xs text-gray-600 mt-2 line-clamp-2">
              {result.snippet}
            </p>
          </button>
        ))}

        {useEMagazineStore((state) => state.searchResults).length === 0 &&
          searchQuery &&
          !isSearching && (
            <p className="text-sm text-gray-500 text-center py-4">
              No results found for "{searchQuery}"
            </p>
          )}
      </div>
    </div>
  );
}
