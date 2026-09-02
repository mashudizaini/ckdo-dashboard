import React, { useState } from 'react';
import { Upload, AlertCircle, CheckCircle } from 'lucide-react';
import emagazineAPI from '../../utils/emagazineApi';

export default function EditionUploader({ onUploadSuccess }) {
  const [formData, setFormData] = useState({
    title: '',
    edition_number: '',
    published_date: '',
  });
  const [selectedFile, setSelectedFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

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

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedFile) {
      setMessage({ type: 'error', text: 'Please select a PDF file' });
      return;
    }

    if (!formData.title || !formData.edition_number || !formData.published_date) {
      setMessage({ type: 'error', text: 'Please fill in all fields' });
      return;
    }

    setLoading(true);
    setMessage(null);

    try {
      // Create FormData for multipart upload
      const uploadFormData = new FormData();
      uploadFormData.append('title', formData.title);
      uploadFormData.append('edition_number', formData.edition_number);
      uploadFormData.append('published_date', formData.published_date);
      uploadFormData.append('file', selectedFile);

      // Upload the edition
      const result = await emagazineAPI.uploadEdition(uploadFormData);

      setMessage({
        type: 'success',
        text: `Edition uploaded successfully! ${result.total_pages} pages parsed and indexed.`,
      });

      // Reset form
      setFormData({ title: '', edition_number: '', published_date: '' });
      setSelectedFile(null);

      // Call success callback
      if (onUploadSuccess) onUploadSuccess();
    } catch (error) {
      const errorMsg = error.response?.data?.detail || error.message || 'Failed to upload edition';
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
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <div className="flex gap-3">
          <div className="text-blue-600 mt-0.5">
            <AlertCircle size={20} />
          </div>
          <div>
            <h4 className="font-semibold text-blue-900">How to Upload a New Edition</h4>
            <ol className="text-sm text-blue-800 mt-2 space-y-1 ml-4 list-decimal">
              <li>Fill in the edition details below</li>
              <li>Select the PDF file (max 50MB)</li>
              <li>Click Upload to parse and import content</li>
              <li>View analytics and manage hotspots once uploaded</li>
            </ol>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 bg-white border border-gray-200 rounded-lg p-6">
        {/* Form Fields */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Edition Title
            </label>
            <input
              type="text"
              name="title"
              value={formData.title}
              onChange={handleInputChange}
              placeholder="e.g., CKD OTTO E-Magazine 4th Edition"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

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

          <div className="col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Published Date
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

        {/* File Upload */}
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
              Upload Edition
            </>
          )}
        </button>
      </form>

      <div className="mt-6 text-sm text-gray-600 bg-gray-50 rounded-lg p-4">
        <p className="font-medium mb-2">Process:</p>
        <ol className="space-y-1 ml-4 list-decimal">
          <li>Upload triggers backend PDF parsing</li>
          <li>Content extracted and indexed (searchable)</li>
          <li>Edition added to database with metadata</li>
          <li>Hotspots can be created per page</li>
          <li>Analytics tracking begins automatically</li>
        </ol>
      </div>
    </div>
  );
}
