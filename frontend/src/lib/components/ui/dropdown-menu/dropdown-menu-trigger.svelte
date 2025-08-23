<script lang="ts">
	import { PopoverTrigger } from '$lib/components/ui/popover';
	
	export let asChild = false;
</script>

<PopoverTrigger {asChild}>
	<slot />
</PopoverTrigger>