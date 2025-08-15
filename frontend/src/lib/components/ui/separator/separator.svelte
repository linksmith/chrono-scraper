<script lang="ts">
	import { cn } from "$lib/utils";
	
	let className: string = "";
	export { className as class };
	export let orientation: "horizontal" | "vertical" = "horizontal";
	export let decorative: boolean = true;
</script>

<div
	class={cn(
		"shrink-0 bg-border",
		orientation === "horizontal" ? "h-[1px] w-full" : "h-full w-[1px]",
		className
	)}
	data-orientation={orientation}
	role={decorative ? "none" : "separator"}
	aria-orientation={decorative ? undefined : orientation}
></div>