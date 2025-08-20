<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { isAuthenticated, auth, user } from '$lib/stores/auth';
	import { Card, CardContent, CardHeader } from '$lib/components/ui/card';
	import { Skeleton } from '$lib/components/ui/skeleton';
	
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
	<!-- Dashboard loading skeleton instead of spinner -->
	<div class="container mx-auto px-4 py-8">
		<div class="space-y-8">
			<!-- Header Skeleton -->
			<div class="flex items-center justify-between">
				<div class="space-y-2">
					<Skeleton class="h-8 w-48" />
					<Skeleton class="h-4 w-80" />
				</div>
				<Skeleton class="h-10 w-32" />
			</div>

			<!-- Statistics Cards Skeleton -->
			<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
				{#each Array(4) as _}
					<Card>
						<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
							<Skeleton class="h-4 w-24" />
							<Skeleton class="h-4 w-4" />
						</CardHeader>
						<CardContent class="space-y-2">
							<Skeleton class="h-8 w-16" />
							<Skeleton class="h-3 w-32" />
						</CardContent>
					</Card>
				{/each}
			</div>
		</div>
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