<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Filter, Grid, List, AlertTriangle } from 'lucide-svelte';
	import PageReviewCard from '$lib/components/page-management/PageReviewCard.svelte';
	import MarkdownViewer from '$lib/components/page-management/MarkdownViewer.svelte';
	import BulkSelectAllManager from '$lib/components/page-management/BulkSelectAllManager.svelte';
	import BulkActionToolbar from '$lib/components/page-management/BulkActionToolbar.svelte';
	import BulkSelectionManager from '$lib/components/page-management/BulkSelectionManager.svelte';
	import { 
		pageManagementStore, 
		pageManagementActions,
		bulkSelectionMode,
		selectedPagesCount,
		hasSelectedPages
	} from '$lib/stores/page-management';

	export let results: any[] = [];
	export let loading: boolean = false;
	export let error: string = '';
	export let searchQuery: string = '';
	export let viewMode: 'list' | 'grid' = 'list';
	export let showPageManagement: boolean = false;
	export let refreshCallback: () => Promise<void>;
	export let loadPageContentCallback: (pageId: number, format?: 'markdown' | 'html' | 'text') => Promise<any>;
	export let loadTagSuggestionsCallback: () => Promise<void>;

	const dispatch = createEventDispatcher<{
		viewModeChange: { mode: 'list' | 'grid' };
		pageManagementToggle: boolean;
		pageAction: { type: string; pageId: number; data?: any };
		updateTags: { pageId: number; tags: string[] };
		loadContent: { pageId: number; format?: 'markdown' | 'html' | 'text' };
	}>();

	let selectedPageId: number | null = null;
	let pageContent: any = null;
	let contentLoading = false;

	// Reactive state for bulk selection
	$: inBulkMode = $bulkSelectionMode;
	$: selectedCount = $selectedPagesCount;
	$: showBulkToolbar = $hasSelectedPages;

	// Handle page actions with consistent logging
	async function handlePageAction(event: CustomEvent) {
		console.log('🔄 UnifiedSearchResults handlePageAction called:', event.detail);
		const { type, pageId } = event.detail as { type: string; pageId: number };
		if (type === 'view') {
			selectedPageId = pageId;
			showPageManagement = true;
			contentLoading = true;
			try {
				pageContent = await loadPageContentCallback(pageId, 'markdown');
			} catch (error) {
				console.error('Failed to load page content:', error);
			} finally {
				contentLoading = false;
			}
			return;
		}
		dispatch('pageAction', event.detail);
		// Avoid forcing a full refresh here; parent decides whether to refresh or apply optimistic update
	}

	async function handleUpdateTags(event: CustomEvent) {
		console.log('🏷️ UnifiedSearchResults handleUpdateTags called:', event.detail);
		dispatch('updateTags', event.detail);
		// Avoid forcing a full refresh here to prevent UI flash; parent will update state optimistically
	}

	async function handleLoadContent(event: CustomEvent) {
		const { pageId, format } = event.detail;
		selectedPageId = pageId;
		showPageManagement = true;
		
		contentLoading = true;
		try {
			pageContent = await loadPageContentCallback(pageId, format);
		} catch (error) {
			console.error('Content loading error:', error);
		} finally {
			contentLoading = false;
		}
	}

	async function handleLoadTagSuggestions() {
		try {
			await loadTagSuggestionsCallback();
		} catch (error) {
			console.error('Failed to load tag suggestions:', error);
		}
	}

	function handleViewModeChange(mode: 'list' | 'grid') {
		dispatch('viewModeChange', { mode });
	}

	function handlePageManagementToggle() {
		const newValue = !showPageManagement;
		dispatch('pageManagementToggle', newValue);
		
		// Also toggle bulk selection mode
		pageManagementActions.toggleBulkSelectionMode();
	}

	function closePageManagement() {
		showPageManagement = false;
		selectedPageId = null;
		pageContent = null;
	}

	function handleEsc(event: KeyboardEvent) {
		if (event.key === 'Escape' && showPageManagement) {
			closePageManagement();
		}
	}

	// Bulk action handlers
	async function handleBulkAction(event: CustomEvent) {
		console.log('📦 Bulk action performed:', event.detail);
		try {
			// Refresh results after bulk action
			await refreshCallback();
		} catch (error) {
			console.error('Failed to refresh after bulk action:', error);
		}
	}

	function handleCloseBulkToolbar() {
		pageManagementActions.clearSelection();
	}

	// Sync pages to store when results change
	$: if (results) {
		pageManagementStore.update(state => ({
			...state,
			pages: results.map(result => ({
				id: parseInt(result.id),
				title: result.title,
				url: result.url,
				review_status: result.review_status || 'unreviewed',
				tags: result.tags || [],
				word_count: result.word_count,
				content_snippet: result.content_snippet || result.content,
				scraped_at: result.scraped_at,
				reviewed_at: result.reviewed_at,
				author: result.author,
				language: result.language,
				meta_description: result.meta_description,
				is_starred: result.is_starred
			}))
		}));
	}
</script>

<!-- Global ESC handler for closing the content overlay -->
<svelte:window on:keydown={handleEsc} />

