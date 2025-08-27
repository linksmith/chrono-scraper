/**
 * Enhanced Filtering Store - Comprehensive state management for Phase 4 Enhanced Filtering System
 * Provides real-time WebSocket integration, bulk operations tracking, and filtering transparency
 */
import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { auth } from './auth';
import { websocketStore, isConnected, type MessageType } from './websocket';
import type {
	ScrapePage,
	ScrapeSession,
	EnhancedFilters,
	FilteringAnalysis,
	BulkActionType,
	ScrapePageStatus,
	TaskProgressPayload,
	ProjectUpdatePayload,
	BulkActionResponse
} from '$lib/types/scraping';

// Enhanced filtering state interface
interface FilteringState {
	// Page data
	pages: ScrapePage[];
	totalCount: number;
	hasMore: boolean;
	nextCursor: string | null;
	
	// Pagination
	currentPage: number;
	pageSize: number;
	totalPages: number;
	
	// Filters
	activeFilters: EnhancedFilters;
	filterPresets: Record<string, EnhancedFilters>;
	
	// Statistics and analysis
	statistics: FilteringAnalysis | null;
	statusCounts: Record<string, number>;
	
	// Sessions
	sessions: ScrapeSession[];
	
	// Selection and bulk operations
	selectedPageIds: Set<number>;
	bulkMode: boolean;
	bulkOperations: BulkOperationState[];
	
	// UI state
	viewMode: 'list' | 'grid' | 'table';
	expandedDetails: Set<number>;
	showFilters: boolean;
	sortBy: string;
	sortOrder: 'asc' | 'desc';
	
	// Loading and error states
	loading: boolean;
	error: string | null;
	lastUpdateTime: string | null;
	
	// Real-time updates
	isReceivingUpdates: boolean;
	updateQueue: PageUpdate[];
	pendingOperations: Set<string>;
}

interface BulkOperationState {
	id: string;
	action: BulkActionType;
	pageIds: number[];
	status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
	progress: number;
	message: string;
	startTime: string;
	endTime?: string;
	result?: BulkActionResponse;
	error?: string;
}

interface PageUpdate {
	pageId: number;
	updates: Partial<ScrapePage>;
	timestamp: string;
	source: 'websocket' | 'api' | 'bulk_operation';
}

// Default state
const defaultFilters: EnhancedFilters = {
	status: [],
	filterCategory: [],
	sessionId: null,
	searchQuery: '',
	dateRange: { from: null, to: null },
	contentType: [],
	hasErrors: null,
	isManuallyOverridden: null,
	priorityScore: { min: null, max: null },
	showOnlyProcessable: false
};

const initialState: FilteringState = {
	pages: [],
	totalCount: 0,
	hasMore: false,
	nextCursor: null,
	currentPage: 1,
	pageSize: 50,
	totalPages: 1,
	activeFilters: { ...defaultFilters },
	filterPresets: {
		all: { ...defaultFilters },
		filtered_only: { ...defaultFilters, status: ['filtered_duplicate', 'filtered_list_page', 'filtered_low_quality', 'filtered_size', 'filtered_type', 'filtered_custom'] },
		processable: { ...defaultFilters, showOnlyProcessable: true },
		overridden: { ...defaultFilters, isManuallyOverridden: true },
		high_priority: { ...defaultFilters, priorityScore: { min: 7, max: 10 } },
		errors_only: { ...defaultFilters, hasErrors: true }
	},
	statistics: null,
	statusCounts: {},
	sessions: [],
	selectedPageIds: new Set(),
	bulkMode: false,
	bulkOperations: [],
	viewMode: 'table',
	expandedDetails: new Set(),
	showFilters: true,
	sortBy: 'created_at',
	sortOrder: 'desc',
	loading: false,
	error: null,
	lastUpdateTime: null,
	isReceivingUpdates: false,
	updateQueue: [],
	pendingOperations: new Set()
};

