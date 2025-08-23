<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import Spinner from './Spinner.svelte';

	export let loading: boolean = false;
	export let disabled: boolean = false;
	export let loadingText: string = '';
	export let variant: any = 'default';
	export let size: any = 'default';
	export let onclick: (() => void) | undefined = undefined;

	$: isDisabled = loading || disabled;
</script>

<Button 
	{variant} 
	{size} 
	disabled={isDisabled}
	{onclick}
	class="relative {$$props.class || ''}"
>
	{#if loading}
		<div class="flex items-center space-x-2">
			<Spinner size="sm" color="white" />
			<span>{loadingText || 'Loading...'}</span>
		</div>
	{:else}
		<slot />
	{/if}
</Button>