import { create } from 'zustand';

export const useEMagazineStore = create((set) => ({
  // State
  editions: [],
  currentEditionId: null,
  currentPage: 1,
  totalPages: 0,
  searchQuery: '',
  searchResults: [],
  tableOfContents: {},
  isLoading: false,
  error: null,
  showSidebar: true,
  showSearch: false,

  // Actions
  setCurrentEdition: (editionId, totalPages) =>
    set({ currentEditionId: editionId, totalPages, currentPage: 1 }),

  setCurrentPage: (page) => set({ currentPage: Math.max(1, page) }),

  nextPage: () =>
    set((state) => ({
      currentPage: Math.min(state.currentPage + 1, state.totalPages),
    })),

  prevPage: () =>
    set((state) => ({
      currentPage: Math.max(state.currentPage - 1, 1),
    })),

  setSearchQuery: (query) => set({ searchQuery: query }),

  setSearchResults: (results) => set({ searchResults: results }),

  setTableOfContents: (toc) => set({ tableOfContents: toc }),

  setEditions: (editions) => set({ editions }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  toggleSidebar: () =>
    set((state) => ({ showSidebar: !state.showSidebar })),

  toggleSearch: () =>
    set((state) => ({ showSearch: !state.showSearch })),

  reset: () =>
    set({
      editions: [],
      currentEditionId: null,
      currentPage: 1,
      totalPages: 0,
      searchQuery: '',
      searchResults: [],
      tableOfContents: {},
      isLoading: false,
      error: null,
    }),
}));
