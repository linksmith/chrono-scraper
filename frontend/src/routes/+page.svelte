<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { auth, isAuthenticated, isLoading } from '$lib/stores/auth';
	import { getApiUrl, apiFetch, getRelativeTime } from '$lib/utils';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Label } from '$lib/components/ui/label';
	import { Input } from '$lib/components/ui/input';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Select,
		SelectContent,
		SelectItem,
		SelectTrigger
	} from '$lib/components/ui/select';
	import { AlertCircle, Play, Loader2, ChevronDown, ChevronRight } from 'lucide-svelte';
	import { DEFAULT_ARCHIVE_CONFIG } from '$lib/types/archive';

	// ── Form state ──────────────────────────────────────────────
	let domainsText = '';
	let archiveSource: 'wayback' | 'commoncrawl' | 'hybrid' = 'hybrid';
	let fromDate = '';
	let toDate = '';
	let showAdvanced = false;

	let submitting = false;
	let error = '';

	// ── Recent scrapes ──────────────────────────────────────────
	interface RecentProject {
		id: number;
		name: string;
		status: string;
		created_at: string;
	}
	let recent: RecentProject[] = [];
	let recentLoading = true;

	const archiveLabels: Record<string, string> = {
		commoncrawl: 'Common Crawl',
		wayback: 'Wayback Machine',
		hybrid: 'Hybrid (Common Crawl first, Wayback for the rest)'
	};

	onMount(() => {
		if (!browser) return;
		const unsub = auth.subscribe((state) => {
			if (!state.isLoading && !state.isAuthenticated) {
				goto('/auth/login?redirect=/');
			}
		});
		loadRecent();
		return unsub;
	});

	async function loadRecent() {
		recentLoading = true;
		try {
			const res = await apiFetch(getApiUrl('/api/v1/projects/?skip=0&limit=10'));
			if (res.ok) {
				const data = await res.json();
				const items = Array.isArray(data) ? data : (data.items ?? data.projects ?? []);
				recent = items.map((p: any) => ({
					id: p.id,
					name: p.name,
					status: p.status,
					created_at: p.created_at
				}));
			}
		} catch (e) {
			// non-fatal — the form is the primary surface
			console.error('Failed to load recent scrapes', e);
		} finally {
			recentLoading = false;
		}
	}

	// Split textarea into distinct, trimmed, de-duplicated targets.
	function parseTargets(text: string): string[] {
		return Array.from(
			new Set(
				text
					.split(/[\n,]/)
					.map((t) => t.trim())
					.filter(Boolean)
			)
		);
	}

	// Preserve the backend's domain-vs-URL distinction: anything with a path
	// component is a URL prefix scrape; a bare host is a whole-domain scrape.
	function classifyTarget(raw: string): {
		domain_name: string;
		match_type: 'domain' | 'prefix';
		url_path: string | null;
	} {
		let value = raw;
		const hasScheme = /^https?:\/\//i.test(value);
		if (!hasScheme && value.includes('/')) {
			value = 'https://' + value;
		}
		try {
			if (/^https?:\/\//i.test(value)) {
				const u = new URL(value);
				const isUrl = u.pathname && u.pathname !== '/';
				return {
					domain_name: u.hostname,
					match_type: isUrl ? 'prefix' : 'domain',
					url_path: isUrl ? raw : null
				};
			}
		} catch {
			// fall through to treating it as a bare domain
		}
		return { domain_name: value.replace(/^https?:\/\//i, ''), match_type: 'domain', url_path: null };
	}

	$: targets = parseTargets(domainsText);
	$: canSubmit = targets.length > 0 && !submitting;

	async function startScrape() {
		const parsed = targets;
		if (parsed.length === 0) {
			error = 'Enter at least one domain or URL.';
			return;
		}

		submitting = true;
		error = '';

		try {
			const projectName =
				parsed.length === 1 ? parsed[0] : `${parsed[0]} +${parsed.length - 1} more`;

			// 1. Create the project (the container the domains + scrape hang off).
			const projectRes = await apiFetch(getApiUrl('/api/v1/projects'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: projectName,
					description: null,
					process_documents: true,
					enable_attachment_download: false,
					langextract_enabled: false,
					langextract_provider: 'disabled',
					archive_source: archiveSource,
					fallback_enabled: true,
					archive_config: { ...DEFAULT_ARCHIVE_CONFIG }
				})
			});

			if (!projectRes.ok) {
				const data = await projectRes.json().catch(() => ({}));
				error = data.detail || 'Failed to create the scrape.';
				return;
			}
			const project = await projectRes.json();

			// 2. Register each target domain/URL.
			let domainFailures = 0;
			for (const raw of parsed) {
				const t = classifyTarget(raw);
				try {
					const dRes = await apiFetch(getApiUrl(`/api/v1/projects/${project.id}/domains`), {
						method: 'POST',
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({
							domain_name: t.domain_name,
							match_type: t.match_type,
							url_path: t.url_path,
							from_date: fromDate || null,
							to_date: toDate || null,
							max_pages: null,
							active: true
						})
					});
					if (!dRes.ok) domainFailures++;
				} catch {
					domainFailures++;
				}
			}

			if (domainFailures === parsed.length) {
				error = 'None of the targets could be registered. Check the domain format and try again.';
				return;
			}

			// 3. Kick off scraping.
			const scrapeRes = await apiFetch(getApiUrl(`/api/v1/projects/${project.id}/scrape`), {
				method: 'POST',
				headers: {}
			});
			if (!scrapeRes.ok) {
				// Project + domains exist; surface the failure but still route to the
				// progress page where the user can retry the trigger.
				console.error('Failed to start scraping', scrapeRes.status);
			}

			await goto(`/projects/${project.id}`);
		} catch (e) {
			console.error('Scrape start failed', e);
			error = 'A network error occurred while starting the scrape.';
		} finally {
			submitting = false;
		}
	}

	function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
		const s = (status || '').toLowerCase();
		if (s.includes('complet')) return 'default';
		if (s.includes('fail') || s.includes('error')) return 'destructive';
		if (s.includes('index') || s.includes('run') || s.includes('progress') || s.includes('scrap'))
			return 'secondary';
		return 'outline';
	}
