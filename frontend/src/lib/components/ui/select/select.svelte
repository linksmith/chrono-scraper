<script lang="ts">
	import { setContext } from 'svelte';
	import { writable } from 'svelte/store';
	import type { HTMLAttributes } from 'svelte/elements';

	type $$Props = HTMLAttributes<HTMLDivElement> & {
		value?: string;
		onValueChange?: (value: string) => void;
		disabled?: boolean;
	};

	let className: $$Props['class'] = undefined;
	export { className as class };
	export let value: $$Props['value'] = '';
	export let onValueChange: $$Props['onValueChange'] = undefined;
	export let disabled: $$Props['disabled'] = false;

	const valueStore = writable(value);
	const openStore = writable(false);
	const disabledStore = writable(disabled);

	$: valueStore.set(value);
	$: disabledStore.set(disabled);

	setContext('select', {
		value: valueStore,
		open: openStore,
		disabled: disabledStore,
		setValue: (newValue: string) => {
			value = newValue;
			valueStore.set(newValue);
			if (onValueChange) {
				onValueChange(newValue);
			}
		},
		setOpen: (newOpen: boolean) => {
			openStore.set(newOpen);
		}
	});
</script>

<div class={className} {...$$restProps}>
	<slot />
</div>