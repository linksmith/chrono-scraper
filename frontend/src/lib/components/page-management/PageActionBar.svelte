<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Star, Tag, CheckCircle, XCircle, Eye, MoreHorizontal } from 'lucide-svelte';
	import Button from '$lib/components/ui/button/button.svelte';
	import { cn } from '$lib/utils';

	export let pageId: number;
	export let isStarred: boolean = false;
	export let reviewStatus: string = 'unreviewed';
	export let tags: string[] = [];
	export let size: 'sm' | 'md' | 'lg' = 'md';
	export let showLabels: boolean = false;
	export let disabled: boolean = false;

	const dispatch = createEventDispatcher();

	const sizeClasses = {
		sm: 'h-8 w-8',
		md: 'h-9 w-9',
		lg: 'h-10 w-10'
	};

	function handleStar() {
		if (disabled) return;
		dispatch('star', { pageId, isStarred: !isStarred });
	}

	function handleTag() {
		if (disabled) return;
		dispatch('tag', { pageId, tags });
	}

	function handleMarkRelevant() {
		if (disabled) return;
		dispatch('review', { pageId, reviewStatus: 'relevant' });
	}

	function handleMarkIrrelevant() {
		if (disabled) return;
		dispatch('review', { pageId, reviewStatus: 'irrelevant' });
	}

	function handleView() {
		if (disabled) return;
		dispatch('view', { pageId });
	}

	function handleMore() {
		if (disabled) return;
		dispatch('more', { pageId });
	}

	$: starIcon = isStarred ? 'filled' : 'outline';
	$: reviewStatusColor = 
		reviewStatus === 'relevant' ? 'text-green-600 hover:text-green-700' :
		reviewStatus === 'irrelevant' ? 'text-red-600 hover:text-red-700' :
		'text-gray-600 hover:text-gray-700';
</script>

<div class="flex items-center gap-1">
	<!-- Star Button -->
	<Button
		variant="ghost"
		size="icon"
		class={cn(
			sizeClasses[size],
			isStarred ? 'text-yellow-500 hover:text-yellow-600' : 'text-gray-500 hover:text-gray-600',
			disabled && 'opacity-50 cursor-not-allowed'
		)}
		on:click={handleStar}
		{disabled}
		title={isStarred ? 'Remove from starred' : 'Add to starred'}
	>
		<Star 
			class={cn('h-4 w-4', isStarred && 'fill-current')} 
		/>
		{#if showLabels}
			<span class="ml-1 text-xs">Star</span>
		{/if}
	</Button>

	<!-- Tag Button -->
	<Button
		variant="ghost"
		size="icon"
		class={cn(
			sizeClasses[size],
			tags.length > 0 ? 'text-blue-600 hover:text-blue-700' : 'text-gray-500 hover:text-gray-600',
			disabled && 'opacity-50 cursor-not-allowed'
		)}
		on:click={handleTag}
		{disabled}
		title="Manage tags"
	>
		<Tag class="h-4 w-4" />
		{#if tags.length > 0}
			<span class="absolute -top-1 -right-1 bg-blue-500 text-white text-xs rounded-full h-4 w-4 flex items-center justify-center">
				{tags.length}
			</span>
		{/if}
		{#if showLabels}
			<span class="ml-1 text-xs">Tag</span>
		{/if}
	</Button>

	<!-- Mark Relevant Button -->
	<Button
		variant="ghost"
		size="icon"
		class={cn(
			sizeClasses[size],
			reviewStatus === 'relevant' ? 'text-green-600 hover:text-green-700' : 'text-gray-500 hover:text-gray-600',
			disabled && 'opacity-50 cursor-not-allowed'
		)}
		on:click={handleMarkRelevant}
		{disabled}
		title="Mark as relevant"
	>
		<CheckCircle class={cn('h-4 w-4', reviewStatus === 'relevant' && 'fill-current')} />
		{#if showLabels}
			<span class="ml-1 text-xs">Relevant</span>
		{/if}
	</Button>

	<!-- Mark Irrelevant Button -->
	<Button
		variant="ghost"
		size="icon"
		class={cn(
			sizeClasses[size],
			reviewStatus === 'irrelevant' ? 'text-red-600 hover:text-red-700' : 'text-gray-500 hover:text-gray-600',
			disabled && 'opacity-50 cursor-not-allowed'
		)}
		on:click={handleMarkIrrelevant}
		{disabled}
		title="Mark as irrelevant"
	>
		<XCircle class={cn('h-4 w-4', reviewStatus === 'irrelevant' && 'fill-current')} />
		{#if showLabels}
			<span class="ml-1 text-xs">Irrelevant</span>
		{/if}
	</Button>

	<!-- View Button -->
	<Button
		variant="ghost"
		size="icon"
		class={cn(
			sizeClasses[size],
			'text-gray-500 hover:text-gray-600',
			disabled && 'opacity-50 cursor-not-allowed'
		)}
		on:click={handleView}
		{disabled}
		title="View content"
	>
		<Eye class="h-4 w-4" />
		{#if showLabels}
			<span class="ml-1 text-xs">View</span>
		{/if}
	</Button>

	<!-- More Actions Button -->
	<Button
		variant="ghost"
		size="icon"
		class={cn(
			sizeClasses[size],
			'text-gray-500 hover:text-gray-600',
			disabled && 'opacity-50 cursor-not-allowed'
		)}
		on:click={handleMore}
		{disabled}
		title="More actions"
	>
		<MoreHorizontal class="h-4 w-4" />
		{#if showLabels}
			<span class="ml-1 text-xs">More</span>
		{/if}
	</Button>
</div>

<style>
	.absolute {
		position: absolute;
	}
</style>