</script>

<svelte:head>
	<title>Chrono Scraper</title>
</svelte:head>

{#if $isLoading}
	<div class="flex min-h-[60vh] items-center justify-center">
		<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
	</div>
{:else if $isAuthenticated}
	<div class="mx-auto w-full max-w-2xl space-y-8 px-4 py-10">
		<div class="space-y-1">
			<h1 class="text-2xl font-bold tracking-tight">Start a scrape</h1>
			<p class="text-sm text-muted-foreground">
				Enter one or more domains (or full URLs), one per line. We'll discover archived pages and
				scrape them.
			</p>
		</div>

		{#if error}
			<Alert class="border-destructive">
				<AlertCircle class="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		{/if}

		<Card>
			<CardContent class="space-y-5 p-5">
				<div class="space-y-2">
					<Label for="domains">Domains or URLs</Label>
					<Textarea
						id="domains"
						bind:value={domainsText}
						rows={5}
						placeholder={'example.com\nnews.example.org\nhttps://example.com/section/'}
						class="font-mono text-sm"
					/>
					{#if targets.length > 0}
						<p class="text-xs text-muted-foreground">
							{targets.length} target{targets.length === 1 ? '' : 's'} ready
						</p>
					{/if}
				</div>

				<div class="space-y-2">
					<Label>Archive source</Label>
					<Select
						value={archiveSource}
						onValueChange={(v) => (archiveSource = v as typeof archiveSource)}
					>
						<SelectTrigger>
							<span>{archiveLabels[archiveSource]}</span>
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="commoncrawl">{archiveLabels.commoncrawl}</SelectItem>
							<SelectItem value="wayback">{archiveLabels.wayback}</SelectItem>
							<SelectItem value="hybrid">{archiveLabels.hybrid}</SelectItem>
						</SelectContent>
					</Select>
				</div>

				<button
					type="button"
					class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
					onclick={() => (showAdvanced = !showAdvanced)}
				>
					{#if showAdvanced}
						<ChevronDown class="h-4 w-4" />
					{:else}
						<ChevronRight class="h-4 w-4" />
					{/if}
					Date range (optional)
				</button>

				{#if showAdvanced}
					<div class="grid grid-cols-2 gap-4">
						<div class="space-y-2">
							<Label for="from">From</Label>
							<Input id="from" type="date" bind:value={fromDate} />
						</div>
						<div class="space-y-2">
							<Label for="to">To</Label>
							<Input id="to" type="date" bind:value={toDate} />
						</div>
					</div>
				{/if}

				<Button class="w-full gap-2" disabled={!canSubmit} onclick={startScrape}>
					{#if submitting}
						<Loader2 class="h-4 w-4 animate-spin" />
						Starting…
					{:else}
						<Play class="h-4 w-4" />
						Start scraping
					{/if}
				</Button>
			</CardContent>
		</Card>

		<div class="space-y-3">
			<h2 class="text-sm font-semibold text-muted-foreground">Recent scrapes</h2>
			{#if recentLoading}
				<p class="text-sm text-muted-foreground">Loading…</p>
			{:else if recent.length === 0}
				<p class="text-sm text-muted-foreground">No scrapes yet.</p>
			{:else}
				<div class="divide-y rounded-md border">
					{#each recent as p}
						<a
							href={`/projects/${p.id}`}
							class="flex items-center justify-between px-4 py-3 hover:bg-accent"
						>
							<div class="min-w-0">
								<p class="truncate text-sm font-medium">{p.name}</p>
								<p class="text-xs text-muted-foreground">{getRelativeTime(p.created_at)}</p>
							</div>
							<Badge variant={statusVariant(p.status)}>{p.status}</Badge>
						</a>
					{/each}
				</div>
			{/if}
		</div>
	</div>
{/if}
