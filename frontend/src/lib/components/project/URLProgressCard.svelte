<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { getFileSize, formatDate, getRelativeTime, parseTimestamp } from '$lib/utils';
	import { 
		ExternalLink,
		AlertTriangle,
		Clock,
		CheckCircle,
		Activity,
		Ban,
		FileText,
		RotateCcw,
		ChevronDown,
		ChevronRight
	} from 'lucide-svelte';

	export let scrapePage: any;
	export let isSelected: boolean = false;
	export let compact: boolean = true;
	export let showUrl: boolean = true;
	export let showIndex: number | null = null;

	const dispatch = createEventDispatcher<{
		action: { type: 'retry' | 'skip' | 'priority' | 'view'; pageId: number };
		select: { pageId: number; selected: boolean; shiftKey?: boolean };
		expand: { pageId: number };
	}>();

	let isExpanded = false;

	function getStatusIcon(status: string) {
		switch (status?.toLowerCase()) {
			case 'pending': return Clock;
			case 'in_progress': return Activity;
			case 'completed': return CheckCircle;
			case 'failed': return AlertTriangle;
			case 'skipped': return Ban;
			default: return Clock;
		}
	}

	function getStatusColor(status: string) {
		switch (status?.toLowerCase()) {
			case 'pending': return 'warning';
			case 'in_progress': return 'default';
			case 'completed': return 'outline';
			case 'failed': return 'destructive';
			case 'skipped': return 'secondary';
			default: return 'secondary';
		}
	}

	function handleAction(type: 'retry' | 'skip' | 'priority' | 'view') {
		dispatch('action', { type, pageId: scrapePage.id });
	}

	function handleSelect(event: MouseEvent) {
		dispatch('select', { 
			pageId: scrapePage.id, 
			selected: !isSelected,
			shiftKey: event.shiftKey 
		});
	}

	function toggleExpanded() {
		isExpanded = !isExpanded;
		if (isExpanded) {
			dispatch('expand', { pageId: scrapePage.id });
		}
	}

	function openWaybackUrl() {
		if (scrapePage.wayback_url) {
			window.open(scrapePage.wayback_url, '_blank');
		}
	}

	$: StatusIcon = getStatusIcon(scrapePage.status);
	$: captureDate = scrapePage.unix_timestamp 
		? parseTimestamp(scrapePage.unix_timestamp) 
		: null;
</script>

<div 
	class="border rounded-lg transition-all duration-200 hover:shadow-md {isSelected ? 'ring-2 ring-primary' : ''} {compact ? 'p-2' : 'p-3'}"
	class:bg-blue-50={isSelected}
