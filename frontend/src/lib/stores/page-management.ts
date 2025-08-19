import { writable, derived } from 'svelte/store';
import { goto } from '$app/navigation';

export interface PageData {
	id: number;
	title?: string;
	url: string;
	review_status: 'unreviewed' | 'relevant' | 'irrelevant' | 'needs_review' | 'duplicate';
	tags: string[];
	word_count?: number;
	content_snippet?: string;
	scraped_at?: string;
	reviewed_at?: string;
	author?: string;
	language?: string;
	meta_description?: string;
	is_starred?: boolean;
	
	// Additional search result properties
	highlighted_snippet_html?: string;
	capture_date?: string;
	original_url?: string;
	wayback_url?: string;
}

export interface PageContent {
	page_id: number;
	title: string;
	url: string;
	content: string;
	format: 'markdown' | 'html' | 'text';
	word_count?: number;
	character_count?: number;
	language?: string;
	author?: string;
	published_date?: string;
	meta_description?: string;
}

export interface PageManagementFilters {
	review_status?: string;
	project_id?: number;
	starred_only?: boolean;
	exclude_irrelevant?: boolean;
	search?: string;
	tags?: string[];
}

interface PageManagementState {
	// Pages data
	pages: PageData[];
	totalPages: number;
	currentPage: number;
	pageSize: number;
	loading: boolean;
	error: string | null;

	// Filters
	filters: PageManagementFilters;

	// Bulk selection state
	bulkSelectionMode: boolean;
	selectedPageIds: Set<number>;
	lastSelectedIndex: number | null;
	bulkActionInProgress: boolean;

	// Tag suggestions
	tagSuggestions: string[];
	tagSuggestionsLoading: boolean;

	// Page content cache
	pageContentCache: Map<string, PageContent>; // key: `${pageId}-${format}`
	contentLoading: Set<number>;

	// UI state
	showBulkActions: boolean;
	currentView: 'list' | 'grid';
	showFilters: boolean;
}

const initialState: PageManagementState = {
	pages: [],
	totalPages: 0,
	currentPage: 1,
	pageSize: 20,
	loading: false,
	error: null,
	filters: {
		exclude_irrelevant: true
	},
	bulkSelectionMode: false,
	selectedPageIds: new Set(),
	lastSelectedIndex: null,
	bulkActionInProgress: false,
	tagSuggestions: [],
	tagSuggestionsLoading: false,
	pageContentCache: new Map(),
	contentLoading: new Set(),
	showBulkActions: false,
	currentView: 'list',
	showFilters: true
};

export const pageManagementStore = writable<PageManagementState>(initialState);

// Derived stores
export const selectedPagesCount = derived(
	pageManagementStore,
	($store) => $store.selectedPageIds.size
);

export const hasSelectedPages = derived(
	selectedPagesCount,
	(count) => count > 0
);

export const filteredPagesCount = derived(
	pageManagementStore,
	($store) => $store.totalPages
);

export const bulkSelectionMode = derived(
	pageManagementStore,
	($store) => $store.bulkSelectionMode
);

export const bulkActionInProgress = derived(
	pageManagementStore,
	($store) => $store.bulkActionInProgress
);

export const isAllPagesSelected = derived(
	pageManagementStore,
	($store) => $store.pages.length > 0 && $store.selectedPageIds.size === $store.pages.length
);

export const isSomePagesSelected = derived(
	pageManagementStore,
	($store) => $store.selectedPageIds.size > 0 && $store.selectedPageIds.size < $store.pages.length
);