// Create the store
function createFilteringStore() {
	const { subscribe, set, update } = writable<FilteringState>(initialState);
	
	let debounceTimer: NodeJS.Timeout | null = null;
	let currentProjectId: number | null = null;
	
	// WebSocket message handler
	function handleWebSocketMessage(message: any) {
		const { type, payload } = message;
		
		switch (type) {
			case 'task_progress':
				handleTaskProgressUpdate(payload);
				break;
			case 'project_update':
				handleProjectUpdate(payload);
				break;
			case 'bulk_operation_update':
				handleBulkOperationUpdate(payload);
				break;
		}
	}
	
	function handleTaskProgressUpdate(payload: TaskProgressPayload) {
		if (!currentProjectId || payload.project_id !== currentProjectId) return;
		
		update(state => {
			// Update page statuses
			if (payload.page_updates && payload.page_updates.length > 0) {
				const updatedPages = state.pages.map(page => {
					const update = payload.page_updates?.find(u => u.page_id === page.id);
					if (update) {
						const updatedPage = {
							...page,
							status: update.status,
							filter_reason: update.filter_reason ?? page.filter_reason,
							filter_category: update.filter_category ?? page.filter_category,
							is_manually_overridden: update.is_manually_overridden ?? page.is_manually_overridden,
							priority_score: update.priority_score ?? page.priority_score,
							error_message: update.error_message ?? page.error_message,
							updated_at: new Date().toISOString()
						};
						
						// Add to update queue for processing
						state.updateQueue.push({
							pageId: page.id,
							updates: updatedPage,
							timestamp: new Date().toISOString(),
							source: 'websocket'
						});
						
						return updatedPage;
					}
					return page;
				});
				
				return {
					...state,
					pages: updatedPages,
					statusCounts: { ...state.statusCounts, ...payload.status_counts },
					lastUpdateTime: new Date().toISOString(),
					isReceivingUpdates: true
				};
			}
			
			return state;
		});
	}
	
	function handleProjectUpdate(payload: ProjectUpdatePayload) {
		if (!currentProjectId || payload.project_id !== currentProjectId) return;
		
		update(state => ({
			...state,
			lastUpdateTime: new Date().toISOString(),
			// Trigger reload if requested
			...(payload.should_reload_pages && { loading: true })
		}));
		
		// Reload pages if requested
		if (payload.should_reload_pages) {
			setTimeout(() => {
				loadPages(get({ subscribe }), false);
			}, 1000);
		}
	}
	
	function handleBulkOperationUpdate(payload: any) {
		update(state => {
			const operationIndex = state.bulkOperations.findIndex(op => op.id === payload.operation_id);
			
			if (operationIndex >= 0) {
				const updatedOperations = [...state.bulkOperations];
				updatedOperations[operationIndex] = {
					...updatedOperations[operationIndex],
					status: payload.status,
					progress: payload.progress || 0,
					message: payload.message || '',
					...(payload.status === 'completed' && { endTime: new Date().toISOString() }),
					...(payload.error && { error: payload.error }),
					...(payload.result && { result: payload.result })
				};
				
				return {
					...state,
					bulkOperations: updatedOperations,
					...(payload.status === 'completed' && {
						pendingOperations: new Set([...state.pendingOperations].filter(id => id !== payload.operation_id))
					})
				};
			}
			
			return state;
		});
	}
	
	// API Functions
	async function loadPages(state: FilteringState, resetPagination = true): Promise<void> {
		if (!currentProjectId) return;
		
		try {
			if (resetPagination) {
				update(s => ({ ...s, currentPage: 1, nextCursor: null, loading: true, error: null }));
			}
			
			const params = buildApiParams(state);
			const response = await fetch(`/api/v1/projects/${currentProjectId}/scrape-pages?${params}`, {
				headers: {
					'Authorization': `Bearer ${get(auth).token}`,
					'Content-Type': 'application/json'
				}
			});
			
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.error || `HTTP ${response.status}`);
			}
			
			const data = await response.json();
			
			update(s => ({
				...s,
				pages: resetPagination ? data.scrape_pages || [] : [...s.pages, ...(data.scrape_pages || [])],
				totalCount: data.total_count || 0,
				hasMore: data.has_more || false,
				nextCursor: data.next_cursor || null,
				totalPages: Math.ceil((data.total_count || 0) / s.pageSize),
				statusCounts: data.status_counts || {},
				loading: false,
				error: null,
				lastUpdateTime: new Date().toISOString()
			}));
			
		} catch (err) {
			console.error('Failed to load pages:', err);
			update(s => ({
				...s,
				loading: false,
				error: err instanceof Error ? err.message : 'Failed to load pages'
			}));
		}
	}
	
	async function loadStatistics(): Promise<void> {
		if (!currentProjectId) return;
		
		try {
			const response = await fetch(`/api/v1/projects/${currentProjectId}/scrape-pages/statistics`, {
				headers: {
					'Authorization': `Bearer ${get(auth).token}`
				}
			});
			
			if (response.ok) {
				const statistics = await response.json();
				update(s => ({ ...s, statistics }));
			}
		} catch (err) {
			console.warn('Failed to load statistics:', err);
		}
	}
	
	async function loadSessions(): Promise<void> {
		if (!currentProjectId) return;
		
		try {
			const response = await fetch(`/api/v1/projects/${currentProjectId}/sessions`, {
				headers: {
					'Authorization': `Bearer ${get(auth).token}`
				}
			});
			
			if (response.ok) {
				const data = await response.json();
				update(s => ({ ...s, sessions: data.sessions || [] }));
			}
		} catch (err) {
			console.warn('Failed to load sessions:', err);
		}
	}
	
	function buildApiParams(state: FilteringState): string {
		const params = new URLSearchParams({
			page: state.currentPage.toString(),
			limit: state.pageSize.toString(),
			sort_by: state.sortBy,
			order: state.sortOrder
		});
		
		// Add filters
		const filters = state.activeFilters;
		
		if (filters.sessionId) params.append('scrape_session_id', filters.sessionId.toString());
		if (filters.searchQuery) params.append('search_query', filters.searchQuery);
		if (filters.hasErrors !== null) params.append('has_errors', filters.hasErrors.toString());
		if (filters.isManuallyOverridden !== null) params.append('is_manually_overridden', filters.isManuallyOverridden.toString());
		if (filters.showOnlyProcessable) params.append('can_be_manually_processed', 'true');
		if (filters.priorityScore.min !== null) params.append('priority_min', filters.priorityScore.min.toString());
		if (filters.priorityScore.max !== null) params.append('priority_max', filters.priorityScore.max.toString());
		if (filters.dateRange.from) params.append('created_after', filters.dateRange.from);
		if (filters.dateRange.to) params.append('created_before', filters.dateRange.to);
		
		// Add array filters
		filters.status.forEach(status => params.append('status', status));
		filters.filterCategory.forEach(category => params.append('filter_category', category));
		filters.contentType.forEach(type => params.append('content_type', type));
		
		return params.toString();
	}
	
	// Store methods
	return {
		subscribe,
		
		// Initialization
		init: (projectId: number) => {
			currentProjectId = projectId;
			
			// Setup WebSocket listeners
			if (browser && typeof window !== 'undefined') {
				window.addEventListener('websocket-message', (event: any) => {
					handleWebSocketMessage(event.detail);
				});
				
				// Connect WebSocket if needed
				if (!get(isConnected)) {
					const wsUrl = `ws://localhost:8000/api/v1/ws/projects/${projectId}`;
					websocketStore.connect(wsUrl, get(auth).token || '');
				}
			}
			
			// Load initial data
			const state = get({ subscribe });
			Promise.all([
				loadPages(state, true),
				loadStatistics(),
				loadSessions()
			]);
		},
		
		// Filter management
		setFilters: (filters: Partial<EnhancedFilters>) => {
			update(state => {
				const newFilters = { ...state.activeFilters, ...filters };
				return { ...state, activeFilters: newFilters };
			});
			
			// Debounced reload
			if (debounceTimer) clearTimeout(debounceTimer);
			debounceTimer = setTimeout(() => {
				const state = get({ subscribe });
				loadPages(state, true);
			}, 300);
		},
		
		applyFilterPreset: (presetName: string) => {
			update(state => {
				const preset = state.filterPresets[presetName];
				if (preset) {
					return { ...state, activeFilters: { ...preset } };
				}
				return state;
			});
			
			const state = get({ subscribe });
			loadPages(state, true);
		},
		
		saveFilterPreset: (name: string, filters?: EnhancedFilters) => {
			update(state => ({
				...state,
				filterPresets: {
					...state.filterPresets,
					[name]: filters || { ...state.activeFilters }
				}
			}));
		},
		
		clearFilters: () => {
			update(state => ({
				...state,
				activeFilters: { ...defaultFilters }
			}));
			
			const state = get({ subscribe });
			loadPages(state, true);
		},
		
		// Page management
		refreshPages: () => {
			const state = get({ subscribe });
			update(s => ({ ...s, loading: true }));
			loadPages(state, true);
		},
		
		loadMorePages: () => {
			const state = get({ subscribe });
			if (state.hasMore && !state.loading) {
				update(s => ({ ...s, currentPage: s.currentPage + 1 }));
				loadPages({ ...state, currentPage: state.currentPage + 1 }, false);
			}
		},
		
		goToPage: (page: number) => {
			update(state => {
				if (page >= 1 && page <= state.totalPages) {
					const newState = { ...state, currentPage: page };
					loadPages(newState, false);
					return newState;
				}
				return state;
			});
		},
		
		// Selection management
		selectPage: (pageId: number, selected: boolean) => {
			update(state => {
				const newSelection = new Set(state.selectedPageIds);
				if (selected) {
					newSelection.add(pageId);
				} else {
					newSelection.delete(pageId);
				}
				return { ...state, selectedPageIds: newSelection };
			});
		},
		
		selectRange: (startPageId: number, endPageId: number, selected: boolean) => {
			update(state => {
				const pageIds = state.pages.map(p => p.id);
				const startIndex = pageIds.indexOf(startPageId);
				const endIndex = pageIds.indexOf(endPageId);
				
				if (startIndex !== -1 && endIndex !== -1) {
					const start = Math.min(startIndex, endIndex);
					const end = Math.max(startIndex, endIndex);
					const newSelection = new Set(state.selectedPageIds);
					
					for (let i = start; i <= end; i++) {
						if (selected) {
							newSelection.add(pageIds[i]);
						} else {
							newSelection.delete(pageIds[i]);
						}
					}
					
					return { ...state, selectedPageIds: newSelection };
				}
				return state;
			});
		},
		
		selectAll: (selected: boolean) => {
			update(state => {
				if (selected) {
					const allIds = new Set(state.pages.map(p => p.id));
					return { ...state, selectedPageIds: allIds };
				} else {
					return { ...state, selectedPageIds: new Set() };
				}
			});
		},
		
		clearSelection: () => {
			update(state => ({
				...state,
				selectedPageIds: new Set(),
				bulkMode: false
			}));
		},
		
		// Bulk operations
		startBulkOperation: async (action: BulkActionType, pageIds: number[], data?: any): Promise<string> => {
			if (!currentProjectId) throw new Error('No project selected');
			
			const operationId = crypto.randomUUID();
			
			// Add to tracking
			update(state => ({
				...state,
				bulkOperations: [
					...state.bulkOperations,
					{
						id: operationId,
						action,
						pageIds: [...pageIds],
						status: 'pending',
						progress: 0,
						message: 'Starting operation...',
						startTime: new Date().toISOString()
					}
				],
				pendingOperations: new Set([...state.pendingOperations, operationId])
			}));
			
			try {
				const response = await fetch(`/api/v1/projects/${currentProjectId}/scrape-pages/bulk/${action}`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						'Authorization': `Bearer ${get(auth).token}`
					},
					body: JSON.stringify({
						page_ids: pageIds,
						operation_id: operationId,
						...data
					})
				});
				
				if (!response.ok) {
					const errorData = await response.json().catch(() => ({}));
					throw new Error(errorData.error || `HTTP ${response.status}`);
				}
				
				const result = await response.json();
				
				// Update operation status
				update(state => {
					const operations = state.bulkOperations.map(op => 
						op.id === operationId 
							? { ...op, status: 'in_progress' as const, message: 'Operation started' }
							: op
					);
					return { ...state, bulkOperations: operations };
				});
				
				return operationId;
				
			} catch (err) {
				// Update operation with error
				update(state => {
					const operations = state.bulkOperations.map(op => 
						op.id === operationId 
							? { 
								...op, 
								status: 'failed' as const, 
								error: err instanceof Error ? err.message : 'Operation failed',
								endTime: new Date().toISOString()
							}
							: op
					);
					return { 
						...state, 
						bulkOperations: operations,
						pendingOperations: new Set([...state.pendingOperations].filter(id => id !== operationId))
					};
				});
				
				throw err;
			}
		},
		
		getBulkOperationStatus: (operationId: string) => {
			const state = get({ subscribe });
			return state.bulkOperations.find(op => op.id === operationId);
		},
		
		removeBulkOperation: (operationId: string) => {
			update(state => ({
				...state,
				bulkOperations: state.bulkOperations.filter(op => op.id !== operationId),
				pendingOperations: new Set([...state.pendingOperations].filter(id => id !== operationId))
			}));
		},
		
		// UI state management
		setViewMode: (mode: 'list' | 'grid' | 'table') => {
			update(state => ({ ...state, viewMode: mode }));
		},
		
		toggleFilters: () => {
			update(state => ({ ...state, showFilters: !state.showFilters }));
		},
		
		toggleBulkMode: () => {
			update(state => ({ ...state, bulkMode: !state.bulkMode }));
		},
		
		toggleDetailExpansion: (pageId: number) => {
			update(state => {
				const expanded = new Set(state.expandedDetails);
				if (expanded.has(pageId)) {
					expanded.delete(pageId);
				} else {
					expanded.add(pageId);
				}
				return { ...state, expandedDetails: expanded };
			});
		},
		
		setSorting: (sortBy: string, sortOrder: 'asc' | 'desc') => {
			update(state => ({ ...state, sortBy, sortOrder }));
			const state = get({ subscribe });
			loadPages(state, true);
		},
		
		// Statistics
		refreshStatistics: () => {
			loadStatistics();
		},
		
		// Error handling
		clearError: () => {
			update(state => ({ ...state, error: null }));
		},
		
		setError: (error: string) => {
			update(state => ({ ...state, error }));
		},
		
		// Cleanup
		destroy: () => {
			currentProjectId = null;
			if (debounceTimer) {
				clearTimeout(debounceTimer);
				debounceTimer = null;
			}
			
			// Remove WebSocket listeners
			if (browser && typeof window !== 'undefined') {
				window.removeEventListener('websocket-message', handleWebSocketMessage);
			}
			
			// Reset to initial state
			set(initialState);
		}
	};
}

