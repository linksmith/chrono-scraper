<script lang="ts">
	import SvelteMarkdown from 'svelte-markdown';
	import type { ComponentType } from 'svelte';
	
	// Props
	export let source: string = '';
	export let truncate: boolean = false;
	export let maxLength: number = 300;
	export let className: string = '';
	
	// Truncate markdown content if needed
	$: processedSource = truncate && source.length > maxLength 
		? source.substring(0, maxLength) + '...' 
		: source;
	
	// Custom renderers for better styling
	const renderers: Record<string, ComponentType> = {};
</script>

<div class="markdown-content {className}">
	<SvelteMarkdown 
		source={processedSource}
		{renderers}
	/>
</div>

<style>
	/* Global styles for markdown content */
	:global(.markdown-content) {
		@apply text-foreground;
	}
	
	:global(.markdown-content h1) {
		@apply text-3xl font-bold mb-4 mt-6;
	}
	
	:global(.markdown-content h2) {
		@apply text-2xl font-semibold mb-3 mt-5;
	}
	
	:global(.markdown-content h3) {
		@apply text-xl font-semibold mb-2 mt-4;
	}
	
	:global(.markdown-content h4) {
		@apply text-lg font-medium mb-2 mt-3;
	}
	
	:global(.markdown-content h5) {
		@apply text-base font-medium mb-1 mt-2;
	}
	
	:global(.markdown-content h6) {
		@apply text-sm font-medium mb-1 mt-2;
	}
	
	:global(.markdown-content p) {
		@apply mb-4 leading-relaxed;
	}
	
	:global(.markdown-content ul) {
		@apply list-disc list-inside mb-4;
	}
	
	:global(.markdown-content ol) {
		@apply list-decimal list-inside mb-4;
	}
	
	:global(.markdown-content li) {
		@apply ml-4 mb-1;
	}
	
	:global(.markdown-content blockquote) {
		@apply border-l-4 border-muted-foreground/30 pl-4 italic my-4;
	}
	
	:global(.markdown-content code) {
		@apply bg-muted px-1.5 py-0.5 rounded text-sm font-mono;
	}
	
	:global(.markdown-content pre) {
		@apply bg-muted p-4 rounded-lg overflow-x-auto mb-4;
	}
	
	:global(.markdown-content pre code) {
		@apply bg-transparent p-0;
	}
	
	:global(.markdown-content table) {
		@apply w-full border-collapse mb-4;
	}
	
	:global(.markdown-content th) {
		@apply border-b-2 border-muted-foreground/30 p-2 text-left font-semibold;
	}
	
	:global(.markdown-content td) {
		@apply border-b border-muted-foreground/20 p-2;
	}
	
	:global(.markdown-content a) {
		@apply text-primary hover:underline;
	}
	
	:global(.markdown-content img) {
		@apply max-w-full h-auto rounded-lg my-4;
	}
	
	:global(.markdown-content hr) {
		@apply border-t border-muted-foreground/30 my-6;
	}
	
	:global(.markdown-content strong) {
		@apply font-semibold;
	}
	
	:global(.markdown-content em) {
		@apply italic;
	}
	
	/* Truncated content styles */
	:global(.markdown-content.truncated) {
		@apply relative;
	}
	
	:global(.markdown-content.truncated::after) {
		@apply absolute bottom-0 left-0 right-0 h-8;
		background: linear-gradient(to bottom, transparent, hsl(var(--background)));
		content: '';
	}
</style>