<script lang="ts">
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { AlertTriangle, Home, ArrowLeft } from 'lucide-svelte';
</script>

<svelte:head>
	<title>{$page.status} - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-background flex items-center justify-center p-4">
	<Card class="w-full max-w-md">
		<CardContent class="pt-6">
			<div class="flex flex-col items-center space-y-4 text-center">
				<div class="h-16 w-16 rounded-full bg-muted flex items-center justify-center">
					<AlertTriangle class="h-8 w-8 text-muted-foreground" />
				</div>

				<div class="space-y-2">
					<h1 class="text-4xl font-bold">{$page.status}</h1>
					<p class="text-muted-foreground">
						{#if $page.status === 404}
							The page you're looking for doesn't exist or has been moved.
						{:else if $page.status === 500}
							Something went wrong on our end. Please try again later.
						{:else}
							{$page.error?.message || 'An unexpected error occurred.'}
						{/if}
					</p>
				</div>

				<div class="flex gap-2 pt-2">
					<Button variant="outline" href="javascript:history.back()">
						<ArrowLeft class="mr-2 h-4 w-4" />
						Go Back
					</Button>
					<Button href="/dashboard">
						<Home class="mr-2 h-4 w-4" />
						Dashboard
					</Button>
				</div>
			</div>
		</CardContent>
	</Card>
</div>
