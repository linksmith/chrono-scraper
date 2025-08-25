<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Separator } from '$lib/components/ui/separator';
	import {
		BarChart3,
		TrendingUp,
		TrendingDown,
		Users,
		UserCheck,
		UserX,
		Clock,
		Download,
		RefreshCw,
		Calendar,
		Activity,
		Target,
		AlertTriangle
	} from 'lucide-svelte';
	import { getApiUrl, formatNumber, formatDateTime } from '$lib/utils';

	interface UserAnalytics {
		summary: {
			total_users: number;
			new_users_period: number;
			growth_rate_percent: number;
			approval_stats: {
				pending: number;
				approved: number;
				rejected: number;
				approval_rate_percent: number;
				avg_approval_time_hours: number;
			};
			activity_stats: {
				active_users: number;
				users_with_projects: number;
				avg_login_count: number;
				engagement_rate_percent: number;
			};
		};
		time_series: Array<{
			period: string;
			date: string;
			registrations?: number;
			approvals?: number;
			logins?: number;
		}>;
		breakdowns: {
			approval_status: Record<string, number>;
			user_type: Record<string, number>;
			activity_level: Record<string, number>;
		};
	}

	interface ActivitySummary {
		user_id: number;
		email: string;
		full_name?: string;
		login_count: number;
		last_login?: string;
		projects_created: number;
		pages_scraped: number;
		searches_performed: number;
		approval_status: string;
		is_active: boolean;
		is_verified: boolean;
		created_at: string;
		engagement_score: number;
	}

	// State management
	const analytics = writable<UserAnalytics | null>(null);
	const activitySummaries = writable<ActivitySummary[]>([]);
	const loading = writable(false);
	const error = writable<string | null>(null);

	// Form state
	let dateRangeStart = '';
	let dateRangeEnd = '';
	let groupBy = 'day';
	let selectedMetrics = ['registrations', 'approvals', 'logins'];
	let includeInactive = false;

	// Set default date range (last 30 days)
	onMount(() => {
		const end = new Date();
		const start = new Date();
		start.setDate(start.getDate() - 30);
		
		dateRangeEnd = end.toISOString().split('T')[0];
		dateRangeStart = start.toISOString().split('T')[0];
		
		loadAnalytics();
		loadActivitySummary();
	});

	async function loadAnalytics() {
		try {
			loading.set(true);
			error.set(null);

			const requestBody = {
				date_range_start: dateRangeStart ? new Date(dateRangeStart).toISOString() : undefined,
				date_range_end: dateRangeEnd ? new Date(dateRangeEnd).toISOString() : undefined,
				group_by: groupBy,
				metrics: selectedMetrics,
				include_inactive: includeInactive
			};

			const response = await fetch(getApiUrl('/api/v1/admin/analytics'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify(requestBody)
			});

			if (!response.ok) {
				throw new Error('Failed to load analytics');
			}

			const data: UserAnalytics = await response.json();
			analytics.set(data);

		} catch (err) {
			console.error('Analytics loading error:', err);
			error.set(err instanceof Error ? err.message : 'Unknown error');
		} finally {
			loading.set(false);
		}
	}

	async function loadActivitySummary() {
		try {
			const response = await fetch(getApiUrl('/api/v1/admin/activity-summary?limit=50'), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error('Failed to load activity summary');
			}

			const data: ActivitySummary[] = await response.json();
			activitySummaries.set(data);

		} catch (err) {
			console.error('Activity summary loading error:', err);
		}
	}

	async function exportAnalytics() {
		try {
			const requestBody = {
				format: 'csv',
				date_range_start: dateRangeStart ? new Date(dateRangeStart).toISOString() : undefined,
				date_range_end: dateRangeEnd ? new Date(dateRangeEnd).toISOString() : undefined,
				include_inactive: includeInactive
			};

			const response = await fetch(getApiUrl('/api/v1/admin/export'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify(requestBody)
			});

			if (!response.ok) {
				throw new Error('Export failed');
			}

			// Trigger file download
			const blob = await response.blob();
			const url = window.URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `user_analytics_${new Date().toISOString().split('T')[0]}.csv`;
			document.body.appendChild(a);
			a.click();
			window.URL.revokeObjectURL(url);
			document.body.removeChild(a);

		} catch (err) {
			console.error('Export error:', err);
			error.set(err instanceof Error ? err.message : 'Export failed');
		}
	}

	function getGrowthIcon(rate: number) {
		return rate >= 0 ? TrendingUp : TrendingDown;
	}

	function getGrowthColor(rate: number) {
		return rate >= 0 ? 'text-green-600' : 'text-red-600';
	}

	function getEngagementColor(score: number) {
		if (score >= 80) return 'text-green-600';
		if (score >= 60) return 'text-yellow-600';
		if (score >= 40) return 'text-orange-600';
		return 'text-red-600';
	}

	function getEngagementLabel(score: number) {
		if (score >= 80) return 'High';
		if (score >= 60) return 'Medium';
		if (score >= 40) return 'Low';
		return 'Very Low';
	}
