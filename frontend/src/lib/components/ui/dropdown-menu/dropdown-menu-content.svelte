<script lang="ts">
	import { PopoverContent } from '$lib/components/ui/popover';
	
	export let align: 'start' | 'center' | 'end' = 'center';
	export let side: 'top' | 'right' | 'bottom' | 'left' = 'bottom';
</script>

<PopoverContent 
	{align} 
	{side}
	class="w-56 p-1 {$$props.class || ''}"
>
	<slot />
</PopoverContent>