<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { searchState, searchActions } from '$lib/stores/search';

	const dispatch = createEventDispatcher<{
		pageChanged: { page: number };
		pageSizeChanged: { pageSize: number };
	}>();

	// Subscribe to search state
	$: pagination = $searchState.pagination;
	$: currentPage = pagination.page;
	$: totalPages = pagination.totalPages;
	$: total = pagination.total;
	$: pageSize = pagination.pageSize;

	// Page size options
	const pageSizeOptions = [10, 20, 50, 100];

	function goToPage(page: number) {
		if (page < 1 || page > totalPages || page === currentPage) return;
		
		searchActions.setPage(page);
		dispatch('pageChanged', { page });
	}

	function handlePageSizeChange(newPageSize: string) {
		const size = parseInt(newPageSize);
		searchActions.setPage(1); // Reset to first page
		dispatch('pageSizeChanged', { pageSize: size });
	}

	// Generate page numbers for pagination
	function getVisiblePages(): (number | string)[] {
		const pages: (number | string)[] = [];
		const delta = 2;

		if (totalPages <= 7) {
			// Show all pages if total is small
			for (let i = 1; i <= totalPages; i++) {
				pages.push(i);
			}
		} else {
			// Always show first page
			pages.push(1);

			// Show ellipsis if needed
			if (currentPage - delta > 2) {
				pages.push('...');
			}

			// Show pages around current
			const start = Math.max(2, currentPage - delta);
			const end = Math.min(totalPages - 1, currentPage + delta);

			for (let i = start; i <= end; i++) {
				pages.push(i);
			}

			// Show ellipsis if needed
			if (currentPage + delta < totalPages - 1) {
				pages.push('...');
			}

			// Always show last page
			if (totalPages > 1) {
				pages.push(totalPages);
			}
		}

		return pages;
	}

	$: visiblePages = getVisiblePages();
	$: startItem = (currentPage - 1) * pageSize + 1;
	$: endItem = Math.min(currentPage * pageSize, total);
</script>

{#if total > 0}
	<div class="flex flex-col sm:flex-row items-center justify-between space-y-4 sm:space-y-0 border-t pt-4">
		<!-- Results info -->
		<div class="text-sm text-muted-foreground">
			Showing {startItem.toLocaleString()} to {endItem.toLocaleString()} of {total.toLocaleString()} results
		</div>

		<!-- Page size selector -->
		<div class="flex items-center space-x-2">
			<span class="text-sm text-muted-foreground">Show</span>
			<select 
				value={pageSize.toString()}
				onchange={(e) => handlePageSizeChange(e.currentTarget.value)}
				class="w-20 h-8 border border-input bg-background rounded-md px-2 text-sm"
			>
				{#each pageSizeOptions as option}
					<option value={option.toString()}>{option}</option>
				{/each}
			</select>
			<span class="text-sm text-muted-foreground">per page</span>
		</div>

		<!-- Pagination controls -->
		{#if totalPages > 1}
			<div class="flex items-center space-x-1">
				<!-- First page -->
				<Button
					variant="outline"
					size="sm"
					onclick={() => goToPage(1)}
					disabled={currentPage === 1}
				>
					<ChevronsLeft class="h-4 w-4" />
					<span class="sr-only">Go to first page</span>
				</Button>

				<!-- Previous page -->
				<Button
					variant="outline"
					size="sm"
					onclick={() => goToPage(currentPage - 1)}
					disabled={currentPage === 1}
				>
					<ChevronLeft class="h-4 w-4" />
					<span class="sr-only">Go to previous page</span>
				</Button>

				<!-- Page numbers -->
				{#each visiblePages as page}
					{#if page === '...'}
						<span class="px-2 text-muted-foreground">...</span>
					{:else}
						<Button
							variant={page === currentPage ? 'default' : 'outline'}
							size="sm"
							onclick={() => goToPage(page)}
							class="min-w-[2rem]"
						>
							{page}
						</Button>
					{/if}
				{/each}

				<!-- Next page -->
				<Button
					variant="outline"
					size="sm"
					onclick={() => goToPage(currentPage + 1)}
					disabled={currentPage === totalPages}
				>
					<ChevronRight class="h-4 w-4" />
					<span class="sr-only">Go to next page</span>
				</Button>

				<!-- Last page -->
				<Button
					variant="outline"
					size="sm"
					onclick={() => goToPage(totalPages)}
					disabled={currentPage === totalPages}
				>
					<ChevronsRight class="h-4 w-4" />
					<span class="sr-only">Go to last page</span>
				</Button>
			</div>
		{/if}
	</div>
{/if}