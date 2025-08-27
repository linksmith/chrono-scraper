<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Progress } from '$lib/components/ui/progress';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '$lib/components/ui/collapsible';
	import { 
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
		Download,
		ChevronDown,
		ChevronUp,
		TrendingUp,
		Target,
		Activity
	} from 'lucide-svelte';
	
	import { formatDateTime, formatNumber } from '$lib/utils';
	import IncrementalScrapingPanel from '../scraping/IncrementalScrapingPanel.svelte';

	export let domain: {
		id: number;
		domain_name: string;
		status: string;
		total_pages: number;
		scraped_pages: number;
		failed_pages: number;
		last_scraped?: string;
		created_at: string;
		updated_at?: string;
	};
	export let projectId: number;
	export let projectName: string = '';
	export let isScrapingActive: boolean = false;
	export let canControl: boolean = true;

	const dispatch = createEventDispatcher();

	let isExpanded = false;
	let activeTab = 'overview';

	function onStartScraping() {
		dispatch('startScraping', { domain });
	}

	function onDeleteDomain() {
		dispatch('deleteDomain', { domainId: domain.id });
	}

	function onViewDetails() {
		dispatch('viewDetails', { domain });
	}

	function onExportData() {
		dispatch('exportData', { domain });
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

	function calculateSuccessRate(): number {
		if (domain.total_pages === 0) return 0;
		return (domain.scraped_pages / domain.total_pages) * 100;
	}

	function onIncrementalUpdate(event: CustomEvent) {
		// Forward incremental scraping updates to parent
		dispatch('incrementalUpdate', event.detail);
	}

	function onScrapeTriggered(event: CustomEvent) {
		dispatch('scrapeTriggered', event.detail);
	}

	function onConfigUpdated(event: CustomEvent) {
		dispatch('configUpdated', event.detail);
	}
</script>

<Card class="w-full">
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
						onclick={onStartScraping}
						disabled={domain.status === 'scraping' || isScrapingActive || !canControl}
					>
						<Play class="w-3 h-3" />
					</Button>
					<Button 
						variant="outline" 
						size="sm"
						onclick={onViewDetails}
					>
						<Settings class="w-3 h-3" />
					</Button>
					<Button 
						variant="outline" 
						size="sm"
						onclick={onDeleteDomain}
						disabled={!canControl}
					>
						<Trash2 class="w-3 h-3" />
					</Button>
				</div>
				
				<Collapsible bind:open={isExpanded}>
					<CollapsibleTrigger asChild let:builder>
						<Button builders={[builder]} variant="ghost" size="sm">
							{#if isExpanded}
								<ChevronUp class="w-4 h-4" />
							{:else}
								<ChevronDown class="w-4 h-4" />
							{/if}
						</Button>
					</CollapsibleTrigger>
				</Collapsible>
			</div>
		</div>
	</CardHeader>

	<CardContent class="space-y-4">
		<!-- Basic Statistics - Always Visible -->
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
				<div class="text-2xl font-bold">{calculateSuccessRate().toFixed(1)}%</div>
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

		<!-- Expanded Content -->
		<Collapsible bind:open={isExpanded}>
			<CollapsibleContent>
				<div class="pt-4 border-t">
					<Tabs bind:value={activeTab} class="w-full">
						<TabsList class="grid w-full grid-cols-3">
							<TabsTrigger value="overview" class="flex items-center gap-2">
								<BarChart3 class="h-4 w-4" />
								Overview
							</TabsTrigger>
							<TabsTrigger value="incremental" class="flex items-center gap-2">
								<TrendingUp class="h-4 w-4" />
								Incremental
							</TabsTrigger>
							<TabsTrigger value="analytics" class="flex items-center gap-2">
								<Activity class="h-4 w-4" />
								Analytics
							</TabsTrigger>
						</TabsList>

						<TabsContent value="overview" class="space-y-4">
							<!-- Detailed Statistics -->
							<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
								<Card>
									<CardContent class="pt-6">
										<div class="space-y-4">
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Total Discovered</span>
												<span class="font-bold">{formatNumber(domain.total_pages)}</span>
											</div>
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Successfully Scraped</span>
												<span class="font-bold text-green-600">{formatNumber(domain.scraped_pages)}</span>
											</div>
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Failed to Scrape</span>
												<span class="font-bold text-red-600">{formatNumber(domain.failed_pages)}</span>
											</div>
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Remaining</span>
												<span class="font-bold text-yellow-600">
													{formatNumber(domain.total_pages - domain.scraped_pages - domain.failed_pages)}
												</span>
											</div>
										</div>
									</CardContent>
								</Card>

								<Card>
									<CardContent class="pt-6">
										<div class="space-y-4">
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Success Rate</span>
												<span class="font-bold">{calculateSuccessRate().toFixed(2)}%</span>
											</div>
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Status</span>
												<Badge variant={getStatusColor(domain.status)}>
													{domain.status}
												</Badge>
											</div>
											<div class="flex items-center justify-between">
												<span class="text-sm font-medium">Created</span>
												<span class="text-sm">{formatDateTime(domain.created_at)}</span>
											</div>
											{#if domain.updated_at}
												<div class="flex items-center justify-between">
													<span class="text-sm font-medium">Last Updated</span>
													<span class="text-sm">{formatDateTime(domain.updated_at)}</span>
												</div>
											{/if}
										</div>
									</CardContent>
								</Card>
							</div>

							<!-- Action Buttons -->
							<div class="flex gap-2 pt-4 border-t">
								<Button 
									variant="outline" 
									size="sm"
									onclick={onViewDetails}
								>
									<BarChart3 class="w-4 h-4 mr-2" />
									View Details
								</Button>
								<Button 
									variant="outline" 
									size="sm"
									onclick={onExportData}
								>
									<Download class="w-4 h-4 mr-2" />
									Export Data
								</Button>
								<Button 
									variant="outline" 
									size="sm"
									onclick={onStartScraping}
									disabled={domain.status === 'scraping' || isScrapingActive || !canControl}
								>
									<Play class="w-4 h-4 mr-2" />
									Start Scraping
								</Button>
							</div>
						</TabsContent>

						<TabsContent value="incremental" class="space-y-4">
							<IncrementalScrapingPanel
								domainId={domain.id}
								{projectId}
								domainName={domain.domain_name}
								{canControl}
								on:incrementalUpdate={onIncrementalUpdate}
								on:scrapeTriggered={onScrapeTriggered}
								on:configUpdated={onConfigUpdated}
							/>
						</TabsContent>

						<TabsContent value="analytics" class="space-y-4">
							<div class="text-center py-8">
								<Activity class="w-12 h-12 text-gray-400 mx-auto mb-4" />
								<h3 class="text-lg font-medium text-gray-900 mb-2">Analytics Coming Soon</h3>
								<p class="text-gray-600">
									Detailed analytics and performance metrics will be available here.
								</p>
							</div>
						</TabsContent>
					</Tabs>
				</div>
			</CollapsibleContent>
		</Collapsible>
	</CardContent>
</Card>