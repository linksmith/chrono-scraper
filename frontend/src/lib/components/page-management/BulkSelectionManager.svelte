<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Check } from 'lucide-svelte';
	import { cn } from '$lib/utils';
	import { 
		pageManagementStore, 
		pageManagementActions,
		bulkSelectionMode,
		selectedPagesCount,
		isAllPagesSelected,
		isSomePagesSelected,
		bulkActionInProgress
	} from '$lib/stores/page-management';

	// Props
	export let pageId: number;
	export let pageIndex: number;
	export let compact: boolean = false;

	const dispatch = createEventDispatcher<{
		selectionChange: { pageId: number; selected: boolean; pageIndex: number };
	}>();

	// Reactive state
	$: isSelected = $pageManagementStore.selectedPageIds.has(pageId);
	$: inSelectionMode = $bulkSelectionMode;
	$: actionInProgress = $bulkActionInProgress;

	function handleCheckboxClick(event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();
		
		const shiftKey = event.shiftKey;
		
		// Call the enhanced selection method from the store
		pageManagementActions.togglePageSelectionWithShift(pageId, pageIndex, shiftKey);
		
		// Dispatch event for parent component
		dispatch('selectionChange', { 
			pageId, 
			selected: !isSelected, 
			pageIndex 
		});
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.code === 'Space' || event.code === 'Enter') {
			event.preventDefault();
			handleCheckboxClick(event as any);
		}
	}
</script>

{#if inSelectionMode}
	<div class="flex items-center {compact ? 'justify-center' : 'mr-3'}">
		<button
			type="button"
			onclick={handleCheckboxClick}
			onkeydown={handleKeydown}
			disabled={actionInProgress}
			class={cn(
				"w-4 h-4 border border-input rounded-sm transition-all duration-200 flex items-center justify-center",
				"hover:border-primary focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
				isSelected && "bg-primary border-primary text-primary-foreground",
				actionInProgress && "opacity-50 cursor-not-allowed",
				!actionInProgress && "cursor-pointer"
			)}
			aria-label={`Select page ${pageId}`}
			role="checkbox"
			tabindex="0"
			aria-checked={isSelected}
		>
			{#if isSelected}
				<Check class="h-3 w-3" />
			{/if}
		</button>
	</div>
{/if}

<!-- Select All/None Component for Page Headers -->
<script lang="ts" context="module">
	export const BulkSelectAllManager = {
		// This will be exported as a separate component
	};
</script>

<style>
	/* Ensure checkbox is properly styled for selection */
	:global(.bulk-selection-checkbox) {
		cursor: pointer;
		user-select: none;
	}
	
	:global(.bulk-selection-checkbox:hover) {
		transform: scale(1.05);
	}
	
	:global(.bulk-selection-checkbox[data-state="checked"]) {
		background-color: hsl(var(--primary));
		border-color: hsl(var(--primary));
	}
</style>