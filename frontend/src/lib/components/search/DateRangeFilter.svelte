<script lang="ts">
    import { onMount } from 'svelte';
    import { Slider } from "$lib/components/ui/slider";
    import { Input } from "$lib/components/ui/input";
    import { Button } from "$lib/components/ui/button";
    import { Badge } from "$lib/components/ui/badge";
    import { Calendar, X } from "lucide-svelte";
    import { filters } from "$lib/stores/filters";
    
    export let dateRange: [Date | null, Date | null] = [null, null];
    
    // Convert dates to/from slider values (days since min date)
    let minDate = new Date('1990-01-01');
    let maxDate = new Date();
    let totalDays = Math.floor((maxDate.getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24));

    // Try to load actual min/max capture dates from facets for better bounds
    onMount(async () => {
        try {
            const response = await fetch('/api/v1/search/facets', { credentials: 'include' });
            if (response.ok) {
                const data = await response.json();
                const min = data?.date_range?.min;
                const max = data?.date_range?.max;
                if (min) minDate = new Date(min);
                if (max) maxDate = new Date(max);
            }
        } catch (_) {
            // Ignore and keep defaults
        }
    });

    // Keep totalDays in sync when bounds change
    $: totalDays = Math.floor((maxDate.getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24));
    
    let sliderValues: number[] = [0, totalDays];
    let startDateInput = '';
    let endDateInput = '';
    
    // Reactive updates
    $: {
        if (dateRange[0] && dateRange[1]) {
            const startDays = Math.floor((dateRange[0].getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24));
            const endDays = Math.floor((dateRange[1].getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24));
            sliderValues = [Math.max(0, startDays), Math.min(totalDays, endDays)];
            startDateInput = dateRange[0].toISOString().split('T')[0];
            endDateInput = dateRange[1].toISOString().split('T')[0];
        } else if (dateRange[0]) {
            const startDays = Math.floor((dateRange[0].getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24));
            sliderValues = [Math.max(0, startDays), totalDays];
            startDateInput = dateRange[0].toISOString().split('T')[0];
            endDateInput = '';
        } else if (dateRange[1]) {
            const endDays = Math.floor((dateRange[1].getTime() - minDate.getTime()) / (1000 * 60 * 60 * 24));
            sliderValues = [0, Math.min(totalDays, endDays)];
            startDateInput = '';
            endDateInput = dateRange[1].toISOString().split('T')[0];
        } else {
            sliderValues = [0, totalDays];
            startDateInput = '';
            endDateInput = '';
        }
    }
    
    function sliderToDate(days: number): Date {
        return new Date(minDate.getTime() + days * 24 * 60 * 60 * 1000);
    }
    
    function handleSliderChange(values: number[]) {
        const startDate = values[0] > 0 ? sliderToDate(values[0]) : null;
        const endDate = values[1] < totalDays ? sliderToDate(values[1]) : null;
        
        updateDateRange(startDate, endDate);
    }
    
    function handleStartDateInput() {
        if (startDateInput) {
            const startDate = new Date(startDateInput);
            updateDateRange(startDate, dateRange[1]);
        } else {
            updateDateRange(null, dateRange[1]);
        }
    }
    
    function handleEndDateInput() {
        if (endDateInput) {
            const endDate = new Date(endDateInput);
            updateDateRange(dateRange[0], endDate);
        } else {
            updateDateRange(dateRange[0], null);
        }
    }
    
    function updateDateRange(start: Date | null, end: Date | null) {
        dateRange = [start, end];
        filters.update(f => ({
            ...f,
            dateRange: [start, end]
        }));
    }
    
    function clearDateRange() {
        updateDateRange(null, null);
    }
    
    function formatDateRange(): string {
        if (!dateRange[0] && !dateRange[1]) return 'All time';
        if (dateRange[0] && !dateRange[1]) return `From ${dateRange[0].toLocaleDateString()}`;
        if (!dateRange[0] && dateRange[1]) return `Until ${dateRange[1].toLocaleDateString()}`;
        if (dateRange[0] && dateRange[1]) {
            return `${dateRange[0].toLocaleDateString()} - ${dateRange[1].toLocaleDateString()}`;
        }
        return 'Select range';
    }
    
    $: hasDateFilter = dateRange[0] !== null || dateRange[1] !== null;
</script>

<div class="space-y-4">
    <div class="flex items-center justify-between">
        <div class="flex items-center space-x-2">
            <Calendar class="h-4 w-4 text-muted-foreground" />
            <span class="text-sm font-medium">Date Range</span>
        </div>
        {#if hasDateFilter}
            <Button
                variant="ghost"
                size="sm"
                onclick={clearDateRange}
                class="h-6 px-2 text-xs"
            >
                <X class="h-3 w-3" />
            </Button>
        {/if}
    </div>
    
    <!-- Current selection display -->
    {#if hasDateFilter}
        <Badge variant="secondary" class="text-xs">
            {formatDateRange()}
        </Badge>
    {/if}
    
    <!-- Date range slider -->
    <div class="space-y-3">
        <div class="px-2">
            <Slider
                type="multiple"
                bind:value={sliderValues}
                max={totalDays}
                step={1}
                onValueChange={handleSliderChange}
                class="w-full"
            />
        </div>
        
        <!-- Date range labels -->
        <div class="flex justify-between text-xs text-muted-foreground px-2 pt-4">
            <span>{minDate.toLocaleDateString()}</span>
            <span>{maxDate.toLocaleDateString()}</span>
        </div>
    </div>
    
    <!-- Manual date inputs -->
    <div class="grid grid-cols-2 gap-2">
        <div class="space-y-1">
            <label for="date-from" class="text-xs text-muted-foreground">From</label>
            <Input
                id="date-from"
                type="date"
                bind:value={startDateInput}
                on:change={handleStartDateInput}
                class="text-xs h-8"
                max={maxDate.toISOString().split('T')[0]}
            />
        </div>
        <div class="space-y-1">
            <label for="date-to" class="text-xs text-muted-foreground">To</label>
            <Input
                id="date-to"
                type="date"
                bind:value={endDateInput}
                on:change={handleEndDateInput}
                class="text-xs h-8"
                max={maxDate.toISOString().split('T')[0]}
            />
        </div>
    </div>
    
    
</div>