// Actions
export const pageManagementActions = {
	// Load pages
	async loadPages(filters: PageManagementFilters = {}, page = 1, pageSize = 20) {
		pageManagementStore.update(state => ({
			...state,
			loading: true,
			error: null,
			currentPage: page,
			pageSize,
			filters: { ...state.filters, ...filters }
		}));

		try {
			const queryParams = new URLSearchParams();
			queryParams.set('skip', ((page - 1) * pageSize).toString());
			queryParams.set('limit', pageSize.toString());

			if (filters.review_status) queryParams.set('review_status', filters.review_status);
			if (filters.project_id) queryParams.set('project_id', filters.project_id.toString());
			if (filters.starred_only) queryParams.set('starred_only', 'true');
			if (filters.exclude_irrelevant !== undefined) {
				queryParams.set('exclude_irrelevant', filters.exclude_irrelevant.toString());
			}
			if (filters.search) queryParams.set('search', filters.search);

			const response = await fetch(`/api/v1/pages/for-review?${queryParams}`);
			if (!response.ok) throw new Error('Failed to load pages');

			const data = await response.json();

			pageManagementStore.update(state => ({
				...state,
				pages: data.items || [],
				totalPages: Math.ceil((data.total || 0) / pageSize),
				loading: false
			}));
		} catch (error) {
			pageManagementStore.update(state => ({
				...state,
				loading: false,
				error: error instanceof Error ? error.message : 'Failed to load pages'
			}));
		}
	},

	// Star/unstar page
	async toggleStar(pageId: number, starData: { tags?: string[]; personal_note?: string; folder?: string } = {}) {
		console.log('🌟 toggleStar called with:', { pageId, starData });
		try {
			const response = await fetch(`/api/v1/pages/${pageId}/star`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(starData)
			});
			console.log('🌟 Star API response:', response.status, response.statusText);

			if (!response.ok) {
				console.error('🌟 Star API failed:', response.status, response.statusText);
				throw new Error('Failed to toggle star');
			}

			const result = await response.json();
			console.log('🌟 Star API result:', result);

			// Update the page in the store
			pageManagementStore.update(state => ({
				...state,
				pages: state.pages.map(page => 
					page.id === pageId 
						? { ...page, is_starred: result.starred }
						: page
				)
			}));

			return result;
		} catch (error) {
			console.error('Error toggling star:', error);
			throw error;
		}
	},

	// Review page
	async reviewPage(pageId: number, reviewData: {
		review_status: string;
		review_notes?: string;
		quick_notes?: string;
		quality_score?: number;
		tags?: string[];
	}) {
		console.log('✅ reviewPage called with:', { pageId, reviewData });
		try {
			const response = await fetch(`/api/v1/pages/${pageId}/review`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(reviewData)
			});
			console.log('✅ Review API response:', response.status, response.statusText);

			if (!response.ok) {
				console.error('✅ Review API failed:', response.status, response.statusText);
				throw new Error('Failed to review page');
			}

			const updatedPage = await response.json();
			console.log('✅ Review API result:', updatedPage);

			// Update the page in the store
			pageManagementStore.update(state => ({
				...state,
				pages: state.pages.map(page => 
					page.id === pageId 
						? { ...page, ...updatedPage }
						: page
				)
			}));

			return updatedPage;
		} catch (error) {
			console.error('Error reviewing page:', error);
			throw error;
		}
	},

	// Update page tags
	async updatePageTags(pageId: number, tags: string[]) {
		try {
			const response = await fetch(`/api/v1/pages/${pageId}/tags`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ tags })
			});

			if (!response.ok) throw new Error('Failed to update tags');

			const result = await response.json();

			// Update the page in the store
			pageManagementStore.update(state => ({
				...state,
				pages: state.pages.map(page => 
					page.id === pageId 
						? { ...page, tags: result.tags }
						: page
				)
			}));

			return result;
		} catch (error) {
			console.error('Error updating tags:', error);
			throw error;
		}
	},

	// Load tag suggestions
	async loadTagSuggestions(query?: string, pageId?: number) {
		pageManagementStore.update(state => ({
			...state,
			tagSuggestionsLoading: true
		}));

		try {
			const queryParams = new URLSearchParams();
			if (query) queryParams.set('query', query);
			if (pageId) queryParams.set('page_id', pageId.toString());

			const qs = queryParams.toString();
			const response = await fetch(`/api/v1/pages/tag-suggestions${qs ? `?${qs}` : ''}` , {
				credentials: 'include',
				headers: {
					'Authorization': `Bearer ${document.cookie.split('access_token=')[1]?.split(';')[0] || ''}`
				}
			});
			if (!response.ok) {
				try {
					const err = await response.json();
					console.error('Tag suggestions API error:', response.status, err);
				} catch (_) {
					console.error('Tag suggestions API error (non-JSON):', response.status, await response.text().catch(() => ''));
				}
				throw new Error('Failed to load tag suggestions');
			}

			const suggestions = await response.json();

			pageManagementStore.update(state => ({
				...state,
				tagSuggestions: suggestions.map((s: any) => s.tag),
				tagSuggestionsLoading: false
			}));
		} catch (error) {
			pageManagementStore.update(state => ({
				...state,
				tagSuggestionsLoading: false
			}));
			console.error('Error loading tag suggestions:', error);
		}
	},

	// Load page content
	async loadPageContent(pageId: number, format: 'markdown' | 'html' | 'text' = 'markdown') {
		const cacheKey = `${pageId}-${format}`;
		
		pageManagementStore.update(state => ({
			...state,
			contentLoading: new Set([...state.contentLoading, pageId])
		}));

		try {
			const response = await fetch(`/api/v1/pages/${pageId}/content?format=${format}`);
			if (!response.ok) throw new Error('Failed to load page content');

			const content = await response.json();

			pageManagementStore.update(state => {
				const newContentLoading = new Set(state.contentLoading);
				newContentLoading.delete(pageId);
				
				const newCache = new Map(state.pageContentCache);
				newCache.set(cacheKey, content);

				return {
					...state,
					pageContentCache: newCache,
					contentLoading: newContentLoading
				};
			});

			return content;
		} catch (error) {
			pageManagementStore.update(state => {
				const newContentLoading = new Set(state.contentLoading);
				newContentLoading.delete(pageId);
				return {
					...state,
					contentLoading: newContentLoading
				};
			});
			console.error('Error loading page content:', error);
			throw error;
		}
	},

	// Bulk operations
	async bulkAction(action: string, pageIds: number[], data: any = {}) {
		try {
			const response = await fetch('/api/v1/pages/bulk-actions', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					page_ids: pageIds,
					action,
					...data
				})
			});

			if (!response.ok) throw new Error('Failed to perform bulk action');

			const result = await response.json();

			// Refresh the current page
			const currentState = pageManagementStore.get();
			await this.loadPages(currentState.filters, currentState.currentPage, currentState.pageSize);

			return result;
		} catch (error) {
			console.error('Error performing bulk action:', error);
			throw error;
		}
	},

	// Selection management
	togglePageSelection(pageId: number) {
		pageManagementStore.update(state => {
			const newSelection = new Set(state.selectedPageIds);
			if (newSelection.has(pageId)) {
				newSelection.delete(pageId);
			} else {
				newSelection.add(pageId);
			}
			return {
				...state,
				selectedPageIds: newSelection,
				showBulkActions: newSelection.size > 0
			};
		});
	},

	clearSelection() {
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: new Set(),
			lastSelectedIndex: null,
			showBulkActions: false
		}));
	},

	// Enhanced bulk selection methods
	toggleBulkSelectionMode() {
		pageManagementStore.update(state => ({
			...state,
			bulkSelectionMode: !state.bulkSelectionMode,
			selectedPageIds: new Set(), // Clear selections when toggling mode
			lastSelectedIndex: null,
			showBulkActions: false
		}));
	},

	togglePageSelectionWithShift(pageId: number, pageIndex: number, shiftKey: boolean) {
		pageManagementStore.update(state => {
			const newSelection = new Set(state.selectedPageIds);
			
			if (shiftKey && state.lastSelectedIndex !== null && state.lastSelectedIndex !== pageIndex) {
				// Range selection with shift key
				const startIndex = Math.min(state.lastSelectedIndex, pageIndex);
				const endIndex = Math.max(state.lastSelectedIndex, pageIndex);
				
				// Determine if we're selecting or deselecting based on the target page's current state
				const shouldSelect = !newSelection.has(pageId);
				
				// Apply the action to all pages in the range
				for (let i = startIndex; i <= endIndex; i++) {
					if (i < state.pages.length) {
						const targetPageId = state.pages[i].id;
						if (shouldSelect) {
							newSelection.add(targetPageId);
						} else {
							newSelection.delete(targetPageId);
						}
					}
				}
			} else {
				// Single selection toggle
				if (newSelection.has(pageId)) {
					newSelection.delete(pageId);
				} else {
					newSelection.add(pageId);
				}
			}

			return {
				...state,
				selectedPageIds: newSelection,
				lastSelectedIndex: pageIndex,
				showBulkActions: newSelection.size > 0
			};
		});
	},

	selectRange(startIndex: number, endIndex: number) {
		pageManagementStore.update(state => {
			const newSelection = new Set(state.selectedPageIds);
			const actualStart = Math.min(startIndex, endIndex);
			const actualEnd = Math.max(startIndex, endIndex);
			
			for (let i = actualStart; i <= actualEnd; i++) {
				if (i < state.pages.length) {
					newSelection.add(state.pages[i].id);
				}
			}

			return {
				...state,
				selectedPageIds: newSelection,
				showBulkActions: newSelection.size > 0
			};
		});
	},

	selectAllPages() {
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: new Set(state.pages.map(p => p.id)),
			showBulkActions: true
		}));
	},

	// Bulk actions with progress tracking
	async performBulkAction(action: string, data: any = {}) {
		pageManagementStore.update(state => ({
			...state,
			bulkActionInProgress: true
		}));

		try {
			const currentState = get(pageManagementStore);
			const pageIds = Array.from(currentState.selectedPageIds);
			
			if (pageIds.length === 0) {
				throw new Error('No pages selected');
			}

			const result = await this.bulkAction(action, pageIds, data);
			
			// Clear selections after successful bulk action
			pageManagementStore.update(state => ({
				...state,
				selectedPageIds: new Set(),
				lastSelectedIndex: null,
				showBulkActions: false,
				bulkActionInProgress: false
			}));

			return result;
		} catch (error) {
			pageManagementStore.update(state => ({
				...state,
				bulkActionInProgress: false
			}));
			throw error;
		}
	},

	// UI state
	setView(view: 'list' | 'grid') {
		pageManagementStore.update(state => ({
			...state,
			currentView: view
		}));
	},

	toggleFilters() {
		pageManagementStore.update(state => ({
			...state,
			showFilters: !state.showFilters
		}));
	},

	// Navigation
	viewPage(pageId: number) {
		goto(`/pages/${pageId}`);
	},

	openPageInNewTab(url: string) {
		window.open(url, '_blank');
	}
};

// Helper function to get current state
function get<T>(store: { subscribe: (fn: (value: T) => void) => () => void }): T {
	let value: T;
	const unsubscribe = store.subscribe((v) => value = v);
	unsubscribe();
	return value!;
}

// Add get method to store
(pageManagementStore as any).get = () => get(pageManagementStore);