>
	<div class="flex items-center gap-3">
		<!-- Selection Checkbox -->
		<button
			class="flex-shrink-0 w-4 h-4 border-2 rounded flex items-center justify-center transition-colors
			{isSelected ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground hover:border-primary'}"
			onclick={handleSelect}
		>
			{#if isSelected}
				<svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
					<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>
				</svg>
			{/if}
		</button>

		<!-- Status Icon and Badge -->
		<div class="flex items-center gap-2 flex-shrink-0">
			<StatusIcon class="w-4 h-4 text-muted-foreground" />
			<Badge variant={getStatusColor(scrapePage.status)} class="text-xs px-2 py-0.5">
				{scrapePage.status}
			</Badge>
		</div>

		<!-- URL and Basic Info -->
		<div class="flex-1 min-w-0 space-y-1">
			<div class="flex items-center gap-2">
				{#if showIndex}
					<div class="flex-shrink-0 text-xs text-muted-foreground font-mono bg-muted px-2 py-0.5 rounded">
						#{showIndex}
					</div>
				{/if}
				<div class="flex items-center gap-1 flex-shrink-0">
					{#if scrapePage.is_pdf}
						<Badge variant="outline" class="text-xs px-1 py-0">PDF</Badge>
					{/if}
					{#if scrapePage.is_list_page}
						<Badge variant="secondary" class="text-xs px-1 py-0">List</Badge>
					{/if}
				</div>
				{#if showUrl}
					<div class="text-sm font-mono truncate text-muted-foreground" title={scrapePage.original_url}>
						{scrapePage.original_url}
					</div>
				{/if}
			</div>
			
			{#if !compact || isExpanded}
				<div class="text-xs text-muted-foreground flex items-center gap-3">
					{#if captureDate}
						<span>{captureDate.toLocaleDateString()}</span>
					{/if}
					<span>{scrapePage.mime_type}</span>
					{#if scrapePage.content_length}
						<span>{getFileSize(scrapePage.content_length)}</span>
					{/if}
					{#if scrapePage.retry_count > 0}
						<span class="text-amber-600">{scrapePage.retry_count} retries</span>
					{/if}
				</div>
			{/if}

			{#if scrapePage.error_message && (isExpanded || scrapePage.status === 'failed')}
				<div class="text-xs text-red-600 truncate" title={scrapePage.error_message}>
					Error: {scrapePage.error_message}
				</div>
			{/if}
		</div>

		<!-- Actions -->
		<div class="flex items-center gap-1 flex-shrink-0">
			<!-- Expand/Collapse -->
			{#if compact}
				<Button
					variant="ghost"
					size="sm"
					class="h-6 w-6 p-0"
					onclick={toggleExpanded}
					title={isExpanded ? 'Collapse' : 'Expand details'}
				>
					{#if isExpanded}
						<ChevronDown class="h-3 w-3" />
					{:else}
						<ChevronRight class="h-3 w-3" />
					{/if}
				</Button>
			{/if}

			<!-- Status-specific actions -->
			{#if scrapePage.status === 'failed'}
				<Button
					variant="outline"
					size="sm"
					class="h-6 px-2 text-xs"
					onclick={() => handleAction('retry')}
					title="Retry failed page"
				>
					<RotateCcw class="h-3 w-3 mr-1" />
					Retry
				</Button>
			{/if}

			{#if scrapePage.status === 'pending'}
				<Button
					variant="outline"
					size="sm"
					class="h-6 px-2 text-xs"
					onclick={() => handleAction('skip')}
					title="Skip this page"
				>
					<Ban class="h-3 w-3 mr-1" />
					Skip
				</Button>
			{/if}

			<!-- Wayback Machine Link -->
			{#if scrapePage.wayback_url}
				<Button
					variant="ghost"
					size="sm"
					class="h-6 w-6 p-0"
					onclick={openWaybackUrl}
					title="View in Wayback Machine"
				>
					<ExternalLink class="h-3 w-3" />
				</Button>
			{/if}
		</div>
	</div>

	<!-- Expanded Details -->
	{#if isExpanded && compact}
		<div class="mt-3 pt-3 border-t space-y-2 text-xs text-muted-foreground">
			<div class="grid grid-cols-2 gap-4">
				<div>
					<strong>Domain:</strong> {scrapePage.domain_name || 'Unknown'}
				</div>
				<div>
					<strong>Session:</strong> {scrapePage.scrape_session_id || 'N/A'}
				</div>
				<div>
					<strong>Status Code:</strong> {scrapePage.status_code || 'N/A'}
				</div>
				<div>
					<strong>Method:</strong> {scrapePage.extraction_method || 'N/A'}
				</div>
			</div>
			
			{#if scrapePage.title}
				<div>
					<strong>Title:</strong> {scrapePage.title}
				</div>
			{/if}

			{#if scrapePage.extracted_text}
				<div>
					<strong>Content Preview:</strong>
					<div class="mt-1 p-2 bg-muted rounded text-xs max-h-20 overflow-y-auto">
						{scrapePage.extracted_text}
					</div>
				</div>
			{/if}

			<div class="flex justify-between pt-2">
				<div class="space-y-1">
					{#if scrapePage.first_seen_at}
						<div>First seen: {getRelativeTime(scrapePage.first_seen_at)}</div>
					{/if}
					{#if scrapePage.last_attempt_at}
						<div>Last attempt: {getRelativeTime(scrapePage.last_attempt_at)}</div>
					{/if}
				</div>
				<div class="space-y-1 text-right">
					{#if scrapePage.fetch_time}
						<div>Fetch: {scrapePage.fetch_time}ms</div>
					{/if}
					{#if scrapePage.extraction_time}
						<div>Extract: {scrapePage.extraction_time}ms</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>

<style>
	/* Compact spacing for better density */
	.border {
		@apply border-border;
	}
</style>