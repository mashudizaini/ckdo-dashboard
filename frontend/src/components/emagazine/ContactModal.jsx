import React from 'react';
import { Mail, Phone, MapPin, Globe, QrCode } from 'lucide-react';
import Modal from './Modal';
import QRCode from 'qrcode.react';

export default function ContactModal({ isOpen, onClose, data }) {
  if (!data) return null;

  const { name, title, email, phone, address, website, bio } = data;

  const handleEmailClick = () => {
    if (email) {
      window.location.href = `mailto:${email}`;
    }
  };

  const handlePhoneClick = () => {
    if (phone) {
      window.location.href = `tel:${phone}`;
    }
  };

  const qrValue = email || name || 'Contact';

  return (
    <Modal isOpen={isOpen} title="Contact" onClose={onClose} size="md">
      <div className="space-y-4">
        {/* Profile Header */}
        {name && (
          <div>
            <h3 className="text-lg font-bold text-gray-900">{name}</h3>
            {title && <p className="text-sm text-gray-600">{title}</p>}
          </div>
        )}

        {/* Bio */}
        {bio && (
          <p className="text-sm text-gray-700 leading-relaxed">{bio}</p>
        )}

        {/* Contact Info */}
        <div className="space-y-2 border-t border-gray-200 pt-4">
          {email && (
            <button
              onClick={handleEmailClick}
              className="w-full flex items-center gap-3 p-3 hover:bg-blue-50 rounded transition"
            >
              <Mail size={18} className="text-blue-600 shrink-0" />
              <span className="text-sm text-blue-600 hover:underline">{email}</span>
            </button>
          )}

          {phone && (
            <button
              onClick={handlePhoneClick}
              className="w-full flex items-center gap-3 p-3 hover:bg-blue-50 rounded transition"
            >
              <Phone size={18} className="text-blue-600 shrink-0" />
              <span className="text-sm text-blue-600 hover:underline">{phone}</span>
            </button>
          )}

          {address && (
            <div className="flex items-start gap-3 p-3">
              <MapPin size={18} className="text-gray-600 shrink-0 mt-1" />
              <span className="text-sm text-gray-700">{address}</span>
            </div>
          )}

          {website && (
            <a
              href={website}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 p-3 hover:bg-blue-50 rounded transition"
            >
              <Globe size={18} className="text-blue-600 shrink-0" />
              <span className="text-sm text-blue-600 hover:underline">{website}</span>
            </a>
          )}
        </div>

        {/* QR Code */}
        {email && (
          <div className="border-t border-gray-200 pt-4">
            <div className="flex items-center gap-2 mb-3">
              <QrCode size={16} className="text-gray-600" />
              <p className="text-xs text-gray-600">Scan to contact</p>
            </div>
            <div className="flex justify-center p-4 bg-gray-50 rounded">
              <QRCode
                value={`mailto:${email}`}
                size={120}
                level="H"
                includeMargin={true}
              />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
