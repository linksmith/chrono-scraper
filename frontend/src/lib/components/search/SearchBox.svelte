<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Search, X } from 'lucide-svelte';
	import { Input } from '$lib/components/ui/input';
	import { Button } from '$lib/components/ui/button';
	import { searchState, searchActions } from '$lib/stores/search';

	export let placeholder = 'Search through historical web content...';
	export let showClearButton = true;
	
	const dispatch = createEventDispatcher<{
		search: { query: string };
		clear: void;
	}>();

	let inputElement: HTMLInputElement;
	
	// Subscribe to search state
	$: query = $searchState.query;
	$: loading = $searchState.loading;

	function handleSearch() {
		const trimmedQuery = query.trim();
		searchActions.setQuery(trimmedQuery);
		dispatch('search', { query: trimmedQuery });
	}

	function handleClear() {
		searchActions.setQuery('');
		dispatch('clear');
		inputElement?.focus();
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			event.preventDefault();
			handleSearch();
		} else if (event.key === 'Escape') {
			event.preventDefault();
			handleClear();
		}
	}

	// Auto-focus on mount
	import { onMount } from 'svelte';
	onMount(() => {
		inputElement?.focus();
	});
</script>

<div class="relative w-full">
	<div class="relative">
		<Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
		<Input
			bind:this={inputElement}
			bind:value={query}
			{placeholder}
			class="pl-10 pr-12 h-12 text-base"
			disabled={loading}
			onkeydown={handleKeydown}
		/>
		{#if showClearButton && query.length > 0}
			<Button
				variant="ghost"
				size="sm"
				class="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 p-0"
				onclick={handleClear}
				disabled={loading}
			>
				<X class="h-4 w-4" />
				<span class="sr-only">Clear search</span>
			</Button>
		{/if}
	</div>
	
	{#if loading}
		<div class="absolute right-3 top-1/2 -translate-y-1/2">
			<div class="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent"></div>
		</div>
	{/if}
</div>

<style>
	/* Subtle animation for search input */
	:global(.search-input:focus) {
		box-shadow: 0 0 0 2px hsl(var(--ring));
	}
</style>