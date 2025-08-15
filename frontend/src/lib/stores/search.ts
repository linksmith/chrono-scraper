/**
 * Search store for Meilisearch integration
 */
import { writable } from 'svelte/store';
import { browser } from '$app/environment';

// Search client configuration
const MEILISEARCH_HOST = 'http://localhost:7700';
const MEILISEARCH_SEARCH_API_KEY = 'RuvEMt9LztgYqdfqRFmZbT52uysNrt73ps57RZ2PRd53kjWxe2qiv9kadk9EiV5k';

// Create Meilisearch search client lazily (only in browser)
let _searchClient: any = null;

export function getSearchClient() {
	if (!browser) {
		return null; // Return null during SSR
	}
	
	if (!_searchClient) {
		// Lazy import to avoid SSR issues
		import('@meilisearch/instant-meilisearch').then(({ instantMeiliSearch }) => {
			const { searchClient } = instantMeiliSearch(
				MEILISEARCH_HOST,
				MEILISEARCH_SEARCH_API_KEY,
				{
					placeholderSearch: true,
					primaryKey: 'id',
					keepZeroFacets: true
				}
			);
			_searchClient = searchClient;
		});
	}
	
	return _searchClient;
}

// Search state management
export interface SearchState {
	query: string;
	results: any[];
	facets: Record<string, any>;
	loading: boolean;
	error: string | null;
	pagination: {
		page: number;
		pageSize: number;
		total: number;
		totalPages: number;
	};
}

const initialState: SearchState = {
	query: '',
	results: [],
	facets: {},
	loading: false,
	error: null,
	pagination: {
		page: 1,
		pageSize: 20,
		total: 0,
		totalPages: 0
	}
};

export const searchState = writable<SearchState>(initialState);

// Search actions
export const searchActions = {
	setQuery: (query: string) => {
		searchState.update(state => ({
			...state,
			query
		}));
	},

	setLoading: (loading: boolean) => {
		searchState.update(state => ({
			...state,
			loading
		}));
	},

	setResults: (results: any[], total: number = 0) => {
		searchState.update(state => ({
			...state,
			results,
			pagination: {
				...state.pagination,
				total,
				totalPages: Math.ceil(total / state.pagination.pageSize)
			}
		}));
	},

	setFacets: (facets: Record<string, any>) => {
		searchState.update(state => ({
			...state,
			facets
		}));
	},

	setError: (error: string | null) => {
		searchState.update(state => ({
			...state,
			error
		}));
	},

	setPage: (page: number) => {
		searchState.update(state => ({
			...state,
			pagination: {
				...state.pagination,
				page
			}
		}));
	},

	reset: () => {
		searchState.set(initialState);
	}
};

// Search filters interface for OSINT investigations
export interface SearchFilters {
	projects?: string[];
	domains?: string[];
	dateRange?: {
		from: string;
		to: string;
	};
	contentTypes?: string[];
	languages?: string[];
	wordCountRange?: {
		min: number;
		max: number;
	};
	hasTitle?: boolean;
	hasAuthor?: boolean;
	statusCodes?: number[];
	keywords?: string[];
}

export const searchFilters = writable<SearchFilters>({});

// Helper function to build Meilisearch filter string from SearchFilters
export function buildMeilisearchFilter(filters: SearchFilters): string {
	const filterParts: string[] = [];

	// Project filtering
	if (filters.projects && filters.projects.length > 0) {
		const projectFilter = filters.projects.map(p => `project_id = "${p}"`).join(' OR ');
		filterParts.push(`(${projectFilter})`);
	}

	// Domain filtering
	if (filters.domains && filters.domains.length > 0) {
		const domainFilter = filters.domains.map(d => `domain = "${d}"`).join(' OR ');
		filterParts.push(`(${domainFilter})`);
	}

	// Date range filtering
	if (filters.dateRange) {
		if (filters.dateRange.from) {
			filterParts.push(`scraped_at >= ${new Date(filters.dateRange.from).getTime()}`);
		}
		if (filters.dateRange.to) {
			filterParts.push(`scraped_at <= ${new Date(filters.dateRange.to).getTime()}`);
		}
	}

	// Content type filtering
	if (filters.contentTypes && filters.contentTypes.length > 0) {
		const contentTypeFilter = filters.contentTypes.map(ct => `content_type = "${ct}"`).join(' OR ');
		filterParts.push(`(${contentTypeFilter})`);
	}

	// Language filtering
	if (filters.languages && filters.languages.length > 0) {
		const languageFilter = filters.languages.map(lang => `language = "${lang}"`).join(' OR ');
		filterParts.push(`(${languageFilter})`);
	}

	// Word count range
	if (filters.wordCountRange) {
		if (filters.wordCountRange.min !== undefined) {
			filterParts.push(`word_count >= ${filters.wordCountRange.min}`);
		}
		if (filters.wordCountRange.max !== undefined) {
			filterParts.push(`word_count <= ${filters.wordCountRange.max}`);
		}
	}

	// Boolean filters
	if (filters.hasTitle !== undefined) {
		filterParts.push(`title ${filters.hasTitle ? '!=' : '='} ""`);
	}

	if (filters.hasAuthor !== undefined) {
		filterParts.push(`author ${filters.hasAuthor ? '!=' : '='} ""`);
	}

	// Status code filtering
	if (filters.statusCodes && filters.statusCodes.length > 0) {
		const statusFilter = filters.statusCodes.map(sc => `status_code = ${sc}`).join(' OR ');
		filterParts.push(`(${statusFilter})`);
	}

	return filterParts.join(' AND ');
}