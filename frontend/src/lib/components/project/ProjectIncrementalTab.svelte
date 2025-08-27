<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Badge } from '$lib/components/ui/badge';
	import { 
		TrendingUp,
		Globe,
		BarChart3,
		History,
		AlertTriangle,
		Info
	} from 'lucide-svelte';
	
	import IncrementalScrapingDashboard from '../scraping/IncrementalScrapingDashboard.svelte';
	import IncrementalScrapingPanel from '../scraping/IncrementalScrapingPanel.svelte';
	import { getApiUrl } from '$lib/utils';

	export let projectId: number;
	export let projectName: string = '';

	const dispatch = createEventDispatcher();

	let domains = writable<Array<{
		id: number;
		domain_name: string;
		status: string;
		incremental_enabled: boolean;
		coverage_percentage: number;
		total_gaps: number;
	}>>([]);
	
	let selectedDomainId: number | null = null;
	let isLoading = false;
	let error = '';

	onMount(async () => {
		await loadDomains();
	});

	async function loadDomains() {
		try {
			isLoading = true;
			error = '';
			
			const response = await fetch(getApiUrl(`/api/v1/projects/${projectId}/domains`), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const domainsData = await response.json();
			domains.set(domainsData.map((domain: any) => ({
				...domain,
				incremental_enabled: false, // This would come from the API
				coverage_percentage: 0, // This would come from the API
				total_gaps: 0 // This would come from the API
			})));
			
			// Auto-select first domain if available
			if (domainsData.length > 0 && !selectedDomainId) {
				selectedDomainId = domainsData[0].id;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load domains';
			console.error('Load domains error:', e);
		} finally {
			isLoading = false;
		}
	}

	function onScrapeTriggered(event: CustomEvent) {
		dispatch('scrapeTriggered', event.detail);
	}

	function onConfigUpdated(event: CustomEvent) {
		dispatch('configUpdated', event.detail);
		// Reload domains to reflect changes
		setTimeout(loadDomains, 1000);
	}

	function onIncrementalUpdate(event: CustomEvent) {
		dispatch('incrementalUpdate', event.detail);
	}

	function onViewSchedule() {
		dispatch('viewSchedule');
	}

	function onFillAllGaps() {
		dispatch('fillAllGaps');
	}

	function onConfigureSchedule() {
		dispatch('configureSchedule');
	}

	$: selectedDomain = selectedDomainId ? $domains.find(d => d.id === selectedDomainId) : null;
	$: enabledDomains = $domains.filter(d => d.incremental_enabled);
</script>

<div class="space-y-6">
	{#if error}
		<Alert variant="destructive">
			<AlertTriangle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	<Tabs value="overview" class="w-full">
		<TabsList class="grid w-full grid-cols-3">
			<TabsTrigger value="overview" class="flex items-center gap-2">
				<BarChart3 class="h-4 w-4" />
				Project Overview
			</TabsTrigger>
			<TabsTrigger value="domains" class="flex items-center gap-2">
				<Globe class="h-4 w-4" />
				Domain Configuration
			</TabsTrigger>
			<TabsTrigger value="history" class="flex items-center gap-2">
				<History class="h-4 w-4" />
				Activity History
			</TabsTrigger>
		</TabsList>

		<TabsContent value="overview" class="space-y-6">
			<!-- Project-wide Dashboard -->
			<IncrementalScrapingDashboard
				{projectId}
				{projectName}
				showDomainBreakdown={true}
				on:scrapeTriggered={onScrapeTriggered}
				on:viewSchedule={onViewSchedule}
				on:fillAllGaps={onFillAllGaps}
				on:configureSchedule={onConfigureSchedule}
			/>

			<!-- Quick Domain Status -->
			{#if $domains.length > 0}
				<Card>
					<CardHeader>
						<CardTitle class="flex items-center space-x-2">
							<Globe class="h-5 w-5" />
							<span>Domain Status Overview</span>
						</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
							{#each $domains as domain}
								<div 
									class="p-4 border rounded-lg hover:bg-gray-50 cursor-pointer {selectedDomainId === domain.id ? 'ring-2 ring-primary' : ''}"
									onclick={() => selectedDomainId = domain.id}
									role="button"
									tabindex="0"
									onkeydown={(e) => {
										if (e.key === 'Enter' || e.key === ' ') {
											e.preventDefault();
											selectedDomainId = domain.id;
										}
									}}
								>
									<div class="flex items-center justify-between mb-2">
										<span class="font-medium">{domain.domain_name}</span>
										<Badge variant={domain.incremental_enabled ? 'default' : 'secondary'}>
											{domain.incremental_enabled ? 'Enabled' : 'Disabled'}
										</Badge>
									</div>
									<div class="text-sm text-gray-600 space-y-1">
										<div>Coverage: {domain.coverage_percentage.toFixed(1)}%</div>
										<div>Gaps: {domain.total_gaps}</div>
									</div>
								</div>
							{/each}
						</div>
					</CardContent>
				</Card>
			{/if}
		</TabsContent>

		<TabsContent value="domains" class="space-y-6">
			{#if $domains.length === 0}
				<Alert>
					<Info class="h-4 w-4" />
					<AlertDescription>
						<strong>No domains configured.</strong>
						Add domains to your project first, then configure incremental scraping for each domain.
					</AlertDescription>
				</Alert>
			{:else}
				<!-- Domain Selection -->
				<Card>
					<CardHeader>
						<CardTitle>Select Domain to Configure</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
							{#each $domains as domain}
								<button 
									class="p-3 border rounded-lg text-left hover:bg-gray-50 {selectedDomainId === domain.id ? 'ring-2 ring-primary bg-primary/5' : ''}"
									onclick={() => selectedDomainId = domain.id}
								>
									<div class="font-medium">{domain.domain_name}</div>
									<div class="text-sm text-gray-600 mt-1">
										{domain.incremental_enabled ? 'Enabled' : 'Disabled'}
									</div>
								</button>
							{/each}
						</div>
					</CardContent>
				</Card>

				<!-- Selected Domain Configuration -->
				{#if selectedDomain}
					<IncrementalScrapingPanel
						domainId={selectedDomain.id}
						{projectId}
						domainName={selectedDomain.domain_name}
						canControl={true}
						on:incrementalUpdate={onIncrementalUpdate}
						on:scrapeTriggered={onScrapeTriggered}
						on:configUpdated={onConfigUpdated}
					/>
				{/if}
			{/if}
		</TabsContent>

		<TabsContent value="history" class="space-y-6">
			<div class="text-center py-8">
				<History class="h-12 w-12 text-gray-400 mx-auto mb-4" />
				<h3 class="text-lg font-medium text-gray-900 mb-2">Activity History</h3>
				<p class="text-gray-600">
					Project-wide incremental scraping history and analytics will be displayed here.
				</p>
			</div>
		</TabsContent>
	</Tabs>

	<!-- Summary Information -->
	{#if $domains.length > 0}
		<Alert>
			<TrendingUp class="h-4 w-4" />
			<AlertDescription>
				<strong>Incremental Scraping Summary:</strong>
				{enabledDomains.length} of {$domains.length} domains have incremental scraping enabled.
				{#if enabledDomains.length === 0}
					Enable incremental scraping for individual domains to maintain continuous coverage.
				{:else if enabledDomains.length < $domains.length}
					Consider enabling incremental scraping for remaining domains to ensure comprehensive coverage.
				{:else}
					All domains are configured for incremental scraping.
				{/if}
			</AlertDescription>
		</Alert>
	{/if}
</div>