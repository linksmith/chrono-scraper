<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Progress } from '$lib/components/ui/progress';
	import { formatNumber, formatDateTime, formatPercentage, getApiUrl } from '$lib/utils';
	import { 
		BarChart3,
		TrendingUp,
		TrendingDown,
		Globe,
		FileText,
		Clock,
		Users,
		Calendar,
		Download,
		RefreshCw,
		AlertCircle,
		CheckCircle
	} from 'lucide-svelte';

	export let projectId: number | null = null;
	export let timeRange: '7d' | '30d' | '90d' | '1y' = '30d';

	interface AnalyticsData {
		overview: {
			total_pages: number;
			total_domains: number;
			scraped_pages: number;
			failed_pages: number;
			success_rate: number;
			avg_word_count: number;
			unique_content_pages: number;
			duplicate_rate: number;
		};
		timeline: Array<{
			date: string;
			pages_scraped: number;
			success_rate: number;
		}>;
		top_domains: Array<{
			domain_name: string;
			total_pages: number;
			scraped_pages: number;
			success_rate: number;
		}>;
		content_types: Array<{
			type: string;
			count: number;
			percentage: number;
		}>;
		languages: Array<{
			language: string;
			count: number;
			percentage: number;
		}>;
		quality_distribution: {
			excellent: number;
			good: number;
			fair: number;
			poor: number;
			very_poor: number;
		};
		recent_activity: Array<{
			date: string;
			type: string;
			description: string;
			count?: number;
		}>;
	}

	const analytics = writable<AnalyticsData | null>(null);
	const loading = writable(false);
	const error = writable<string | null>(null);

	onMount(() => {
		loadAnalytics();
	});

	async function loadAnalytics() {
		loading.set(true);
		error.set(null);

		try {
			const endpoint = projectId 
				? `/api/v1/projects/${projectId}/analytics?days=${getDaysFromRange()}`
				: `/api/v1/monitoring/dashboard`;

			const response = await fetch(getApiUrl(endpoint), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const data = await response.json();
			
			// Transform data to match our interface
			const transformedData: AnalyticsData = {
				overview: {
					total_pages: data.totals?.pages || 0,
					total_domains: data.totals?.domains || 0,
					scraped_pages: data.totals?.pages || 0, // Simplified
					failed_pages: 0, // Would need additional endpoint
					success_rate: 95, // Placeholder
					avg_word_count: 850, // Placeholder
					unique_content_pages: Math.floor((data.totals?.pages || 0) * 0.85),
					duplicate_rate: 15 // Placeholder
				},
				timeline: generateMockTimeline(), // Would come from real endpoint
				top_domains: generateMockDomains(), // Would come from real endpoint
				content_types: [
					{ type: 'text/html', count: data.totals?.pages || 0, percentage: 80 },
					{ type: 'application/pdf', count: Math.floor((data.totals?.pages || 0) * 0.15), percentage: 15 },
					{ type: 'text/plain', count: Math.floor((data.totals?.pages || 0) * 0.05), percentage: 5 }
				],
				languages: [
					{ language: 'en', count: Math.floor((data.totals?.pages || 0) * 0.7), percentage: 70 },
					{ language: 'es', count: Math.floor((data.totals?.pages || 0) * 0.2), percentage: 20 },
					{ language: 'fr', count: Math.floor((data.totals?.pages || 0) * 0.1), percentage: 10 }
				],
				quality_distribution: {
					excellent: Math.floor((data.totals?.pages || 0) * 0.2),
					good: Math.floor((data.totals?.pages || 0) * 0.3),
					fair: Math.floor((data.totals?.pages || 0) * 0.3),
					poor: Math.floor((data.totals?.pages || 0) * 0.15),
					very_poor: Math.floor((data.totals?.pages || 0) * 0.05)
				},
				recent_activity: generateMockActivity() // Would come from real endpoint
			};

			analytics.set(transformedData);
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to load analytics');
		} finally {
			loading.set(false);
		}
	}

	function getDaysFromRange(): number {
		switch (timeRange) {
			case '7d': return 7;
			case '30d': return 30;
			case '90d': return 90;
			case '1y': return 365;
			default: return 30;
		}
	}

	function generateMockTimeline() {
		const days = getDaysFromRange();
		const timeline = [];
		const now = new Date();
		
		for (let i = days - 1; i >= 0; i--) {
			const date = new Date(now);
			date.setDate(date.getDate() - i);
			timeline.push({
				date: date.toISOString().split('T')[0],
				pages_scraped: Math.floor(Math.random() * 100) + 50,
				success_rate: 85 + Math.random() * 10
			});
		}
		
		return timeline;
	}

	function generateMockDomains() {
		return [
			{ domain_name: 'example.com', total_pages: 1500, scraped_pages: 1350, success_rate: 90 },
			{ domain_name: 'test.org', total_pages: 800, scraped_pages: 720, success_rate: 90 },
			{ domain_name: 'demo.net', total_pages: 600, scraped_pages: 480, success_rate: 80 },
		];
	}

	function generateMockActivity() {
		return [
			{ date: new Date().toISOString(), type: 'scraping', description: 'Completed scraping example.com', count: 150 },
			{ date: new Date(Date.now() - 3600000).toISOString(), type: 'indexing', description: 'Indexed new content', count: 89 },
			{ date: new Date(Date.now() - 7200000).toISOString(), type: 'analysis', description: 'Quality analysis completed', count: 234 }
		];
	}

	function exportAnalytics() {
		// Implementation for exporting analytics data
		console.log('Exporting analytics data...');
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-3xl font-bold">Analytics Dashboard</h2>
			<p class="text-muted-foreground">
				{#if projectId}
					Project analytics for the last {timeRange}
				{:else}
					System-wide analytics for the last {timeRange}
				{/if}
			</p>
		</div>
		
		<div class="flex gap-2">
			<!-- Time Range Selector -->
			<div class="flex border rounded-lg">
				{#each ['7d', '30d', '90d', '1y'] as range}
					<button
						class="px-3 py-1 text-sm {timeRange === range ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'} {range === '7d' ? 'rounded-l-md' : range === '1y' ? 'rounded-r-md' : ''}"
						on:click={() => { timeRange = range; loadAnalytics(); }}
					>
						{range.toUpperCase()}
					</button>
				{/each}
			</div>
			
			<Button variant="outline" on:click={loadAnalytics} disabled={$loading}>
				<RefreshCw class="w-4 h-4 {$loading ? 'animate-spin' : ''}" />
			</Button>
			
			<Button variant="outline" on:click={exportAnalytics}>
				<Download class="w-4 h-4" />
			</Button>
		</div>
	</div>

	{#if $error}
		<Card class="border-destructive">
			<CardContent class="pt-6">
				<div class="flex items-center gap-2 text-destructive">
					<AlertCircle class="w-5 h-5" />
					<span>{$error}</span>
				</div>
			</CardContent>
		</Card>
	{/if}

	{#if $analytics}
		<!-- Overview Cards -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Total Pages</p>
							<p class="text-2xl font-bold">{formatNumber($analytics.overview.total_pages)}</p>
						</div>
						<FileText class="w-8 h-8 text-muted-foreground" />
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Domains</p>
							<p class="text-2xl font-bold">{formatNumber($analytics.overview.total_domains)}</p>
						</div>
						<Globe class="w-8 h-8 text-muted-foreground" />
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Success Rate</p>
							<p class="text-2xl font-bold">{$analytics.overview.success_rate.toFixed(1)}%</p>
							<div class="flex items-center text-sm">
								<TrendingUp class="w-3 h-3 text-green-500 mr-1" />
								<span class="text-green-500">+2.3%</span>
							</div>
						</div>
						<CheckCircle class="w-8 h-8 text-green-500" />
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardContent class="pt-6">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Avg. Word Count</p>
							<p class="text-2xl font-bold">{formatNumber($analytics.overview.avg_word_count)}</p>
						</div>
						<BarChart3 class="w-8 h-8 text-muted-foreground" />
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Content Quality Overview -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<Card>
				<CardHeader>
					<CardTitle>Content Quality Distribution</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="space-y-4">
						{#each Object.entries($analytics.quality_distribution) as [grade, count]}
							{@const total = Object.values($analytics.quality_distribution).reduce((a, b) => a + b, 0)}
							{@const percentage = total > 0 ? (count / total) * 100 : 0}
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-2">
									<Badge variant={
										grade === 'excellent' ? 'success' : 
										grade === 'good' ? 'info' : 
										grade === 'fair' ? 'warning' : 
										'destructive'
									}>
										{grade.charAt(0).toUpperCase() + grade.slice(1)}
									</Badge>
									<span class="text-sm">{formatNumber(count)} pages</span>
								</div>
								<div class="flex items-center gap-2 min-w-[100px]">
									<Progress value={count} max={total} class="flex-1" />
									<span class="text-sm text-muted-foreground w-12 text-right">
										{percentage.toFixed(1)}%
									</span>
								</div>
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle>Content Uniqueness</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="space-y-4">
						<div class="flex items-center justify-between">
							<span class="text-sm font-medium">Unique Content</span>
							<span class="text-2xl font-bold text-green-600">
								{formatNumber($analytics.overview.unique_content_pages)}
							</span>
						</div>
						<Progress 
							value={$analytics.overview.unique_content_pages} 
							max={$analytics.overview.total_pages} 
							class="h-2"
						/>
						<div class="flex justify-between text-sm text-muted-foreground">
							<span>Duplicate Rate: {$analytics.overview.duplicate_rate}%</span>
							<span>
								{formatPercentage(
									$analytics.overview.unique_content_pages,
									$analytics.overview.total_pages
								)} unique
							</span>
						</div>
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Top Domains -->
		<Card>
			<CardHeader>
				<CardTitle>Top Performing Domains</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="space-y-4">
					{#each $analytics.top_domains as domain}
						<div class="flex items-center justify-between p-3 border rounded-lg">
							<div class="flex items-center gap-3">
								<Globe class="w-5 h-5 text-muted-foreground" />
								<div>
									<p class="font-medium">{domain.domain_name}</p>
									<p class="text-sm text-muted-foreground">
										{formatNumber(domain.scraped_pages)} / {formatNumber(domain.total_pages)} pages
									</p>
								</div>
							</div>
							<div class="text-right">
								<Badge variant={domain.success_rate >= 90 ? 'success' : domain.success_rate >= 70 ? 'warning' : 'destructive'}>
									{domain.success_rate.toFixed(1)}% success
								</Badge>
							</div>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>

		<!-- Content Types and Languages -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
			<Card>
				<CardHeader>
					<CardTitle>Content Types</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="space-y-3">
						{#each $analytics.content_types as contentType}
							<div class="flex items-center justify-between">
								<span class="text-sm font-mono">{contentType.type}</span>
								<div class="flex items-center gap-2">
									<Progress value={contentType.count} max={$analytics.overview.total_pages} class="w-20" />
									<span class="text-sm text-muted-foreground w-12 text-right">
										{contentType.percentage}%
									</span>
								</div>
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>

			<Card>
				<CardHeader>
					<CardTitle>Languages</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="space-y-3">
						{#each $analytics.languages as language}
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-2">
									<Badge variant="outline" class="font-mono">
										{language.language.toUpperCase()}
									</Badge>
									<span class="text-sm">{formatNumber(language.count)} pages</span>
								</div>
								<div class="flex items-center gap-2">
									<Progress value={language.count} max={$analytics.overview.total_pages} class="w-20" />
									<span class="text-sm text-muted-foreground w-12 text-right">
										{language.percentage}%
									</span>
								</div>
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Recent Activity -->
		<Card>
			<CardHeader>
				<CardTitle>Recent Activity</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="space-y-3">
					{#each $analytics.recent_activity as activity}
						<div class="flex items-center gap-3 p-3 border rounded-lg">
							<div class="w-2 h-2 rounded-full bg-primary"></div>
							<div class="flex-1">
								<p class="text-sm">{activity.description}</p>
								<p class="text-xs text-muted-foreground">
									{formatDateTime(activity.date)}
									{#if activity.count}
										• {formatNumber(activity.count)} items
									{/if}
								</p>
							</div>
							<Badge variant="secondary">{activity.type}</Badge>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>
	{:else if $loading}
		<div class="flex items-center justify-center py-12">
			<RefreshCw class="w-8 h-8 animate-spin mr-2" />
			<span>Loading analytics...</span>
		</div>
	{/if}
</div>