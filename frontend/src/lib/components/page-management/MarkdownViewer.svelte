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
		Hash,
		Eye,
		EyeOff,
		ChevronDown,
		ChevronUp
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
	} | null = null;
	export let loading: boolean = false;
	export let error: string | null = null;
	export let allowFormatChange: boolean = true;
	export let compact: boolean = false;

	const dispatch = createEventDispatcher();

	let selectedFormat: 'markdown' | 'html' | 'text' = 'markdown';
	let showMetadata = true;
	let isCollapsed = false;

	const formats = ['markdown', 'html', 'text'] as const;

	$: if (content && content.format !== selectedFormat) {
		loadContent(selectedFormat);
	}

	function loadContent(format: 'markdown' | 'html' | 'text' = 'markdown') {
		selectedFormat = format;
		dispatch('loadContent', { pageId, format });
	}

	function copyToClipboard() {
		if (content?.content) {
			navigator.clipboard.writeText(content.content);
			dispatch('copy', { pageId, format: selectedFormat });
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

	function openOriginalUrl() {
		if (content?.url) {
			window.open(content.url, '_blank');
			dispatch('openUrl', { pageId, url: content.url });
		}
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

	$: formattedContent = content?.content ? (
		selectedFormat === 'markdown' ? 
			`<p class="mb-3">${renderMarkdown(content.content)}</p>` :
		selectedFormat === 'html' ?
			content.content :
		`<pre class="whitespace-pre-wrap font-mono text-sm">${content.content}</pre>`
	) : '';
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
				{#if allowFormatChange}
					<div class="flex bg-muted rounded-md p-1">
						{#each formats as format}
							<Button
								variant={selectedFormat === format ? 'default' : 'ghost'}
								size="sm"
								class="h-7 px-2 text-xs"
								on:click={() => loadContent(format as 'markdown' | 'html' | 'text')}
								disabled={loading}
							>
								{format.toUpperCase()}
							</Button>
						{/each}
					</div>
				{/if}

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					on:click={() => showMetadata = !showMetadata}
					title={showMetadata ? 'Hide metadata' : 'Show metadata'}
				>
					{#if showMetadata}
						<EyeOff class="h-4 w-4" />
					{:else}
						<Eye class="h-4 w-4" />
					{/if}
				</Button>

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					on:click={copyToClipboard}
					disabled={!content}
					title="Copy content"
				>
					<Copy class="h-4 w-4" />
				</Button>

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					on:click={downloadContent}
					disabled={!content}
					title="Download content"
				>
					<Download class="h-4 w-4" />
				</Button>

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					on:click={openOriginalUrl}
					disabled={!content}
					title="Open original URL"
				>
					<ExternalLink class="h-4 w-4" />
				</Button>

				<Button
					variant="ghost"
					size="icon"
					class="h-8 w-8"
					on:click={() => isCollapsed = !isCollapsed}
					title={isCollapsed ? 'Expand content' : 'Collapse content'}
				>
					{#if isCollapsed}
						<ChevronDown class="h-4 w-4" />
					{:else}
						<ChevronUp class="h-4 w-4" />
					{/if}
				</Button>
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
					"prose prose-sm max-w-none",
					selectedFormat === 'text' && "font-mono text-sm whitespace-pre-wrap",
					selectedFormat === 'html' && "prose-headings:mt-4 prose-headings:mb-2 prose-p:mb-3",
					compact && "prose-xs"
				)}>
					{@html formattedContent}
				</div>
			{:else}
				<div class="text-muted-foreground text-sm text-center py-8">
					No content loaded. Click a format button to load content.
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