<!-- Results Header -->
{#if results.length > 0}
	<div class="space-y-4">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-4">
				<p class="text-sm text-muted-foreground">
					Found {results.length} result{results.length !== 1 ? 's' : ''}
					{#if searchQuery.trim()}
						for "<strong>{searchQuery}</strong>"
					{/if}
				</p>
				
				{#if inBulkMode}
					<BulkSelectAllManager />
				{/if}
			</div>
			
			<div class="flex items-center space-x-2">
				<!-- View Mode Toggle -->
				<div class="flex bg-muted rounded-md p-1">
					<Button
						variant={viewMode === 'list' ? 'default' : 'ghost'}
						size="sm"
						class="h-8 px-2"
						onclick={() => handleViewModeChange('list')}
					>
						<List class="h-4 w-4" />
					</Button>
					<Button
						variant={viewMode === 'grid' ? 'default' : 'ghost'}
						size="sm"
						class="h-8 px-2"
						onclick={() => handleViewModeChange('grid')}
					>
						<Grid class="h-4 w-4" />
					</Button>
				</div>

				<Button 
					variant="outline" 
					size="sm"
					onclick={handlePageManagementToggle}
				>
					<Filter class="h-4 w-4 mr-2" />
					{showPageManagement ? 'Hide' : 'Show'} Page Management
				</Button>
			</div>
		</div>

		<!-- Results Grid/List -->
		<div class="relative">
			<!-- Loading overlay for smooth transitions -->
			{#if loading}
				<div class="absolute inset-0 bg-background/80 backdrop-blur-sm z-10 flex items-center justify-center rounded-lg transition-all duration-200">
					<div class="flex items-center space-x-3">
						<div class="animate-spin h-5 w-5 border-2 border-primary border-t-transparent rounded-full"></div>
						<span class="text-sm text-muted-foreground">Updating results...</span>
					</div>
				</div>
			{/if}
			
			<div class="{viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4' : 'space-y-4'} transition-opacity duration-200 {loading ? 'opacity-50' : 'opacity-100'}">
				{#each results as result, index}
					<div class="relative">
						{#if inBulkMode}
							<div class="absolute top-2 left-2 z-10">
								<BulkSelectionManager
									pageId={parseInt(result.id)}
									pageIndex={index}
									compact={viewMode === 'grid'}
								/>
							</div>
						{/if}
						
						<PageReviewCard
							page={{
								id: result.id,
								title: result.title,
								url: result.url,
								review_status: result.review_status || 'unreviewed',
								tags: result.tags || [],
								word_count: result.word_count,
								content_snippet: result.content_snippet || result.content,
								highlighted_snippet_html: result.highlighted_snippet_html,
								capture_date: result.capture_date,
								scraped_at: result.scraped_at,
								reviewed_at: result.reviewed_at,
								author: result.author,
								language: result.language,
								meta_description: result.meta_description,
								original_url: result.original_url,
								wayback_url: result.wayback_url
							}}
							isStarred={result.is_starred || false}
							tagSuggestions={$pageManagementStore.tagSuggestions.map(s => typeof s === 'string' ? s : s.tag)}
							compact={viewMode === 'grid'}
							showExpandToggle={false}
							on:action={handlePageAction}
							on:updateTags={handleUpdateTags}
							on:loadTagSuggestions={handleLoadTagSuggestions}
							on:loadContent={handleLoadContent}
						/>
					</div>
				{/each}
			</div>
		</div>
	</div>
{:else if searchQuery.trim() && !loading}
	<Card>
		<CardContent class="pt-6">
			<div class="flex flex-col items-center justify-center space-y-3 py-12">
				<div class="text-center">
					<h3 class="text-lg font-semibold">No results found</h3>
					<p class="text-muted-foreground">
						Try different search terms or adjust your filters.
					</p>
				</div>
			</div>
		</CardContent>
	</Card>
{:else if !searchQuery.trim() && !loading}
	<Card>
		<CardContent class="pt-6">
			<div class="flex flex-col items-center justify-center space-y-3 py-12">
				<div class="text-center">
					<h3 class="text-lg font-semibold">Start searching</h3>
					<p class="text-muted-foreground">
						Enter a search query to find content.
					</p>
				</div>
			</div>
		</CardContent>
	</Card>
{/if}

<!-- Error Message -->
{#if error}
	<Card class="border-destructive">
		<CardContent class="pt-4 sm:pt-6">
			<div class="flex items-start sm:items-center space-x-2 text-destructive">
				<AlertTriangle class="h-4 w-4 mt-0.5 sm:mt-0 flex-shrink-0" />
				<p class="text-sm sm:text-base break-words">{error}</p>
			</div>
		</CardContent>
	</Card>
{/if}

<!-- Page Content Viewer Modal/Sidebar -->
{#if showPageManagement && selectedPageId}
	<div class="fixed inset-0 z-50 flex justify-end !mt-0" style="margin:0 !important;">
		<!-- Dimmed background; clicking closes -->
		<div
			class="absolute inset-0 bg-black/50"
			role="button"
			tabindex="0"
			aria-label="Close page content"
			on:click={closePageManagement}
			on:keydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); closePageManagement(); } }}
			style="margin:0 !important;"
		></div>
		<!-- Slide-over panel without top white band -->
		<div class="relative z-10 w-full max-w-4xl h-full overflow-y-auto bg-background" style="margin:0 !important;">
			<div class="p-6">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-xl font-semibold">Page Content</h2>
					<Button variant="ghost" size="sm" onclick={closePageManagement}>✕</Button>
				</div>
				<MarkdownViewer
					pageId={selectedPageId}
					content={pageContent}
					loading={contentLoading}
					on:loadContent={handleLoadContent}
					on:viewWayback={(e) => { console.log('🔗 [UnifiedSearchResults] viewWayback event', e.detail); window.open(e.detail.url, '_blank'); }}
					on:copy={() => console.log('Content copied')}
					on:download={() => console.log('Content downloaded')}
					on:openUrl={(e) => window.open(e.detail.url, '_blank')}
				/>
			</div>
		</div>
	</div>
{/if}

<!-- Bulk Action Toolbar -->
{#if showBulkToolbar}
	<BulkActionToolbar
		on:bulkAction={handleBulkAction}
		on:closeToolbar={handleCloseBulkToolbar}
	/>
{/if}