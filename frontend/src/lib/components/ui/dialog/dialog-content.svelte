<script lang="ts">
	import { cn } from '$lib/utils';
	import { getContext } from 'svelte';
	import { X } from 'lucide-svelte';

	let className: string | undefined = undefined;
	export { className as class };

	const dialog = getContext<{ open: boolean; setOpen: (v: boolean) => void }>('dialog');
</script>

{#if dialog.open}
	<div class="fixed inset-0 z-50 flex items-center justify-center">
		<div
			class={cn(
				'relative z-50 grid w-full max-w-lg gap-4 border bg-background p-6 shadow-lg sm:rounded-lg',
				className
			)}
			{...$$restProps}
		>
			<slot />
			<button
				class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
				on:click={() => dialog.setOpen(false)}
			>
				<X class="h-4 w-4" />
				<span class="sr-only">Close</span>
			</button>
		</div>
	</div>
{/if}
