import { writable, derived } from 'svelte/store';
import { goto } from '$app/navigation';

export interface PageData {
	id: number;
	title?: string;
	url: string;
	review_status: 'unreviewed' | 'relevant' | 'irrelevant' | 'needs_review' | 'duplicate';
	page_category?: 'government' | 'research' | 'news' | 'blog' | 'commercial' | 'personal' | 'social_media' | 'academic' | 'legal' | 'technical';
	priority_level: 'low' | 'medium' | 'high' | 'critical';
	tags: string[];
	word_count?: number;
	content_snippet?: string;
	scraped_at?: string;
	reviewed_at?: string;
	author?: string;
	language?: string;
	meta_description?: string;
	is_starred?: boolean;
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
	page_category?: string;
	priority_level?: string;
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

	// Selected pages for bulk operations
	selectedPageIds: Set<number>;

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
	selectedPageIds: new Set(),
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
			if (filters.page_category) queryParams.set('page_category', filters.page_category);
			if (filters.priority_level) queryParams.set('priority_level', filters.priority_level);
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
		try {
			const response = await fetch(`/api/v1/pages/${pageId}/star`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(starData)
			});

			if (!response.ok) throw new Error('Failed to toggle star');

			const result = await response.json();

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
		page_category?: string;
		priority_level?: string;
		review_notes?: string;
		quick_notes?: string;
		quality_score?: number;
		tags?: string[];
	}) {
		try {
			const response = await fetch(`/api/v1/pages/${pageId}/review`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(reviewData)
			});

			if (!response.ok) throw new Error('Failed to review page');

			const updatedPage = await response.json();

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

			const response = await fetch(`/api/v1/pages/tag-suggestions?${queryParams}`);
			if (!response.ok) throw new Error('Failed to load tag suggestions');

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

	selectAllPages() {
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: new Set(state.pages.map(p => p.id)),
			showBulkActions: true
		}));
	},

	clearSelection() {
		pageManagementStore.update(state => ({
			...state,
			selectedPageIds: new Set(),
			showBulkActions: false
		}));
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