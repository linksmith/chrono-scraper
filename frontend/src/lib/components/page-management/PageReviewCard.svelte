<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader } from '$lib/components/ui/card';
	import PageActionBar from './PageActionBar.svelte';
	import TagAutocomplete from './TagAutocomplete.svelte';
	import { Calendar, Clock, User, Globe, FileText, Hash, ChevronDown, ChevronUp, ExternalLink, Eye } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import { cn } from '$lib/utils';

	export let page: {
		id: number;
		title?: string;
		url: string;
		review_status: string;
		tags: string[];
		word_count?: number;
		content_snippet?: string;
		// Optional pre-highlighted HTML snippet to render with {@html}
		highlighted_snippet_html?: string;
		capture_date?: string;
		scraped_at?: string;
		reviewed_at?: string;
		author?: string;
		language?: string;
		meta_description?: string;
		// Optional fields from search results
		original_url?: string;
		wayback_url?: string;
	};
	export let isStarred: boolean = false;
	export let tagSuggestions: string[] = [];
	export let showExpandedContent: boolean = false;
	export let compact: boolean = false;

	const dispatch = createEventDispatcher();

	let showTagEditor = false;
	let isExpanded = false;

	$: priorityColor = 'border-l-blue-500 bg-blue-50'; // Default styling without priority

	$: statusColor = {
		relevant: 'bg-green-100 text-green-800 border-green-200',
		irrelevant: 'bg-red-100 text-red-800 border-red-200',
		needs_review: 'bg-yellow-100 text-yellow-800 border-yellow-200',
		duplicate: 'bg-purple-100 text-purple-800 border-purple-200',
		unreviewed: 'bg-gray-100 text-gray-800 border-gray-200'
	}[page.review_status] || 'bg-gray-100 text-gray-800 border-gray-200';

	function handleAction(event: CustomEvent) {
		dispatch('action', event.detail);
	}

	function handleStar(event: CustomEvent) {
		dispatch('action', { ...event.detail, type: 'star' });
	}

	function handleReview(event: CustomEvent) {
		dispatch('action', { ...event.detail, type: 'review' });
	}


	function handleTagUpdate(event: CustomEvent) {
		dispatch('updateTags', { pageId: page.id, tags: event.detail });
	}

	function toggleExpanded() {
		isExpanded = !isExpanded;
		if (isExpanded && !showExpandedContent) {
			dispatch('loadContent', { pageId: page.id });
		}
	}

	function truncateText(text: string, maxLength: number): string {
		if (text.length <= maxLength) return text;
		return text.substring(0, maxLength) + '...';
	}

	function getDomainFromUrl(url: string): string {
		try {
			return new URL(url).hostname;
		} catch {
			return url;
		}
	}
</script>

