<script lang="ts">
	import { Popover } from '$lib/components/ui/popover';
	
	export let open = false;
</script>

<Popover bind:open>
	<slot />
</Popover>