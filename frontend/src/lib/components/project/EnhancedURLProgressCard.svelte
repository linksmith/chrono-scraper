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
		ChevronRight,
		Info,
		Filter,
		PlayCircle,
		Eye,
		XCircle,
		ShieldCheck,
		AlertCircle
	} from 'lucide-svelte';

	export let scrapePage: any;
	export let isSelected: boolean = false;
	export let compact: boolean = true;
	export let showUrl: boolean = true;
	export let showIndex: number | null = null;
	export let showFilteringDetails: boolean = true;

	const dispatch = createEventDispatcher<{
		action: { type: 'retry' | 'skip' | 'priority' | 'view' | 'manual_process' | 'override_filter'; pageId: number; data?: any };
		select: { pageId: number; selected: boolean; shiftKey?: boolean };
		expand: { pageId: number };
	}>();

	let isExpanded = false;

	// Enhanced status and filtering logic
	function getStatusIcon(status: string) {
		switch (status?.toLowerCase()) {
			case 'pending': return Clock;
			case 'in_progress': return Activity;
			case 'completed': return CheckCircle;
			case 'failed': return AlertTriangle;
			case 'skipped': return AlertCircle;
			case 'filtered_duplicate': return XCircle;
			case 'filtered_list_page': return Filter;
			case 'filtered_low_quality': return AlertCircle;
			case 'filtered_size': return FileText;
			case 'filtered_type': return Ban;
			case 'filtered_custom': return Filter;
			case 'awaiting_manual_review': return Eye;
			case 'manually_approved': return ShieldCheck;
			default: return Clock;
		}
	}

	function getStatusColor(status: string) {
		switch (status?.toLowerCase()) {
			case 'pending': return 'warning';
			case 'in_progress': return 'default';
			case 'completed': return 'success';
			case 'failed': return 'destructive';
			case 'skipped': return 'warning';
			case 'filtered_duplicate': return 'outline';
			case 'filtered_list_page': return 'outline';
			case 'filtered_low_quality': return 'warning';
			case 'filtered_size': return 'outline';
			case 'filtered_type': return 'secondary';
			case 'filtered_custom': return 'outline';
			case 'awaiting_manual_review': return 'warning';
			case 'manually_approved': return 'success';
			default: return 'secondary';
		}
	}

	function getStatusDisplayName(status: string): string {
		switch (status?.toLowerCase()) {
			case 'pending': return 'Pending';
			case 'in_progress': return 'In Progress';
			case 'completed': return 'Complete';
			case 'failed': return 'Failed';
			case 'skipped': return 'Low Content';
			case 'filtered_duplicate': return 'Filtered: Duplicate';
			case 'filtered_list_page': return 'Filtered: List Page';
			case 'filtered_low_quality': return 'Filtered: Low Quality';
			case 'filtered_size': return 'Filtered: Size';
			case 'filtered_type': return 'Filtered: File Type';
			case 'filtered_custom': return 'Filtered: Custom';
			case 'awaiting_manual_review': return 'Awaiting Review';
			case 'manually_approved': return 'Manually Approved';
			default: return status;
		}
	}

	function getErrorTypeBadge(errorType: string | null): { label: string; color: string } {
		if (!errorType) return { label: 'Unknown', color: 'secondary' };
		switch (errorType.toLowerCase()) {
			case 'insufficient_content': return { label: 'Low Content', color: 'warning' };
			case 'no_data': return { label: 'No Data', color: 'destructive' };
			case 'extraction_exception': return { label: 'Error', color: 'destructive' };
			case 'timeout_error': return { label: 'Timeout', color: 'destructive' };
			case 'connection_error': return { label: 'Connection', color: 'destructive' };
			case 'indexing_error': return { label: 'Indexing', color: 'destructive' };
			default: return { label: errorType, color: 'destructive' };
		}
	}

	function isFilteredStatus(status: string): boolean {
		return status?.toLowerCase().startsWith('filtered_') ||
		       status?.toLowerCase() === 'awaiting_manual_review';
	}

	function canBeManuallyProcessed(status: string): boolean {
		return isFilteredStatus(status) &&
		       scrapePage.can_be_manually_processed !== false &&
		       status?.toLowerCase() !== 'manually_approved';
	}

	function canRetry(status: string): boolean {
		return status?.toLowerCase() === 'failed' || status?.toLowerCase() === 'skipped';
	}

	function getFilterReasonIcon(reason: string | null) {
		if (!reason) return Filter;

		switch (reason.toLowerCase()) {
			case 'duplicate_content': return XCircle;
			case 'list_page_pattern': return Filter;
			case 'low_quality_content': return AlertCircle;
			case 'size_threshold': return FileText;
			case 'file_type_excluded': return Ban;
			case 'custom_rule': return Filter;
			default: return Info;
		}
	}

	function getFilterCategoryColor(category: string | null): string {
		if (!category) return 'secondary';

		switch (category.toLowerCase()) {
			case 'content_quality': return 'warning';
			case 'duplicate': return 'outline';
			case 'format': return 'secondary';
			case 'size': return 'outline';
			case 'custom': return 'default';
			default: return 'secondary';
		}
	}

	/** Parse filter_details whether it's a string or already an object */
	function parseFilterDetails(details: any): Record<string, any> | null {
		if (!details) return null;
		if (typeof details === 'object') return details;
		try {
			return JSON.parse(details);
		} catch {
			return null;
		}
	}

	function handleAction(type: 'retry' | 'skip' | 'priority' | 'view' | 'manual_process' | 'override_filter', data?: any) {
		dispatch('action', { type, pageId: scrapePage.id, data });
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
		if (scrapePage.wayback_url || scrapePage.content_url) {
			window.open(scrapePage.wayback_url || scrapePage.content_url, '_blank');
		}
	}

	$: StatusIcon = getStatusIcon(scrapePage.status);
	$: FilterIcon = getFilterReasonIcon(scrapePage.filter_reason);
	$: captureDate = scrapePage.unix_timestamp
		? parseTimestamp(scrapePage.unix_timestamp)
		: null;
	$: isFiltered = isFilteredStatus(scrapePage.status);
	$: canManualProcess = canBeManuallyProcessed(scrapePage.status);
	$: wasManuallyOverridden = scrapePage.is_manually_overridden;
	$: isSkipped = scrapePage.status?.toLowerCase() === 'skipped';
	$: isFailed = scrapePage.status?.toLowerCase() === 'failed';
	$: errorTypeBadge = getErrorTypeBadge(scrapePage.error_type);
	$: extractionDiagnostics = parseFilterDetails(scrapePage.filter_details);
	$: retryAttempt = scrapePage.retry_count || 0;
	$: maxRetries = scrapePage.max_retries || 3;
