<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import Button from '$lib/components/ui/button/button.svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { 
		Copy, 
		Download, 
		ExternalLink, 
		FileText, 
		Globe, 
		Calendar,
		User,
		Hash
	} from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import { cn } from '$lib/utils';

	export let pageId: number;
	export let content: {
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
		[key: string]: any;
	} | null = null;
	export let loading: boolean = false;
	export let error: string | null = null;
	export let compact: boolean = false;

	const dispatch = createEventDispatcher();

	let selectedFormat: 'markdown' = 'markdown';
	let showMetadata = true;
	let isCollapsed = false;

	$: if (content && content.format !== selectedFormat) {
		loadContent(selectedFormat);
	}

	function loadContent(format: 'markdown' = 'markdown') {
		selectedFormat = format;
		dispatch('loadContent', { pageId, format });
	}

	function copyToClipboard() {
		if (content?.content) {
			try {
				navigator.clipboard.writeText(content.content);
				dispatch('copy', { pageId, format: selectedFormat });
			} catch (e) {
				console.error('Copy failed', e);
			}
		}
	}

	function downloadContent() {
		if (content?.content) {
			const blob = new Blob([content.content], { type: 'text/plain' });
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `page-${pageId}-content.${selectedFormat}`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
			dispatch('download', { pageId, format: selectedFormat });
		}
	}

	function openWaybacklUrl() {
		// Emit event like handleViewWayback from search results
		const wayback = (content as any)?.wayback_url || (content?.url?.includes('web.archive.org') ? content?.url : null);
		const timestamp = (content as any)?.scraped_at || (content as any)?.capture_date || content?.published_date || '';
		console.log('🔎 [MarkdownViewer] openWaybacklUrl()', {
			pageId,
			contentUrl: content?.url,
			wayback_url: (content as any)?.wayback_url,
			resolvedWayback: wayback,
			timestamp
		});
		if (!wayback) {
			console.warn('⚠️ [MarkdownViewer] No Wayback URL available.');
			return;
		}
		dispatch('viewWayback', { url: wayback, timestamp });
	}

	function renderMarkdown(markdown: string): string {
		// Basic markdown rendering - in a real app, use a proper markdown library
		return markdown
			.replace(/^### (.*$)/gim, '<h3 class="text-lg font-semibold mt-4 mb-2">$1</h3>')
			.replace(/^## (.*$)/gim, '<h2 class="text-xl font-semibold mt-6 mb-3">$1</h2>')
			.replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-8 mb-4">$1</h1>')
			.replace(/\*\*(.*)\*\*/gim, '<strong class="font-semibold">$1</strong>')
			.replace(/\*(.*)\*/gim, '<em class="italic">$1</em>')
			.replace(/\[([^\]]+)\]\(([^)]+)\)/gim, '<a href="$2" class="text-primary hover:underline" target="_blank" rel="noopener noreferrer">$1</a>')
			.replace(/\n\n/gim, '</p><p class="mb-3">')
			.replace(/\n/gim, '<br>');
	}

	$: formattedContent = content?.content ? 
		`<p class="mb-3">${renderMarkdown(content.content)}</p>` : '';

	// Build a list of additional metadata entries dynamically (beyond the common ones)
	const STANDARD_FIELDS = new Set([
		'page_id', 'title', 'url', 'content', 'format',
		'word_count', 'character_count', 'language', 'author',
		'published_date', 'meta_description'
	]);

	$: additionalMetadata = content
		? Object.entries(content)
			.filter(([key, value]) => !STANDARD_FIELDS.has(key) && value !== null && value !== undefined && typeof value !== 'object')
			.map(([key, value]) => ({ key, value }))
		: [];
</script>

