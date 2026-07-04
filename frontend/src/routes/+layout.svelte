<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { onMount } from 'svelte';
	import { auth, isAuthenticated } from '$lib/stores/auth';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import ErrorBoundary from '$lib/components/ErrorBoundary.svelte';
	import Toast from '$lib/components/Toast.svelte';
	import LoadingOverlay from '$lib/components/loading/LoadingOverlay.svelte';
	import { Button } from '$lib/components/ui/button';
	import { LogOut, Plus, Search } from 'lucide-svelte';

	let mounted = false;

	onMount(() => {
		auth.init();
		mounted = true;
	});

	// The header only makes sense inside the authenticated app, never on the
	// login/verify pages.
	$: onAuthPage = $page.url.pathname.startsWith('/auth') ||
		$page.url.pathname.startsWith('/verify-email') ||
		$page.url.pathname.startsWith('/reset-password');
	$: showHeader = $isAuthenticated && !onAuthPage;
</script>

{#if mounted}
	<ModeWatcher />
{/if}

<!-- Global Toast Notifications -->
<Toast />

<!-- Global Loading Overlay -->
<LoadingOverlay />

<div class="min-h-screen bg-background">
	{#if showHeader}
		<header class="border-b">
			<div class="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
				<a href="/" class="flex items-center gap-2">
					<img
						src={`${base}/logo/chrono-scraper-logo.png`}
						alt=""
						class="h-6 w-6"
						width="24"
						height="24"
					/>
					<span class="font-semibold">Chrono Scraper</span>
				</a>
				<div class="flex items-center gap-2">
					<Button href="/" variant="ghost" size="sm" class="gap-1">
						<Plus class="h-4 w-4" />
						New scrape
					</Button>
					<Button href="/search" variant="ghost" size="sm" class="gap-1">
						<Search class="h-4 w-4" />
						Search
					</Button>
					<Button variant="ghost" size="sm" class="gap-1" onclick={() => auth.logout()}>
						<LogOut class="h-4 w-4" />
						Logout
					</Button>
				</div>
			</div>
		</header>
	{/if}

	<main>
		<ErrorBoundary
			fallback="We're having trouble loading this page. Please try refreshing or contact support if the problem persists."
		>
			<slot />
		</ErrorBoundary>
	</main>
</div>
