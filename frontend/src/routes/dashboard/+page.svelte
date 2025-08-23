<script lang="ts">
	import { onMount } from 'svelte';
	import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Progress } from '$lib/components/ui/progress';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { 
		Activity, 
		Database,
		Search,
		Target,
		Clock,
		Star,
		Users,
		TrendingUp,
		Globe,
		Filter,
		CheckCircle2,
		BookMarked,
		Zap,
		Calendar,
		BarChart3,
		AlertCircle,
		RefreshCw
	} from 'lucide-svelte';
	
	let loading = true;
	
	// Dashboard data structure for researchers
	let dashboardData = {
		userStats: {
			myProjectsCount: 0,
			totalPagesScraped: 0,
			entitiesDiscovered: 0,
			savedSearchesCount: 0,
			libraryItemsCount: 0,
			averageContentQuality: 0
		},
		recentActivity: [],
		entityInsights: {
			topEntities: [],
			entityTypesDistribution: [],
			confidenceStats: {
				average: 0,
				minimum: 0,
				maximum: 0
			}
		},
		projectProgress: {
			activeJobs: [],
			projectStats: [],
			summary: {
				totalActiveJobs: 0,
				totalProjects: 0,
				activeProjects: 0
			}
		},
		contentTimeline: {
			dailyTimeline: [],
			productiveDomains: [],
			timeframeDays: 30
		}
	};
	
	let errorMessage = '';
	let retryCount = 0;
	const maxRetries = 3;

	async function loadDashboardData() {
		try {
			errorMessage = '';
			const options = {
				credentials: 'include' as RequestCredentials,
				headers: {
					'Content-Type': 'application/json'
				}
			};

			// Load user statistics with individual error handling
			const [userStatsRes, recentActivityRes, entityInsightsRes, projectProgressRes, contentTimelineRes] = await Promise.allSettled([
				fetch('/api/v1/dashboard/user-stats', options),
				fetch('/api/v1/dashboard/recent-activity', options),
				fetch('/api/v1/dashboard/entity-insights', options),
				fetch('/api/v1/dashboard/project-progress', options),
				fetch('/api/v1/dashboard/content-timeline', options)
			]);

			// Handle user stats
			if (userStatsRes.status === 'fulfilled' && userStatsRes.value.ok) {
				dashboardData.userStats = await userStatsRes.value.json();
			} else if (userStatsRes.status === 'fulfilled' && userStatsRes.value.status === 401) {
				window.location.href = '/auth/login';
				return;
			}
			
			// Handle recent activity
			if (recentActivityRes.status === 'fulfilled' && recentActivityRes.value.ok) {
				const recentData = await recentActivityRes.value.json();
				dashboardData.recentActivity = recentData.recent_activity || [];
			}
			
			// Handle entity insights
			if (entityInsightsRes.status === 'fulfilled' && entityInsightsRes.value.ok) {
				dashboardData.entityInsights = await entityInsightsRes.value.json();
			}
			
			// Handle project progress
			if (projectProgressRes.status === 'fulfilled' && projectProgressRes.value.ok) {
				dashboardData.projectProgress = await projectProgressRes.value.json();
			}
			
			// Handle content timeline
			if (contentTimelineRes.status === 'fulfilled' && contentTimelineRes.value.ok) {
				dashboardData.contentTimeline = await contentTimelineRes.value.json();
			}
			
		} catch (error) {
			console.error('Failed to load dashboard data:', error);
			errorMessage = 'Failed to load dashboard data. Please try refreshing the page.';
			
			// Retry logic
			if (retryCount < maxRetries) {
				retryCount++;
				setTimeout(() => {
					loadDashboardData();
				}, 1000 * retryCount); // Exponential backoff
			}
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		loadDashboardData();
	});
	
	function getActivityIcon(type: string) {
		switch (type) {
			case 'scrape_completed': return CheckCircle2;
			case 'entity_discovered': return Target;
			case 'page_starred': return Star;
			default: return Activity;
		}
	}
	
	function getActivityColor(type: string) {
		switch (type) {
			case 'scrape_completed': return 'text-green-600';
			case 'entity_discovered': return 'text-blue-600';
			case 'page_starred': return 'text-yellow-600';
			default: return 'text-gray-600';
		}
	}

	function formatActivityDescription(activity: any): string {
		switch (activity.type) {
			case 'scrape_completed':
				return `Discovered "${activity.title}" in ${activity.project_name}`;
			case 'entity_discovered':
				return `Found ${activity.entity_type}: "${activity.entity_name}" (${Math.round(activity.confidence * 100)}% confidence)`;
			case 'page_starred':
				return `Starred "${activity.title}" from ${activity.project_name}`;
			default:
				return 'Unknown activity';
		}
	}

	function formatTimestamp(timestamp: string): string {
		const date = new Date(timestamp);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		
		const minutes = Math.floor(diff / (1000 * 60));
		const hours = Math.floor(diff / (1000 * 60 * 60));
		const days = Math.floor(diff / (1000 * 60 * 60 * 24));
		
		if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
		if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
		if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
		return 'Just now';
	}

	function getEntityTypeIcon(entityType: string) {
		switch (entityType.toLowerCase()) {
			case 'person': return Users;
			case 'organization': return Database;
			case 'location': return Globe;
			default: return Target;
		}
	}
