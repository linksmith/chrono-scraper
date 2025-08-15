<script lang="ts">
  import { cn } from "$lib/utils";
  import type { HTMLLabelAttributes } from "svelte/elements";

  type $$Props = HTMLLabelAttributes;

  let className: $$Props["class"] = undefined;
  export { className as class };
</script>

<label
  class={cn(
    "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
    className
  )}
  {...$$restProps}
>
  <slot />
</label>