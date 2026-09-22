import React from 'react';
import { QRCodeSVG } from 'qrcode.react';
import Modal from './Modal';

export default function QrCodeModal({ isOpen, onClose, data }) {
  if (!data) return null;

  const { label, description, value } = data;

  if (!value) {
    return (
      <Modal isOpen={isOpen} title="QR Code" onClose={onClose} size="sm">
        <p className="text-gray-600">QR code not available</p>
      </Modal>
    );
  }

  return (
    <Modal isOpen={isOpen} title={label || 'QR Code'} onClose={onClose} size="sm">
      <div className="space-y-4">
        {description && (
          <p className="text-sm text-gray-700">{description}</p>
        )}

        <div className="flex justify-center p-4 bg-gray-50 rounded">
          <QRCodeSVG value={value} size={180} level="H" includeMargin={true} />
        </div>

        <p className="text-xs text-gray-500 text-center break-all">{value}</p>
      </div>
    </Modal>
  );
}
