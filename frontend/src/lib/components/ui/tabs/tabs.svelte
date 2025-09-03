<script lang="ts">
	import { setContext } from 'svelte';
	import { writable } from 'svelte/store';
	import type { HTMLAttributes } from 'svelte/elements';
	import { cn } from '$lib/utils.js';

	type $$Props = HTMLAttributes<HTMLDivElement> & {
		value?: string;
		orientation?: 'horizontal' | 'vertical';
		activationMode?: 'automatic' | 'manual';
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let value: $$Props['value'] = '';
	export let orientation: $$Props['orientation'] = 'horizontal';
	export let activationMode: $$Props['activationMode'] = 'automatic';

	const valueStore = writable(value);
	const orientationStore = writable(orientation);
	const activationModeStore = writable(activationMode);

	$: valueStore.set(value || '');
	$: orientationStore.set(orientation || 'horizontal');
	$: activationModeStore.set(activationMode || 'automatic');

	setContext('tabs', {
		value: valueStore,
		orientation: orientationStore,
		activationMode: activationModeStore,
		setValue: (newValue: string) => {
			value = newValue;
			valueStore.set(newValue);
		}
	});
</script>

<div
	class={cn(
		'data-[orientation=vertical]:flex-col data-[orientation=vertical]:space-x-0 data-[orientation=vertical]:space-y-2',
		className
	)}
	data-orientation={orientation}
	{...$$restProps}
>
	<slot />
</div>