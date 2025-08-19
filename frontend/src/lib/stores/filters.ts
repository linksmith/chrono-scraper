import { writable, derived } from 'svelte/store';
import type { Writable, Readable } from 'svelte/store';

export interface FilterState {
    dateRange: [Date | null, Date | null];
    entities: {
        person: string[];
        organization: string[];
        location: string[];
        event: string[];
    };
    contentTypes: string[];
    wordCount: [number | null, number | null];
    languages: string[];
    projects: number[];
    domains: string[];
    hasTitle: boolean | null;
    hasAuthor: boolean | null;
    keywords: string[];
    excludeKeywords: string[];
    
    // Page management filters
    starredOnly: boolean;
    tags: string[];
    reviewStatus: string[];
}

export interface FilterCounts {
    totalResults: number;
    entityCounts: {
        person: number;
        organization: number;
        location: number;
        event: number;
    };
    contentTypeCounts: Record<string, number>;
    languageCounts: Record<string, number>;
}

const initialFilterState: FilterState = {
    dateRange: [null, null],
    entities: {
        person: [],
        organization: [],
        location: [],
        event: []
    },
    contentTypes: [],
    wordCount: [null, null],
    languages: [],
    projects: [],
    domains: [],
    hasTitle: null,
    hasAuthor: null,
    keywords: [],
    excludeKeywords: [],
    
    // Page management filters
    starredOnly: false,
    tags: [],
    reviewStatus: []
};

export const filters: Writable<FilterState> = writable(initialFilterState);
export const filterCounts: Writable<FilterCounts> = writable({
    totalResults: 0,
    entityCounts: {
        person: 0,
        organization: 0,
        location: 0,
        event: 0
    },
    contentTypeCounts: {},
    languageCounts: {}
});

// Derived stores for computed values
export const hasActiveFilters: Readable<boolean> = derived(filters, ($filters) => {
    return (
        $filters.dateRange[0] !== null ||
        $filters.dateRange[1] !== null ||
        Object.values($filters.entities).some(arr => arr.length > 0) ||
        $filters.contentTypes.length > 0 ||
        $filters.wordCount[0] !== null ||
        $filters.wordCount[1] !== null ||
        $filters.languages.length > 0 ||
        $filters.projects.length > 0 ||
        $filters.domains.length > 0 ||
        $filters.hasTitle !== null ||
        $filters.hasAuthor !== null ||
        $filters.keywords.length > 0 ||
        $filters.excludeKeywords.length > 0 ||
        
        // Page management filters
        $filters.starredOnly ||
        $filters.tags.length > 0 ||
        $filters.reviewStatus.length > 0
    );
});

export const activeFilterCount: Readable<number> = derived(filters, ($filters) => {
    let count = 0;
    
    if ($filters.dateRange[0] !== null || $filters.dateRange[1] !== null) count++;
    
    Object.values($filters.entities).forEach(arr => {
        count += arr.length;
    });
    
    count += $filters.contentTypes.length;
    count += $filters.languages.length;
    count += $filters.projects.length;
    count += $filters.domains.length;
    count += $filters.keywords.length;
    count += $filters.excludeKeywords.length;
    
    if ($filters.wordCount[0] !== null || $filters.wordCount[1] !== null) count++;
    if ($filters.hasTitle !== null) count++;
    if ($filters.hasAuthor !== null) count++;
    
    // Page management filters
    if ($filters.starredOnly) count++;
    count += $filters.tags.length;
    count += $filters.reviewStatus.length;
    
    return count;
});

// Helper functions
export function resetFilters() {
    filters.set(initialFilterState);
}

export function removeFilter(filterType: keyof FilterState, value?: any) {
    filters.update($filters => {
        const newFilters = { ...$filters };
        
        switch (filterType) {
            case 'dateRange':
                newFilters.dateRange = [null, null];
                break;
            case 'entities':
                if (value && typeof value === 'object' && 'type' in value && 'value' in value) {
                    const entityType = value.type as keyof FilterState['entities'];
                    newFilters.entities[entityType] = newFilters.entities[entityType].filter(
                        item => item !== value.value
                    );
                }
                break;
            case 'contentTypes':
                if (value) {
                    newFilters.contentTypes = newFilters.contentTypes.filter(item => item !== value);
                }
                break;
            case 'wordCount':
                newFilters.wordCount = [null, null];
                break;
            case 'languages':
                if (value) {
                    newFilters.languages = newFilters.languages.filter(item => item !== value);
                }
                break;
            case 'projects':
                if (value) {
                    newFilters.projects = newFilters.projects.filter(item => item !== value);
                }
                break;
            case 'domains':
                if (value) {
                    newFilters.domains = newFilters.domains.filter(item => item !== value);
                }
                break;
            case 'keywords':
                if (value) {
                    newFilters.keywords = newFilters.keywords.filter(item => item !== value);
                }
                break;
            case 'excludeKeywords':
                if (value) {
                    newFilters.excludeKeywords = newFilters.excludeKeywords.filter(item => item !== value);
                }
                break;
            case 'hasTitle':
                newFilters.hasTitle = null;
                break;
            case 'hasAuthor':
                newFilters.hasAuthor = null;
                break;
            case 'starredOnly':
                newFilters.starredOnly = false;
                break;
            case 'tags':
                if (value) {
                    newFilters.tags = newFilters.tags.filter(item => item !== value);
                } else {
                    newFilters.tags = [];
                }
                break;
            case 'reviewStatus':
                if (value) {
                    newFilters.reviewStatus = newFilters.reviewStatus.filter(item => item !== value);
                } else {
                    newFilters.reviewStatus = [];
                }
                break;
        }
        
        return newFilters;
    });
}

