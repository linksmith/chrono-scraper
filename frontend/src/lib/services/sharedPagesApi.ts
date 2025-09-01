/**
 * Shared Pages API Service
 * 
 * Provides access to the new shared pages API endpoints that support:
 * - Cross-project page sharing
 * - Project-specific metadata (tags, review status, notes)
 * - Enhanced search and filtering
 * - Bulk operations
 */

import { getApiUrl, apiFetch } from '$lib/utils';

// TypeScript interfaces for the new shared pages API
export interface SharedPageAssociation {
	project_id: number;
	project_name: string;
	tags: string[];
	review_status: 'unreviewed' | 'relevant' | 'irrelevant' | 'needs_review' | 'duplicate';
	review_notes?: string;
	personal_note?: string;
	quality_score?: number;
	is_starred: boolean;
	reviewed_at?: string;
	starred_at?: string;
}

export interface SharedPage {
	id: number;
	title?: string;
	url: string;
	original_url?: string;
	content_url?: string;
	content_preview?: string;
	word_count?: number;
	character_count?: number;
	language?: string;
	author?: string;
	published_date?: string;
	meta_description?: string;
	scraped_at: string;
	capture_date?: string;
	content_type?: string;
	
	// Project associations
	project_associations: SharedPageAssociation[];
	
	// Aggregated data across projects
	total_projects: number;
	all_tags: string[];
	
	// Search-specific fields
	highlighted_snippet_html?: string;
}

export interface SharedPageContent {
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

export interface SharedPageSearchRequest {
	query?: string;
	project_ids?: number[];
	review_statuses?: string[];
	tags?: string[];
	starred_only?: boolean;
	exclude_irrelevant?: boolean;
	language?: string;
	content_type?: string[];
	date_range?: {
		start?: string;
		end?: string;
		field?: 'scraped_at' | 'capture_date' | 'published_date';
	};
	sort_by?: 'relevance' | 'scraped_at' | 'capture_date' | 'title' | 'word_count';
	sort_order?: 'asc' | 'desc';
	skip?: number;
	limit?: number;
}

export interface SharedPageSearchResponse {
	pages: SharedPage[];
	total: number;
	facets?: {
		projects?: Array<{ project_id: number; project_name: string; count: number }>;
		review_statuses?: Array<{ status: string; count: number }>;
		tags?: Array<{ tag: string; count: number }>;
		languages?: Array<{ language: string; count: number }>;
		content_types?: Array<{ type: string; count: number }>;
	};
}

export interface BulkActionRequest {
	page_ids: number[];
	action: 'update_associations' | 'delete_associations' | 'bulk_review' | 'bulk_star' | 'bulk_tag';
	project_id?: number;
	data?: {
		// For update_associations
		tags?: string[];
		review_status?: string;
		review_notes?: string;
		personal_note?: string;
		quality_score?: number;
		is_starred?: boolean;
		
		// For bulk_review
		review_status?: string;
		review_notes?: string;
		
		// For bulk_star
		is_starred?: boolean;
		
		// For bulk_tag
		tags?: string[];
		tag_action?: 'add' | 'remove' | 'replace';
	};
}

export interface BulkActionResponse {
	success: boolean;
	updated_count: number;
	errors?: Array<{ page_id: number; error: string }>;
}

export interface SharingStatistics {
	total_shared_pages: number;
	pages_by_project_count: Array<{ project_count: number; page_count: number }>;
	most_shared_pages: Array<{ page_id: number; title: string; project_count: number }>;
	cross_project_tags: Array<{ tag: string; project_count: number; page_count: number }>;
}

export class SharedPagesApiService {
	/**
	 * Get a single shared page with all project associations
	 */
	static async getSharedPage(pageId: number): Promise<any> {
		const response = await apiFetch(getApiUrl(`/api/v1/shared-pages/${pageId}`));
		
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const data = await response.json();
		return {
			success: true,
			data: data,
			status: response.status
		};
	}

	/**
	 * List user's shared pages with filtering
	 */
	static async listUserPages(filters: {
		project_id?: number;
		review_status?: string;
		starred_only?: boolean;
		exclude_irrelevant?: boolean;
		tags?: string[];
		skip?: number;
		limit?: number;
		sort_by?: string;
		sort_order?: 'asc' | 'desc';
	} = {}): Promise<any> {
		const params = new URLSearchParams();
		
		Object.entries(filters).forEach(([key, value]) => {
			if (value !== undefined && value !== null) {
				if (Array.isArray(value)) {
					value.forEach(v => params.append(key, v.toString()));
				} else {
					params.set(key, value.toString());
				}
			}
		});

		const response = await apiFetch(getApiUrl(`/api/v1/shared-pages?${params.toString()}`));
		
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const data = await response.json();
		return {
			success: true,
			data: data,
			status: response.status
		};
	}

	/**
	 * Get pages for a specific project
	 */
	static async getProjectPages(
		projectId: number,
		filters: {
			review_status?: string;
			starred_only?: boolean;
			exclude_irrelevant?: boolean;
			tags?: string[];
			skip?: number;
			limit?: number;
			sort_by?: string;
			sort_order?: 'asc' | 'desc';
		} = {}
	): Promise<any> {
		const params = new URLSearchParams();
		
		Object.entries(filters).forEach(([key, value]) => {
			if (value !== undefined && value !== null) {
				if (Array.isArray(value)) {
					value.forEach(v => params.append(key, v.toString()));
				} else {
					params.set(key, value.toString());
				}
			}
		});

		const response = await apiFetch(getApiUrl(`/api/v1/shared-pages/projects/${projectId}/pages?${params.toString()}`), {
			method: 'GET',
			headers: { 'Content-Type': 'application/json' },
		});

		// Parse the response JSON - apiFetch returns a raw Response object
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const data = await response.json();
		return {
			success: true,
			data: data,
			status: response.status
		};
	}

