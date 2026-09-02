import React, { useEffect, useState } from 'react';
import { useEMagazineStore } from '../../stores/emagazineStore';
import emagazineAPI from '../../utils/emagazineApi';
import HotspotLayer from './HotspotLayer';
import Modal from './Modal';
import ContactModal from './ContactModal';
import LinkModal from './LinkModal';
import VideoModal from './VideoModal';

export default function PageViewer() {
  const { currentPage, currentEditionId, setLoading } = useEMagazineStore();
  const [pageContent, setPageContent] = useState(null);
  const [hotspots, setHotspots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeModal, setActiveModal] = useState(null);
  const [modalData, setModalData] = useState(null);

  useEffect(() => {
    if (!currentEditionId) return;

    const loadPageContent = async () => {
      setLoading(true);
      setError(null);
      try {
        const content = await emagazineAPI.getPage(currentEditionId, currentPage);
        setPageContent(content);

        // Load hotspots for this page
        const hs = await emagazineAPI.getPageHotspots(currentEditionId, currentPage);
        setHotspots(hs || []);

        // Track page view
        await emagazineAPI.trackAnalytics(currentEditionId, 'page_view', {
          pageNumber: currentPage,
        });
      } catch (err) {
        console.error('Error loading page:', err);
        setError('Failed to load page content');
      } finally {
        setLoading(false);
      }
    };

    loadPageContent();
  }, [currentPage, currentEditionId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading page {currentPage}...</p>
        </div>
      </div>
    );
  }

  const handleHotspotClick = (hotspot) => {
    setModalData({
      actionType: hotspot.action_type,
      data: hotspot.action_data,
    });
    setActiveModal(hotspot.action_type);

    // Track analytics
    emagazineAPI.trackAnalytics(currentEditionId, 'hotspot_click', {
      pageNumber: currentPage,
      hotspotId: hotspot.id,
      actionType: hotspot.action_type,
    });
  };

  if (error) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <div className="text-center">
          <p className="text-red-600 font-semibold">{error}</p>
          <p className="text-gray-600 text-sm mt-2">Page {currentPage}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex-1 overflow-auto bg-gray-100">
        <div className="flex items-center justify-center min-h-full p-4">
          <div className="bg-white shadow-lg rounded-lg max-w-4xl w-full relative">
            {/* Page Header */}
            <div className="border-b border-gray-200 px-6 py-4 bg-gray-50">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">
                    {pageContent?.title || `Page ${currentPage}`}
                  </h2>
                  <p className="text-sm text-gray-600 mt-1">
                    {pageContent?.section_name} • Page {pageContent?.page_number}
                  </p>
                </div>
                {hotspots.length > 0 && (
                  <div className="text-xs text-gray-500 bg-blue-50 px-2 py-1 rounded">
                    {hotspots.length} interactive area{hotspots.length > 1 ? 's' : ''}
                  </div>
                )}
              </div>
            </div>

            {/* Page Content with Hotspots Overlay */}
            <div className="px-6 py-8 max-h-[70vh] overflow-y-auto relative">
              {pageContent?.searchable_text ? (
                <div className="prose prose-sm max-w-none relative">
                  {/* Hotspot Layer */}
                  {hotspots.length > 0 && (
                    <div className="absolute inset-0">
                      <HotspotLayer
                        hotspots={hotspots}
                        pageWidth={800}
                        pageHeight={1000}
                        onHotspotClick={handleHotspotClick}
                      />
                    </div>
                  )}

                  {/* Content Text */}
                  <div className="relative z-0">
                    {pageContent.searchable_text.split('\n').map((line, idx) => (
                      <p key={idx} className="text-gray-700 mb-2 leading-relaxed">
                        {line || <br />}
                      </p>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center text-gray-500 py-12">
                  <p>No content available for this page</p>
                </div>
              )}
            </div>

            {/* Page Footer */}
            <div className="border-t border-gray-200 px-6 py-4 bg-gray-50 text-center text-sm text-gray-600">
              Page {pageContent?.page_number}
              {hotspots.length > 0 && (
                <span className="ml-2 text-blue-600">
                  • Hover over highlighted areas to see details
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modals */}
      <ContactModal
        isOpen={activeModal === 'contact' || activeModal === 'profile'}
        onClose={() => setActiveModal(null)}
        data={modalData?.actionType === 'contact' || modalData?.actionType === 'profile' ? modalData?.data : null}
      />

      <LinkModal
        isOpen={activeModal === 'link'}
        onClose={() => setActiveModal(null)}
        data={modalData?.actionType === 'link' ? modalData?.data : null}
      />

      <VideoModal
        isOpen={activeModal === 'video'}
        onClose={() => setActiveModal(null)}
        data={modalData?.actionType === 'video' ? modalData?.data : null}
      />

      <Modal
        isOpen={activeModal === 'form'}
        onClose={() => setActiveModal(null)}
        title="Form"
        size="md"
      >
        <p className="text-gray-600">Form feature coming soon</p>
      </Modal>

      <Modal
        isOpen={activeModal === 'qrcode'}
        onClose={() => setActiveModal(null)}
        title="QR Code"
        size="sm"
      >
        <p className="text-gray-600">QR Code feature coming soon</p>
      </Modal>
    </>
  );
}