// Convert filters to URL params
export function filtersToUrlParams(filterState: FilterState): URLSearchParams {
    const params = new URLSearchParams();
    
    if (filterState.dateRange[0]) {
        params.set('date_from', filterState.dateRange[0].toISOString().split('T')[0]);
    }
    if (filterState.dateRange[1]) {
        params.set('date_to', filterState.dateRange[1].toISOString().split('T')[0]);
    }
    
    // Entity filters
    Object.entries(filterState.entities).forEach(([type, entities]) => {
        if (entities.length > 0) {
            params.set(`entities_${type}`, entities.join(','));
        }
    });
    
    if (filterState.contentTypes.length > 0) {
        params.set('content_types', filterState.contentTypes.join(','));
    }
    
    if (filterState.wordCount[0] !== null) {
        params.set('word_count_min', filterState.wordCount[0].toString());
    }
    if (filterState.wordCount[1] !== null) {
        params.set('word_count_max', filterState.wordCount[1].toString());
    }
    
    if (filterState.languages.length > 0) {
        params.set('languages', filterState.languages.join(','));
    }
    
    if (filterState.projects.length > 0) {
        params.set('projects', filterState.projects.join(','));
    }
    
    if (filterState.domains.length > 0) {
        params.set('domains', filterState.domains.join(','));
    }
    
    if (filterState.hasTitle !== null) {
        params.set('has_title', filterState.hasTitle.toString());
    }
    
    if (filterState.hasAuthor !== null) {
        params.set('has_author', filterState.hasAuthor.toString());
    }
    
    if (filterState.keywords.length > 0) {
        params.set('keywords', filterState.keywords.join(','));
    }
    
    if (filterState.excludeKeywords.length > 0) {
        params.set('exclude_keywords', filterState.excludeKeywords.join(','));
    }
    
    // Page management filters
    if (filterState.starredOnly) {
        params.set('starred_only', 'true');
    }
    
    if (filterState.tags.length > 0) {
        params.set('tags', filterState.tags.join(','));
    }
    
    if (filterState.reviewStatus.length > 0) {
        params.set('review_status', filterState.reviewStatus.join(','));
    }
    
    return params;
}

// Convert URL params to filters
export function urlParamsToFilters(params: URLSearchParams): FilterState {
    const filterState: FilterState = { ...initialFilterState };
    
    const dateFrom = params.get('date_from');
    const dateTo = params.get('date_to');
    
    if (dateFrom) {
        filterState.dateRange[0] = new Date(dateFrom);
    }
    if (dateTo) {
        filterState.dateRange[1] = new Date(dateTo);
    }
    
    // Entity filters
    ['person', 'organization', 'location', 'event'].forEach(type => {
        const entityParam = params.get(`entities_${type}`);
        if (entityParam) {
            filterState.entities[type as keyof FilterState['entities']] = entityParam.split(',');
        }
    });
    
    const contentTypes = params.get('content_types');
    if (contentTypes) {
        filterState.contentTypes = contentTypes.split(',');
    }
    
    const wordCountMin = params.get('word_count_min');
    const wordCountMax = params.get('word_count_max');
    if (wordCountMin) {
        filterState.wordCount[0] = parseInt(wordCountMin);
    }
    if (wordCountMax) {
        filterState.wordCount[1] = parseInt(wordCountMax);
    }
    
    const languages = params.get('languages');
    if (languages) {
        filterState.languages = languages.split(',');
    }
    
    const projects = params.get('projects');
    if (projects) {
        filterState.projects = projects.split(',').map(p => parseInt(p));
    }
    
    const domains = params.get('domains');
    if (domains) {
        filterState.domains = domains.split(',');
    }
    
    const hasTitle = params.get('has_title');
    if (hasTitle !== null) {
        filterState.hasTitle = hasTitle === 'true';
    }
    
    const hasAuthor = params.get('has_author');
    if (hasAuthor !== null) {
        filterState.hasAuthor = hasAuthor === 'true';
    }
    
    const keywords = params.get('keywords');
    if (keywords) {
        filterState.keywords = keywords.split(',');
    }
    
    const excludeKeywords = params.get('exclude_keywords');
    if (excludeKeywords) {
        filterState.excludeKeywords = excludeKeywords.split(',');
    }
    
    // Page management filters
    const starredOnly = params.get('starred_only');
    if (starredOnly !== null) {
        filterState.starredOnly = starredOnly === 'true';
    }
    
    const tags = params.get('tags');
    if (tags) {
        filterState.tags = tags.split(',');
    }
    
    const reviewStatus = params.get('review_status');
    if (reviewStatus) {
        filterState.reviewStatus = reviewStatus.split(',');
    }
    
    return filterState;
}