</script>

<div class="space-y-6">
	<!-- Analytics Header -->
	<Card>
		<CardHeader>
			<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
				<div>
					<CardTitle class="flex items-center gap-2">
						<BarChart3 class="h-5 w-5" />
						User Analytics & Reports
					</CardTitle>
					<CardDescription>
						Comprehensive insights into user registration, approval, and activity patterns
					</CardDescription>
				</div>
				<div class="flex items-center gap-2">
					<Button variant="outline" onclick={loadAnalytics} disabled={$loading}>
						<RefreshCw class="h-4 w-4 mr-2" />
						Refresh
					</Button>
					<Button variant="outline" onclick={exportAnalytics}>
						<Download class="h-4 w-4 mr-2" />
						Export Data
					</Button>
				</div>
			</div>
		</CardHeader>

		<CardContent>
			<!-- Analytics Controls -->
			<div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
				<div>
					<Label for="start-date">Start Date</Label>
					<Input
						id="start-date"
						type="date"
						bind:value={dateRangeStart}
						class="mt-1"
					/>
				</div>
				<div>
					<Label for="end-date">End Date</Label>
					<Input
						id="end-date"
						type="date"
						bind:value={dateRangeEnd}
						class="mt-1"
					/>
				</div>
				<div>
					<Label for="group-by">Group By</Label>
					<Select bind:value={groupBy}>
						<SelectTrigger>
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="day">Day</SelectItem>
							<SelectItem value="week">Week</SelectItem>
							<SelectItem value="month">Month</SelectItem>
						</SelectContent>
					</Select>
				</div>
				<div class="flex items-end">
					<Button onclick={loadAnalytics} disabled={$loading} class="w-full">
						{#if $loading}
							Loading...
						{:else}
							Generate Report
						{/if}
					</Button>
				</div>
			</div>

			<!-- Error Display -->
			{#if $error}
				<Alert variant="destructive" class="mb-6">
					<AlertTriangle class="h-4 w-4" />
					<AlertDescription>{$error}</AlertDescription>
				</Alert>
			{/if}
		</CardContent>
	</Card>

	{#if $analytics}
		<!-- Summary Statistics -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
			<!-- Total Users -->
			<Card>
				<CardContent class="p-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm font-medium text-gray-600">Total Users</p>
							<p class="text-2xl font-bold">{formatNumber($analytics.summary.total_users)}</p>
						</div>
						<Users class="h-8 w-8 text-blue-600" />
					</div>
					<div class="mt-2 flex items-center text-sm">
						<svelte:component 
							this={getGrowthIcon($analytics.summary.growth_rate_percent)}
							class="h-4 w-4 mr-1 {getGrowthColor($analytics.summary.growth_rate_percent)}"
						/>
						<span class="{getGrowthColor($analytics.summary.growth_rate_percent)}">
							{Math.abs($analytics.summary.growth_rate_percent).toFixed(1)}%
						</span>
						<span class="text-gray-600 ml-1">vs previous period</span>
					</div>
				</CardContent>
			</Card>

			<!-- New Users This Period -->
			<Card>
				<CardContent class="p-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm font-medium text-gray-600">New Users</p>
							<p class="text-2xl font-bold">{formatNumber($analytics.summary.new_users_period)}</p>
						</div>
						<UserCheck class="h-8 w-8 text-green-600" />
					</div>
					<div class="mt-2">
						<Badge variant="secondary">
							{((($analytics.summary.new_users_period / $analytics.summary.total_users) || 0) * 100).toFixed(1)}% of total
						</Badge>
					</div>
				</CardContent>
			</Card>

			<!-- Approval Rate -->
			<Card>
				<CardContent class="p-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm font-medium text-gray-600">Approval Rate</p>
							<p class="text-2xl font-bold">{$analytics.summary.approval_stats.approval_rate_percent.toFixed(1)}%</p>
						</div>
						<Target class="h-8 w-8 text-purple-600" />
					</div>
					<div class="mt-2 text-sm text-gray-600">
						Avg: {$analytics.summary.approval_stats.avg_approval_time_hours.toFixed(1)}h
					</div>
				</CardContent>
			</Card>

			<!-- Engagement Rate -->
			<Card>
				<CardContent class="p-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm font-medium text-gray-600">Engagement Rate</p>
							<p class="text-2xl font-bold">{$analytics.summary.activity_stats.engagement_rate_percent.toFixed(1)}%</p>
						</div>
						<Activity class="h-8 w-8 text-orange-600" />
					</div>
					<div class="mt-2 text-sm text-gray-600">
						{formatNumber($analytics.summary.activity_stats.active_users)} active users
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Detailed Analytics Tabs -->
		<Card>
			<CardContent class="p-6">
				<Tabs value="overview" class="w-full">
					<TabsList class="grid w-full grid-cols-4">
						<TabsTrigger value="overview">Overview</TabsTrigger>
						<TabsTrigger value="approval">Approval Stats</TabsTrigger>
						<TabsTrigger value="activity">Activity Stats</TabsTrigger>
						<TabsTrigger value="breakdown">Breakdowns</TabsTrigger>
					</TabsList>

					<!-- Overview Tab -->
					<TabsContent value="overview" class="space-y-6">
						<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
							<!-- Quick Stats -->
							<Card>
								<CardHeader>
									<CardTitle class="text-lg">Quick Statistics</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="space-y-4">
										<div class="flex justify-between items-center">
											<span class="text-sm font-medium">Total Registrations</span>
											<span class="text-lg font-bold">{formatNumber($analytics.summary.total_users)}</span>
										</div>
										<Separator />
										<div class="flex justify-between items-center">
											<span class="text-sm font-medium">New This Period</span>
											<span class="text-lg font-bold text-green-600">+{formatNumber($analytics.summary.new_users_period)}</span>
										</div>
										<Separator />
										<div class="flex justify-between items-center">
											<span class="text-sm font-medium">Growth Rate</span>
											<span class="text-lg font-bold {getGrowthColor($analytics.summary.growth_rate_percent)}">
												{$analytics.summary.growth_rate_percent > 0 ? '+' : ''}{$analytics.summary.growth_rate_percent.toFixed(1)}%
											</span>
										</div>
									</div>
								</CardContent>
							</Card>

							<!-- Period Summary -->
							<Card>
								<CardHeader>
									<CardTitle class="text-lg">Period Summary</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="space-y-4">
										<div class="text-sm">
											<strong>Date Range:</strong><br>
											{new Date(dateRangeStart).toLocaleDateString()} - {new Date(dateRangeEnd).toLocaleDateString()}
										</div>
										<Separator />
										<div class="text-sm">
											<strong>Data Points:</strong> {$analytics.time_series.length} {groupBy}s
										</div>
										<Separator />
										<div class="text-sm">
											<strong>Metrics Tracked:</strong><br>
											{selectedMetrics.join(', ')}
										</div>
									</div>
								</CardContent>
							</Card>
						</div>
					</TabsContent>

					<!-- Approval Stats Tab -->
					<TabsContent value="approval" class="space-y-6">
						<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
							<Card>
								<CardContent class="p-6 text-center">
									<UserCheck class="h-12 w-12 text-green-600 mx-auto mb-2" />
									<div class="text-2xl font-bold text-green-600">{formatNumber($analytics.summary.approval_stats.approved)}</div>
									<div class="text-sm text-gray-600">Approved</div>
								</CardContent>
							</Card>
							<Card>
								<CardContent class="p-6 text-center">
									<Clock class="h-12 w-12 text-yellow-600 mx-auto mb-2" />
									<div class="text-2xl font-bold text-yellow-600">{formatNumber($analytics.summary.approval_stats.pending)}</div>
									<div class="text-sm text-gray-600">Pending</div>
								</CardContent>
							</Card>
							<Card>
								<CardContent class="p-6 text-center">
									<UserX class="h-12 w-12 text-red-600 mx-auto mb-2" />
									<div class="text-2xl font-bold text-red-600">{formatNumber($analytics.summary.approval_stats.rejected)}</div>
									<div class="text-sm text-gray-600">Rejected</div>
								</CardContent>
							</Card>
						</div>

						<Card>
							<CardHeader>
								<CardTitle>Approval Metrics</CardTitle>
							</CardHeader>
							<CardContent>
								<div class="space-y-4">
									<div class="flex justify-between items-center">
										<span>Approval Rate</span>
										<Badge variant="default">{$analytics.summary.approval_stats.approval_rate_percent.toFixed(1)}%</Badge>
									</div>
									<div class="flex justify-between items-center">
										<span>Average Approval Time</span>
										<Badge variant="secondary">{$analytics.summary.approval_stats.avg_approval_time_hours.toFixed(1)} hours</Badge>
									</div>
								</div>
							</CardContent>
						</Card>
					</TabsContent>

					<!-- Activity Stats Tab -->
					<TabsContent value="activity" class="space-y-6">
						<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
							<Card>
								<CardHeader>
									<CardTitle>User Activity</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="space-y-4">
										<div class="flex justify-between items-center">
											<span>Active Users</span>
											<span class="font-bold">{formatNumber($analytics.summary.activity_stats.active_users)}</span>
										</div>
										<div class="flex justify-between items-center">
											<span>Users with Projects</span>
											<span class="font-bold">{formatNumber($analytics.summary.activity_stats.users_with_projects)}</span>
										</div>
										<div class="flex justify-between items-center">
											<span>Average Logins</span>
											<span class="font-bold">{$analytics.summary.activity_stats.avg_login_count.toFixed(1)}</span>
										</div>
									</div>
								</CardContent>
							</Card>

							<Card>
								<CardHeader>
									<CardTitle>Engagement</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="text-center">
										<div class="text-4xl font-bold text-blue-600 mb-2">
											{$analytics.summary.activity_stats.engagement_rate_percent.toFixed(1)}%
										</div>
										<div class="text-sm text-gray-600">Overall Engagement Rate</div>
									</div>
								</CardContent>
							</Card>
						</div>
					</TabsContent>

					<!-- Breakdown Tab -->
					<TabsContent value="breakdown" class="space-y-6">
						<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
							<!-- Approval Status Breakdown -->
							<Card>
								<CardHeader>
									<CardTitle class="text-lg">By Approval Status</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="space-y-3">
										{#each Object.entries($analytics.breakdowns.approval_status) as [status, count]}
											<div class="flex justify-between items-center">
												<span class="capitalize">{status}</span>
												<Badge variant="outline">{formatNumber(count)}</Badge>
											</div>
										{/each}
									</div>
								</CardContent>
							</Card>

							<!-- User Type Breakdown -->
							<Card>
								<CardHeader>
									<CardTitle class="text-lg">By User Type</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="space-y-3">
										{#each Object.entries($analytics.breakdowns.user_type) as [type, count]}
											<div class="flex justify-between items-center">
												<span>{type}</span>
												<Badge variant="outline">{formatNumber(count)}</Badge>
											</div>
										{/each}
									</div>
								</CardContent>
							</Card>

							<!-- Activity Level Breakdown -->
							<Card>
								<CardHeader>
									<CardTitle class="text-lg">By Activity Level</CardTitle>
								</CardHeader>
								<CardContent>
									<div class="space-y-3">
										{#each Object.entries($analytics.breakdowns.activity_level) as [level, count]}
											<div class="flex justify-between items-center">
												<span>{level}</span>
												<Badge variant="outline">{formatNumber(count)}</Badge>
											</div>
										{/each}
									</div>
								</CardContent>
							</Card>
						</div>
					</TabsContent>
				</Tabs>
			</CardContent>
		</Card>

		<!-- Top Users by Activity -->
		<Card>
			<CardHeader>
				<CardTitle>Top Users by Engagement</CardTitle>
				<CardDescription>
					Most active and engaged users based on activity metrics
				</CardDescription>
			</CardHeader>
			<CardContent>
				{#if $activitySummaries.length > 0}
					<div class="space-y-4">
						{#each $activitySummaries.slice(0, 10) as summary}
							<div class="flex items-center justify-between p-4 border rounded-lg">
								<div class="flex-1">
									<div class="font-medium">{summary.email}</div>
									{#if summary.full_name}
										<div class="text-sm text-gray-600">{summary.full_name}</div>
									{/if}
									<div class="text-xs text-gray-500 mt-1">
										{summary.projects_created} projects • {summary.searches_performed} searches • {summary.login_count} logins
									</div>
								</div>
								<div class="text-right">
									<div class="text-lg font-bold {getEngagementColor(summary.engagement_score)}">
										{summary.engagement_score.toFixed(0)}
									</div>
									<div class="text-xs text-gray-500">
										{getEngagementLabel(summary.engagement_score)}
									</div>
								</div>
							</div>
						{/each}
					</div>
				{:else}
					<div class="text-center py-8 text-gray-500">
						No activity data available
					</div>
				{/if}
			</CardContent>
		</Card>
	{:else if $loading}
		<div class="text-center py-12">
			<RefreshCw class="h-8 w-8 animate-spin mx-auto mb-4 text-gray-400" />
			<p class="text-gray-600">Loading analytics...</p>
		</div>
	{:else}
		<Card>
			<CardContent class="text-center py-12">
				<BarChart3 class="h-12 w-12 mx-auto mb-4 text-gray-400" />
				<p class="text-gray-600 mb-4">Configure your analytics parameters and generate a report</p>
				<Button onclick={loadAnalytics}>Generate Analytics Report</Button>
			</CardContent>
		</Card>
	{/if}
</div>