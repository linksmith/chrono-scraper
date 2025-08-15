<script lang="ts">
	import { cn } from "$lib/utils";
	
	let className: string = "";
	export { className as class };
	export let src: string;
	export let alt: string = "";
</script>

<img 
	{src} 
	{alt} 
	class={cn("aspect-square h-full w-full", className)}
/>