<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, auth, user } from '$lib/stores/auth';
	import { Card, CardContent } from '$lib/components/ui/card';
	
	let isLoading = true;
	let authChecked = false;
	
	onMount(async () => {
		// Initialize auth system
		await auth.init();
		authChecked = true;
		
		// Check if user is authenticated
		if (!$isAuthenticated) {
			// Redirect to login with current path as redirect parameter
			const redirectPath = $page.url.pathname + $page.url.search;
			goto(`/auth/login?redirect=${encodeURIComponent(redirectPath)}`);
			return;
		}
		
		isLoading = false;
	});
	
	// Reactive statement to handle auth state changes
	$: if (authChecked && !$isAuthenticated) {
		const redirectPath = $page.url.pathname + $page.url.search;
		goto(`/auth/login?redirect=${encodeURIComponent(redirectPath)}`);
	}
</script>

<svelte:head>
	<title>Dashboard - Chrono Scraper</title>
</svelte:head>

{#if isLoading}
	<div class="min-h-screen flex items-center justify-center bg-background">
		<Card class="w-96">
			<CardContent class="pt-6">
				<div class="flex flex-col items-center space-y-4">
					<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
					<p class="text-sm text-muted-foreground">Loading dashboard...</p>
				</div>
			</CardContent>
		</Card>
	</div>
{:else if $isAuthenticated}
	<slot />
{:else}
	<div class="min-h-screen flex items-center justify-center bg-background">
		<Card class="w-96">
			<CardContent class="pt-6">
				<div class="flex flex-col items-center space-y-4">
					<p class="text-sm text-muted-foreground">Redirecting to login...</p>
				</div>
			</CardContent>
		</Card>
	</div>
{/if}