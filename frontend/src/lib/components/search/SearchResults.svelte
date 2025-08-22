<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { ExternalLink, Calendar, Globe, FileText, User } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { searchState } from '$lib/stores/search';
	import { formatDistanceToNow } from 'date-fns';
	import PageActionBar from '$lib/components/page-management/PageActionBar.svelte';
	import { pageManagementActions } from '$lib/stores/page-management';
	import MarkdownRenderer from '$lib/components/ui/markdown-renderer.svelte';

	const dispatch = createEventDispatcher<{
		select: { page: any };
		viewWayback: { url: string; timestamp: string };
		pageAction: { type: string; pageId: number; data?: any };
		loadContent: { pageId: number };
	}>();

	// Subscribe to search state
	$: results = $searchState.results;
	$: loading = $searchState.loading;
	$: error = $searchState.error;
	$: pagination = $searchState.pagination;

	interface PageResult {
		id: string;
		title: string;
		url: string;
		domain: string;
		scraped_at: string;
		content_preview: string;
		word_count: number;
		content_type: string;
		language?: string;
		author?: string;
		wayback_url?: string;
		status_code: number;
		project_name?: string;
	}

	function handleSelectPage(page: PageResult) {
		dispatch('select', { page });
	}

	function handleViewWayback(page: PageResult) {
		if (page.wayback_url) {
			dispatch('viewWayback', { 
				url: page.wayback_url, 
				timestamp: page.scraped_at 
			});
		}
	}

	function formatDate(dateString: string): string {
		try {
			// Use more predictable date formatting to avoid hydration mismatches
			const date = new Date(dateString);
			if (isNaN(date.getTime())) {
				return dateString;
			}
			// Use a more stable format that doesn't depend on exact timing
			const now = new Date();
			const diffMs = now.getTime() - date.getTime();
			const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
			
			if (diffDays === 0) return 'Today';
			if (diffDays === 1) return 'Yesterday';
			if (diffDays < 7) return `${diffDays} days ago`;
			if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
			if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
			return `${Math.floor(diffDays / 365)} years ago`;
		} catch {
			return dateString;
		}
	}

	function getStatusBadgeVariant(statusCode: number) {
		if (statusCode >= 200 && statusCode < 300) return 'default';
		if (statusCode >= 300 && statusCode < 400) return 'secondary';
		if (statusCode >= 400 && statusCode < 500) return 'destructive';
		if (statusCode >= 500) return 'destructive';
		return 'outline';
	}

	// Page management handlers
	async function handlePageAction(event: CustomEvent) {
		console.log('📝 handlePageAction called with:', event.detail);
		const { type, pageId } = event.detail;
		try {
			let result: any;
			switch (type) {
				case 'star':
					console.log('🌟 Calling toggleStar for pageId:', pageId);
					result = await pageManagementActions.toggleStar(pageId, event.detail);
					// Update search results locally
					searchState.update(state => ({
						...state,
						results: state.results.map(page => 
							parseInt(page.id) === pageId 
								? { ...page, is_starred: result.starred }
								: page
						)
					}));
					break;
				case 'review':
					console.log('✅ Calling reviewPage for pageId:', pageId, 'with status:', event.detail.reviewStatus);
					result = await pageManagementActions.reviewPage(pageId, {
						review_status: event.detail.reviewStatus
					});
					// Update search results locally
					searchState.update(state => ({
						...state,
						results: state.results.map(page => 
							parseInt(page.id) === pageId 
								? { ...page, review_status: event.detail.reviewStatus }
								: page
						)
					}));
					break;
				case 'view':
					dispatch('loadContent', { pageId });
					break;
				case 'more':
					// Handle more actions
					break;
			}
			dispatch('pageAction', event.detail);
		} catch (error) {
			console.error('Page action error:', error);
		}
	}


</script>

