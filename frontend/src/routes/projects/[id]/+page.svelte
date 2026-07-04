<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { auth, isAuthenticated } from '$lib/stores/auth';
	import { getApiUrl, apiFetch, getRelativeTime } from '$lib/utils';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Progress } from '$lib/components/ui/progress';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import ScrapeLog from '$lib/components/scraping/ScrapeLog.svelte';
	import {
		Loader2,
		Pause,
		Play,
		RefreshCw,
		CheckCircle2,
		XCircle,
		Filter as FilterIcon,
		Clock,
		AlertCircle,
		ChevronLeft
	} from 'lucide-svelte';

	$: projectId = $page.params.id as string;

	interface Project {
		id: number;
		name: string;
		status: string;
		archive_source?: string;
		created_at?: string;
	}
	interface Session {
		id: number;
		status: string;
		total_urls: number;
		completed_urls: number;
		failed_urls: number;
		progress: number;
		error_message?: string | null;
		started_at?: string | null;
		completed_at?: string | null;
	}
	interface FailedPage {
		id: number;
		original_url: string;
		domain_name: string;
		error_message?: string | null;
		error_type?: string | null;
		retry_count?: number;
	}
	interface DomainReport {
		domain_name: string;
		discovered: number;
		scraped: number;
		failed: number;
		filtered: number;
		pending: number;
		awaiting_review: number;
	}

	let project: Project | null = null;
	let sessions: Session[] = [];
	let statusCounts: Record<string, number> = {};
	let failedPages: FailedPage[] = [];
	let perDomain: DomainReport[] = [];
	let loading = true;
	let error = '';
	let actionPending = '';

	let pollingInterval: ReturnType<typeof setInterval> | null = null;
	const POLL_MS = 4000;

	// ── Derived progress buckets ───────────────────────────────
	const FILTERED_STATUSES = [
		'skipped',
		'manually_skipped',
		'filtered_list_page',
		'filtered_already_processed',
		'filtered_attachment_disabled',
		'filtered_file_extension',
		'filtered_size_too_small',
		'filtered_size_too_large',
		'filtered_low_priority',
		'filtered_custom_rule'
	];
	const IN_PROGRESS_STATUSES = ['pending', 'in_progress', 'retry'];

	function sumStatuses(keys: string[]): number {
		return keys.reduce((acc, k) => acc + (statusCounts[k] || 0), 0);
	}

	$: discovered = Object.values(statusCounts).reduce((a, b) => a + b, 0);
	$: completed = statusCounts['completed'] || 0;
	$: failed = statusCounts['failed'] || 0;
	$: filtered = sumStatuses(FILTERED_STATUSES);
	$: inProgress = sumStatuses(IN_PROGRESS_STATUSES);
	$: awaitingReview = statusCounts['awaiting_manual_review'] || 0;

	$: hasActiveSession = sessions.some((s) =>
		['running', 'pending', 'queued'].includes((s.status || '').toLowerCase())
	);
	// The scrape-progress WebSocket is keyed by session id; use the newest.
	$: latestSessionId = sessions.length ? Math.max(...sessions.map((s) => s.id)) : null;
	// The scrape is "settled" once nothing is queued/running and discovery produced pages.
	$: isSettled = !hasActiveSession && inProgress === 0 && discovered > 0;
	$: processedTarget = discovered - filtered; // pages we actually intend to scrape
	$: percent =
		processedTarget > 0 ? Math.min(100, Math.round(((completed + failed) / processedTarget) * 100)) : 0;

	onMount(() => {
		if (!browser) return;
		const unsub = auth.subscribe((state) => {
			if (!state.isLoading && !state.isAuthenticated) {
				goto(`/auth/login?redirect=/projects/${projectId}`);
			}
		});
		load(true);
		return unsub;
	});

	onDestroy(() => stopPolling());

	// Start/stop the poll loop as session activity changes.
	$: if (browser) {
		if (hasActiveSession && !pollingInterval) {
			pollingInterval = setInterval(() => load(false), POLL_MS);
		} else if (!hasActiveSession && pollingInterval) {
			stopPolling();
		}
	}

	function stopPolling() {
		if (pollingInterval) {
			clearInterval(pollingInterval);
			pollingInterval = null;
		}
	}

	async function load(initial: boolean) {
		if (initial) loading = true;
		try {
			const [projRes, sessRes, pagesRes, reportRes] = await Promise.all([
				apiFetch(getApiUrl(`/api/v1/projects/${projectId}`)),
				apiFetch(getApiUrl(`/api/v1/projects/${projectId}/sessions`)),
				// One call yields the full status breakdown *and* the failed URL list.
				apiFetch(
					getApiUrl(`/api/v1/projects/${projectId}/scrape-pages?status_filter=failed&limit=100`)
				),
				apiFetch(getApiUrl(`/api/v1/projects/${projectId}/report`))
			]);

			if (projRes.ok) project = await projRes.json();
			else if (projRes.status === 404) {
				error = 'Scrape not found.';
				return;
			}

			if (sessRes.ok) sessions = await sessRes.json();

			if (pagesRes.ok) {
				const data = await pagesRes.json();
				statusCounts = data.status_counts || {};
				failedPages = data.scrape_pages || [];
			}

			if (reportRes.ok) {
				const report = await reportRes.json();
				perDomain = report.per_domain || [];
			}
			error = '';
		} catch (e) {
			console.error('Failed to load scrape', e);
			if (initial) error = 'Failed to load this scrape.';
		} finally {
			loading = false;
		}
	}

	async function control(action: 'scrape' | 'pause' | 'retry-failed') {
		actionPending = action;
		try {
			const res = await apiFetch(getApiUrl(`/api/v1/projects/${projectId}/${action}`), {
				method: 'POST',
				headers: {}
			});
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				error = data.detail || `Failed to ${action.replace('-', ' ')}.`;
			}
			await load(false);
		} catch (e) {
			error = `Failed to ${action.replace('-', ' ')}.`;
		} finally {
			actionPending = '';
		}
	}

	function fmtStatus(s: string): string {
		return (s || '').replace(/_/g, ' ');
	}
	function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		const s = (status || '').toLowerCase();
		if (s.includes('complet')) return 'default';
		if (s.includes('fail') || s.includes('error') || s.includes('cancel')) return 'destructive';
		if (s.includes('run') || s.includes('index') || s.includes('pending') || s.includes('queue'))
			return 'secondary';
		return 'outline';
	}
