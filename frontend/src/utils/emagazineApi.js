import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001/api';

const emagazineAPI = {
  // Get all editions
  getEditions: async () => {
    try {
      const res = await axios.get(`${API_BASE}/emagazine/editions`);
      return res.data;
    } catch (error) {
      console.error('Error fetching editions:', error);
      throw error;
    }
  },

  // Get single edition
  getEdition: async (editionId) => {
    try {
      const res = await axios.get(`${API_BASE}/emagazine/editions/${editionId}`);
      return res.data;
    } catch (error) {
      console.error('Error fetching edition:', error);
      throw error;
    }
  },

  // Get single page content
  getPage: async (editionId, pageNum) => {
    try {
      const res = await axios.get(
        `${API_BASE}/emagazine/editions/${editionId}/pages/${pageNum}`
      );
      return res.data;
    } catch (error) {
      console.error(`Error fetching page ${pageNum}:`, error);
      throw error;
    }
  },

  // Search content
  search: async (query, editionId = null) => {
    try {
      const res = await axios.post(`${API_BASE}/emagazine/search`, {
        query,
        edition_id: editionId,
      });
      return res.data;
    } catch (error) {
      console.error('Error searching:', error);
      throw error;
    }
  },

  // Get table of contents
  getTableOfContents: async (editionId) => {
    try {
      const res = await axios.get(
        `${API_BASE}/emagazine/editions/${editionId}/toc`
      );
      return res.data;
    } catch (error) {
      console.error('Error fetching TOC:', error);
      throw error;
    }
  },

  // Track analytics
  trackAnalytics: async (editionId, actionType, metadata = {}) => {
    try {
      const payload = {
        action_type: actionType,
        metadata,
      };

      // Add page number if available
      if (metadata.pageNumber) {
        payload.page_number = metadata.pageNumber;
      }

      await axios.post(
        `${API_BASE}/emagazine/analytics?edition_id=${editionId}`,
        payload
      );
    } catch (error) {
      console.error('Error tracking analytics:', error);
      // Don't throw - analytics errors should not break UX
    }
  },

  // Get analytics summary
  getAnalyticsSummary: async (editionId) => {
    try {
      const res = await axios.get(
        `${API_BASE}/emagazine/analytics/${editionId}/summary`
      );
      return res.data;
    } catch (error) {
      console.error('Error fetching analytics:', error);
      throw error;
    }
  },

  // Get hotspots for a page
  getPageHotspots: async (editionId, pageNum) => {
    try {
      const res = await axios.get(
        `${API_BASE}/emagazine/hotspots/editions/${editionId}/pages/${pageNum}`
      );
      return res.data;
    } catch (error) {
      console.error('Error fetching hotspots:', error);
      return [];
    }
  },

  // Get all hotspots for edition
  getEditionHotspots: async (editionId) => {
    try {
      const res = await axios.get(
        `${API_BASE}/emagazine/hotspots/editions/${editionId}`
      );
      return res.data;
    } catch (error) {
      console.error('Error fetching hotspots:', error);
      return [];
    }
  },

  // Create hotspot
  createHotspot: async (editionId, hotspot) => {
    try {
      const res = await axios.post(`${API_BASE}/emagazine/hotspots`, {
        edition_id: editionId,
        ...hotspot,
      });
      return res.data;
    } catch (error) {
      console.error('Error creating hotspot:', error);
      throw error;
    }
  },

  // Update hotspot
  updateHotspot: async (hotspotId, hotspot) => {
    try {
      const res = await axios.put(
        `${API_BASE}/emagazine/hotspots/${hotspotId}`,
        hotspot
      );
      return res.data;
    } catch (error) {
      console.error('Error updating hotspot:', error);
      throw error;
    }
  },

  // Delete hotspot
  deleteHotspot: async (hotspotId) => {
    try {
      await axios.delete(`${API_BASE}/emagazine/hotspots/${hotspotId}`);
    } catch (error) {
      console.error('Error deleting hotspot:', error);
      throw error;
    }
  },

  // Upload new edition PDF
  uploadEdition: async (formData) => {
    try {
      const res = await axios.post(
        `${API_BASE}/emagazine/editions/upload`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );
      return res.data;
    } catch (error) {
      console.error('Error uploading edition:', error);
      throw error;
    }
  },
};

export default emagazineAPI;
