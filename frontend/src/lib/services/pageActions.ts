/**
 * Unified page action service for consistent handling across search pages
 * Updated to use shared pages API exclusively for tag synchronization
 */
import { SharedPagesApiService } from './sharedPagesApi';
import { pageManagementActions } from '$lib/stores/page-management';

export interface PageActionEvent {
	type: string;
	pageId: number;
	projectId?: number; // Required for shared pages API
	reviewStatus?: string;
	isStarred?: boolean;
	tags?: string[];
	[key: string]: any;
}

export interface TagUpdateEvent {
	pageId: number;
	projectId?: number; // Required for shared pages API
	tags: string[];
}

export class PageActionsService {
	/**
	 * Handle page actions with consistent logging and error handling
	 * Uses shared pages API exclusively for tag synchronization
	 */
	static async handlePageAction(event: PageActionEvent): Promise<void> {
		console.log('🎯 PageActionsService.handlePageAction called:', event);
		const { type, pageId, projectId } = event;
		
		// Determine project ID - required for shared pages API
		const targetProjectId = projectId || this._getDefaultProjectId(event);
		if (!targetProjectId && ['star', 'review'].includes(type)) {
			throw new Error(`Project ID required for ${type} action in shared pages API`);
		}
		
		try {
			switch (type) {
				case 'star':
					console.log('🌟 Calling toggleStar for pageId:', pageId, 'projectId:', targetProjectId);
					const starResponse = await SharedPagesApiService.toggleStar(
						pageId, 
						targetProjectId!, 
						event.isStarred || false,
						{
							tags: event.tags,
							personal_note: event.personal_note,
							folder: event.folder
						}
					);
					if (!starResponse.success) {
						throw new Error(starResponse.error?.message || 'Failed to toggle star');
					}
					break;
					
				case 'review':
					console.log('✅ Calling reviewPage for pageId:', pageId, 'projectId:', targetProjectId, 'status:', event.reviewStatus);
					const reviewResponse = await SharedPagesApiService.reviewPage(
						pageId,
						targetProjectId!,
						{
							review_status: event.reviewStatus!,
							review_notes: event.reviewNotes || event.quick_notes,
							quality_score: event.quality_score,
							tags: event.tags
						}
					);
					if (!reviewResponse.success) {
						throw new Error(reviewResponse.error?.message || 'Failed to review page');
					}
					break;
					
				case 'view':
					console.log('👁️ View action for pageId:', pageId);
					// View action is handled by parent component
					break;
					
				case 'more':
					console.log('⋯ More action for pageId:', pageId);
					// More action is handled by parent component
					break;
					
				default:
					console.warn('Unknown page action type:', type);
			}
		} catch (error) {
			console.error(`Page action '${type}' failed for pageId ${pageId}:`, error);
			throw error;
		}
	}

	/**
	 * Handle tag updates with consistent logging and error handling
	 * Uses shared pages API exclusively for tag synchronization
	 */
	static async handleUpdateTags(event: TagUpdateEvent): Promise<void> {
		console.log('🏷️ PageActionsService.handleUpdateTags called:', event);
		const { pageId, tags, projectId } = event;
		
		// Determine project ID - required for shared pages API
		const targetProjectId = projectId || this._getDefaultProjectId(event);
		if (!targetProjectId) {
			throw new Error('Project ID required for tag update in shared pages API');
		}
		
		try {
			console.log('🏷️ Updating tags for pageId:', pageId, 'projectId:', targetProjectId, 'tags:', tags);
			const response = await SharedPagesApiService.updatePageTags(
				pageId,
				targetProjectId,
				tags
			);
			
			if (!response.success) {
				throw new Error(response.error?.message || 'Failed to update tags');
			}
			console.log('🏷️ Tags updated successfully:', response.data);
		} catch (error) {
			console.error(`Tag update failed for pageId ${pageId}:`, error);
			throw error;
		}
	}

