<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Popover, PopoverContent, PopoverTrigger } from '$lib/components/ui/popover';
	import { Progress } from '$lib/components/ui/progress';
	import { Separator } from '$lib/components/ui/separator';
	import { 
		Filter,
		XCircle,
		AlertCircle,
		FileText,
		Ban,
		Info,
		ShieldCheck,
		Eye,
		Clock,
		Activity,
		CheckCircle,
		AlertTriangle,
		Zap,
		Star,
		Target,
		Layers,
		TrendingUp,
		TrendingDown
	} from 'lucide-svelte';
	
	import type { ScrapePageStatus, FilterReason, FilterCategory } from '$lib/types/scraping';
	
	export let status: ScrapePageStatus;
	export let filterReason: FilterReason | null = null;
	export let filterCategory: FilterCategory | null = null;
	export let isManuallyOverridden: boolean = false;
	export let priorityScore: number | null = null;
	export let confidenceScore: number | null = null;
	export let filterDetails: string | null = null;
	export let canBeProcessed: boolean = false;
	export let size: 'xs' | 'sm' | 'md' | 'lg' = 'md';
	export let showIcon: boolean = true;
	export let showTooltip: boolean = true;
	export let showLayered: boolean = true;
	export let interactive: boolean = false;
	
	const dispatch = createEventDispatcher<{
		statusClick: {
			status: ScrapePageStatus;
			details: any;
		};
		overrideClick: {
			action: 'override' | 'restore';
			status: ScrapePageStatus;
		};
	}>();
	
	// Enhanced status mappings with comprehensive filtering states
	function getStatusConfig(status: ScrapePageStatus) {
		const baseStatus = status?.toLowerCase() || '';
		
		// Processing states
		if (baseStatus === 'pending') return {
			label: 'Pending',
			shortLabel: 'Pending',
			variant: 'outline' as const,
			icon: Clock,
			color: 'text-yellow-700',
			bgColor: 'bg-yellow-50',
			borderColor: 'border-yellow-200',
			fillColor: 'bg-yellow-100',
			category: 'processing',
			priority: 2,
			description: 'Page is queued for processing'
		};
		
		if (baseStatus === 'in_progress') return {
			label: 'Processing',
			shortLabel: 'Active',
			variant: 'default' as const,
			icon: Activity,
			color: 'text-blue-700',
			bgColor: 'bg-blue-50',
			borderColor: 'border-blue-200',
			fillColor: 'bg-blue-100',
			category: 'processing',
			priority: 1,
			description: 'Page is currently being processed'
		};
		
		if (baseStatus === 'completed') return {
			label: 'Completed',
			shortLabel: 'Done',
			variant: 'success' as const,
			icon: CheckCircle,
			color: 'text-green-700',
			bgColor: 'bg-green-50',
			borderColor: 'border-green-200',
			fillColor: 'bg-green-100',
			category: 'success',
			priority: 5,
			description: 'Page successfully processed and indexed'
		};
		
		if (baseStatus === 'failed') return {
			label: 'Failed',
			shortLabel: 'Error',
			variant: 'destructive' as const,
			icon: AlertTriangle,
			color: 'text-red-700',
			bgColor: 'bg-red-50',
			borderColor: 'border-red-200',
			fillColor: 'bg-red-100',
			category: 'error',
			priority: 6,
			description: 'Processing failed due to an error'
		};
		
		if (baseStatus === 'skipped') return {
			label: 'Skipped',
			shortLabel: 'Skip',
			variant: 'secondary' as const,
			icon: Ban,
			color: 'text-gray-700',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200',
			fillColor: 'bg-gray-100',
			category: 'neutral',
			priority: 4,
			description: 'Page was skipped by user or system'
		};

		// Filtering states with enhanced details
		if (baseStatus === 'filtered_duplicate') return {
			label: 'Duplicate Content',
			shortLabel: 'Duplicate',
			variant: 'outline' as const,
			icon: XCircle,
			color: 'text-orange-700',
			bgColor: 'bg-orange-50',
			borderColor: 'border-orange-200',
			fillColor: 'bg-orange-100',
			category: 'filtered',
			priority: 3,
			description: 'Page content is a duplicate of existing content'
		};
		
		if (baseStatus === 'filtered_list_page') return {
			label: 'List/Navigation Page',
			shortLabel: 'List Page',
			variant: 'outline' as const,
			icon: Filter,
			color: 'text-purple-700',
			bgColor: 'bg-purple-50',
			borderColor: 'border-purple-200',
			fillColor: 'bg-purple-100',
			category: 'filtered',
			priority: 3,
			description: 'Page identified as list/navigation with low content value'
		};
		
		if (baseStatus === 'filtered_low_quality') return {
			label: 'Low Quality Content',
			shortLabel: 'Low Quality',
			variant: 'warning' as const,
			icon: AlertCircle,
			color: 'text-amber-700',
			bgColor: 'bg-amber-50',
			borderColor: 'border-amber-200',
			fillColor: 'bg-amber-100',
			category: 'filtered',
			priority: 3,
			description: 'Content quality below minimum threshold'
		};
		
		if (baseStatus === 'filtered_size') return {
			label: 'Size Constraints',
			shortLabel: 'Size Limit',
			variant: 'outline' as const,
			icon: FileText,
			color: 'text-indigo-700',
			bgColor: 'bg-indigo-50',
			borderColor: 'border-indigo-200',
			fillColor: 'bg-indigo-100',
			category: 'filtered',
			priority: 3,
			description: 'Page size outside acceptable range'
		};
		
		if (baseStatus === 'filtered_type') return {
			label: 'File Type Excluded',
			shortLabel: 'File Type',
			variant: 'secondary' as const,
			icon: Ban,
			color: 'text-gray-700',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200',
			fillColor: 'bg-gray-100',
			category: 'filtered',
			priority: 4,
			description: 'File type not in allowed formats'
		};
		
		if (baseStatus === 'filtered_custom') return {
			label: 'Custom Rule Match',
			shortLabel: 'Custom Rule',
			variant: 'outline' as const,
			icon: Filter,
			color: 'text-teal-700',
			bgColor: 'bg-teal-50',
			borderColor: 'border-teal-200',
			fillColor: 'bg-teal-100',
			category: 'filtered',
			priority: 3,
			description: 'Matched custom filtering rule'
		};

		// Review states
		if (baseStatus === 'awaiting_manual_review') return {
			label: 'Awaiting Manual Review',
			shortLabel: 'Review Needed',
			variant: 'warning' as const,
			icon: Eye,
			color: 'text-amber-700',
			bgColor: 'bg-amber-50',
			borderColor: 'border-amber-200',
			fillColor: 'bg-amber-100',
			category: 'review',
			priority: 2,
			description: 'Requires manual review before processing'
		};
		
		if (baseStatus === 'manually_approved') return {
			label: 'Manually Approved',
			shortLabel: 'Approved',
			variant: 'success' as const,
			icon: ShieldCheck,
			color: 'text-green-700',
			bgColor: 'bg-green-50',
			borderColor: 'border-green-200',
			fillColor: 'bg-green-100',
			category: 'approved',
			priority: 5,
			description: 'Manually approved for processing'
		};

		// Default fallback
		return {
			label: status || 'Unknown Status',
			shortLabel: 'Unknown',
			variant: 'secondary' as const,
			icon: Info,
			color: 'text-gray-600',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200',
			fillColor: 'bg-gray-100',
			category: 'unknown',
			priority: 0,
			description: 'Status information not available'
		};
	}
	
	function getPriorityConfig(score: number | null) {
		if (score === null) return { label: 'No Priority', color: 'text-gray-500', icon: Target };
		
		if (score >= 7) return {
			label: 'High Priority',
			color: 'text-green-600',
			icon: TrendingUp,
			badgeColor: 'bg-green-100 text-green-700 border-green-200'
		};
		
		if (score >= 4) return {
			label: 'Normal Priority',
			color: 'text-blue-600',
			icon: Target,
			badgeColor: 'bg-blue-100 text-blue-700 border-blue-200'
		};
		
		return {
			label: 'Low Priority',
			color: 'text-orange-600',
			icon: TrendingDown,
			badgeColor: 'bg-orange-100 text-orange-700 border-orange-200'
		};
	}
	
	function getConfidenceConfig(score: number | null) {
		if (score === null) return { label: 'No Confidence Score', color: 'text-gray-500' };
		
		const percentage = Math.round(score * 100);
		
		if (percentage >= 80) return {
			label: `${percentage}% Confidence`,
			color: 'text-green-600',
			level: 'high'
		};
		
		if (percentage >= 60) return {
			label: `${percentage}% Confidence`,
			color: 'text-blue-600',
			level: 'medium'
		};
		
		return {
			label: `${percentage}% Confidence`,
			color: 'text-orange-600',
			level: 'low'
		};
	}
	
	function getSizeClasses(size: string) {
		switch (size) {
			case 'xs': return 'text-xs px-1.5 py-0.5 h-5';
			case 'sm': return 'text-xs px-2 py-0.5 h-6';
			case 'lg': return 'text-sm px-3 py-1.5 h-8';
			case 'md':
			default: return 'text-xs px-2.5 py-1 h-7';
		}
	}
	
	function getIconSize(size: string) {
		switch (size) {
			case 'xs': return 'h-2.5 w-2.5';
			case 'sm': return 'h-3 w-3';
			case 'lg': return 'h-4 w-4';
			case 'md':
			default: return 'h-3.5 w-3.5';
		}
	}
	
	function handleStatusClick() {
		if (!interactive) return;
		
		dispatch('statusClick', {
			status,
			details: {
				filterReason,
				filterCategory,
				filterDetails,
				priorityScore,
				confidenceScore,
				isManuallyOverridden,
				canBeProcessed
			}
		});
	}
	
	function handleOverrideAction(action: 'override' | 'restore') {
		dispatch('overrideClick', { action, status });
	}
	
	// Computed values
	$: config = getStatusConfig(status);
	$: priorityConfig = getPriorityConfig(priorityScore);
	$: confidenceConfig = getConfidenceConfig(confidenceScore);
	$: sizeClasses = getSizeClasses(size);
	$: iconSize = getIconSize(size);
	$: isFiltered = config.category === 'filtered';
	$: needsReview = config.category === 'review';
	$: hasError = config.category === 'error';
	$: isSuccess = config.category === 'success' || config.category === 'approved';
	
	// Complex tooltip content
	$: tooltipContent = showTooltip ? {
		title: config.label,
		description: config.description,
		details: [
			...(filterReason ? [`Reason: ${filterReason.replace(/_/g, ' ')}`] : []),
			...(filterCategory ? [`Category: ${filterCategory.replace(/_/g, ' ')}`] : []),
			...(priorityScore !== null ? [`Priority: ${priorityScore}/10`] : []),
			...(confidenceScore !== null ? [`Confidence: ${Math.round(confidenceScore * 100)}%`] : []),
			...(isManuallyOverridden ? ['Manual Override Active'] : []),
			...(canBeProcessed ? ['Can be manually processed'] : [])
		]
	} : null;
	
	$: showAdvancedIndicators = showLayered && (
		priorityScore !== null || 
		confidenceScore !== null || 
		isManuallyOverridden || 
		canBeProcessed
	);
