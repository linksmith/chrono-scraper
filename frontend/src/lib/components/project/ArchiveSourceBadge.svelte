<script lang="ts">
  import { Badge } from '$lib/components/ui/badge';
  import { Archive, Globe, Zap, Activity } from 'lucide-svelte';
  import type { ArchiveSource, ArchiveSourceMetrics } from '$lib/types/scraping';
  
  export let archiveSource: ArchiveSource;
  export let fallbackEnabled: boolean = false;
  export let metrics: ArchiveSourceMetrics | undefined = undefined;
  export let size: 'sm' | 'md' | 'lg' = 'sm';
  export let showIcon: boolean = true;
  export let showTooltip: boolean = true;
  export let interactive: boolean = false;
  
  // Archive source configuration mapping
  const archiveSourceConfig = {
    wayback: {
      label: 'Wayback Machine',
      shortLabel: 'Wayback',
      icon: Archive,
      variant: 'default' as const,
      color: 'text-blue-600 dark:text-blue-400',
      bgColor: 'bg-blue-50 dark:bg-blue-950/20',
      borderColor: 'border-blue-200 dark:border-blue-800',
      emoji: '🏛️'
    },
    commoncrawl: {
      label: 'Common Crawl',
      shortLabel: 'CommonCrawl',
      icon: Globe,
      variant: 'secondary' as const,
      color: 'text-green-600 dark:text-green-400',
      bgColor: 'bg-green-50 dark:bg-green-950/20',
      borderColor: 'border-green-200 dark:border-green-800',
      emoji: '🌐'
    },
    hybrid: {
      label: 'Hybrid Mode',
      shortLabel: 'Hybrid',
      icon: Zap,
      variant: 'outline' as const,
      color: 'text-purple-600 dark:text-purple-400',
      bgColor: 'bg-purple-50 dark:bg-purple-950/20',
      borderColor: 'border-purple-200 dark:border-purple-800',
      emoji: '⚡'
    }
  };
  
  $: config = archiveSourceConfig[archiveSource];
  $: IconComponent = config.icon;
  
  // Generate tooltip content
  $: tooltipContent = generateTooltipContent();
  
  function generateTooltipContent(): string {
    let content = `Archive Source: ${config.label}`;
    
    if (fallbackEnabled && archiveSource === 'hybrid') {
      content += '\nFallback enabled for maximum reliability';
    }
    
    if (metrics) {
      content += `\nSuccess Rate: ${metrics.success_rate.toFixed(1)}%`;
      content += `\nAvg Response: ${metrics.avg_response_time_ms}ms`;
      
      if (metrics.circuit_breaker_status !== 'closed') {
        content += `\nStatus: ${metrics.circuit_breaker_status.toUpperCase()}`;
      }
    }
    
    return content;
  }
  
  // Size classes
  const sizeClasses = {
    sm: 'text-xs px-1.5 py-0.5',
    md: 'text-sm px-2 py-1',
    lg: 'text-base px-3 py-1.5'
  };
  
  const iconSizes = {
    sm: 'h-3 w-3',
    md: 'h-4 w-4', 
    lg: 'h-5 w-5'
  };
</script>

<div 
  class="inline-flex items-center gap-1 rounded-md border {config.borderColor} {config.bgColor} {sizeClasses[size]} transition-all duration-200 {interactive ? 'hover:shadow-sm cursor-pointer' : ''}"
  title={showTooltip ? tooltipContent : ''}
  role={interactive ? 'button' : undefined}
  tabindex={interactive ? 0 : undefined}
  on:click
  on:keydown
>
  {#if showIcon}
    <svelte:component 
      this={IconComponent} 
      class="{iconSizes[size]} {config.color} flex-shrink-0"
      aria-hidden="true"
    />
  {/if}
  
  <span class="font-medium {config.color}">
    {size === 'sm' ? config.shortLabel : config.label}
  </span>
  
  {#if fallbackEnabled && archiveSource === 'hybrid'}
    <Activity 
      class="{iconSizes[size]} text-amber-500 dark:text-amber-400 animate-pulse" 
      aria-hidden="true"
      title="Fallback enabled"
    />
  {/if}
  
  {#if metrics && metrics.circuit_breaker_status !== 'closed'}
    <div 
      class="w-2 h-2 rounded-full {metrics.circuit_breaker_status === 'open' ? 'bg-red-500' : 'bg-yellow-500'} animate-pulse"
      title="Circuit breaker: {metrics.circuit_breaker_status}"
      aria-label="Service status indicator"
    ></div>
  {/if}
</div>

<style>
  /* Enhanced hover effects for interactive badges */
  [role="button"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  
  [role="button"]:active {
    transform: translateY(0);
  }
  
  /* Focus styles for accessibility */
  [role="button"]:focus-visible {
    outline: 2px solid currentColor;
    outline-offset: 2px;
  }
</style>