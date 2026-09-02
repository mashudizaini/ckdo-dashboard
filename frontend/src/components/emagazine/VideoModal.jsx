import React from 'react';
import { PlayCircle } from 'lucide-react';
import Modal from './Modal';

export default function VideoModal({ isOpen, onClose, data }) {
  if (!data) return null;

  const { title, description, videoUrl, videoId, provider = 'youtube' } = data;

  // Construct embed URL based on provider
  let embedUrl = '';
  if (provider === 'youtube' && videoId) {
    embedUrl = `https://www.youtube.com/embed/${videoId}`;
  } else if (provider === 'vimeo' && videoId) {
    embedUrl = `https://player.vimeo.com/video/${videoId}`;
  } else if (videoUrl) {
    embedUrl = videoUrl;
  }

  if (!embedUrl) {
    return (
      <Modal isOpen={isOpen} title="Video" onClose={onClose}>
        <p className="text-gray-600">Video not available</p>
      </Modal>
    );
  }

  return (
    <Modal isOpen={isOpen} title={title || 'Video'} onClose={onClose} size="lg">
      <div className="space-y-4">
        {/* Video Embed */}
        <div className="relative w-full bg-black rounded overflow-hidden" style={{ paddingBottom: '56.25%' }}>
          <iframe
            className="absolute top-0 left-0 w-full h-full"
            src={embedUrl}
            title={title}
            allowFullScreen
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          />
        </div>

        {/* Description */}
        {description && (
          <div>
            <h3 className="font-semibold text-gray-900 mb-2">{title}</h3>
            <p className="text-sm text-gray-700 leading-relaxed">{description}</p>
          </div>
        )}
      </div>
    </Modal>
  );
}