</script>

<div
	class="border rounded-lg transition-all duration-200 hover:shadow-md {isSelected ? 'ring-2 ring-primary' : ''} {compact ? 'p-2' : 'p-3'}"
	class:bg-blue-50={isSelected}
	class:border-amber-200={(isFiltered || isSkipped) && !wasManuallyOverridden}
	class:bg-amber-50={(isFiltered || isSkipped) && !wasManuallyOverridden}
	class:border-red-200={isFailed && !isSelected}
	class:bg-red-50={isFailed && !isSelected}
	class:border-green-200={wasManuallyOverridden}
	class:bg-green-50={wasManuallyOverridden}
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
				{getStatusDisplayName(scrapePage.status)}
			</Badge>

			<!-- Error Type Badge (for failed/skipped) -->
			{#if (isFailed || isSkipped) && scrapePage.error_type}
				<Badge variant={errorTypeBadge.color} class="text-xs px-1.5 py-0">
					{errorTypeBadge.label}
				</Badge>
			{/if}

			<!-- Manual Override Indicator -->
			{#if wasManuallyOverridden}
				<Badge variant="success" class="text-xs px-1 py-0" title="Manually overridden filter">
					<ShieldCheck class="w-3 h-3 mr-0.5" />
					Override
				</Badge>
			{/if}
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
					{#if scrapePage.priority_score && scrapePage.priority_score > 7}
						<Badge variant="default" class="text-xs px-1 py-0">High Priority</Badge>
					{/if}
				</div>
				{#if showUrl}
					<div class="text-sm font-mono truncate text-muted-foreground" title={scrapePage.original_url}>
						{scrapePage.original_url}
					</div>
				{/if}
			</div>

			<!-- Filter Details (always visible for filtered content) -->
			{#if isFiltered && showFilteringDetails}
				<div class="bg-amber-100 border border-amber-200 rounded p-2 text-xs space-y-1">
					<div class="flex items-center gap-2">
						<FilterIcon class="w-3 h-3 text-amber-600" />
						<span class="font-medium text-amber-800">Filtering Reason:</span>
						<span class="text-amber-700">{scrapePage.filter_reason || 'Not specified'}</span>
					</div>
					{#if scrapePage.filter_category}
						<div class="flex items-center gap-2">
							<Badge variant={getFilterCategoryColor(scrapePage.filter_category)} class="text-xs px-1 py-0">
								{scrapePage.filter_category}
							</Badge>
						</div>
					{/if}
					{#if extractionDiagnostics}
						<div class="text-amber-700 italic">
							{#if extractionDiagnostics.word_count !== undefined}
								{extractionDiagnostics.word_count} words extracted
							{/if}
							{#if extractionDiagnostics.extraction_method}
								via {extractionDiagnostics.extraction_method}
							{/if}
						</div>
					{:else if scrapePage.filter_details && typeof scrapePage.filter_details === 'string'}
						<div class="text-amber-700 italic">{scrapePage.filter_details}</div>
					{/if}
					{#if wasManuallyOverridden && scrapePage.original_filter_decision}
						<div class="text-xs text-muted-foreground border-t border-amber-300 pt-1 mt-1">
							Originally: {scrapePage.original_filter_decision}
						</div>
					{/if}
				</div>
			{/if}

			<!-- Extraction Diagnostics for SKIPPED pages -->
			{#if isSkipped && extractionDiagnostics && showFilteringDetails}
				<div class="bg-amber-100 border border-amber-200 rounded p-2 text-xs space-y-1">
					<div class="flex items-center gap-2">
						<AlertCircle class="w-3 h-3 text-amber-600" />
						<span class="font-medium text-amber-800">Extraction Result:</span>
						<span class="text-amber-700">
							{extractionDiagnostics.word_count ?? 0} words
							(min {extractionDiagnostics.min_threshold ?? 50})
						</span>
					</div>
					{#if extractionDiagnostics.extraction_method}
						<div class="text-amber-700">
							Method: <span class="font-mono">{extractionDiagnostics.extraction_method}</span>
						</div>
					{/if}
					{#if extractionDiagnostics.title}
						<div class="text-amber-700">
							Title: <span class="italic">{extractionDiagnostics.title}</span>
						</div>
					{/if}
					{#if extractionDiagnostics.text_preview && isExpanded}
						<div class="mt-1 p-1.5 bg-amber-50 rounded text-amber-800 font-mono text-xs max-h-20 overflow-y-auto">
							{extractionDiagnostics.text_preview}
						</div>
					{/if}
				</div>
			{/if}

			{#if !compact || isExpanded}
				<div class="text-xs text-muted-foreground flex items-center gap-3">
					{#if captureDate}
						<span>{captureDate.toLocaleDateString()}</span>
					{/if}
					<span>{scrapePage.mime_type}</span>
					{#if scrapePage.content_length}
						<span>{getFileSize(scrapePage.content_length)}</span>
					{/if}
					{#if retryAttempt > 0}
						<span class="text-amber-600">Attempt {retryAttempt}/{maxRetries}</span>
					{/if}
				</div>
			{/if}

			{#if scrapePage.error_message && (isExpanded || isFailed)}
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

			<!-- Manual Override Actions -->
			{#if canManualProcess}
				<Button
					variant="outline"
					size="sm"
					class="h-6 px-2 text-xs bg-green-50 hover:bg-green-100 border-green-200"
					onclick={() => handleAction('manual_process')}
					title="Process this page manually despite filtering"
				>
					<PlayCircle class="h-3 w-3 mr-1" />
					Process Anyway
				</Button>
			{/if}

			<!-- Retry button for FAILED and SKIPPED -->
			{#if canRetry(scrapePage.status)}
				<Button
					variant="outline"
					size="sm"
					class="h-6 px-2 text-xs"
					onclick={() => handleAction('retry')}
					title={isSkipped ? "Retry with escalated extraction" : "Retry failed page"}
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

			<!-- Priority boost for any pending/failed/skipped page -->
			{#if scrapePage.status === 'pending' || canRetry(scrapePage.status)}
				<Button
					variant="outline"
					size="sm"
					class="h-6 px-2 text-xs"
					onclick={() => handleAction('priority')}
					title="Bump to high priority queue"
				>
					Priority
				</Button>
			{/if}

			<!-- Override filter action for filtered pages -->
			{#if isFiltered && !wasManuallyOverridden}
				<Button
					variant="ghost"
					size="sm"
					class="h-6 w-6 p-0 text-amber-600 hover:text-amber-800"
					onclick={() => handleAction('override_filter')}
					title="Override filter decision"
				>
					<ShieldCheck class="h-3 w-3" />
				</Button>
			{/if}

			<!-- Wayback Machine Link -->
			{#if scrapePage.wayback_url || scrapePage.content_url}
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

			{#if isFiltered}
				<div class="bg-amber-50 border border-amber-200 rounded p-2 space-y-1">
					<div><strong>Filter Category:</strong> {scrapePage.filter_category || 'N/A'}</div>
					<div><strong>Filter Reason:</strong> {scrapePage.filter_reason || 'N/A'}</div>
					{#if extractionDiagnostics}
						<div class="space-y-1">
							{#if extractionDiagnostics.word_count !== undefined}
								<div><strong>Word Count:</strong> {extractionDiagnostics.word_count}</div>
							{/if}
							{#if extractionDiagnostics.extraction_method}
								<div><strong>Method:</strong> {extractionDiagnostics.extraction_method}</div>
							{/if}
							{#if extractionDiagnostics.text_preview}
								<div>
									<strong>Preview:</strong>
									<div class="mt-1 p-1.5 bg-white rounded text-xs font-mono max-h-20 overflow-y-auto">
										{extractionDiagnostics.text_preview}
									</div>
								</div>
							{/if}
						</div>
					{:else if scrapePage.filter_details && typeof scrapePage.filter_details === 'string'}
						<div><strong>Details:</strong> {scrapePage.filter_details}</div>
					{/if}
					<div><strong>Can Override:</strong> {scrapePage.can_be_manually_processed !== false ? 'Yes' : 'No'}</div>
					{#if scrapePage.priority_score}
						<div><strong>Priority Score:</strong> {scrapePage.priority_score}/10</div>
					{/if}
				</div>
			{/if}

			<!-- Extraction diagnostics in expanded view for SKIPPED/FAILED -->
			{#if (isSkipped || isFailed) && extractionDiagnostics && !isFiltered}
				<div class="bg-gray-50 border border-gray-200 rounded p-2 space-y-1">
					<div class="font-medium text-gray-700">Extraction Diagnostics</div>
					{#if extractionDiagnostics.word_count !== undefined}
						<div><strong>Word Count:</strong> {extractionDiagnostics.word_count} / {extractionDiagnostics.min_threshold ?? 50} min</div>
					{/if}
					{#if extractionDiagnostics.extraction_method}
						<div><strong>Method:</strong> <span class="font-mono">{extractionDiagnostics.extraction_method}</span></div>
					{/if}
					{#if extractionDiagnostics.title}
						<div><strong>Title:</strong> {extractionDiagnostics.title}</div>
					{/if}
					{#if extractionDiagnostics.error}
						<div><strong>Error:</strong> <span class="text-red-600">{extractionDiagnostics.error}</span></div>
					{/if}
					{#if extractionDiagnostics.error_type}
						<div><strong>Error Type:</strong> {extractionDiagnostics.error_type}</div>
					{/if}
					{#if extractionDiagnostics.text_preview}
						<div>
							<strong>Content Preview:</strong>
							<div class="mt-1 p-1.5 bg-white rounded text-xs font-mono max-h-24 overflow-y-auto">
								{extractionDiagnostics.text_preview}
							</div>
						</div>
					{/if}
					{#if extractionDiagnostics.retry_count !== undefined}
						<div><strong>Retry:</strong> Attempt {extractionDiagnostics.retry_count}/{maxRetries}</div>
					{/if}
				</div>
			{/if}

			{#if scrapePage.extracted_text && scrapePage.status === 'completed'}
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
	/* Enhanced styling for filter states */
	.border {
		@apply border-border;
	}

	/* Subtle animations for state changes */
	.transition-all {
		transition-property: all;
		transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
		transition-duration: 200ms;
	}
</style>
