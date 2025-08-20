<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { isAuthenticated } from '$lib/stores/auth';
    import { base } from '$app/paths';
	
	let apiStatus = 'checking...';
	
	onMount(async () => {
		// Redirect authenticated users to dashboard
		if ($isAuthenticated) {
			goto('/dashboard');
			return;
		}
		
		try {
			const response = await fetch('/api/v1/health/status');
			if (response.ok) {
				const data = await response.json();
				apiStatus = data.status;
			} else {
				apiStatus = 'error';
			}
		} catch (error) {
			apiStatus = 'disconnected';
		}
	});
</script>

<div class="container mx-auto px-4 py-16">
	<div class="max-w-4xl mx-auto">
		<div class="flex items-center gap-3 mb-4">
			<img src={`${base}/logo/chrono-scraper-logo.png`} alt="" class="h-10 w-10" width="40" height="40" />
			<h1 class="text-5xl font-bold">Welcome to Chrono Scraper</h1>
		</div>
		<div class="h-2"></div>
		<p class="text-xl text-muted-foreground mb-8">
			Full-text indexing for the Wayback Machine, reimagined with modern technology.
		</p>
		
		<div class="grid md:grid-cols-2 gap-8 mb-12">
			<div class="border rounded-lg p-6">
				<h2 class="text-2xl font-semibold mb-3">🚀 Fast & Scalable</h2>
				<p class="text-muted-foreground">
					Built with FastAPI and async Python for maximum performance. Handle thousands of pages with ease.
				</p>
			</div>
			
			<div class="border rounded-lg p-6">
				<h2 class="text-2xl font-semibold mb-3">🔍 Powerful Search</h2>
				<p class="text-muted-foreground">
					Meilisearch provides instant, typo-tolerant search across all your indexed content.
				</p>
			</div>
			
			<div class="border rounded-lg p-6">
				<h2 class="text-2xl font-semibold mb-3">📊 Rich Analytics</h2>
				<p class="text-muted-foreground">
					Entity extraction, timeline visualization, and content analysis powered by AI.
				</p>
			</div>
			
			<div class="border rounded-lg p-6">
				<h2 class="text-2xl font-semibold mb-3">🛡️ Enterprise Ready</h2>
				<p class="text-muted-foreground">
					Comprehensive monitoring, security features, and production-grade infrastructure.
				</p>
			</div>
		</div>
		
		<div class="bg-secondary rounded-lg p-6 mb-8">
			<h3 class="text-lg font-semibold mb-2">System Status</h3>
			<div class="flex items-center gap-2">
				<div class="w-3 h-3 rounded-full {apiStatus === 'healthy' ? 'bg-green-500' : 'bg-red-500'}"></div>
				<span>API: {apiStatus}</span>
			</div>
		</div>
		
		<div class="flex gap-4">
			<a href="/dashboard" class="inline-flex items-center justify-center rounded-md bg-primary px-8 py-3 text-primary-foreground hover:bg-primary/90">
				Get Started
			</a>
			<a href="/docs" class="inline-flex items-center justify-center rounded-md border px-8 py-3 hover:bg-secondary">
				Documentation
			</a>
		</div>
	</div>
</div>