</script>

<svelte:head>
	<title>Research Dashboard - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
{#if loading}
	<!-- Loading skeleton dashboard -->
	<div class="space-y-8">
		<!-- Header Skeleton -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
			<div class="space-y-2">
				<Skeleton class="h-6 sm:h-8 w-64" />
				<Skeleton class="h-4 w-full sm:w-96" />
			</div>
		</div>
		
		<!-- Statistics Cards Skeleton -->
		<div class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
			{#each Array(6) as _}
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
		
		<!-- Main Content Skeleton -->
		<div class="grid gap-4 grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
			{#each Array(3) as _}
				<Card>
					<CardHeader>
						<Skeleton class="h-6 w-32 mb-2" />
						<Skeleton class="h-4 w-64" />
					</CardHeader>
					<CardContent class="space-y-4">
						{#each Array(5) as _}
							<Skeleton class="h-4 w-full" />
						{/each}
					</CardContent>
				</Card>
			{/each}
		</div>
	</div>
{:else}
	<!-- Research Dashboard -->
	<div class="space-y-8">
		<!-- Header -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
			<div>
				<h2 class="text-2xl sm:text-3xl font-bold tracking-tight">Research Dashboard</h2>
				<p class="text-muted-foreground text-sm sm:text-base">
					Track your investigations, discoveries, and research progress
				</p>
			</div>
			{#if errorMessage}
				<div class="flex items-center gap-2">
					<Button 
						variant="outline" 
						size="sm"
						onclick={() => {
							loading = true;
							retryCount = 0;
							loadDashboardData();
						}}
						disabled={loading}
					>
						<RefreshCw class="mr-2 h-4 w-4 {loading ? 'animate-spin' : ''}" />
						{loading ? 'Refreshing...' : 'Retry'}
					</Button>
				</div>
			{/if}
		</div>
		
		<!-- Error Message -->
		{#if errorMessage && !loading}
			<Card class="border-red-200 bg-red-50">
				<CardContent class="flex items-center gap-2 py-4">
					<AlertCircle class="h-4 w-4 text-red-600 flex-shrink-0" />
					<p class="text-sm text-red-800">{errorMessage}</p>
				</CardContent>
			</Card>
		{/if}
		
		<!-- Researcher Statistics Cards -->
		<div class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">My Projects</CardTitle>
					<Database class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.userStats.myProjectsCount}</div>
					<p class="text-xs text-muted-foreground">
						<Target class="inline h-3 w-3 mr-1" />
						Active investigations
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Pages Discovered</CardTitle>
					<Search class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.userStats.totalPagesScraped.toLocaleString()}</div>
					<p class="text-xs text-muted-foreground">
						<TrendingUp class="inline h-3 w-3 mr-1" />
						Historical content found
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Entities Extracted</CardTitle>
					<Users class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.userStats.entitiesDiscovered.toLocaleString()}</div>
					<p class="text-xs text-muted-foreground">
						<Target class="inline h-3 w-3 mr-1" />
						People, places, orgs
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Saved Searches</CardTitle>
					<Filter class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.userStats.savedSearchesCount}</div>
					<p class="text-xs text-muted-foreground">
						<Search class="inline h-3 w-3 mr-1" />
						Query patterns
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Library Items</CardTitle>
					<BookMarked class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.userStats.libraryItemsCount}</div>
					<p class="text-xs text-muted-foreground">
						<Star class="inline h-3 w-3 mr-1" />
						Starred content
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Content Quality</CardTitle>
					<BarChart3 class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.userStats.averageContentQuality}</div>
					<p class="text-xs text-muted-foreground">
						<TrendingUp class="inline h-3 w-3 mr-1" />
						Average score
					</p>
				</CardContent>
			</Card>
		</div>
		
		<!-- Main Dashboard Grid -->
		<div class="grid gap-4 grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
			<!-- Recent Discoveries -->
			<Card class="lg:col-span-1">
				<CardHeader>
					<CardTitle>Recent Discoveries</CardTitle>
					<CardDescription>
						Your latest research activity and findings
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4 max-h-96 overflow-y-auto">
					{#each dashboardData.recentActivity.slice(0, 8) as activity}
						<div class="flex items-start space-x-3">
							<div class="flex-shrink-0 mt-1">
								<svelte:component 
									this={getActivityIcon(activity.type)} 
									class="h-4 w-4 {getActivityColor(activity.type)}"
								/>
							</div>
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-foreground break-words">
									{formatActivityDescription(activity)}
								</p>
								<p class="text-xs text-muted-foreground">
									{formatTimestamp(activity.timestamp)}
								</p>
							</div>
						</div>
					{:else}
						<p class="text-sm text-muted-foreground italic">No recent activity</p>
					{/each}
				</CardContent>
			</Card>
			
			<!-- Entity Insights -->
			<Card class="lg:col-span-1">
				<CardHeader>
					<CardTitle>Entity Insights</CardTitle>
					<CardDescription>
						Key entities discovered in your research
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="space-y-2">
						<div class="flex items-center justify-between text-sm">
							<span>Average Confidence</span>
							<Badge variant="secondary">
								{Math.round(dashboardData.entityInsights.confidenceStats.average * 100)}%
							</Badge>
						</div>
						<Progress 
							value={dashboardData.entityInsights.confidenceStats.average * 100} 
							class="h-2"
						/>
					</div>
					
					<div class="space-y-2">
						<h4 class="text-sm font-medium">Top Entities</h4>
						<div class="space-y-1 max-h-40 overflow-y-auto">
							{#each dashboardData.entityInsights.topEntities.slice(0, 5) as entity}
								<div class="flex items-center justify-between text-sm">
									<div class="flex items-center space-x-2 min-w-0 flex-1">
										<svelte:component 
											this={getEntityTypeIcon(entity.type)}
											class="h-3 w-3 text-muted-foreground flex-shrink-0"
										/>
										<span class="truncate">{entity.name}</span>
									</div>
									<Badge variant="outline" class="text-xs">
										{entity.frequency}
									</Badge>
								</div>
							{:else}
								<p class="text-sm text-muted-foreground italic">No entities found</p>
							{/each}
						</div>
					</div>
					
					<div class="grid grid-cols-3 gap-2 text-center">
						{#each dashboardData.entityInsights.entityTypesDistribution.slice(0, 3) as typeData}
							<div>
								<div class="text-lg font-bold">{typeData.count}</div>
								<p class="text-xs text-muted-foreground capitalize">{typeData.type}</p>
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>
			
			<!-- Active Research Jobs -->
			<Card class="lg:col-span-2 xl:col-span-1">
				<CardHeader>
					<CardTitle>Active Research</CardTitle>
					<CardDescription>
						Currently running scraping and analysis jobs
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="space-y-4">
						{#each dashboardData.projectProgress.activeJobs as job}
							<div class="space-y-2">
								<div class="flex items-center justify-between">
									<div class="flex items-center space-x-2">
										<div class="flex-shrink-0">
											{#if job.status === 'running'}
												<div class="h-2 w-2 bg-green-500 rounded-full animate-pulse"></div>
											{:else if job.status === 'queued'}
												<div class="h-2 w-2 bg-yellow-500 rounded-full"></div>
											{:else}
												<div class="h-2 w-2 bg-gray-500 rounded-full"></div>
											{/if}
										</div>
										<div>
											<p class="text-sm font-medium">{job.name}</p>
											<p class="text-xs text-muted-foreground">
												{job.completed}/{job.total} pages
											</p>
										</div>
									</div>
									<span class="text-sm font-medium">
										{job.progress}%
									</span>
								</div>
								<Progress value={job.progress} class="h-1.5" />
							</div>
						{:else}
							<div class="text-center py-4">
								<Clock class="h-8 w-8 text-muted-foreground mx-auto mb-2" />
								<p class="text-sm text-muted-foreground">No active jobs</p>
								<p class="text-xs text-muted-foreground">Start a new project to begin research</p>
							</div>
						{/each}
						
						{#if dashboardData.projectProgress.summary.totalActiveJobs > 0}
							<div class="pt-2 border-t text-xs text-muted-foreground text-center">
								{dashboardData.projectProgress.summary.totalActiveJobs} active job{dashboardData.projectProgress.summary.totalActiveJobs !== 1 ? 's' : ''}
								across {dashboardData.projectProgress.summary.activeProjects} project{dashboardData.projectProgress.summary.activeProjects !== 1 ? 's' : ''}
							</div>
						{/if}
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Content Timeline -->
		{#if dashboardData.contentTimeline.dailyTimeline.length > 0}
		<Card>
			<CardHeader>
				<CardTitle>Discovery Timeline</CardTitle>
				<CardDescription>
					Content extraction activity over the last {dashboardData.contentTimeline.timeframeDays} days
				</CardDescription>
			</CardHeader>
			<CardContent>
				<div class="grid gap-4 grid-cols-1 lg:grid-cols-2">
					<div>
						<h4 class="text-sm font-medium mb-3">Most Productive Domains</h4>
						<div class="space-y-2 max-h-40 overflow-y-auto">
							{#each dashboardData.contentTimeline.productiveDomains.slice(0, 5) as domain}
								<div class="flex items-center justify-between">
									<div class="flex items-center space-x-2 min-w-0 flex-1">
										<Globe class="h-3 w-3 text-muted-foreground flex-shrink-0" />
										<span class="text-sm truncate">{domain.domain}</span>
									</div>
									<div class="text-right">
										<div class="text-sm font-medium">{domain.pages_count}</div>
										<div class="text-xs text-muted-foreground">
											Quality: {domain.avg_quality}
										</div>
									</div>
								</div>
							{/each}
						</div>
					</div>
					
					<div>
						<h4 class="text-sm font-medium mb-3">Recent Activity</h4>
						<div class="text-center space-y-1">
							{#if dashboardData.contentTimeline.dailyTimeline.length > 0}
								<div class="text-2xl font-bold">
									{dashboardData.contentTimeline.dailyTimeline
										.reduce((sum, day) => sum + day.count, 0)
										.toLocaleString()}
								</div>
								<p class="text-sm text-muted-foreground">
									Pages discovered in last {dashboardData.contentTimeline.timeframeDays} days
								</p>
							{:else}
								<div class="py-4">
									<Calendar class="h-8 w-8 text-muted-foreground mx-auto mb-2" />
									<p class="text-sm text-muted-foreground">No recent activity</p>
								</div>
							{/if}
						</div>
					</div>
				</div>
			</CardContent>
		</Card>
		{/if}
	</div>
{/if}
</DashboardLayout>