// Create and export the store
export const filteringStore = createFilteringStore();

// Derived stores for easy access to specific state
export const pages = derived(filteringStore, $store => $store.pages);
export const selectedCount = derived(filteringStore, $store => $store.selectedPageIds.size);
export const hasSelection = derived(selectedCount, $count => $count > 0);
export const activeFilters = derived(filteringStore, $store => $store.activeFilters);
export const statistics = derived(filteringStore, $store => $store.statistics);
export const isLoading = derived(filteringStore, $store => $store.loading);
export const currentError = derived(filteringStore, $store => $store.error);
export const statusCounts = derived(filteringStore, $store => $store.statusCounts);
export const bulkOperations = derived(filteringStore, $store => $store.bulkOperations);
export const activeBulkOperations = derived(bulkOperations, $ops => 
	$ops.filter(op => op.status === 'in_progress' || op.status === 'pending')
);
export const viewMode = derived(filteringStore, $store => $store.viewMode);
export const showFilters = derived(filteringStore, $store => $store.showFilters);

// Helper functions for components
export function hasActiveFilters(filters: EnhancedFilters): boolean {
	return (
		filters.status.length > 0 ||
		filters.filterCategory.length > 0 ||
		filters.contentType.length > 0 ||
		filters.sessionId !== null ||
		filters.searchQuery.trim().length > 0 ||
		filters.dateRange.from !== null ||
		filters.dateRange.to !== null ||
		filters.hasErrors !== null ||
		filters.isManuallyOverridden !== null ||
		filters.priorityScore.min !== null ||
		filters.priorityScore.max !== null ||
		filters.showOnlyProcessable
	);
}

export function getFilterSummary(filters: EnhancedFilters): string {
	const parts: string[] = [];
	
	if (filters.status.length > 0) parts.push(`${filters.status.length} statuses`);
	if (filters.filterCategory.length > 0) parts.push(`${filters.filterCategory.length} categories`);
	if (filters.searchQuery) parts.push('text search');
	if (filters.sessionId) parts.push('session filter');
	if (filters.showOnlyProcessable) parts.push('processable only');
	if (filters.isManuallyOverridden !== null) parts.push('override filter');
	if (filters.hasErrors !== null) parts.push('error filter');
	
	return parts.join(', ') || 'no filters';
}

// Export types for use in components
export type { FilteringState, BulkOperationState, PageUpdate };