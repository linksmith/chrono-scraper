<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { Badge } from '$lib/components/ui/badge';
	import Button from '$lib/components/ui/button/button.svelte';
	import { Input } from '$lib/components/ui/input';
	import { X, Plus, Hash } from 'lucide-svelte';
	import { cn } from '$lib/utils';

	export let tags: string[] = [];
	export let suggestions: string[] = [];
	export let placeholder: string = 'Add tags...';
	export let maxTags: number = 20;
	export let disabled: boolean = false;
	export let size: 'sm' | 'md' | 'lg' = 'md';

	const dispatch = createEventDispatcher();

	let inputValue = '';
	let showSuggestions = false;
	let filteredSuggestions: string[] = [];
	let selectedSuggestionIndex = -1;

	$: {
		if (inputValue.trim()) {
			filteredSuggestions = suggestions
				.filter(s => 
					s.toLowerCase().includes(inputValue.toLowerCase()) && 
					!tags.includes(s)
				)
				.slice(0, 10);
			showSuggestions = filteredSuggestions.length > 0;
		} else {
			showSuggestions = false;
			filteredSuggestions = [];
		}
		selectedSuggestionIndex = -1;
	}

	function addTag(tag: string) {
		if (!tag.trim() || tags.includes(tag.trim()) || tags.length >= maxTags) return;
		
		const newTags = [...tags, tag.trim()];
		dispatch('update', newTags);
		inputValue = '';
		showSuggestions = false;
	}

	function removeTag(tagIndex: number) {
		const newTags = tags.filter((_, i) => i !== tagIndex);
		dispatch('update', newTags);
	}

	function handleInputKeydown(event: KeyboardEvent) {
		if (disabled) return;

		switch (event.key) {
			case 'Enter':
				event.preventDefault();
				if (selectedSuggestionIndex >= 0 && filteredSuggestions[selectedSuggestionIndex]) {
					addTag(filteredSuggestions[selectedSuggestionIndex]);
				} else if (inputValue.trim()) {
					addTag(inputValue.trim());
				}
				break;
			
			case 'ArrowDown':
				event.preventDefault();
				selectedSuggestionIndex = Math.min(
					selectedSuggestionIndex + 1, 
					filteredSuggestions.length - 1
				);
				break;
			
			case 'ArrowUp':
				event.preventDefault();
				selectedSuggestionIndex = Math.max(selectedSuggestionIndex - 1, -1);
				break;
			
			case 'Escape':
				showSuggestions = false;
				selectedSuggestionIndex = -1;
				break;
			
			case 'Backspace':
				if (inputValue === '' && tags.length > 0) {
					removeTag(tags.length - 1);
				}
				break;
		}
	}

	function handleSuggestionClick(suggestion: string) {
		addTag(suggestion);
	}

	function handleInputFocus() {
		if (inputValue.trim() && filteredSuggestions.length > 0) {
			showSuggestions = true;
		}
	}

	function handleInputBlur() {
		// Delay hiding suggestions to allow for clicks
		setTimeout(() => {
			showSuggestions = false;
		}, 150);
	}

	const sizeClasses = {
		sm: 'text-xs',
		md: 'text-sm',
		lg: 'text-base'
	};

	onMount(() => {
		// Defer tag suggestions loading to avoid race condition with authentication
		// Use requestAnimationFrame to ensure DOM and authentication are fully ready
		requestAnimationFrame(() => {
			dispatch('loadSuggestions', { query: '' });
		});
	});
</script>

<div class="relative w-full">
	<!-- Tags and Input Container -->
	<div class={cn(
		"flex flex-wrap items-center gap-1 p-2 border rounded-md bg-background",
		disabled && "opacity-50 cursor-not-allowed",
		sizeClasses[size]
	)}>
		<!-- Existing Tags -->
		{#each tags as tag, index}
			<Badge 
				variant="secondary" 
				class="flex items-center gap-1 {size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1'}"
			>
				<Hash class={cn('h-3 w-3', size === 'sm' && 'h-2.5 w-2.5')} />
				{tag}
				{#if !disabled}
					<Button
						variant="ghost"
						size="icon"
						class="h-4 w-4 p-0 hover:bg-destructive hover:text-destructive-foreground"
						onclick={() => removeTag(index)}
						title="Remove tag"
					>
						<X class="h-3 w-3" />
					</Button>
				{/if}
			</Badge>
		{/each}

		<!-- Input Field -->
		{#if tags.length < maxTags && !disabled}
			<Input
				bind:value={inputValue}
				{placeholder}
				class={cn(
					"border-0 p-0 h-auto bg-transparent focus-visible:ring-0 flex-1 min-w-32",
					sizeClasses[size]
				)}
				on:keydown={handleInputKeydown}
				on:focus={handleInputFocus}
				on:blur={handleInputBlur}
				on:input={() => dispatch('loadSuggestions', { query: inputValue })}
				{disabled}
			/>
		{/if}

		<!-- Add Button -->
		{#if inputValue.trim() && !disabled}
			<Button
				variant="ghost"
				size="icon"
				class="h-6 w-6 text-primary"
				onclick={() => addTag(inputValue.trim())}
				title="Add tag"
			>
				<Plus class="h-3 w-3" />
			</Button>
		{/if}
	</div>

	<!-- Suggestions Dropdown -->
	{#if showSuggestions && !disabled}
		<div class="absolute top-full left-0 right-0 z-50 mt-1 bg-popover border rounded-md shadow-md max-h-48 overflow-y-auto">
			{#each filteredSuggestions as suggestion, index}
				<button
					class={cn(
						"w-full px-3 py-2 text-left hover:bg-accent hover:text-accent-foreground text-sm",
						index === selectedSuggestionIndex && "bg-accent text-accent-foreground"
					)}
					on:click={() => handleSuggestionClick(suggestion)}
				>
					<Hash class="inline h-3 w-3 mr-1" />
					{suggestion}
				</button>
			{/each}
		</div>
	{/if}


</div>