	/**
	 * Search shared pages with advanced filtering
	 */
	static async searchPages(request: SharedPageSearchRequest): Promise<any> {
		const response = await apiFetch(getApiUrl('/api/v1/shared-pages/search'), {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
			},
			body: JSON.stringify(request),
		});

		// Parse the response JSON - apiFetch returns a raw Response object
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const data = await response.json();
		
		// Transform backend response format to match frontend expectations
		// Backend returns: { success: true, data: {...}, query: "...", ... }
		// Frontend expects: { success: true, data: { pages: [...], total: ... } }
		return {
			success: data.success || true,
			data: {
				pages: data.data?.hits || data.data?.pages || [],
				total: data.data?.totalHits || data.data?.total || 0,
				facets: data.data?.facets
			},
			query: data.query,
			filters_applied: data.filters_applied,
			error: data.error
		};
	}

	/**
	 * Update page associations for a specific project
	 */
	static async updatePageAssociation(
		pageId: number,
		projectId: number,
		data: {
			tags?: string[];
			review_status?: string;
			review_notes?: string;
			personal_note?: string;
			quality_score?: number;
			is_starred?: boolean;
		}
	): Promise<any> {
		const response = await apiFetch(getApiUrl(`/api/v1/shared-pages/${pageId}/associations/${projectId}`), {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(data),
		});

		// Parse the response JSON - apiFetch returns a raw Response object
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const responseData = await response.json();
		return {
			success: true,
			data: responseData,
			status: response.status
		};
	}

	/**
	 * Perform bulk operations on shared pages
	 */
	static async bulkAction(request: BulkActionRequest): Promise<any> {
		const response = await apiFetch(getApiUrl('/api/v1/shared-pages/bulk-actions'), {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(request),
		});

		// Parse the response JSON - apiFetch returns a raw Response object
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const responseData = await response.json();
		return {
			success: true,
			data: responseData,
			status: response.status
		};
	}

	/**
	 * Get sharing statistics
	 */
	static async getSharingStatistics(): Promise<any> {
		const response = await apiFetch(getApiUrl('/api/v1/shared-pages/statistics/sharing'));
		
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const data = await response.json();
		return {
			success: true,
			data: data,
			status: response.status
		};
	}

	/**
	 * Get page content in different formats
	 */
	static async getPageContent(
		pageId: number,
		format: 'markdown' | 'html' | 'text' = 'markdown'
	): Promise<any> {
		const response = await apiFetch(getApiUrl(`/api/v1/pages/${pageId}/content?format=${format}`), {
			method: 'GET',
			headers: { 'Content-Type': 'application/json' },
		});

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			return {
				success: false,
				error: errorData,
				status: response.status
			};
		}

		const data = await response.json();
		return {
			success: true,
			data: data,
			status: response.status
		};
	}


	/**
	 * Star/unstar a page in a specific project context
	 */
	static async toggleStar(
		pageId: number,
		projectId: number,
		isStarred: boolean,
		data: {
			tags?: string[];
			personal_note?: string;
			folder?: string;
		} = {}
	): Promise<any> {
		return this.updatePageAssociation(pageId, projectId, {
			...data,
			is_starred: isStarred
		}).then(response => ({
			...response,
			data: response.data ? {
				starred: response.data.is_starred,
				starred_at: response.data.starred_at
			} : undefined
		}));
	}

	/**
	 * Review a page in a specific project context
	 */
	static async reviewPage(
		pageId: number,
		projectId: number,
		reviewData: {
			review_status: string;
			review_notes?: string;
			quality_score?: number;
			tags?: string[];
		}
	): Promise<any> {
		return this.updatePageAssociation(pageId, projectId, reviewData);
	}

	/**
	 * Update page tags in a specific project context
	 */
	static async updatePageTags(
		pageId: number,
		projectId: number,
		tags: string[]
	): Promise<any> {
		return this.updatePageAssociation(pageId, projectId, { tags }).then(response => ({
			...response,
			data: response.data ? { tags: response.data.tags } : undefined
		}));
	}

	/**
	 * Bulk star/unstar pages
	 */
	static async bulkStar(
		pageIds: number[],
		projectId: number,
		isStarred: boolean
	): Promise<any> {
		return this.bulkAction({
			page_ids: pageIds,
			action: 'bulk_star',
			project_id: projectId,
			data: { is_starred: isStarred }
		});
	}

	/**
	 * Bulk review pages
	 */
	static async bulkReview(
		pageIds: number[],
		projectId: number,
		reviewStatus: string,
		reviewNotes?: string
	): Promise<any> {
		return this.bulkAction({
			page_ids: pageIds,
			action: 'bulk_review',
			project_id: projectId,
			data: { review_status: reviewStatus, review_notes: reviewNotes }
		});
	}

	/**
	 * Bulk update tags
	 */
	static async bulkUpdateTags(
		pageIds: number[],
		projectId: number,
		tags: string[],
		action: 'add' | 'remove' | 'replace' = 'replace'
	): Promise<any> {
		return this.bulkAction({
			page_ids: pageIds,
			action: 'bulk_tag',
			project_id: projectId,
			data: { tags, tag_action: action }
		});
	}
}

// Export convenience functions for compatibility with existing code
export const sharedPagesApi = SharedPagesApiService;