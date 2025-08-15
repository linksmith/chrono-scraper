<script lang="ts">
	import { cn } from "$lib/utils";
	
	let className: string = "";
	export { className as class };
</script>

<div class={cn("relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full", className)}>
	<slot />
</div>