import React from 'react';
import { ChevronLeft, ChevronRight, Menu, Search, Download, Printer, Share2 } from 'lucide-react';
import { useEMagazineStore } from '../../stores/emagazineStore';

export default function NavigationBar() {
  const {
    currentPage,
    totalPages,
    setCurrentPage,
    prevPage,
    nextPage,
    toggleSidebar,
    toggleSearch,
    currentEditionId,
    currentPageImage,
  } = useEMagazineStore();
  const [downloading, setDownloading] = React.useState(false);

  const handlePageChange = (e) => {
    const page = parseInt(e.target.value);
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  const handleDownload = async () => {
    if (!currentPageImage?.path) return;
    setDownloading(true);
    try {
      const res = await fetch(currentPageImage.path);
      const blob = await res.blob();
      const ext = currentPageImage.path.split('.').pop().split('?')[0] || 'jpg';
      const safeName = (currentPageImage.title || `page-${currentPage}`).replace(/[^\w\- ]+/g, '').trim() || `page-${currentPage}`;

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${safeName}.${ext}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed:', err);
      alert('Failed to download this page.');
    } finally {
      setDownloading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleShare = () => {
    const url = `${window.location.origin}/e-magazine-viewer?edition=${currentEditionId}&page=${currentPage}`;
    navigator.clipboard.writeText(url);
    alert('Link copied to clipboard!');
  };

  return (
    <div className="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-40">
      <div className="flex items-center justify-between px-4 py-3 gap-4">
        {/* Left Section - Navigation */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleSidebar}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            title="Toggle sidebar"
          >
            <Menu size={20} />
          </button>

          <button
            onClick={prevPage}
            disabled={currentPage === 1}
            className="p-2 hover:bg-gray-100 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            title="Previous page"
          >
            <ChevronLeft size={20} />
          </button>

          <button
            onClick={nextPage}
            disabled={currentPage === totalPages}
            className="p-2 hover:bg-gray-100 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            title="Next page"
          >
            <ChevronRight size={20} />
          </button>
        </div>

        {/* Center Section - Page Info */}
        <div className="flex items-center gap-2">
          <input
            type="number"
            min="1"
            max={totalPages}
            value={currentPage}
            onChange={handlePageChange}
            className="w-16 px-2 py-1 border border-gray-300 rounded text-center text-sm"
          />
          <span className="text-sm text-gray-600">
            of {totalPages}
          </span>
        </div>

        {/* Right Section - Tools */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleSearch}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            title="Search"
          >
            <Search size={20} />
          </button>

          <button
            onClick={handleDownload}
            disabled={!currentPageImage?.path || downloading}
            className="p-2 hover:bg-gray-100 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
            title="Download this page"
          >
            <Download size={20} className={downloading ? 'animate-pulse' : ''} />
          </button>

          <button
            onClick={handlePrint}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            title="Print"
          >
            <Printer size={20} />
          </button>

          <button
            onClick={handleShare}
            className="p-2 hover:bg-gray-100 rounded-lg transition"
            title="Share"
          >
            <Share2 size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
