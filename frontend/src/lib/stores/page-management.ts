import { writable, derived } from 'svelte/store';
import { goto } from '$app/navigation';
import { 
	SharedPagesApiService, 
	type SharedPage, 
	type SharedPageContent, 
	type SharedPageAssociation 
} from '$lib/services/sharedPagesApi';

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
	content_url?: string;
	
	// Shared pages properties
	project_associations?: SharedPageAssociation[];
	total_projects?: number;
	all_tags?: string[];
	project_name?: string; // For backward compatibility with search results
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
	project_ids?: number[]; // For multi-project filtering
	starred_only?: boolean;
	exclude_irrelevant?: boolean;
	search?: string;
	tags?: string[];
	language?: string;
	content_type?: string[];
	date_range?: {
		start?: string;
		end?: string;
		field?: 'scraped_at' | 'capture_date' | 'published_date';
	};
	sort_by?: 'relevance' | 'scraped_at' | 'capture_date' | 'title' | 'word_count';
	sort_order?: 'asc' | 'desc';
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
	tagSuggestions: Array<{ tag: string; count: number; projects: string[] }>;
	tagSuggestionsLoading: boolean;

	// Page content cache
	pageContentCache: Map<string, PageContent>; // key: `${pageId}-${format}`
	contentLoading: Set<number>;

	// UI state
	showBulkActions: boolean;
	currentView: 'list' | 'grid';
	showFilters: boolean;
	
	// Shared pages mode
	useSharedPagesApi: boolean;
	currentProjectId?: number; // For project-specific operations
	sharingStatistics?: {
		total_shared_pages: number;
		pages_by_project_count: Array<{ project_count: number; page_count: number }>;
		most_shared_pages: Array<{ page_id: number; title: string; project_count: number }>;
		cross_project_tags: Array<{ tag: string; project_count: number; page_count: number }>;
	};
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
	showFilters: true,
	useSharedPagesApi: false, // Default to legacy API for backward compatibility
	currentProjectId: undefined,
	sharingStatistics: undefined
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
	// Configuration
	enableSharedPagesApi(projectId?: number) {
		pageManagementStore.update(state => ({
			...state,
			useSharedPagesApi: true,
			currentProjectId: projectId
		}));
	},

	disableSharedPagesApi() {
		pageManagementStore.update(state => ({
			...state,
			useSharedPagesApi: false,
			currentProjectId: undefined
		}));
	},

	// Convert SharedPage to PageData for backward compatibility
	_convertSharedPageToPageData(sharedPage: SharedPage, currentProjectId?: number): PageData {
		// Find the current project's association or use the first one
		const projectAssociation = currentProjectId 
			? sharedPage.project_associations.find(a => a.project_id === currentProjectId)
			: sharedPage.project_associations[0];

		return {
			id: sharedPage.id,
			title: sharedPage.title,
			url: sharedPage.url,
			review_status: projectAssociation?.review_status || 'unreviewed',
			tags: projectAssociation?.tags || [],
			word_count: sharedPage.word_count,
			content_snippet: sharedPage.content_preview,
			scraped_at: sharedPage.scraped_at,
			reviewed_at: projectAssociation?.reviewed_at,
			author: sharedPage.author,
			language: sharedPage.language,
			meta_description: sharedPage.meta_description,
			is_starred: projectAssociation?.is_starred || false,
			highlighted_snippet_html: sharedPage.highlighted_snippet_html,
			capture_date: sharedPage.capture_date,
			original_url: sharedPage.original_url,
			content_url: sharedPage.content_url,
			project_associations: sharedPage.project_associations,
			total_projects: sharedPage.total_projects,
			all_tags: sharedPage.all_tags,
			project_name: projectAssociation?.project_name
		};
	},

	// Load pages (supports both APIs)
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
			const currentState = get(pageManagementStore);
			
			if (currentState.useSharedPagesApi) {
				// Use new shared pages API
				const searchRequest = {
					query: filters.search,
					project_ids: filters.project_ids || (filters.project_id ? [filters.project_id] : undefined),
					review_statuses: filters.review_status ? [filters.review_status] : undefined,
					tags: filters.tags,
					starred_only: filters.starred_only,
					exclude_irrelevant: filters.exclude_irrelevant,
					language: filters.language,
					content_type: filters.content_type,
					date_range: filters.date_range,
					sort_by: filters.sort_by || 'scraped_at',
					sort_order: filters.sort_order || 'desc',
					skip: (page - 1) * pageSize,
					limit: pageSize
				};

				const response = await SharedPagesApiService.searchPages(searchRequest);
				
				if (!response.success) {
					throw new Error(response.error?.message || 'Failed to load pages');
				}

				const pages = response.data!.pages.map(sharedPage => 
					this._convertSharedPageToPageData(sharedPage, currentState.currentProjectId)
				);

				pageManagementStore.update(state => ({
					...state,
					pages,
					totalPages: Math.ceil((response.data!.total || 0) / pageSize),
					loading: false
				}));
			} else {
				// Use legacy API
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
			}
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
			const currentState = get(pageManagementStore);
			let result;

			if (currentState.useSharedPagesApi && currentState.currentProjectId) {
				// Use new shared pages API
				const currentPage = currentState.pages.find(p => p.id === pageId);
				const newStarredState = !currentPage?.is_starred;
				
				const response = await SharedPagesApiService.toggleStar(
					pageId, 
					currentState.currentProjectId, 
					newStarredState,
					starData
				);
				
				if (!response.success) {
					throw new Error(response.error?.message || 'Failed to toggle star');
				}
				
				result = response.data;
			} else {
				// Use legacy API
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

				result = await response.json();
			}

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
			const currentState = get(pageManagementStore);
			let updatedPage;

			if (currentState.useSharedPagesApi && currentState.currentProjectId) {
				// Use new shared pages API
				const response = await SharedPagesApiService.reviewPage(
					pageId,
					currentState.currentProjectId,
					{
						review_status: reviewData.review_status,
						review_notes: reviewData.review_notes || reviewData.quick_notes,
						quality_score: reviewData.quality_score,
						tags: reviewData.tags
					}
				);
				
				if (!response.success) {
					throw new Error(response.error?.message || 'Failed to review page');
				}
				
				// Convert association back to page format for store update
				const association = response.data!;
				updatedPage = {
					review_status: association.review_status,
					review_notes: association.review_notes,
					quality_score: association.quality_score,
					tags: association.tags,
					reviewed_at: association.reviewed_at
				};
			} else {
				// Use legacy API
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

				updatedPage = await response.json();
			}

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
			const currentState = get(pageManagementStore);
			let result;

			if (currentState.useSharedPagesApi && currentState.currentProjectId) {
				// Use new shared pages API
				const response = await SharedPagesApiService.updatePageTags(
					pageId,
					currentState.currentProjectId,
					tags
				);
				
				if (!response.success) {
					throw new Error(response.error?.message || 'Failed to update tags');
				}
				
				result = response.data;
			} else {
				// Use legacy API
				const response = await fetch(`/api/v1/pages/${pageId}/tags`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ tags })
				});

				if (!response.ok) throw new Error('Failed to update tags');

				result = await response.json();
			}

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
	async loadTagSuggestions(query?: string, pageId?: number, retryCount = 0) {
		pageManagementStore.update(state => ({
			...state,
			tagSuggestionsLoading: true
		}));

		try {
			let suggestions;

			// Always use legacy API for tag suggestions since shared pages API doesn't have this endpoint
			const queryParams = new URLSearchParams();
			if (query) queryParams.set('query', query);
			if (pageId) queryParams.set('page_id', pageId.toString());

			const qs = queryParams.toString();
			const response = await fetch(`/api/v1/pages/tag-suggestions${qs ? `?${qs}` : ''}` , {
				credentials: 'include'
				// Remove manual Authorization header - let browser handle session-based auth
			});
			
			if (!response.ok) {
				let errorDetails = '';
				try {
					const err = await response.json();
					errorDetails = err?.detail || err?.message || JSON.stringify(err);
					console.error('Tag suggestions API error:', response.status, err);
				} catch (_) {
					try {
						errorDetails = await response.text();
					} catch (__) {
						errorDetails = 'Unknown error';
					}
					console.error('Tag suggestions API error (non-JSON):', response.status, errorDetails);
				}
				
				// If it's an auth error and we haven't retried yet, try once more after a short delay
				if (response.status === 401 && retryCount === 0) {
					console.log('Authentication error on tag suggestions, retrying in 500ms...');
					pageManagementStore.update(state => ({
						...state,
						tagSuggestionsLoading: false
					}));
					
					// Wait briefly for authentication to be fully ready
					await new Promise(resolve => setTimeout(resolve, 500));
					return this.loadTagSuggestions(query, pageId, retryCount + 1);
				}
				
				// If it's an auth error after retry, silently fail to avoid disrupting UX
				if (response.status === 401) {
					console.warn('Tag suggestions authentication failed after retry - user may need to refresh page');
					pageManagementStore.update(state => ({
						...state,
						tagSuggestionsLoading: false,
						tagSuggestions: [] // Provide empty array as fallback
					}));
					return;
				}
				
				throw new Error(`Failed to load tag suggestions: ${errorDetails}`);
			}

			const rawSuggestions = await response.json();
			suggestions = rawSuggestions.map((s: any) => ({ 
				tag: s.tag || s, 
				count: s.count || s.frequency || 1, 
				projects: s.projects || [] 
			}));

			pageManagementStore.update(state => ({
				...state,
				tagSuggestions: suggestions,
				tagSuggestionsLoading: false
			}));
		} catch (error) {
			pageManagementStore.update(state => ({
				...state,
				tagSuggestionsLoading: false
			}));
			
			// For non-auth errors, log but don't throw to avoid disrupting the search interface
			if (error.message?.includes('Authentication required')) {
				console.warn('Tag suggestions failed due to authentication - this is expected during page load');
			} else {
				console.error('Error loading tag suggestions:', error);
			}
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
			const currentState = get(pageManagementStore);
			let content;

			if (currentState.useSharedPagesApi) {
				// Use new shared pages API
				const response = await SharedPagesApiService.getPageContent(pageId, format);
				
				if (!response.success) {
					throw new Error(response.error?.message || 'Failed to load page content');
				}
				
				content = response.data;
			} else {
				// Use legacy API
				const response = await fetch(`/api/v1/pages/${pageId}/content?format=${format}`);
				if (!response.ok) throw new Error('Failed to load page content');

				content = await response.json();
			}

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

	// Load sharing statistics (new functionality)
	async loadSharingStatistics() {
		try {
			const response = await SharedPagesApiService.getSharingStatistics();
			
			if (!response.success) {
				throw new Error(response.error?.message || 'Failed to load sharing statistics');
			}

			pageManagementStore.update(state => ({
				...state,
				sharingStatistics: response.data
			}));

			return response.data;
		} catch (error) {
			console.error('Error loading sharing statistics:', error);
			throw error;
		}
	},

	// Bulk operations
	async bulkAction(action: string, pageIds: number[], data: any = {}) {
		try {
			const currentState = get(pageManagementStore);
			let result;

			if (currentState.useSharedPagesApi && currentState.currentProjectId) {
				// Use new shared pages API
				const bulkRequest = {
					page_ids: pageIds,
					action: action as any, // Convert action name to new API format
					project_id: currentState.currentProjectId,
					data
				};

				const response = await SharedPagesApiService.bulkAction(bulkRequest);
				
				if (!response.success) {
					throw new Error(response.error?.message || 'Failed to perform bulk action');
				}
				
				result = response.data;
			} else {
				// Use legacy API
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

				result = await response.json();
			}

			// Refresh the current page
			const refreshedState = get(pageManagementStore);
			await this.loadPages(refreshedState.filters, refreshedState.currentPage, refreshedState.pageSize);

			return result;
		} catch (error) {
			console.error('Error performing bulk action:', error);
			throw error;
		}
	},

	// Enhanced bulk operations using new API
	async bulkStar(pageIds: number[], isStarred: boolean) {
		const currentState = get(pageManagementStore);
		if (!currentState.currentProjectId) {
			throw new Error('Bulk star operation requires project context');
		}

		return SharedPagesApiService.bulkStar(pageIds, currentState.currentProjectId, isStarred);
	},

	async bulkReview(pageIds: number[], reviewStatus: string, reviewNotes?: string) {
		const currentState = get(pageManagementStore);
		if (!currentState.currentProjectId) {
			throw new Error('Bulk review operation requires project context');
		}

		return SharedPagesApiService.bulkReview(pageIds, currentState.currentProjectId, reviewStatus, reviewNotes);
	},

	async bulkUpdateTags(pageIds: number[], tags: string[], action: 'add' | 'remove' | 'replace' = 'replace') {
		const currentState = get(pageManagementStore);
		if (!currentState.currentProjectId) {
			throw new Error('Bulk tag operation requires project context');
		}

		return SharedPagesApiService.bulkUpdateTags(pageIds, currentState.currentProjectId, tags, action);
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