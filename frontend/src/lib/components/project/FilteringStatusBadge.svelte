<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
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
		AlertTriangle
	} from 'lucide-svelte';

	export let status: string;
	export let filterReason: string | null = null;
	export let filterCategory: string | null = null;
	export let isManuallyOverridden: boolean = false;
	export let size: 'sm' | 'md' | 'lg' = 'md';
	export let showIcon: boolean = true;
	export let showTooltip: boolean = true;

	// Enhanced status mappings with filtering states
	function getStatusConfig(status: string) {
		const baseStatus = status?.toLowerCase() || '';
		
		// Processing states
		if (baseStatus === 'pending') return {
			label: 'Pending',
			variant: 'warning' as const,
			icon: Clock,
			color: 'text-yellow-600',
			bgColor: 'bg-yellow-50',
			borderColor: 'border-yellow-200'
		};
		
		if (baseStatus === 'in_progress') return {
			label: 'Processing',
			variant: 'default' as const,
			icon: Activity,
			color: 'text-blue-600',
			bgColor: 'bg-blue-50',
			borderColor: 'border-blue-200'
		};
		
		if (baseStatus === 'completed') return {
			label: 'Complete',
			variant: 'success' as const,
			icon: CheckCircle,
			color: 'text-green-600',
			bgColor: 'bg-green-50',
			borderColor: 'border-green-200'
		};
		
		if (baseStatus === 'failed') return {
			label: 'Failed',
			variant: 'destructive' as const,
			icon: AlertTriangle,
			color: 'text-red-600',
			bgColor: 'bg-red-50',
			borderColor: 'border-red-200'
		};
		
		if (baseStatus === 'skipped') return {
			label: 'Skipped',
			variant: 'secondary' as const,
			icon: Ban,
			color: 'text-gray-600',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200'
		};

		// Filtering states
		if (baseStatus === 'filtered_duplicate') return {
			label: 'Duplicate',
			variant: 'outline' as const,
			icon: XCircle,
			color: 'text-orange-600',
			bgColor: 'bg-orange-50',
			borderColor: 'border-orange-200'
		};
		
		if (baseStatus === 'filtered_list_page') return {
			label: 'List Page',
			variant: 'outline' as const,
			icon: Filter,
			color: 'text-purple-600',
			bgColor: 'bg-purple-50',
			borderColor: 'border-purple-200'
		};
		
		if (baseStatus === 'filtered_low_quality') return {
			label: 'Low Quality',
			variant: 'warning' as const,
			icon: AlertCircle,
			color: 'text-amber-600',
			bgColor: 'bg-amber-50',
			borderColor: 'border-amber-200'
		};
		
		if (baseStatus === 'filtered_size') return {
			label: 'Size Limit',
			variant: 'outline' as const,
			icon: FileText,
			color: 'text-indigo-600',
			bgColor: 'bg-indigo-50',
			borderColor: 'border-indigo-200'
		};
		
		if (baseStatus === 'filtered_type') return {
			label: 'File Type',
			variant: 'secondary' as const,
			icon: Ban,
			color: 'text-gray-600',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200'
		};
		
		if (baseStatus === 'filtered_custom') return {
			label: 'Custom Rule',
			variant: 'outline' as const,
			icon: Filter,
			color: 'text-teal-600',
			bgColor: 'bg-teal-50',
			borderColor: 'border-teal-200'
		};

		// Review states
		if (baseStatus === 'awaiting_manual_review') return {
			label: 'Awaiting Review',
			variant: 'warning' as const,
			icon: Eye,
			color: 'text-amber-600',
			bgColor: 'bg-amber-50',
			borderColor: 'border-amber-200'
		};
		
		if (baseStatus === 'manually_approved') return {
			label: 'Manually Approved',
			variant: 'success' as const,
			icon: ShieldCheck,
			color: 'text-green-600',
			bgColor: 'bg-green-50',
			borderColor: 'border-green-200'
		};

		// Default fallback
		return {
			label: status || 'Unknown',
			variant: 'secondary' as const,
			icon: Info,
			color: 'text-gray-600',
			bgColor: 'bg-gray-50',
			borderColor: 'border-gray-200'
		};
	}

	function getTooltipText(status: string, filterReason: string | null, filterCategory: string | null, isOverridden: boolean): string {
		const config = getStatusConfig(status);
		let tooltip = config.label;
		
		if (filterReason) {
			tooltip += `\nReason: ${filterReason}`;
		}
		
		if (filterCategory) {
			tooltip += `\nCategory: ${filterCategory}`;
		}
		
		if (isOverridden) {
			tooltip += '\nFilter manually overridden';
		}
		
		return tooltip;
	}

	function getSizeClasses(size: string) {
		switch (size) {
			case 'sm': return 'text-xs px-1.5 py-0.5';
			case 'lg': return 'text-sm px-3 py-1';
			case 'md':
			default: return 'text-xs px-2 py-0.5';
		}
	}

	$: config = getStatusConfig(status);
	$: tooltipText = showTooltip ? getTooltipText(status, filterReason, filterCategory, isManuallyOverridden) : '';
	$: sizeClasses = getSizeClasses(size);

	// Determine if this is a filtered status
	$: isFiltered = status?.toLowerCase().startsWith('filtered_') || status?.toLowerCase() === 'awaiting_manual_review';
</script>

<div class="inline-flex items-center gap-1">
	<!-- Main status badge -->
	<Badge 
		variant={config.variant} 
		class="{sizeClasses} flex items-center gap-1 {isManuallyOverridden ? 'ring-1 ring-green-400' : ''}"
		title={tooltipText}
	>
		{#if showIcon}
			<svelte:component this={config.icon} class="h-3 w-3" />
		{/if}
		{config.label}
	</Badge>

	<!-- Manual override indicator -->
	{#if isManuallyOverridden}
		<Badge variant="success" class="text-xs px-1 py-0" title="Filter decision manually overridden">
			<ShieldCheck class="h-2.5 w-2.5" />
		</Badge>
	{/if}

	<!-- Additional filter category badge for filtered content -->
	{#if isFiltered && filterCategory && !isManuallyOverridden}
		<Badge variant="outline" class="text-xs px-1 py-0 {config.bgColor} {config.borderColor} {config.color}">
			{filterCategory.replace('_', ' ')}
		</Badge>
	{/if}
</div>