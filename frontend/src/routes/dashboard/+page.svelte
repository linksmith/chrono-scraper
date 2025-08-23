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
		Users, 
		CreditCard, 
		Download,
		TrendingUp,
		Database,
		Search,
		Target,
		Clock,
		Zap,
		AlertCircle,
		CheckCircle2
	} from 'lucide-svelte';
	
	let loading = true;
	
	// Mock data - this would come from your API
	let dashboardData = {
		stats: {
			totalProjects: 12,
			totalPages: 45678,
			totalUsers: 234,
			activeJobs: 3
		},
		recentActivity: [
			{ id: 1, type: 'scrape_completed', project: 'News Analysis', timestamp: '2 minutes ago' },
			{ id: 2, type: 'user_registered', user: 'john.doe@example.com', timestamp: '15 minutes ago' },
			{ id: 3, type: 'extraction_started', project: 'Research Data', timestamp: '1 hour ago' },
			{ id: 4, type: 'plan_upgraded', user: 'jane.smith@example.com', plan: 'Lightning', timestamp: '2 hours ago' }
		],
		planUsage: {
			current: 'Flash',
			pagesUsed: 2847,
			pagesLimit: 10000,
			projectsUsed: 3,
			projectsLimit: 5
		},
		activeJobs: [
			{ id: 1, name: 'News Scraping', progress: 75, status: 'running' },
			{ id: 2, name: 'Entity Extraction', progress: 45, status: 'running' },
			{ id: 3, name: 'Data Processing', progress: 10, status: 'queued' }
		]
	};
	
	onMount(async () => {
		// Load dashboard data from API
		try {
			// This would be actual API calls
			// const response = await fetch('/api/v1/dashboard/stats');
			// dashboardData = await response.json();
			
			// Simulate loading delay
			setTimeout(() => {
				loading = false;
			}, 2000);
		} catch (error) {
			console.error('Failed to load dashboard data:', error);
			loading = false;
		}
	});
	
	function getActivityIcon(type: string) {
		switch (type) {
			case 'scrape_completed': return CheckCircle2;
			case 'user_registered': return Users;
			case 'extraction_started': return Target;
			case 'plan_upgraded': return Zap;
			default: return Activity;
		}
	}
	
	function getActivityColor(type: string) {
		switch (type) {
			case 'scrape_completed': return 'text-green-600';
			case 'user_registered': return 'text-blue-600';
			case 'extraction_started': return 'text-orange-600';
			case 'plan_upgraded': return 'text-purple-600';
			default: return 'text-gray-600';
		}
	}
</script>