<div class="space-y-4">
	{#if loading}
		<div class="flex items-center justify-center py-12">
			<div class="flex flex-col items-center space-y-4">
				<div class="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
				<p class="text-sm text-muted-foreground">Searching through historical content...</p>
			</div>
		</div>
	{:else if error}
		<Card class="border-destructive">
			<CardContent class="pt-6">
				<div class="flex items-center space-x-2 text-destructive">
					<FileText class="h-5 w-5" />
					<p class="font-medium">Search Error</p>
				</div>
				<p class="mt-2 text-sm text-muted-foreground">{error}</p>
			</CardContent>
		</Card>
	{:else if results.length === 0}
		<Card>
			<CardContent class="pt-6 text-center">
				<FileText class="mx-auto h-12 w-12 text-muted-foreground" />
				<h3 class="mt-4 text-lg font-semibold">No results found</h3>
				<p class="text-muted-foreground">
					Try adjusting your search query or filters to find relevant content.
				</p>
			</CardContent>
		</Card>
	{:else}
		<!-- Results header -->
		<div class="flex items-center justify-between">
			<p class="text-sm text-muted-foreground">
				Found {pagination.total.toLocaleString()} results
				{#if $searchState.query}
					for "<strong>{$searchState.query}</strong>"
				{/if}
			</p>
			<p class="text-sm text-muted-foreground">
				Page {pagination.page} of {pagination.totalPages}
			</p>
		</div>

		<!-- Search results -->
		<div class="space-y-3">
			{#each results as page (page.id)}
				<Card class="transition-colors hover:bg-muted/50">
					<CardHeader class="pb-3">
						<div class="flex items-start justify-between">
							<div class="flex-1 min-w-0">
								<CardTitle class="text-lg leading-6">
									<button
										type="button"
										class="h-auto p-0 text-left text-lg font-semibold text-primary hover:underline bg-transparent border-none cursor-pointer w-full text-left"
										onclick={() => handleSelectPage(page)}
									>
										{page.title || 'Untitled Page'}
									</button>
								</CardTitle>
								<div class="flex items-center space-x-2 mt-1">
									<Globe class="h-3 w-3 text-muted-foreground" />
									<span class="text-sm text-muted-foreground font-mono">
										{page.domain}
									</span>
									<Badge variant={getStatusBadgeVariant(page.status_code)} class="text-xs">
										{page.status_code}
									</Badge>
								</div>
							</div>
							<div class="flex items-center space-x-2">
								{#if page.wayback_url}
									<Button
										variant="outline"
										size="sm"
										onclick={() => handleViewWayback(page)}
									>
										<ExternalLink class="h-3 w-3 mr-1" />
										Wayback
									</Button>
								{/if}
							</div>
						</div>
					</CardHeader>

					<CardContent class="pt-0">
						<!-- Content preview -->
						{#if page.content_preview}
							<div class="text-sm text-muted-foreground mb-3">
								<MarkdownRenderer 
									source={page.content_preview} 
									truncate={true}
									maxLength={300}
									className="prose-sm"
								/>
							</div>
						{/if}

						<!-- Metadata -->
						<div class="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
							<div class="flex items-center space-x-1">
								<Calendar class="h-3 w-3" />
								<span>{formatDate(page.scraped_at)}</span>
							</div>

							{#if page.author}
								<div class="flex items-center space-x-1">
									<User class="h-3 w-3" />
									<span>{page.author}</span>
								</div>
							{/if}

							<div class="flex items-center space-x-1">
								<FileText class="h-3 w-3" />
								<span>{page.word_count.toLocaleString()} words</span>
							</div>

							{#if page.content_type}
								<Badge variant="outline" class="text-xs">
									{page.content_type}
								</Badge>
							{/if}

							{#if page.language}
								<Badge variant="outline" class="text-xs">
									{page.language.toUpperCase()}
								</Badge>
							{/if}

							{#if page.project_name}
								<Badge variant="secondary" class="text-xs">
									{page.project_name}
								</Badge>
							{/if}
						</div>

						<!-- Page Action Bar -->
						<div class="mt-3 pt-3 border-t">
							<PageActionBar
								pageId={parseInt(page.id)}
								isStarred={page.is_starred || false}
								reviewStatus={page.review_status || 'unreviewed'}
								tags={page.tags || []}
								size="sm"
								on:star={handlePageAction}
								on:tag={(e) => console.log('Tag editor needed for page', e.detail.pageId, 'current tags:', e.detail.tags)}
								on:review={handlePageAction}
								on:view={handlePageAction}
								on:more={handlePageAction}
							/>
						</div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{/if}
</div>