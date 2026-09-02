import React from 'react';
import { ExternalLink, Copy, Check } from 'lucide-react';
import Modal from './Modal';

export default function LinkModal({ isOpen, onClose, data }) {
  const [copied, setCopied] = React.useState(false);

  if (!data) return null;

  const { title, description, url } = data;

  const handleCopy = () => {
    navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenLink = () => {
    if (url) {
      window.open(url, '_blank');
    }
  };

  return (
    <Modal isOpen={isOpen} title={title || 'Link'} onClose={onClose} size="md">
      <div className="space-y-4">
        {description && (
          <p className="text-sm text-gray-700">{description}</p>
        )}

        <div className="bg-gray-50 rounded p-4 break-all text-xs text-gray-600">
          {url}
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleOpenLink}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
          >
            <ExternalLink size={16} />
            Open Link
          </button>

          <button
            onClick={handleCopy}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition font-medium"
          >
            {copied ? (
              <>
                <Check size={16} />
                Copied
              </>
            ) : (
              <>
                <Copy size={16} />
                Copy
              </>
            )}
          </button>
        </div>
      </div>
    </Modal>
  );
}
