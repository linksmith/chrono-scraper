<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { auth, isAuthenticated, isLoading } from '$lib/stores/auth';
	import { getApiUrl, apiFetch, formatDate } from '$lib/utils';
	import { Button } from '$lib/components/ui/button';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Select,
		SelectContent,
		SelectItem,
		SelectTrigger
	} from '$lib/components/ui/select';
	import { Search, Loader2, AlertCircle, Star, X } from 'lucide-svelte';

	interface Hit {
		id: string;
		url?: string;
		title?: string;
		content?: string;
		word_count?: number;
		capture_date?: string;
		timestamp?: string | number;
		is_starred?: boolean;
		review_statuses?: string[];
		_formatted?: { content?: string; title?: string };
	}
	interface ProjectOpt {
		id: number;
		name: string;
	}

	const REVIEW_STATUSES = ['relevant', 'irrelevant', 'unreviewed', 'needs_review', 'duplicate'];
	const SORT_OPTIONS: Record<string, string> = {
		relevance: 'Relevance',
		capture_date: 'Capture date',
		word_count: 'Word count',
		quality_score: 'Quality score'
	};

	// ── State ───────────────────────────────────────────────────
	let query = '';
	let projects: ProjectOpt[] = [];
	let projectId: number | null = null; // null = all my projects
	let selectedReviewStatuses = new Set<string>();
	let starredOnly = false;
	let minWordCount: number | null = null;
	let sortBy = 'relevance';
	let sortOrder: 'asc' | 'desc' = 'desc';

	let hits: Hit[] = [];
	let total = 0;
	let searched = false;
	let loading = false;
	let error = '';

	let page = 0;
	const PER_PAGE = 20;

	onMount(() => {
		if (!browser) return;
		const unsub = auth.subscribe((s) => {
			if (!s.isLoading && !s.isAuthenticated) goto('/auth/login?redirect=/search');
		});
		loadProjects();
		return unsub;
	});

	async function loadProjects() {
		try {
			const res = await apiFetch(getApiUrl('/api/v1/projects/?skip=0&limit=100'));
			if (res.ok) {
				const data = await res.json();
				const items = Array.isArray(data) ? data : (data.items ?? data.projects ?? []);
				projects = items.map((p: any) => ({ id: p.id, name: p.name }));
			}
		} catch (e) {
			console.error('Failed to load projects', e);
		}
	}

	function toggleReviewStatus(s: string) {
		if (selectedReviewStatuses.has(s)) selectedReviewStatuses.delete(s);
		else selectedReviewStatuses.add(s);
		selectedReviewStatuses = new Set(selectedReviewStatuses);
	}

	// Strip any HTML from Meilisearch snippets before display (scraped content
	// is untrusted; never inject it as HTML).
	function plainSnippet(hit: Hit): string {
		const raw = hit._formatted?.content || hit.content || '';
		const text = raw.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
		return text.length > 260 ? text.slice(0, 260) + '…' : text;
	}

	async function runSearch(resetPage = true) {
		if (resetPage) page = 0;
		loading = true;
		error = '';
		searched = true;
		try {
			const filters: Record<string, unknown> = {};
			if (starredOnly) filters.is_starred = true;
			if (selectedReviewStatuses.size > 0)
				filters.review_statuses = Array.from(selectedReviewStatuses);
			if (minWordCount != null && minWordCount > 0) filters.min_word_count = minWordCount;

			const body: Record<string, unknown> = {
				query,
				filters,
				limit: PER_PAGE,
				offset: page * PER_PAGE
			};
			if (projectId != null) body.project_id = projectId;
			if (sortBy !== 'relevance') {
				body.sort_by = sortBy;
				body.sort_order = sortOrder;
			}

			const res = await apiFetch(getApiUrl('/api/v1/shared-pages/search'), {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				error = d.detail || `Search failed (HTTP ${res.status}).`;
				hits = [];
				total = 0;
				return;
			}
			const payload = await res.json();
			const data = payload.data ?? payload;
			hits = data.hits ?? data.results ?? [];
			total = data.estimatedTotalHits ?? data.total ?? hits.length;
		} catch (e) {
			console.error('Search error', e);
			error = 'A network error occurred while searching.';
			hits = [];
			total = 0;
		} finally {
			loading = false;
		}
	}

	function onSubmit(e: Event) {
		e.preventDefault();
		runSearch();
	}

	function clearFilters() {
		projectId = null;
		selectedReviewStatuses = new Set();
		starredOnly = false;
		minWordCount = null;
		sortBy = 'relevance';
		sortOrder = 'desc';
	}

	async function nextPage() {
		if ((page + 1) * PER_PAGE >= total) return;
		page += 1;
		await runSearch(false);
	}
	async function prevPage() {
		if (page === 0) return;
		page -= 1;
		await runSearch(false);
	}

	$: projectLabel =
		projectId == null ? 'All my projects' : (projects.find((p) => p.id === projectId)?.name ?? `Project ${projectId}`);
	$: activeFilterCount =
		(projectId != null ? 1 : 0) +
		selectedReviewStatuses.size +
		(starredOnly ? 1 : 0) +
		(minWordCount ? 1 : 0);
</script>

<svelte:head>
	<title>Search · Chrono Scraper</title>
</svelte:head>

{#if $isLoading}
	<div class="flex min-h-[60vh] items-center justify-center">
		<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
	</div>
{:else if $isAuthenticated}
	<div class="mx-auto w-full max-w-5xl space-y-6 px-4 py-8">
		<h1 class="text-2xl font-bold tracking-tight">Search scraped pages</h1>

		<form onsubmit={onSubmit} class="flex gap-2">
			<Input
				bind:value={query}
				placeholder="Search titles and content…"
				class="flex-1"
			/>
			<Button type="submit" class="gap-2" disabled={loading}>
				{#if loading}
					<Loader2 class="h-4 w-4 animate-spin" />
				{:else}
					<Search class="h-4 w-4" />
				{/if}
				Search
			</Button>
		</form>

		{#if error}
			<Alert class="border-destructive">
				<AlertCircle class="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		{/if}

		<div class="grid gap-6 md:grid-cols-[220px_1fr]">
			<!-- Filters -->
			<aside class="space-y-5">
				<div class="flex items-center justify-between">
					<h2 class="text-sm font-semibold">Filters</h2>
					{#if activeFilterCount > 0}
						<button
							type="button"
							class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
							onclick={() => {
								clearFilters();
								if (searched) runSearch();
							}}
						>
							<X class="h-3 w-3" /> Clear ({activeFilterCount})
						</button>
					{/if}
				</div>

				<div class="space-y-2">
					<Label>Project</Label>
					<Select
						value={projectId == null ? '__all__' : String(projectId)}
						onValueChange={(v) => (projectId = v === '__all__' ? null : Number(v))}
					>
						<SelectTrigger><span>{projectLabel}</span></SelectTrigger>
						<SelectContent>
							<SelectItem value="__all__">All my projects</SelectItem>
							{#each projects as p}
								<SelectItem value={String(p.id)}>{p.name}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>

				<div class="space-y-2">
					<Label>Review status</Label>
					<div class="space-y-1">
						{#each REVIEW_STATUSES as s}
							<label class="flex items-center gap-2 text-sm capitalize">
								<input
									type="checkbox"
									checked={selectedReviewStatuses.has(s)}
									onchange={() => toggleReviewStatus(s)}
								/>
								{s.replace('_', ' ')}
							</label>
						{/each}
					</div>
				</div>

				<div class="space-y-2">
					<Label for="minwc">Min word count</Label>
					<Input id="minwc" type="number" min="0" bind:value={minWordCount} placeholder="any" />
				</div>

				<label class="flex items-center gap-2 text-sm">
					<input type="checkbox" bind:checked={starredOnly} />
					<Star class="h-3.5 w-3.5" /> Starred only
				</label>

				<div class="space-y-2">
					<Label>Sort by</Label>
					<Select value={sortBy} onValueChange={(v) => (sortBy = v)}>
						<SelectTrigger><span>{SORT_OPTIONS[sortBy]}</span></SelectTrigger>
						<SelectContent>
							{#each Object.entries(SORT_OPTIONS) as [val, label]}
								<SelectItem value={val}>{label}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
					{#if sortBy !== 'relevance'}
						<Select value={sortOrder} onValueChange={(v) => (sortOrder = v as 'asc' | 'desc')}>
							<SelectTrigger><span>{sortOrder === 'desc' ? 'Descending' : 'Ascending'}</span></SelectTrigger>
							<SelectContent>
								<SelectItem value="desc">Descending</SelectItem>
								<SelectItem value="asc">Ascending</SelectItem>
							</SelectContent>
						</Select>
					{/if}
				</div>

				<Button variant="outline" size="sm" class="w-full" onclick={() => runSearch()} disabled={loading}>
					Apply filters
				</Button>
			</aside>

			<!-- Results -->
			<div class="space-y-3">
				{#if searched && !loading}
					<p class="text-sm text-muted-foreground">
						{total.toLocaleString()} result{total === 1 ? '' : 's'}
						{#if query}for "{query}"{/if}
					</p>
				{/if}

				{#if loading}
					<div class="flex justify-center py-10">
						<Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
					</div>
				{:else if searched && hits.length === 0}
					<p class="py-10 text-center text-sm text-muted-foreground">No matching pages.</p>
				{:else if !searched}
					<p class="py-10 text-center text-sm text-muted-foreground">
						Enter a query and hit Search.
					</p>
				{:else}
					{#each hits as hit}
						<Card>
							<CardContent class="space-y-1 p-4">
								<div class="flex items-start justify-between gap-2">
									<h3 class="font-medium">
										{hit.title || hit.url || 'Untitled page'}
									</h3>
									{#if hit.is_starred}
										<Star class="h-4 w-4 shrink-0 text-amber-500" />
									{/if}
								</div>
								{#if hit.url}
									<a
										href={hit.url}
										target="_blank"
										rel="noopener noreferrer"
										class="block truncate font-mono text-xs text-muted-foreground hover:text-foreground"
									>
										{hit.url}
									</a>
								{/if}
								<p class="text-sm text-muted-foreground">{plainSnippet(hit)}</p>
								<div class="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
									{#if hit.word_count}<Badge variant="outline">{hit.word_count.toLocaleString()} words</Badge>{/if}
									{#if hit.capture_date}<span>{formatDate(hit.capture_date)}</span>{/if}
									{#each hit.review_statuses ?? [] as rs}
										<Badge variant="secondary" class="capitalize">{rs.replace('_', ' ')}</Badge>
									{/each}
								</div>
							</CardContent>
						</Card>
					{/each}

					{#if total > PER_PAGE}
						<div class="flex items-center justify-between pt-2">
							<Button variant="outline" size="sm" disabled={page === 0} onclick={prevPage}>
								Previous
							</Button>
							<span class="text-xs text-muted-foreground">
								Page {page + 1} of {Math.ceil(total / PER_PAGE)}
							</span>
							<Button
								variant="outline"
								size="sm"
								disabled={(page + 1) * PER_PAGE >= total}
								onclick={nextPage}
							>
								Next
							</Button>
						</div>
					{/if}
				{/if}
			</div>
		</div>
	</div>
{/if}