</script>

<svelte:head>
	<title>{project?.name ?? 'Scrape'} · Chrono Scraper</title>
</svelte:head>

<div class="mx-auto w-full max-w-4xl space-y-6 px-4 py-8">
	<a
		href="/"
		class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
	>
		<ChevronLeft class="h-4 w-4" /> New scrape
	</a>

	{#if error}
		<Alert class="border-destructive">
			<AlertCircle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	{#if loading}
		<div class="flex min-h-[40vh] items-center justify-center">
			<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
		</div>
	{:else if project}
		<!-- Header -->
		<div class="flex flex-wrap items-start justify-between gap-3">
			<div class="min-w-0 space-y-1">
				<div class="flex items-center gap-2">
					<h1 class="truncate text-xl font-bold">{project.name}</h1>
					<Badge variant={statusVariant(project.status)}>{fmtStatus(project.status)}</Badge>
					{#if hasActiveSession}
						<span class="flex items-center gap-1 text-xs text-emerald-600">
							<span class="relative flex h-2 w-2">
								<span
									class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"
								></span>
								<span class="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
							</span>
							LIVE
						</span>
					{/if}
				</div>
				{#if project.archive_source}
					<p class="text-xs text-muted-foreground">Source: {project.archive_source}</p>
				{/if}
			</div>
			<div class="flex items-center gap-2">
				{#if hasActiveSession}
					<Button
						variant="outline"
						size="sm"
						class="gap-1"
						disabled={actionPending === 'pause'}
						onclick={() => control('pause')}
					>
						<Pause class="h-4 w-4" /> Pause
					</Button>
				{:else}
					<Button
						variant="outline"
						size="sm"
						class="gap-1"
						disabled={actionPending === 'scrape'}
						onclick={() => control('scrape')}
					>
						<Play class="h-4 w-4" /> Re-run
					</Button>
				{/if}
				{#if failed > 0}
					<Button
						variant="outline"
						size="sm"
						class="gap-1"
						disabled={actionPending === 'retry-failed'}
						onclick={() => control('retry-failed')}
					>
						<RefreshCw class="h-4 w-4" /> Retry failed
					</Button>
				{/if}
			</div>
		</div>

		<!-- Progress bar -->
		<Card>
			<CardContent class="space-y-3 p-5">
				<div class="flex items-center justify-between text-sm">
					<span class="font-medium">
						{#if hasActiveSession}
							Scraping in progress…
						{:else if isSettled}
							Scrape complete
						{:else}
							Awaiting start
						{/if}
					</span>
					<span class="text-muted-foreground">{completed + failed} / {processedTarget} processed</span>
				</div>
				<Progress value={percent} max={100} />
			</CardContent>
		</Card>

		<!-- Stat grid -->
		<div class="grid grid-cols-2 gap-3 sm:grid-cols-5">
			<div class="rounded-lg border p-3">
				<p class="text-xs text-muted-foreground">Discovered</p>
				<p class="text-2xl font-bold">{discovered.toLocaleString()}</p>
			</div>
			<div class="rounded-lg border p-3">
				<p class="flex items-center gap-1 text-xs text-muted-foreground">
					<CheckCircle2 class="h-3 w-3 text-emerald-600" /> Scraped
				</p>
				<p class="text-2xl font-bold text-emerald-600">{completed.toLocaleString()}</p>
			</div>
			<div class="rounded-lg border p-3">
				<p class="flex items-center gap-1 text-xs text-muted-foreground">
					<XCircle class="h-3 w-3 text-destructive" /> Failed
				</p>
				<p class="text-2xl font-bold text-destructive">{failed.toLocaleString()}</p>
			</div>
			<div class="rounded-lg border p-3">
				<p class="flex items-center gap-1 text-xs text-muted-foreground">
					<FilterIcon class="h-3 w-3" /> Filtered
				</p>
				<p class="text-2xl font-bold">{filtered.toLocaleString()}</p>
			</div>
			<div class="rounded-lg border p-3">
				<p class="flex items-center gap-1 text-xs text-muted-foreground">
					<Clock class="h-3 w-3" /> Pending
				</p>
				<p class="text-2xl font-bold">{inProgress.toLocaleString()}</p>
			</div>
		</div>

		<!-- Completion report -->
		{#if isSettled}
			<Card>
				<CardContent class="space-y-2 p-5">
					<h2 class="font-semibold">Completion report</h2>
					{#if failed === 0}
						<p class="flex items-center gap-2 text-sm text-emerald-700">
							<CheckCircle2 class="h-4 w-4" />
							All {processedTarget.toLocaleString()} target pages were scraped successfully
							({filtered.toLocaleString()} additional pages were filtered out).
						</p>
					{:else}
						<p class="flex items-center gap-2 text-sm">
							<AlertCircle class="h-4 w-4 text-amber-600" />
							{completed.toLocaleString()} of {processedTarget.toLocaleString()} target pages scraped;
							<span class="font-medium text-destructive">{failed.toLocaleString()} failed</span>.
							{#if awaitingReview > 0}
								{awaitingReview.toLocaleString()} awaiting manual review.
							{/if}
						</p>
					{/if}
				</CardContent>
			</Card>
		{/if}

		<!-- Per-domain breakdown -->
		{#if perDomain.length > 0}
			<div class="space-y-2">
				<h2 class="text-sm font-semibold text-muted-foreground">By domain</h2>
				<div class="overflow-x-auto rounded-md border">
					<table class="w-full text-sm">
						<thead class="border-b bg-muted/40 text-xs text-muted-foreground">
							<tr>
								<th class="px-3 py-2 text-left font-medium">Domain</th>
								<th class="px-3 py-2 text-right font-medium">Discovered</th>
								<th class="px-3 py-2 text-right font-medium">Scraped</th>
								<th class="px-3 py-2 text-right font-medium">Failed</th>
								<th class="px-3 py-2 text-right font-medium">Filtered</th>
								<th class="px-3 py-2 text-right font-medium">Pending</th>
							</tr>
						</thead>
						<tbody class="divide-y">
							{#each perDomain as d}
								<tr>
									<td class="px-3 py-2 font-mono text-xs">{d.domain_name}</td>
									<td class="px-3 py-2 text-right">{d.discovered.toLocaleString()}</td>
									<td class="px-3 py-2 text-right text-emerald-600">{d.scraped.toLocaleString()}</td>
									<td class="px-3 py-2 text-right {d.failed > 0 ? 'text-destructive' : ''}"
										>{d.failed.toLocaleString()}</td
									>
									<td class="px-3 py-2 text-right text-muted-foreground">{d.filtered.toLocaleString()}</td>
									<td class="px-3 py-2 text-right">{d.pending.toLocaleString()}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<!-- Live log -->
		<ScrapeLog sessionId={latestSessionId} active={hasActiveSession} />

		<!-- Sessions -->
		{#if sessions.length > 0}
			<div class="space-y-2">
				<h2 class="text-sm font-semibold text-muted-foreground">Sessions</h2>
				<div class="divide-y rounded-md border">
					{#each sessions as s}
						<div class="flex items-center justify-between px-4 py-3 text-sm">
							<div class="min-w-0">
								<div class="flex items-center gap-2">
									<Badge variant={statusVariant(s.status)}>{fmtStatus(s.status)}</Badge>
									<span class="text-muted-foreground">
										{s.completed_urls}/{s.total_urls} URLs
										{#if s.failed_urls > 0}· {s.failed_urls} failed{/if}
									</span>
								</div>
								{#if s.error_message}
									<p class="mt-1 truncate text-xs text-destructive">{s.error_message}</p>
								{/if}
							</div>
							{#if s.started_at}
								<span class="whitespace-nowrap text-xs text-muted-foreground"
									>{getRelativeTime(s.started_at)}</span
								>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Failures -->
		{#if failedPages.length > 0}
			<div class="space-y-2">
				<h2 class="text-sm font-semibold text-muted-foreground">
					Failed pages ({failed.toLocaleString()})
				</h2>
				<div class="divide-y rounded-md border">
					{#each failedPages as fp}
						<div class="px-4 py-3 text-sm">
							<p class="truncate font-mono text-xs">{fp.original_url}</p>
							<p class="mt-1 text-xs text-destructive">
								{fp.error_type ? `[${fp.error_type}] ` : ''}{fp.error_message || 'Unknown error'}
								{#if fp.retry_count}· {fp.retry_count} retries{/if}
							</p>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>
