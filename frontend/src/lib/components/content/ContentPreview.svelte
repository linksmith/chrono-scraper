<script lang="ts">
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { formatDateTime, formatNumber, formatBytes } from '$lib/utils';
	import { 
		ExternalLink, 
		Download, 
		Eye, 
		Calendar, 
		FileText, 
		User, 
		Globe,
		Hash,
		BarChart3
	} from 'lucide-svelte';

	export let page: {
		id: number;
		original_url: string;
		wayback_url: string;
		title?: string;
		content_preview?: string;
		word_count?: number;
		character_count?: number;
		capture_date?: string;
		scraped_at?: string;
		status_code?: number;
		content_type?: string;
		language?: string;
		author?: string;
		meta_description?: string;
		domain: {
			id: number;
			domain_name: string;
		};
		project: {
			id: number;
			name: string;
		};
	};

	export let showFullContent = false;
	export let allowExport = true;
	export let allowPreview = true;

	function getStatusCodeColor(code: number): 'success' | 'warning' | 'destructive' | 'secondary' {
		if (code >= 200 && code < 300) return 'success';
		if (code >= 300 && code < 400) return 'warning';
		if (code >= 400) return 'destructive';
		return 'secondary';
	}

	function exportPage(format: 'json' | 'text' | 'markdown') {
		// Implementation would depend on your export API
		console.log(`Exporting page ${page.id} as ${format}`);
	}

	function previewPage() {
		// Open preview modal or new tab
		console.log(`Previewing page ${page.id}`);
	}
</script>

<Card class="w-full">
	<CardHeader class="pb-3">
		<div class="flex items-start justify-between gap-4">
			<div class="flex-1 min-w-0">
				<CardTitle class="text-lg break-words">
					{page.title || 'Untitled Page'}
				</CardTitle>
				<div class="flex flex-wrap items-center gap-2 mt-2 text-sm text-muted-foreground">
					<a 
						href={page.original_url} 
						target="_blank" 
						rel="noopener noreferrer"
						class="inline-flex items-center gap-1 hover:text-foreground transition-colors"
					>
						<Globe class="w-3 h-3" />
						{page.domain.domain_name}
						<ExternalLink class="w-3 h-3" />
					</a>
					<span>•</span>
					<span>{page.project.name}</span>
				</div>
			</div>
			
			<div class="flex flex-col items-end gap-2">
				{#if page.status_code}
					<Badge variant={getStatusCodeColor(page.status_code)}>
						{page.status_code}
					</Badge>
				{/if}
				
				<div class="flex gap-1">
					{#if allowPreview}
						<Button variant="outline" size="sm" on:click={previewPage}>
							<Eye class="w-3 h-3" />
						</Button>
					{/if}
					
					{#if allowExport}
						<Button variant="outline" size="sm" on:click={() => exportPage('json')}>
							<Download class="w-3 h-3" />
						</Button>
					{/if}
					
					<Button variant="outline" size="sm" asChild>
						<a href={page.wayback_url} target="_blank" rel="noopener noreferrer">
							<ExternalLink class="w-3 h-3" />
						</a>
					</Button>
				</div>
			</div>
		</div>
	</CardHeader>

	<CardContent class="space-y-4">
		<!-- Metadata Grid -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
			{#if page.capture_date}
				<div class="flex items-center gap-2">
					<Calendar class="w-4 h-4 text-muted-foreground" />
					<div>
						<div class="text-muted-foreground">Captured</div>
						<div class="font-medium">{formatDateTime(page.capture_date)}</div>
					</div>
				</div>
			{/if}

			{#if page.word_count}
				<div class="flex items-center gap-2">
					<FileText class="w-4 h-4 text-muted-foreground" />
					<div>
						<div class="text-muted-foreground">Word Count</div>
						<div class="font-medium">{formatNumber(page.word_count)}</div>
					</div>
				</div>
			{/if}

			{#if page.character_count}
				<div class="flex items-center gap-2">
					<BarChart3 class="w-4 h-4 text-muted-foreground" />
					<div>
						<div class="text-muted-foreground">Characters</div>
						<div class="font-medium">{formatNumber(page.character_count)}</div>
					</div>
				</div>
			{/if}

			{#if page.language}
				<div class="flex items-center gap-2">
					<Globe class="w-4 h-4 text-muted-foreground" />
					<div>
						<div class="text-muted-foreground">Language</div>
						<div class="font-medium uppercase">{page.language}</div>
					</div>
				</div>
			{/if}
		</div>

		<!-- Author and Meta Description -->
		{#if page.author || page.meta_description}
			<div class="space-y-2">
				{#if page.author}
					<div class="flex items-center gap-2">
						<User class="w-4 h-4 text-muted-foreground" />
						<span class="text-sm">
							<span class="text-muted-foreground">Author:</span>
							<span class="font-medium ml-1">{page.author}</span>
						</span>
					</div>
				{/if}

				{#if page.meta_description}
					<div class="text-sm">
						<span class="text-muted-foreground">Description:</span>
						<p class="mt-1 text-foreground">{page.meta_description}</p>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Content Preview -->
		{#if page.content_preview}
			<div class="space-y-2">
				<div class="text-sm font-medium text-muted-foreground">Content Preview</div>
				<div class="bg-muted/50 rounded-lg p-3 text-sm border">
					<p class="whitespace-pre-wrap break-words leading-relaxed">
						{page.content_preview}
					</p>
				</div>
			</div>
		{/if}

		<!-- Additional Metadata -->
		<details class="text-sm">
			<summary class="cursor-pointer text-muted-foreground hover:text-foreground font-medium">
				Technical Details
			</summary>
			<div class="mt-2 space-y-2">
				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					{#if page.content_type}
						<div>
							<span class="text-muted-foreground">Content Type:</span>
							<span class="font-mono ml-2 text-xs bg-muted px-2 py-1 rounded">{page.content_type}</span>
						</div>
					{/if}

					{#if page.scraped_at}
						<div>
							<span class="text-muted-foreground">Scraped:</span>
							<span class="ml-2 font-medium">{formatDateTime(page.scraped_at)}</span>
						</div>
					{/if}

					<div>
						<span class="text-muted-foreground">Page ID:</span>
						<span class="font-mono ml-2 text-xs">{page.id}</span>
					</div>

					<div>
						<span class="text-muted-foreground">Domain ID:</span>
						<span class="font-mono ml-2 text-xs">{page.domain.id}</span>
					</div>
				</div>

				<div class="pt-2 border-t">
					<div class="text-xs text-muted-foreground mb-1">URLs</div>
					<div class="space-y-1">
						<div>
							<span class="text-muted-foreground">Original:</span>
							<a 
								href={page.original_url} 
								target="_blank" 
								rel="noopener noreferrer"
								class="font-mono text-xs ml-2 text-blue-600 hover:text-blue-800 break-all"
							>
								{page.original_url}
							</a>
						</div>
						<div>
							<span class="text-muted-foreground">Wayback:</span>
							<a 
								href={page.wayback_url} 
								target="_blank" 
								rel="noopener noreferrer"
								class="font-mono text-xs ml-2 text-blue-600 hover:text-blue-800 break-all"
							>
								{page.wayback_url}
							</a>
						</div>
					</div>
				</div>
			</div>
		</details>
	</CardContent>
</Card>