<svelte:head>
	<title>Dashboard - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
{#if loading}
	<!-- Loading skeleton dashboard -->
	<div class="space-y-8">
		<!-- Header Skeleton -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
			<div class="space-y-2">
				<Skeleton class="h-6 sm:h-8 w-48" />
				<Skeleton class="h-4 w-full sm:w-80" />
			</div>
			<Skeleton class="h-10 w-full sm:w-32" />
		</div>
		
		<!-- Statistics Cards Skeleton -->
		<div class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
			{#each Array(4) as _}
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
		
		<!-- Main Content Grid Skeleton -->
		<div class="grid gap-4 grid-cols-1 lg:grid-cols-3 xl:grid-cols-7">
			<!-- Recent Activity Skeleton -->
			<Card class="lg:col-span-2 xl:col-span-4">
				<CardHeader>
					<Skeleton class="h-6 w-32 mb-2" />
					<Skeleton class="h-4 w-64" />
				</CardHeader>
				<CardContent class="space-y-4">
					{#each Array(4) as _}
						<div class="flex items-center space-x-4">
							<Skeleton class="h-4 w-4 flex-shrink-0" />
							<div class="flex-1 space-y-2">
								<Skeleton class="h-4 w-full" />
								<Skeleton class="h-3 w-24" />
							</div>
						</div>
					{/each}
				</CardContent>
			</Card>
			
			<!-- Plan Usage Skeleton -->
			<Card class="lg:col-span-1 xl:col-span-3">
				<CardHeader>
					<div class="flex items-center">
						<Skeleton class="h-6 w-24 mr-2" />
						<Skeleton class="h-5 w-12" />
					</div>
					<Skeleton class="h-4 w-32 mt-2" />
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="space-y-2">
						<div class="flex items-center justify-between">
							<Skeleton class="h-4 w-24" />
							<Skeleton class="h-4 w-20" />
						</div>
						<Skeleton class="h-2 w-full" />
					</div>
					
					<div class="space-y-2">
						<div class="flex items-center justify-between">
							<Skeleton class="h-4 w-16" />
							<Skeleton class="h-4 w-12" />
						</div>
						<Skeleton class="h-2 w-full" />
					</div>
					
					<Skeleton class="h-10 w-full mt-4" />
				</CardContent>
			</Card>
		</div>
		
		<!-- Active Jobs Skeleton -->
		<Card>
			<CardHeader>
				<Skeleton class="h-6 w-28 mb-2" />
				<Skeleton class="h-4 w-80" />
			</CardHeader>
			<CardContent>
				<div class="space-y-4">
					{#each Array(3) as _}
						<div class="flex items-center justify-between space-x-4">
							<div class="flex items-center space-x-3">
								<Skeleton class="h-2 w-2 rounded-full flex-shrink-0" />
								<div class="space-y-1">
									<Skeleton class="h-4 w-32" />
									<Skeleton class="h-3 w-16" />
								</div>
							</div>
							<div class="flex items-center space-x-2 min-w-0 flex-1">
								<Skeleton class="h-2 flex-1" />
								<Skeleton class="h-4 w-12" />
							</div>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>
	</div>
{:else}
	<!-- Actual dashboard content -->
	<div class="space-y-8">
		<!-- Header -->
		<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
			<div>
				<h2 class="text-2xl sm:text-3xl font-bold tracking-tight">Dashboard</h2>
				<p class="text-muted-foreground text-sm sm:text-base">
					Welcome back! Here's what's happening with your projects.
				</p>
			</div>
			<div class="flex items-center space-x-2">
				<Button class="w-full sm:w-auto">
					<Download class="mr-2 h-4 w-4" />
					Export Report
				</Button>
			</div>
		</div>
		
		<!-- Statistics Cards -->
		<div class="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Total Projects</CardTitle>
					<Database class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.stats.totalProjects}</div>
					<p class="text-xs text-muted-foreground">
						<TrendingUp class="inline h-3 w-3 mr-1" />
						+2 from last month
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Pages Scraped</CardTitle>
					<Search class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.stats.totalPages.toLocaleString()}</div>
					<p class="text-xs text-muted-foreground">
						<TrendingUp class="inline h-3 w-3 mr-1" />
						+20.1% from last month
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Active Users</CardTitle>
					<Users class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.stats.totalUsers}</div>
					<p class="text-xs text-muted-foreground">
						<TrendingUp class="inline h-3 w-3 mr-1" />
						+12 new this week
					</p>
				</CardContent>
			</Card>
			
			<Card>
				<CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
					<CardTitle class="text-sm font-medium">Running Jobs</CardTitle>
					<Activity class="h-4 w-4 text-muted-foreground" />
				</CardHeader>
				<CardContent>
					<div class="text-2xl font-bold">{dashboardData.stats.activeJobs}</div>
					<p class="text-xs text-muted-foreground">
						<Clock class="inline h-3 w-3 mr-1" />
						2 queued
					</p>
				</CardContent>
			</Card>
		</div>
		
		<!-- Main Content Grid -->
		<div class="grid gap-4 grid-cols-1 lg:grid-cols-3 xl:grid-cols-7">
			<!-- Recent Activity -->
			<Card class="lg:col-span-2 xl:col-span-4">
				<CardHeader>
					<CardTitle>Recent Activity</CardTitle>
					<CardDescription>
						Latest updates from your projects and system
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					{#each dashboardData.recentActivity as activity}
						<div class="flex items-start sm:items-center space-x-4">
							<div class="flex-shrink-0 mt-1 sm:mt-0">
								<svelte:component 
									this={getActivityIcon(activity.type)} 
									class="h-4 w-4 {getActivityColor(activity.type)}"
								/>
							</div>
							<div class="flex-1 min-w-0">
								<p class="text-sm font-medium text-foreground break-words">
									{#if activity.type === 'scrape_completed'}
										Scraping completed for "{activity.project}"
									{:else if activity.type === 'user_registered'}
										New user registered: {activity.user}
									{:else if activity.type === 'extraction_started'}
										Entity extraction started for "{activity.project}"
									{:else if activity.type === 'plan_upgraded'}
										{activity.user} upgraded to {activity.plan} plan
									{/if}
								</p>
								<p class="text-xs sm:text-sm text-muted-foreground">
									{activity.timestamp}
								</p>
							</div>
						</div>
					{/each}
				</CardContent>
			</Card>
			
			<!-- Plan Usage -->
			<Card class="lg:col-span-1 xl:col-span-3">
				<CardHeader>
					<CardTitle class="flex flex-col sm:flex-row sm:items-center gap-2">
						<span>Current Plan</span>
						<Badge variant="secondary">
							{dashboardData.planUsage.current}
						</Badge>
					</CardTitle>
					<CardDescription>
						Your usage and limits
					</CardDescription>
				</CardHeader>
				<CardContent class="space-y-4">
					<div class="space-y-2">
						<div class="flex items-center justify-between text-sm">
							<span>Pages this month</span>
							<span class="font-medium text-xs sm:text-sm">
								{dashboardData.planUsage.pagesUsed.toLocaleString()} / {dashboardData.planUsage.pagesLimit.toLocaleString()}
							</span>
						</div>
						<Progress 
							value={(dashboardData.planUsage.pagesUsed / dashboardData.planUsage.pagesLimit) * 100} 
							class="h-2"
						/>
					</div>
					
					<div class="space-y-2">
						<div class="flex items-center justify-between text-sm">
							<span>Projects</span>
							<span class="font-medium text-xs sm:text-sm">
								{dashboardData.planUsage.projectsUsed} / {dashboardData.planUsage.projectsLimit}
							</span>
						</div>
						<Progress 
							value={(dashboardData.planUsage.projectsUsed / dashboardData.planUsage.projectsLimit) * 100} 
							class="h-2"
						/>
					</div>
					
					<Button class="w-full mt-4" variant="outline">
						<Zap class="mr-2 h-4 w-4" />
						Upgrade Plan
					</Button>
				</CardContent>
			</Card>
		</div>
		
		<!-- Active Jobs -->
		<Card>
			<CardHeader>
				<CardTitle>Active Jobs</CardTitle>
				<CardDescription>
					Currently running and queued scraping jobs
				</CardDescription>
			</CardHeader>
			<CardContent>
				<div class="space-y-4">
					{#each dashboardData.activeJobs as job}
						<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-2 sm:space-y-0 sm:space-x-4">
							<div class="flex items-center space-x-3">
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
										{job.status === 'running' ? 'Running' : 'Queued'}
									</p>
								</div>
							</div>
							<div class="flex items-center space-x-2 min-w-0 flex-1">
								<Progress value={job.progress} class="flex-1" />
								<span class="text-sm font-medium min-w-[3rem] text-right">
									{job.progress}%
								</span>
							</div>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>
	</div>
{/if}
</DashboardLayout>