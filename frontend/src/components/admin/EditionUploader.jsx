import React, { useState } from 'react';
import { Upload, AlertCircle, CheckCircle, BookOpen, Images, X } from 'lucide-react';
import emagazineAPI from '../../utils/emagazineApi';

export default function EditionUploader({ onUploadSuccess, initialType = 'magazine' }) {
  const [editionType, setEditionType] = useState(initialType); // 'magazine' | 'album'
  const [formData, setFormData] = useState({
    title: '',
    edition_number: '',
    published_date: '',
  });
  const [selectedFile, setSelectedFile] = useState(null);     // magazine: single PDF
  const [selectedPhotos, setSelectedPhotos] = useState([]);   // album: multiple images
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const switchType = (type) => {
    setEditionType(type);
    setMessage(null);
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setMessage(null);
    } else {
      setMessage({
        type: 'error',
        text: 'Please select a valid PDF file',
      });
    }
  };

  const ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

  const handlePhotosSelect = (e) => {
    const files = Array.from(e.target.files || []);
    const invalid = files.filter((f) => !ALLOWED_PHOTO_TYPES.includes(f.type));
    if (invalid.length > 0) {
      setMessage({
        type: 'error',
        text: `${invalid.map((f) => f.name).join(', ')} — only JPEG, PNG, or WebP photos are supported`,
      });
      return;
    }
    setSelectedPhotos((prev) => [...prev, ...files]);
    setMessage(null);
    e.target.value = ''; // allow re-selecting the same file(s) again
  };

  const removePhoto = (idx) => setSelectedPhotos((prev) => prev.filter((_, i) => i !== idx));

  const resetForm = () => {
    setFormData({ title: '', edition_number: '', published_date: '' });
    setSelectedFile(null);
    setSelectedPhotos([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.title || !formData.published_date) {
      setMessage({ type: 'error', text: 'Please fill in all fields' });
      return;
    }

    if (editionType === 'magazine') {
      if (!selectedFile) {
        setMessage({ type: 'error', text: 'Please select a PDF file' });
        return;
      }
      if (!formData.edition_number) {
        setMessage({ type: 'error', text: 'Please fill in all fields' });
        return;
      }
    } else if (selectedPhotos.length === 0) {
      setMessage({ type: 'error', text: 'Please select at least one photo' });
      return;
    }

    setLoading(true);
    setMessage(null);

    try {
      let result;
      if (editionType === 'magazine') {
        const uploadFormData = new FormData();
        uploadFormData.append('title', formData.title);
        uploadFormData.append('edition_number', formData.edition_number);
        uploadFormData.append('published_date', formData.published_date);
        uploadFormData.append('file', selectedFile);
        result = await emagazineAPI.uploadEdition(uploadFormData);
        setMessage({
          type: 'success',
          text: `Edition uploaded successfully! ${result.total_pages} pages parsed and indexed.`,
        });
      } else {
        const uploadFormData = new FormData();
        uploadFormData.append('title', formData.title);
        uploadFormData.append('published_date', formData.published_date);
        selectedPhotos.forEach((photo) => uploadFormData.append('photos', photo));
        result = await emagazineAPI.uploadAlbum(uploadFormData);
        setMessage({
          type: 'success',
          text: `Album uploaded successfully! ${result.total_pages} photos added.`,
        });
      }

      resetForm();
      if (onUploadSuccess) onUploadSuccess();
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to upload';
      setMessage({
        type: 'error',
        text: errorMsg,
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl">
      {/* Edition type toggle */}
      <div className="flex gap-2 mb-6">
        <button
          type="button"
          onClick={() => switchType('magazine')}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition ${
            editionType === 'magazine'
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          <BookOpen size={16} /> Magazine (PDF)
        </button>
        <button
          type="button"
          onClick={() => switchType('album')}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition ${
            editionType === 'album'
              ? 'bg-blue-600 border-blue-600 text-white'
              : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          <Images size={16} /> Photo Album (Photos)
        </button>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <div className="flex gap-3">
          <div className="text-blue-600 mt-0.5">
            <AlertCircle size={20} />
          </div>
          <div>
            <h4 className="font-semibold text-blue-900">
              {editionType === 'magazine' ? 'How to Upload a New Edition' : 'How to Create a Photo Album'}
            </h4>
            <ol className="text-sm text-blue-800 mt-2 space-y-1 ml-4 list-decimal">
              {editionType === 'magazine' ? (
                <>
                  <li>Fill in the edition details below</li>
                  <li>Select the PDF file (max 50MB)</li>
                  <li>Click Upload to parse and import content</li>
                  <li>View analytics and manage hotspots once uploaded</li>
                </>
              ) : (
                <>
                  <li>Give the album a title and a date</li>
                  <li>Select all the event photos (JPEG/PNG/WebP, max 20MB each)</li>
                  <li>Click Upload — photos appear in the order selected</li>
                  <li>Viewers can flip through and download each photo, same as a magazine</li>
                </>
              )}
            </ol>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white border border-gray-200 rounded-lg p-6">
        {/* Form Fields */}
        <div className="grid grid-cols-2 gap-4">
          <div className={editionType === 'album' ? 'col-span-2' : ''}>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {editionType === 'magazine' ? 'Edition Title' : 'Album Title'}
            </label>
            <input
              type="text"
              name="title"
              value={formData.title}
              onChange={handleInputChange}
              placeholder={editionType === 'magazine' ? 'e.g., CKD OTTO E-Magazine 4th Edition' : 'e.g., Company Anniversary 2026'}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {editionType === 'magazine' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Edition Number
              </label>
              <input
                type="number"
                name="edition_number"
                value={formData.edition_number}
                onChange={handleInputChange}
                placeholder="e.g., 4"
                min="1"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          )}

          <div className="col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              {editionType === 'magazine' ? 'Published Date' : 'Event Date'}
            </label>
            <input
              type="date"
              name="published_date"
              value={formData.published_date}
              onChange={handleInputChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>

        {editionType === 'magazine' ? (
          /* PDF File Upload */
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">
              PDF File
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 hover:bg-blue-50 transition cursor-pointer">
              <input
                type="file"
                accept=".pdf"
                onChange={handleFileSelect}
                className="hidden"
                id="pdf-upload"
                disabled={loading}
              />
              <label htmlFor="pdf-upload" className="cursor-pointer block">
                <div className="flex justify-center mb-3">
                  <Upload size={32} className="text-gray-400" />
                </div>
                <p className="text-sm font-medium text-gray-900">
                  {selectedFile ? selectedFile.name : 'Click to select PDF or drag and drop'}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  PDF files up to 50MB supported
                </p>
              </label>
            </div>
          </div>
        ) : (
          /* Photo Upload */
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Photos ({selectedPhotos.length} selected)
            </label>
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 hover:bg-blue-50 transition cursor-pointer">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                onChange={handlePhotosSelect}
                className="hidden"
                id="photos-upload"
                disabled={loading}
              />
              <label htmlFor="photos-upload" className="cursor-pointer block">
                <div className="flex justify-center mb-3">
                  <Images size={32} className="text-gray-400" />
                </div>
                <p className="text-sm font-medium text-gray-900">
                  Click to select photos or drag and drop
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  JPEG, PNG, or WebP, up to 20MB each — select multiple at once
                </p>
              </label>
            </div>

            {selectedPhotos.length > 0 && (
              <div className="mt-4 grid grid-cols-4 sm:grid-cols-6 gap-2">
                {selectedPhotos.map((photo, idx) => (
                  <div key={idx} className="relative group aspect-square rounded-lg overflow-hidden border border-gray-200">
                    <img
                      src={URL.createObjectURL(photo)}
                      alt={photo.name}
                      className="w-full h-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => removePhoto(idx)}
                      className="absolute top-1 right-1 bg-black/60 text-white rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition"
                      title="Remove"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Message */}
        {message && (
          <div
            className={`flex gap-3 p-4 rounded-lg ${
              message.type === 'error'
                ? 'bg-red-50 border border-red-200'
                : message.type === 'success'
                ? 'bg-green-50 border border-green-200'
                : 'bg-blue-50 border border-blue-200'
            }`}
          >
            <div className="mt-0.5">
              {message.type === 'success' ? (
                <CheckCircle
                  size={20}
                  className={message.type === 'error' ? 'text-red-600' : 'text-green-600'}
                />
              ) : (
                <AlertCircle size={20} className="text-blue-600" />
              )}
            </div>
            <p
              className={`text-sm ${
                message.type === 'error'
                  ? 'text-red-800'
                  : message.type === 'success'
                  ? 'text-green-800'
                  : 'text-blue-800'
              }`}
            >
              {message.text}
            </p>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading}
          className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
              Processing...
            </>
          ) : (
            <>
              <Upload size={18} />
              {editionType === 'magazine' ? 'Upload Edition' : 'Upload Album'}
            </>
          )}
        </button>
      </form>

      <div className="mt-6 text-sm text-gray-600 bg-gray-50 rounded-lg p-4">
        <p className="font-medium mb-2">Process:</p>
        {editionType === 'magazine' ? (
          <ol className="space-y-1 ml-4 list-decimal">
            <li>Upload triggers backend PDF parsing</li>
            <li>Content extracted and indexed (searchable)</li>
            <li>Edition added to database with metadata</li>
            <li>Hotspots can be created per page</li>
            <li>Analytics tracking begins automatically</li>
          </ol>
        ) : (
          <ol className="space-y-1 ml-4 list-decimal">
            <li>Photos are saved in the order selected — no parsing needed</li>
            <li>Album added to database with metadata</li>
            <li>Viewers flip through it exactly like a magazine (Next/Prev, Download)</li>
            <li>Analytics tracking begins automatically</li>
          </ol>
        )}
      </div>
    </div>
  );
}
