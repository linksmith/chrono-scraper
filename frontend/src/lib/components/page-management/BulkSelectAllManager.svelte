<script lang="ts">
	import { Check, Minus } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { cn } from '$lib/utils';
	import { 
		pageManagementStore, 
		pageManagementActions,
		selectedPagesCount,
		isAllPagesSelected,
		isSomePagesSelected,
		bulkActionInProgress
	} from '$lib/stores/page-management';

	// Reactive state
	$: allSelected = $isAllPagesSelected;
	$: someSelected = $isSomePagesSelected;
	$: selectedCount = $selectedPagesCount;
	$: totalPages = $pageManagementStore.pages.length;
	$: actionInProgress = $bulkActionInProgress;

	function handleSelectAll() {
		if (allSelected) {
			pageManagementActions.clearSelection();
		} else {
			pageManagementActions.selectAllPages();
		}
	}

	function handleClearSelection() {
		pageManagementActions.clearSelection();
	}

	// Determine checkbox state for tri-state behavior
	$: checkboxState = allSelected ? 'checked' : (someSelected ? 'indeterminate' : 'unchecked');
</script>

<div class="flex items-center space-x-3">
	<!-- Select All Checkbox -->
	<div class="flex items-center space-x-2">
		<Checkbox
			checked={allSelected}
			indeterminate={someSelected}
			onCheckedChange={handleSelectAll}
			disabled={actionInProgress || totalPages === 0}
			class={cn(
				"transition-all duration-200",
				(allSelected || someSelected) && "border-primary",
				allSelected && "bg-primary",
				actionInProgress && "opacity-50 cursor-not-allowed"
			)}
			aria-label="Select all pages"
		/>
		
		<!-- Selection Status Text -->
		<span class="text-sm text-muted-foreground">
			{#if selectedCount > 0}
				{selectedCount} of {totalPages} selected
			{:else}
				Select all
			{/if}
		</span>
	</div>

	<!-- Action Buttons -->
	{#if selectedCount > 0}
		<div class="flex items-center space-x-2">
			<Button
				variant="outline"
				size="sm"
				onclick={handleClearSelection}
				disabled={actionInProgress}
			>
				Clear Selection
			</Button>
			
			<span class="text-xs text-muted-foreground">
				{selectedCount} page{selectedCount !== 1 ? 's' : ''} selected
			</span>
		</div>
	{/if}
</div>

<style>
	/* Custom styling for indeterminate state */
	:global(.bulk-select-all [data-state="indeterminate"]) {
		background-color: hsl(var(--primary));
		border-color: hsl(var(--primary));
	}
	
	:global(.bulk-select-all [data-state="indeterminate"] svg) {
		color: hsl(var(--primary-foreground));
	}
</style>