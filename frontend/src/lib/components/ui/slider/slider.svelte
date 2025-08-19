<script lang="ts">
    export let value: number[] = [0];
    export let max: number = 100;
    export let min: number = 0;
    export let step: number = 1;
    export let type: 'single' | 'multiple' = 'single';
    export let onValueChange: ((values: number[]) => void) | undefined = undefined;
    
    let className = '';
    export { className as class };
    
    function handleInput(event: Event) {
        const target = event.target as HTMLInputElement;
        const newValue = parseInt(target.value);
        
        if (type === 'single') {
            value = [newValue];
        } else {
            // For multiple, we need two inputs - this is a simplified version
            value = [value[0], newValue];
        }
        
        if (onValueChange) {
            onValueChange(value);
        }
    }
    
    function handleInput1(event: Event) {
        const target = event.target as HTMLInputElement;
        const newValue = parseInt(target.value);
        const rightValue = value[1] ?? max;
        const clamped = Math.min(Math.max(newValue, min), rightValue);
        value = [clamped, rightValue];
        
        if (onValueChange) {
            onValueChange(value);
        }
    }
    
    function handleInput2(event: Event) {
        const target = event.target as HTMLInputElement;
        const newValue = parseInt(target.value);
        const leftValue = value[0] ?? min;
        const clamped = Math.max(Math.min(newValue, max), leftValue);
        value = [leftValue, clamped];
        
        if (onValueChange) {
            onValueChange(value);
        }
    }
</script>

<div class="relative w-full {className}">
    {#if type === 'single'}
        <input
            type="range"
            {min}
            {max}
            {step}
            value={value[0]}
            on:input={handleInput}
            class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
        />
    {:else}
        <!-- Multiple sliders for range -->
        <div class="relative">
            <input
                type="range"
                {min}
                {max}
                {step}
                value={value[0] || min}
                on:input={handleInput1}
                class="absolute w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer slider"
            />
            <input
                type="range"
                {min}
                {max}
                {step}
                value={value[1] || max}
                on:input={handleInput2}
                class="absolute w-full h-2 bg-transparent rounded-lg appearance-none cursor-pointer slider"
            />
        </div>
    {/if}
</div>

<style>
    /* Ensure track does not intercept pointer events when overlapping; only thumbs do */
    .slider {
        pointer-events: none;
    }
    .slider::-webkit-slider-thumb {
        appearance: none;
        height: 20px;
        width: 20px;
        background: #007acc;
        border-radius: 50%;
        cursor: pointer;
        pointer-events: all;
    }
    
    .slider::-moz-range-thumb {
        height: 20px;
        width: 20px;
        background: #007acc;
        border-radius: 50%;
        cursor: pointer;
        border: none;
        pointer-events: all;
    }
</style>