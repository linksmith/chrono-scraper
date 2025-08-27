<script lang="ts">
	/**
	 * Example integration of incremental scraping components into a project page
	 * This shows how to add the incremental scraping functionality to existing project pages
	 */
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Badge } from '$lib/components/ui/badge';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { 
		BarChart3,
		Globe,
		TrendingUp,
		Settings,
		History,
		Activity
	} from 'lucide-svelte';

	// Import the new incremental scraping components
	import ProjectIncrementalTab from '../project/ProjectIncrementalTab.svelte';
	import DomainManagement from '../domains/DomainManagement.svelte';
	import ProjectDashboard from '../project/ProjectDashboard.svelte';

	// These would typically come from route parameters
	export let projectId: number;
	export let projectName: string = '';

	let activeTab = 'dashboard';
	let notificationCount = 0;

	// Event handlers for incremental scraping events
	function onScrapeTriggered(event: CustomEvent) {
		console.log('Incremental scrape triggered:', event.detail);
		// Show notification, update UI, etc.
	}

	function onConfigUpdated(event: CustomEvent) {
		console.log('Incremental config updated:', event.detail);
		// Update project statistics, show success message, etc.
	}

	function onIncrementalUpdate(event: CustomEvent) {
		console.log('Incremental update received:', event.detail);
		// Update real-time progress indicators
	}

	function onViewSchedule() {
		console.log('View schedule requested');
		// Navigate to scheduling page or show modal
	}

	function onFillAllGaps() {
		console.log('Fill all gaps requested');
		// Trigger project-wide gap filling
	}

	function onConfigureSchedule() {
		console.log('Configure schedule requested');
		// Navigate to configuration page or show modal
	}

	onMount(() => {
		// Initialize any required data
		console.log('Project page loaded with incremental scraping support');
	});
</script>

<!-- Example project page with incremental scraping integration -->
<div class="container mx-auto py-6 space-y-6">
	<!-- Page Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-3xl font-bold">Project: {projectName}</h1>
			<p class="text-muted-foreground">ID: {projectId}</p>
		</div>
		
		<!-- Project Actions -->
		<div class="flex items-center space-x-2">
			<Badge variant="outline">Active</Badge>
			{#if notificationCount > 0}
				<Badge variant="destructive">{notificationCount}</Badge>
			{/if}
		</div>
	</div>

	<!-- Main Content Tabs -->
	<Tabs bind:value={activeTab} class="w-full">
		<TabsList class="grid w-full grid-cols-5">
			<TabsTrigger value="dashboard" class="flex items-center gap-2">
				<BarChart3 class="h-4 w-4" />
				Dashboard
			</TabsTrigger>
			<TabsTrigger value="domains" class="flex items-center gap-2">
				<Globe class="h-4 w-4" />
				Domains
			</TabsTrigger>
			<TabsTrigger value="incremental" class="flex items-center gap-2">
				<TrendingUp class="h-4 w-4" />
				Incremental
			</TabsTrigger>
			<TabsTrigger value="settings" class="flex items-center gap-2">
				<Settings class="h-4 w-4" />
				Settings
			</TabsTrigger>
			<TabsTrigger value="history" class="flex items-center gap-2">
				<History class="h-4 w-4" />
				History
			</TabsTrigger>
		</TabsList>

		<!-- Dashboard Tab -->
		<TabsContent value="dashboard" class="space-y-6">
			<ProjectDashboard 
				{projectId}
				{projectName}
			/>
		</TabsContent>

		<!-- Domains Tab -->
		<TabsContent value="domains" class="space-y-6">
			<DomainManagement 
				{projectId}
				{projectName}
				on:domainAdded={(e) => console.log('Domain added:', e.detail)}
				on:domainDeleted={(e) => console.log('Domain deleted:', e.detail)}
				on:scrapingStarted={(e) => console.log('Scraping started:', e.detail)}
			/>
		</TabsContent>

		<!-- NEW: Incremental Scraping Tab -->
		<TabsContent value="incremental" class="space-y-6">
			<ProjectIncrementalTab
				{projectId}
				{projectName}
				on:scrapeTriggered={onScrapeTriggered}
				on:configUpdated={onConfigUpdated}
				on:incrementalUpdate={onIncrementalUpdate}
				on:viewSchedule={onViewSchedule}
				on:fillAllGaps={onFillAllGaps}
				on:configureSchedule={onConfigureSchedule}
			/>
		</TabsContent>

		<!-- Settings Tab -->
		<TabsContent value="settings" class="space-y-6">
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center space-x-2">
						<Settings class="h-5 w-5" />
						<span>Project Settings</span>
					</CardTitle>
				</CardHeader>
				<CardContent>
					<p class="text-gray-600">
						Project configuration settings would go here.
					</p>
				</CardContent>
			</Card>
		</TabsContent>

		<!-- History Tab -->
		<TabsContent value="history" class="space-y-6">
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center space-x-2">
						<Activity class="h-5 w-5" />
						<span>Project History</span>
					</CardTitle>
				</CardHeader>
				<CardContent>
					<p class="text-gray-600">
						Project activity history would be displayed here.
					</p>
				</CardContent>
			</Card>
		</TabsContent>
	</Tabs>
</div>

<style>
	/* Example of custom styling for the incremental scraping components */
	:global(.incremental-scraping-panel) {
		/* Custom styles can be applied here */
	}
	
	:global(.coverage-visualization) {
		/* Custom styles for coverage visualization */
	}
</style>