<Card class={cn("w-full", compact && "text-sm")}>
	<CardHeader class={cn("pb-3", compact && "pb-2")}>
		<div class="flex items-start justify-between gap-3">
			<div class="flex-1 min-w-0">
				<CardTitle class={cn("text-lg leading-tight", compact && "text-base")}>
					{content?.title || 'Page Content'}
				</CardTitle>
				{#if content?.url}
					<div class="flex items-center gap-2 text-sm text-muted-foreground mt-1">
						<Globe class="h-3 w-3" />
						<span class="truncate">{content.url}</span>
					</div>
				{/if}
			</div>

			<!-- Action Buttons -->
			<div class="flex items-center gap-1">
				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					onclick={copyToClipboard}
					disabled={!content}
					title="Copy content"
					id="copy-content-btn"
				>
					<Copy class="h-4 w-4" />
				</Button>

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					onclick={downloadContent}
					disabled={!content}
					title="Download content"
					id="download-content-btn"
				>
					<Download class="h-4 w-4" />
				</Button>

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					onclick={openWaybacklUrl}
					disabled={!content}
					title="Open Wayback Machine URL"
					id="open-url-btn"
				>
					<ExternalLink class="h-4 w-4" />
				</Button>

				<!-- collapse chevrons removed -->
			</div>
		</div>

		<!-- Metadata -->
		{#if showMetadata && content && !isCollapsed}
			<div class="flex flex-wrap items-center gap-4 text-xs text-muted-foreground mt-3 pt-3 border-t">
				{#if content.word_count}
					<div class="flex items-center gap-1">
						<FileText class="h-3 w-3" />
						{content.word_count.toLocaleString()} words
					</div>
				{/if}

				{#if content.character_count}
					<div class="flex items-center gap-1">
						<Hash class="h-3 w-3" />
						{content.character_count.toLocaleString()} chars
					</div>
				{/if}

				{#if content.language}
					<Badge variant="outline" class="text-xs">
						{content.language.toUpperCase()}
					</Badge>
				{/if}

				{#if content.author}
					<div class="flex items-center gap-1">
						<User class="h-3 w-3" />
						{content.author}
					</div>
				{/if}

				{#if content.published_date}
					<div class="flex items-center gap-1">
						<Calendar class="h-3 w-3" />
						{formatDistanceToNow(new Date(content.published_date), { addSuffix: true })}
					</div>
				{/if}
			</div>

			{#if content.meta_description}
				<div class="mt-2 pt-2 border-t text-sm text-muted-foreground">
					<strong>Description:</strong> {content.meta_description}
				</div>
			{/if}

			{#if additionalMetadata.length}
				<div class="mt-2 pt-2 border-t text-xs text-muted-foreground grid grid-cols-1 md:grid-cols-2 gap-2">
					{#each additionalMetadata as item}
						<div class="flex items-center gap-2">
							<span class="font-medium capitalize">{item.key.replace(/_/g, ' ')}:</span>
							<span class="font-mono">{String(item.value)}</span>
						</div>
					{/each}
				</div>
			{/if}
		{/if}
	</CardHeader>

	{#if !isCollapsed}
		<CardContent class={cn("pt-0", compact && "pt-0")}>
			{#if loading}
				<div class="space-y-3">
					<Skeleton class="h-4 w-full" />
					<Skeleton class="h-4 w-4/5" />
					<Skeleton class="h-4 w-3/4" />
					<Skeleton class="h-4 w-full" />
					<Skeleton class="h-4 w-2/3" />
				</div>
			{:else if error}
				<div class="text-destructive text-sm p-4 bg-destructive/10 rounded-md">
					<strong>Error loading content:</strong> {error}
				</div>
			{:else if content}
				<div class={cn(
					"prose prose-sm max-w-none prose-headings:mt-4 prose-headings:mb-2 prose-p:mb-3",
					compact && "prose-xs"
				)}>
					{@html formattedContent}
				</div>
			{:else}
				<div class="text-muted-foreground text-sm text-center py-8">
					No content loaded.
				</div>
			{/if}
		</CardContent>
	{/if}
</Card>

<style>
	:global(.prose) {
		color: inherit;
	}
	
	:global(.prose a) {
		color: hsl(var(--primary));
		text-decoration: none;
	}
	
	:global(.prose a:hover) {
		text-decoration: underline;
	}
	
	:global(.prose strong) {
		font-weight: 600;
	}
	
	:global(.prose h1, .prose h2, .prose h3) {
		font-weight: 600;
		margin-top: 1.5em;
		margin-bottom: 0.5em;
	}
	
	:global(.prose p) {
		margin-bottom: 1em;
	}
</style>