</script>

<!-- Main Badge Container -->
<div class="inline-flex items-center gap-1 relative group">
	<!-- Core Status Badge -->
	{#if interactive}
		<Popover>
			<PopoverTrigger asChild>
				<button
					class="inline-flex items-center gap-1.5 {sizeClasses} rounded-md border font-medium transition-all duration-200 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 {config.color} {config.bgColor} {config.borderColor} {isManuallyOverridden ? 'ring-1 ring-green-400 ring-offset-1' : ''}"
					onclick={handleStatusClick}
				>
					{#if showIcon}
						<svelte:component this={config.icon} class="{iconSize} flex-shrink-0" />
					{/if}
					<span class="truncate">
						{size === 'xs' || size === 'sm' ? config.shortLabel : config.label}
					</span>
					
					<!-- Priority indicator dot -->
					{#if priorityScore !== null && showAdvancedIndicators}
						<div class="flex-shrink-0 w-2 h-2 rounded-full {priorityScore >= 7 ? 'bg-green-500' : priorityScore >= 4 ? 'bg-blue-500' : 'bg-orange-500'}"></div>
					{/if}
				</button>
			</PopoverTrigger>
			
			<PopoverContent class="w-80 p-4" side="bottom" align="start">
				<div class="space-y-4">
					<!-- Header -->
					<div class="flex items-center gap-2">
						<svelte:component this={config.icon} class="h-5 w-5 {config.color}" />
						<div>
							<h4 class="font-semibold text-sm">{config.label}</h4>
							<p class="text-xs text-muted-foreground">{config.description}</p>
						</div>
					</div>
					
					<Separator />
					
					<!-- Details Grid -->
					<div class="grid grid-cols-2 gap-3 text-sm">
						{#if filterReason}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Filter Reason</Label>
								<p class="text-xs">{filterReason.replace(/_/g, ' ')}</p>
							</div>
						{/if}
						
						{#if filterCategory}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Category</Label>
								<p class="text-xs">{filterCategory.replace(/_/g, ' ')}</p>
							</div>
						{/if}
						
						{#if priorityScore !== null}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Priority Score</Label>
								<div class="flex items-center gap-2">
									<Progress value={priorityScore * 10} class="flex-1 h-2" />
									<span class="text-xs {priorityConfig.color}">{priorityScore}/10</span>
								</div>
							</div>
						{/if}
						
						{#if confidenceScore !== null}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Confidence</Label>
								<div class="flex items-center gap-2">
									<Progress value={confidenceScore * 100} class="flex-1 h-2" />
									<span class="text-xs {confidenceConfig.color}">{Math.round(confidenceScore * 100)}%</span>
								</div>
							</div>
						{/if}
					</div>
					
					<!-- Filter Details -->
					{#if filterDetails}
						<div>
							<Label class="text-xs font-medium text-muted-foreground mb-2 block">Filter Details</Label>
							<div class="bg-muted rounded-md p-3 text-xs font-mono">
								{#try}
									{JSON.stringify(JSON.parse(filterDetails), null, 2)}
								{:catch}
									{filterDetails}
								{/try}
							</div>
						</div>
					{/if}
					
					<!-- Action Buttons -->
					{#if isFiltered && canBeProcessed}
						<div class="flex gap-2 pt-2">
							{#if !isManuallyOverridden}
								<Button
									size="sm"
									onclick={() => handleOverrideAction('override')}
									class="text-xs"
								>
									<ShieldCheck class="h-3 w-3 mr-1" />
									Override Filter
								</Button>
							{:else}
								<Button
									variant="outline"
									size="sm"
									onclick={() => handleOverrideAction('restore')}
									class="text-xs"
								>
									<Filter class="h-3 w-3 mr-1" />
									Restore Filter
								</Button>
							{/if}
						</div>
					{/if}
				</div>
			</PopoverContent>
		</Popover>
	{:else}
		<!-- Non-interactive Badge -->
		<Badge 
			variant={config.variant}
			class="{sizeClasses} flex items-center gap-1.5 {config.color} {config.bgColor} {config.borderColor} {isManuallyOverridden ? 'ring-1 ring-green-400' : ''}"
			title={tooltipContent ? `${tooltipContent.title}: ${tooltipContent.description}` : undefined}
		>
			{#if showIcon}
				<svelte:component this={config.icon} class="{iconSize} flex-shrink-0" />
			{/if}
			<span class="truncate">
				{size === 'xs' || size === 'sm' ? config.shortLabel : config.label}
			</span>
			
			<!-- Priority indicator dot -->
			{#if priorityScore !== null && showAdvancedIndicators}
				<div class="flex-shrink-0 w-1.5 h-1.5 rounded-full {priorityScore >= 7 ? 'bg-green-500' : priorityScore >= 4 ? 'bg-blue-500' : 'bg-orange-500'}"></div>
			{/if}
		</Badge>
	{/if}
	
	<!-- Secondary Indicators -->
	{#if showLayered && showAdvancedIndicators}
		<div class="inline-flex items-center gap-1">
			<!-- Manual Override Indicator -->
			{#if isManuallyOverridden}
				<Badge variant="success" class="px-1.5 py-0.5 text-xs" title="Filter decision manually overridden">
					<ShieldCheck class="h-2.5 w-2.5" />
				</Badge>
			{/if}
			
			<!-- Can Be Processed Indicator -->
			{#if canBeProcessed && !isManuallyOverridden}
				<Badge variant="outline" class="px-1.5 py-0.5 text-xs border-blue-200 text-blue-700 bg-blue-50" title="Can be manually processed">
					<Zap class="h-2.5 w-2.5" />
				</Badge>
			{/if}
			
			<!-- Priority Score Badge -->
			{#if priorityScore !== null && size !== 'xs'}
				<Badge 
					variant="outline" 
					class="px-1.5 py-0.5 text-xs {priorityConfig.badgeColor}"
					title={priorityConfig.label}
				>
					<svelte:component this={priorityConfig.icon} class="h-2.5 w-2.5 mr-1" />
					{priorityScore}
				</Badge>
			{/if}
			
			<!-- Filter Category Badge -->
			{#if isFiltered && filterCategory && !isManuallyOverridden && size !== 'xs'}
				<Badge 
					variant="outline" 
					class="px-1.5 py-0.5 text-xs {config.fillColor} {config.borderColor} {config.color}"
					title="Filter Category"
				>
					<Layers class="h-2.5 w-2.5 mr-1" />
					{filterCategory.replace('_', ' ')}
				</Badge>
			{/if}
		</div>
	{/if}
	
	<!-- Confidence Progress Bar (for filtered items) -->
	{#if showLayered && isFiltered && confidenceScore !== null && confidenceScore > 0 && size !== 'xs'}
		<div class="flex items-center gap-1" title={confidenceConfig.label}>
			<div class="w-12 h-1.5 bg-gray-200 rounded-full overflow-hidden">
				<div 
					class="h-full transition-all duration-500 {confidenceScore >= 0.8 ? 'bg-green-500' : confidenceScore >= 0.6 ? 'bg-blue-500' : 'bg-orange-500'}" 
					style="width: {confidenceScore * 100}%"
				></div>
			</div>
			<span class="text-xs {confidenceConfig.color}">
				{Math.round(confidenceScore * 100)}%
			</span>
		</div>
	{/if}
</div>