/**
 * Unified page action service for consistent handling across search pages
 */
import { pageManagementActions } from '$lib/stores/page-management';

export interface PageActionEvent {
	type: string;
	pageId: number;
	reviewStatus?: string;
	isStarred?: boolean;
	tags?: string[];
	[key: string]: any;
}

export interface TagUpdateEvent {
	pageId: number;
	tags: string[];
}

export class PageActionsService {
	/**
	 * Handle page actions with consistent logging and error handling
	 */
	static async handlePageAction(event: PageActionEvent): Promise<void> {
		console.log('🎯 PageActionsService.handlePageAction called:', event);
		const { type, pageId } = event;
		
		try {
			switch (type) {
				case 'star':
					console.log('🌟 Calling toggleStar for pageId:', pageId);
					await pageManagementActions.toggleStar(pageId, event);
					break;
					
				case 'review':
					console.log('✅ Calling reviewPage for pageId:', pageId, 'status:', event.reviewStatus);
					await pageManagementActions.reviewPage(pageId, {
						review_status: event.reviewStatus!
					});
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
	 */
	static async handleUpdateTags(event: TagUpdateEvent): Promise<void> {
		console.log('🏷️ PageActionsService.handleUpdateTags called:', event);
		const { pageId, tags } = event;
		
		try {
			await pageManagementActions.updatePageTags(pageId, tags);
		} catch (error) {
			console.error(`Tag update failed for pageId ${pageId}:`, error);
			throw error;
		}
	}

	/**
	 * Load page content with consistent error handling
	 */
	static async loadPageContent(pageId: number, format: 'markdown' | 'html' | 'text' = 'markdown'): Promise<any> {
		console.log('📄 PageActionsService.loadPageContent called:', { pageId, format });
		
		try {
			return await pageManagementActions.loadPageContent(pageId, format);
		} catch (error) {
			console.error(`Content loading failed for pageId ${pageId}:`, error);
			throw error;
		}
	}

	/**
	 * Load tag suggestions with consistent error handling
	 */
	static async loadTagSuggestions(query?: string, pageId?: number): Promise<void> {
		console.log('🔖 PageActionsService.loadTagSuggestions called:', { query, pageId });
		
		try {
			await pageManagementActions.loadTagSuggestions(query, pageId);
		} catch (error) {
			console.error('Tag suggestions loading failed:', error);
			throw error;
		}
	}

	/**
	 * Create a standardized page action handler for components
	 */
	static createPageActionHandler(refreshCallback: () => Promise<void>) {
		return async (event: CustomEvent) => {
			const actionEvent = event.detail as PageActionEvent;
			
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
	 */
	static createTagUpdateHandler(refreshCallback: () => Promise<void>) {
		return async (event: CustomEvent) => {
			const tagEvent = event.detail as TagUpdateEvent;
			// Defer to caller for optimistic update; only call server here
			await PageActionsService.handleUpdateTags(tagEvent);
			
			return tagEvent;
		};
	}
}

// Export convenience functions for direct use
export const handlePageAction = PageActionsService.handlePageAction;
export const handleUpdateTags = PageActionsService.handleUpdateTags;
export const loadPageContent = PageActionsService.loadPageContent;
export const loadTagSuggestions = PageActionsService.loadTagSuggestions;