	/**
	 * Load page content with consistent error handling
	 * Uses shared pages API for content loading
	 */
	static async loadPageContent(pageId: number, format: 'markdown' | 'html' | 'text' = 'markdown'): Promise<any> {
		console.log('📄 PageActionsService.loadPageContent called:', { pageId, format });
		
		try {
			const response = await SharedPagesApiService.getPageContent(pageId, format);
			if (!response.success) {
				throw new Error(response.error?.message || 'Failed to load page content');
			}
			return response.data;
		} catch (error) {
			console.error(`Content loading failed for pageId ${pageId}:`, error);
			throw error;
		}
	}

	/**
	 * Load tag suggestions with consistent error handling and retry logic
	 * Currently uses legacy API as shared pages API doesn't have tag suggestions endpoint
	 */
	static async loadTagSuggestions(query?: string, pageId?: number): Promise<void> {
		console.log('🔖 PageActionsService.loadTagSuggestions called:', { query, pageId });
		
		// Keep using page management store for tag suggestions since shared pages API 
		// doesn't have this endpoint yet
		const maxRetries = 2;
		let lastError: any = null;
		
		for (let attempt = 0; attempt <= maxRetries; attempt++) {
			try {
				await pageManagementActions.loadTagSuggestions(query, pageId);
				return; // Success, exit retry loop
			} catch (error) {
				lastError = error;
				const isAuthError = error instanceof Error && error.message.includes('Authentication required');
				
				console.warn(`Tag suggestions loading attempt ${attempt + 1} failed:`, error);
				
				// Only retry auth errors and if we have attempts left
				if (isAuthError && attempt < maxRetries) {
					console.log(`Retrying tag suggestions loading in ${(attempt + 1) * 1000}ms...`);
					await new Promise(resolve => setTimeout(resolve, (attempt + 1) * 1000));
					continue;
				}
				
				// Don't retry non-auth errors or if max attempts reached
				break;
			}
		}
		
		console.error('Tag suggestions loading failed after all retry attempts:', lastError);
		// Don't throw the error - this allows the UI to continue functioning without tags
		// The loading state will be cleared by the store
	}

	/**
	 * Create a standardized page action handler for components
	 * Updated to pass project context for shared pages API
	 */
	static createPageActionHandler(refreshCallback: () => Promise<void>, defaultProjectId?: number) {
		return async (event: CustomEvent) => {
			const actionEvent = event.detail as PageActionEvent;
			
			// Ensure project ID is available for shared pages API
			if (!actionEvent.projectId && defaultProjectId) {
				actionEvent.projectId = defaultProjectId;
			}
			
			// Handle view and more actions locally
			if (actionEvent.type === 'view' || actionEvent.type === 'more') {
				// These actions don't need server calls, just pass them through
				return actionEvent;
			}
			
			// Handle server actions
			await PageActionsService.handlePageAction(actionEvent);
			
			// Refresh the parent component's data
			try {
				await refreshCallback();
			} catch (error) {
				console.error('Failed to refresh after page action:', error);
			}
			
			return actionEvent;
		};
	}

	/**
	 * Create a standardized tag update handler for components
	 * Updated to pass project context for shared pages API
	 */
	static createTagUpdateHandler(refreshCallback: () => Promise<void>, defaultProjectId?: number) {
		return async (event: CustomEvent) => {
			const tagEvent = event.detail as TagUpdateEvent;
			
			// Ensure project ID is available for shared pages API
			if (!tagEvent.projectId && defaultProjectId) {
				tagEvent.projectId = defaultProjectId;
			}
			
			// Defer to caller for optimistic update; only call server here
			await PageActionsService.handleUpdateTags(tagEvent);
			
			return tagEvent;
		};
	}

	/**
	 * Helper method to extract project ID from page action event or page data
	 */
	static _getDefaultProjectId(event: any): number | undefined {
		// Try to extract project ID from various sources
		if (event.projectId) return event.projectId;
		if (event.project_id) return event.project_id;
		if (event.page?.project_associations?.[0]?.project_id) {
			return event.page.project_associations[0].project_id;
		}
		if (event.projectIds?.[0]) return event.projectIds[0];
		
		// Could not determine project ID
		return undefined;
	}
}

// Export convenience functions for direct use
export const handlePageAction = PageActionsService.handlePageAction;
export const handleUpdateTags = PageActionsService.handleUpdateTags;
export const loadPageContent = PageActionsService.loadPageContent;
export const loadTagSuggestions = PageActionsService.loadTagSuggestions;