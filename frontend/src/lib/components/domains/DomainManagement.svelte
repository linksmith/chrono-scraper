<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Progress } from '$lib/components/ui/progress';
	import { formatDateTime, formatNumber, formatPercentage, getApiUrl, isValidDomain } from '$lib/utils';
	import ScrapingProgress from '../scraping/ScrapingProgress.svelte';
	import { 
		Plus, 
		Globe, 
		Play, 
		Pause, 
		Trash2, 
		Edit, 
		BarChart3, 
		Calendar, 
		CheckCircle, 
		XCircle, 
		Clock, 
		Loader2,
		AlertCircle,
		Settings,
		Download
	} from 'lucide-svelte';

	const dispatch = createEventDispatcher();

	export let projectId: number;
	export let projectName: string = '';

	interface Domain {
		id: number;
		domain_name: string;
		status: string;
		total_pages: number;
		scraped_pages: number;
		failed_pages: number;
		last_scraped?: string;
		created_at: string;
		updated_at?: string;
	}

	const domains = writable<Domain[]>([]);
	const loading = writable(false);
	const error = writable<string | null>(null);

	// Add domain form state
	let showAddForm = false;
	let newDomainName = '';
	let newDomainError = '';

	// Active scraping tasks
	const activeScrapingTasks = writable<Map<number, string>>(new Map());

	onMount(() => {
		loadDomains();
	});

	async function loadDomains() {
		loading.set(true);
		error.set(null);

		try {
			const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/domains`), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const data = await response.json();
			domains.set(data);
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to load domains');
		} finally {
			loading.set(false);
		}
	}

	async function addDomain() {
		if (!newDomainName.trim()) {
			newDomainError = 'Domain name is required';
			return;
		}

		if (!isValidDomain(newDomainName.trim())) {
			newDomainError = 'Invalid domain name format';
			return;
		}

		newDomainError = '';
		loading.set(true);

		try {
			const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/domains`), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({
					domain_name: newDomainName.trim()
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}

			const newDomain = await response.json();
			domains.update(list => [...list, newDomain]);
			
			// Reset form
			newDomainName = '';
			showAddForm = false;

			dispatch('domainAdded', newDomain);
		} catch (err) {
			newDomainError = err instanceof Error ? err.message : 'Failed to add domain';
		} finally {
			loading.set(false);
		}
	}

	async function deleteDomain(domainId: number) {
		if (!confirm('Are you sure you want to delete this domain? This action cannot be undone.')) {
			return;
		}

		try {
			const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/domains/${domainId}`), {
				method: 'DELETE',
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			domains.update(list => list.filter(d => d.id !== domainId));
			dispatch('domainDeleted', domainId);
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to delete domain');
		}
	}

	async function startScraping(domain: Domain) {
		try {
			const response = await fetch(getApiUrl('/api/v1/tasks/scraping/start'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({
					project_id: projectId,
					domain_id: domain.id
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}

			const taskData = await response.json();
			
			// Add to active scraping tasks
			activeScrapingTasks.update(tasks => {
				tasks.set(domain.id, taskData.task_id);
				return tasks;
			});

			// Update domain status
			domains.update(list => 
				list.map(d => d.id === domain.id ? { ...d, status: 'scraping' } : d)
			);

			dispatch('scrapingStarted', { domain, taskId: taskData.task_id });
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to start scraping');
		}
	}

	function getStatusColor(status: string): 'default' | 'success' | 'warning' | 'destructive' | 'info' {
		switch (status.toLowerCase()) {
			case 'completed': return 'success';
			case 'scraping': case 'indexing': return 'info';
			case 'error': case 'failed': return 'destructive';
			case 'pending': return 'warning';
			default: return 'default';
		}
	}

	function getStatusIcon(status: string) {
		switch (status.toLowerCase()) {
			case 'completed': return CheckCircle;
			case 'scraping': case 'indexing': return Loader2;
			case 'error': case 'failed': return XCircle;
			case 'pending': return Clock;
			default: return AlertCircle;
		}
	}

	function calculateSuccessRate(domain: Domain): number {
		if (domain.total_pages === 0) return 0;
		return (domain.scraped_pages / domain.total_pages) * 100;
	}

	function onScrapingComplete(domain: Domain) {
		// Remove from active tasks
		activeScrapingTasks.update(tasks => {
			tasks.delete(domain.id);
			return tasks;
		});

		// Reload domains to get updated stats
		loadDomains();
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold">Domain Management</h2>
			{#if projectName}
				<p class="text-muted-foreground">Project: {projectName}</p>
			{/if}
		</div>
		<Button on:click={() => showAddForm = !showAddForm}>
			<Plus class="w-4 h-4 mr-2" />
			Add Domain
		</Button>
	</div>

	<!-- Add Domain Form -->
	{#if showAddForm}
		<Card>
			<CardHeader>
				<CardTitle>Add New Domain</CardTitle>
			</CardHeader>
			<CardContent class="space-y-4">
				<div>
					<label for="domain-name" class="text-sm font-medium mb-2 block">
						Domain Name
					</label>
					<input
						id="domain-name"
						type="text"
						bind:value={newDomainName}
						placeholder="example.com"
						class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
						class:border-destructive={newDomainError}
					/>
					{#if newDomainError}
						<p class="text-destructive text-sm mt-1">{newDomainError}</p>
					{/if}
					<p class="text-muted-foreground text-xs mt-1">
						Enter the domain name without protocol (e.g., example.com, not https://example.com)
					</p>
				</div>
				<div class="flex gap-2">
					<Button on:click={addDomain} disabled={$loading}>
						{#if $loading}
							<Loader2 class="w-4 h-4 mr-2 animate-spin" />
						{:else}
							<Plus class="w-4 h-4 mr-2" />
						{/if}
						Add Domain
					</Button>
					<Button variant="outline" on:click={() => { showAddForm = false; newDomainError = ''; }}>
						Cancel
					</Button>
				</div>
			</CardContent>
		</Card>
	{/if}

	<!-- Error Display -->
	{#if $error}
		<Card class="border-destructive">
			<CardContent class="pt-6">
				<div class="flex items-center gap-2 text-destructive">
					<AlertCircle class="w-4 h-4" />
					<span>{$error}</span>
				</div>
			</CardContent>
		</Card>
	{/if}

	<!-- Active Scraping Tasks -->
	{#if $activeScrapingTasks.size > 0}
		<div class="space-y-4">
			<h3 class="text-lg font-semibold">Active Scraping Tasks</h3>
			{#each Array.from($activeScrapingTasks.entries()) as [domainId, taskId]}
				{@const domain = $domains.find(d => d.id === domainId)}
				{#if domain}
					<ScrapingProgress
						{taskId}
						domainName={domain.domain_name}
						{projectName}
						on:complete={() => onScrapingComplete(domain)}
					/>
				{/if}
			{/each}
		</div>
	{/if}

	<!-- Domains List -->
	{#if $loading && $domains.length === 0}
		<div class="flex items-center justify-center py-12">
			<Loader2 class="w-8 h-8 animate-spin mr-2" />
			<span>Loading domains...</span>
		</div>
	{:else if $domains.length === 0}
		<Card>
			<CardContent class="pt-6">
				<div class="text-center py-12">
					<Globe class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
					<h3 class="text-lg font-semibold mb-2">No Domains Yet</h3>
					<p class="text-muted-foreground mb-4">
						Add your first domain to start scraping historical web content.
					</p>
					<Button on:click={() => showAddForm = true}>
						<Plus class="w-4 h-4 mr-2" />
						Add Domain
					</Button>
				</div>
			</CardContent>
		</Card>
	{:else}
		<div class="grid gap-4">
			{#each $domains as domain (domain.id)}
				<Card>
					<CardHeader class="pb-3">
						<div class="flex items-center justify-between">
							<div class="flex items-center gap-3">
								<Globe class="w-5 h-5 text-muted-foreground" />
								<div>
									<CardTitle class="text-lg">{domain.domain_name}</CardTitle>
									<p class="text-sm text-muted-foreground">
										Created {formatDateTime(domain.created_at)}
									</p>
								</div>
							</div>
							
							<div class="flex items-center gap-2">
								<Badge variant={getStatusColor(domain.status)}>
									<svelte:component 
										this={getStatusIcon(domain.status)} 
										class="w-3 h-3 mr-1 {domain.status === 'scraping' ? 'animate-spin' : ''}"
									/>
									{domain.status}
								</Badge>
								
								<div class="flex gap-1">
									<Button 
										variant="outline" 
										size="sm"
										on:click={() => startScraping(domain)}
										disabled={domain.status === 'scraping' || $activeScrapingTasks.has(domain.id)}
									>
										<Play class="w-3 h-3" />
									</Button>
									<Button variant="outline" size="sm">
										<Settings class="w-3 h-3" />
									</Button>
									<Button 
										variant="outline" 
										size="sm"
										on:click={() => deleteDomain(domain.id)}
									>
										<Trash2 class="w-3 h-3" />
									</Button>
								</div>
							</div>
						</div>
					</CardHeader>

					<CardContent class="space-y-4">
						<!-- Statistics -->
						<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
							<div class="text-center">
								<div class="text-2xl font-bold">{formatNumber(domain.total_pages)}</div>
								<div class="text-sm text-muted-foreground">Total Pages</div>
							</div>
							<div class="text-center">
								<div class="text-2xl font-bold text-green-600">{formatNumber(domain.scraped_pages)}</div>
								<div class="text-sm text-muted-foreground">Scraped</div>
							</div>
							<div class="text-center">
								<div class="text-2xl font-bold text-red-600">{formatNumber(domain.failed_pages)}</div>
								<div class="text-sm text-muted-foreground">Failed</div>
							</div>
							<div class="text-center">
								<div class="text-2xl font-bold">{calculateSuccessRate(domain).toFixed(1)}%</div>
								<div class="text-sm text-muted-foreground">Success Rate</div>
							</div>
						</div>

						<!-- Progress Bar -->
						{#if domain.total_pages > 0}
							<div class="space-y-2">
								<div class="flex justify-between text-sm">
									<span>Scraping Progress</span>
									<span>{domain.scraped_pages} / {domain.total_pages}</span>
								</div>
								<Progress 
									value={domain.scraped_pages} 
									max={domain.total_pages} 
									class="h-2"
								/>
							</div>
						{/if}

						<!-- Last Scraped -->
						{#if domain.last_scraped}
							<div class="flex items-center gap-2 text-sm text-muted-foreground">
								<Calendar class="w-4 h-4" />
								Last scraped: {formatDateTime(domain.last_scraped)}
							</div>
						{/if}

						<!-- Action Buttons -->
						<div class="flex gap-2 pt-2 border-t">
							<Button 
								variant="outline" 
								size="sm"
								on:click={() => dispatch('viewDomainDetails', domain)}
							>
								<BarChart3 class="w-4 h-4 mr-2" />
								View Details
							</Button>
							<Button 
								variant="outline" 
								size="sm"
								on:click={() => dispatch('exportDomainData', domain)}
							>
								<Download class="w-4 h-4 mr-2" />
								Export Data
							</Button>
						</div>
					</CardContent>
				</Card>
			{/each}
		</div>
	{/if}
</div>