<Card class={cn(
	"border-l-4 transition-all duration-200 hover:shadow-md",
	priorityColor,
	compact && "p-2"
)}>
	<CardHeader class={cn("pb-2", compact && "p-2")}>
		<div class="flex items-start justify-between gap-3">
			<!-- Title and URL -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2 mb-1">
					<h3 class="font-medium text-sm leading-tight truncate">
						{page.title || 'Untitled Page'}
					</h3>
					<button
						class="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
						on:click={() => dispatch('view', { pageId: page.id })}
						title="View content"
					>
						<Eye class="h-3 w-3" />
						View
					</button>
					{#if page.url}
						<a
							class="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
							href={page.url}
							target="_blank"
							rel="noopener noreferrer"
							title="Open archived page in new tab"
						>
							<ExternalLink class="h-3 w-3" />
							Open
						</a>
					{/if}
				</div>
				<div class="flex items-center gap-2 text-xs text-muted-foreground">
					<Globe class="h-3 w-3" />
					<span class="truncate">{getDomainFromUrl(page.url)}</span>
				</div>
			</div>

			<!-- Status -->
			<div class="flex flex-col items-end gap-1">
				<Badge variant="outline" class={statusColor}>
					{page.review_status.replace('_', ' ')}
				</Badge>
			</div>
		</div>

		<!-- Metadata Row -->
		<div class="flex items-center gap-4 text-xs text-muted-foreground mt-2">
			{#if page.word_count}
				<div class="flex items-center gap-1">
					<FileText class="h-3 w-3" />
					{page.word_count} words
				</div>
			{/if}

			{#if page.capture_date}
				<div class="flex items-center gap-1">
					<Calendar class="h-3 w-3" />
					Captured {formatDistanceToNow(new Date(page.capture_date), { addSuffix: true })}
				</div>
			{/if}
			
			{#if page.scraped_at}
				<div class="flex items-center gap-1">
					<Clock class="h-3 w-3" />
					{formatDistanceToNow(new Date(page.scraped_at), { addSuffix: true })}
				</div>
			{/if}

			{#if page.author}
				<div class="flex items-center gap-1">
					<User class="h-3 w-3" />
					{page.author}
				</div>
			{/if}

			{#if page.language}
				<Badge variant="outline" class="text-xs">
					{page.language.toUpperCase()}
				</Badge>
			{/if}
		</div>
	</CardHeader>

	<CardContent class={cn("pt-0", compact && "p-2 pt-0")}>
		<!-- Content Snippet -->
		{#if page.highlighted_snippet_html}
			<div class="text-sm text-muted-foreground mb-3">
				{@html page.highlighted_snippet_html}
			</div>
		{:else if page.content_snippet}
			<div class="text-sm text-muted-foreground mb-3">
				{#if compact}
					{truncateText(page.content_snippet, 120)}
				{:else}
					{truncateText(page.content_snippet, 200)}
				{/if}
			</div>
		{/if}

		<!-- Tags -->
		{#if page.tags.length > 0 || showTagEditor}
			<div class="mb-3">
				{#if showTagEditor}
					<TagAutocomplete
						tags={page.tags}
						suggestions={tagSuggestions}
						on:update={handleTagUpdate}
						on:loadSuggestions={() => dispatch('loadTagSuggestions', { pageId: page.id })}
						size="sm"
					/>
				{:else}
					<div class="flex flex-wrap gap-1">
						{#each page.tags.slice(0, compact ? 3 : 5) as tag}
							<Badge variant="secondary" class="text-xs">
								<Hash class="h-2.5 w-2.5 mr-1" />
								{tag}
							</Badge>
						{/each}
						{#if page.tags.length > (compact ? 3 : 5)}
							<Badge variant="outline" class="text-xs">
								+{page.tags.length - (compact ? 3 : 5)} more
							</Badge>
						{/if}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Action Bar -->
		<div class="flex items-center justify-between">
			<PageActionBar
				pageId={page.id}
				{isStarred}
				reviewStatus={page.review_status}
				tags={page.tags}
				size={compact ? 'sm' : 'md'}
				on:star={handleStar}
				on:tag={() => showTagEditor = !showTagEditor}
				on:review={handleReview}
			/>

			<!-- Expand Button -->
			{#if page.content_snippet && page.content_snippet.length > (compact ? 120 : 200)}
				<button
					class="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
					on:click={toggleExpanded}
				>
					{isExpanded ? 'Less' : 'More'}
					{#if isExpanded}
						<ChevronUp class="h-3 w-3" />
					{:else}
						<ChevronDown class="h-3 w-3" />
					{/if}
				</button>
			{/if}
		</div>

		<!-- Expanded Content -->
		{#if isExpanded && showExpandedContent}
			<div class="mt-3 pt-3 border-t">
				<div class="text-sm space-y-2">
					{#if page.meta_description}
						<div>
							<strong class="text-xs text-muted-foreground">Description:</strong>
							<p class="mt-1">{page.meta_description}</p>
						</div>
					{/if}
					
					<div>
						<strong class="text-xs text-muted-foreground">Full URL:</strong>
						<p class="mt-1 text-xs font-mono break-all text-muted-foreground">{page.url}</p>
					</div>

					{#if page.reviewed_at}
						<div class="text-xs text-muted-foreground">
							<Calendar class="inline h-3 w-3 mr-1" />
							Reviewed {formatDistanceToNow(new Date(page.reviewed_at), { addSuffix: true })}
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</CardContent>
</Card>