<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Progress } from '$lib/components/ui/progress';
	import { formatNumber, formatDateTime, getApiUrl } from '$lib/utils';
	import { 
		Compass,
		TrendingUp,
		Search,
		BookOpen,
		Globe,
		Lightbulb,
		Target,
		BarChart3,
		RefreshCw,
		ExternalLink,
		Star,
		ChevronRight,
		AlertCircle
	} from 'lucide-svelte';

	export let projectId: number | null = null;

	interface Recommendation {
		page_id: number;
		url: string;
		title: string;
		description: string;
		content_preview: string;
		word_count: number;
		domain_name: string;
		scraped_at: string;
		score: number;
		recommendation_type: string;
	}

	interface TopicTrend {
		topic_id: number;
		label: string;
		keywords: string[];
		document_count: number;
		growth_rate: number;
		trend_direction: string;
	}

	interface ContentCluster {
		cluster_id: number;
		label: string;
		document_count: number;
		top_terms: string[];
		cohesion_score: number;
		sample_page_ids: number[];
	}

	const recommendations = writable<Recommendation[]>([]);
	const topicTrends = writable<TopicTrend[]>([]);
	const contentClusters = writable<ContentCluster[]>([]);
	const loading = writable(false);
	const error = writable<string | null>(null);

	// Discovery suggestions
	const newDomains = writable<any[]>([]);
	const trendingContent = writable<any[]>([]);

	onMount(() => {
		loadDiscoveryData();
	});

	async function loadDiscoveryData() {
		loading.set(true);
		error.set(null);

		try {
			// Load personalized recommendations
			await loadRecommendations();
			
			// Load topic trends
			await loadTopicTrends();
			
			// Load content clusters
			await loadContentClusters();
			
			// Load discovery suggestions
			await loadDiscoverySuggestions();
			
			// Load trending content
			await loadTrendingContent();
			
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to load discovery data');
		} finally {
			loading.set(false);
		}
	}

	async function loadRecommendations() {
		const response = await fetch(getApiUrl(`/api/v1/recommendations/personalized?${projectId ? `project_id=${projectId}&` : ''}limit=10`), {
			credentials: 'include'
		});

		if (response.ok) {
			const data = await response.json();
			recommendations.set(data.recommendations || []);
		}
	}

	async function loadTopicTrends() {
		const response = await fetch(getApiUrl(`/api/v1/topics/trends?${projectId ? `project_id=${projectId}&` : ''}days=30`), {
			credentials: 'include'
		});

		if (response.ok) {
			const data = await response.json();
			topicTrends.set(data.trends || []);
		}
	}

	async function loadContentClusters() {
		const response = await fetch(getApiUrl(`/api/v1/topics/clusters?${projectId ? `project_id=${projectId}` : ''}`), {
			credentials: 'include'
		});

		if (response.ok) {
			const data = await response.json();
			contentClusters.set(data.clusters || []);
		}
	}

	async function loadDiscoverySuggestions() {
		const response = await fetch(getApiUrl(`/api/v1/recommendations/discovery?${projectId ? `project_id=${projectId}` : ''}`), {
			credentials: 'include'
		});

		if (response.ok) {
			const data = await response.json();
			newDomains.set(data.suggestions?.new_domains || []);
		}
	}

	async function loadTrendingContent() {
		const response = await fetch(getApiUrl(`/api/v1/recommendations/trending?${projectId ? `project_id=${projectId}&` : ''}limit=5`), {
			credentials: 'include'
		});

		if (response.ok) {
			const data = await response.json();
			trendingContent.set(data.trending_content || []);
		}
	}

	function getTrendIcon(direction: string) {
		return direction === 'up' ? TrendingUp : BarChart3;
	}

	function getRecommendationTypeColor(type: string): 'default' | 'secondary' | 'success' | 'warning' | 'info' {
		switch (type) {
			case 'content_based': return 'info';
			case 'collaborative': return 'success';
			case 'trending': return 'warning';
			default: return 'secondary';
		}
	}
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-3xl font-bold flex items-center gap-2">
				<Compass class="w-8 h-8" />
				Content Discovery
			</h2>
			<p class="text-muted-foreground">
				Discover new content, trends, and insights
			</p>
		</div>
		
		<Button on:click={loadDiscoveryData} disabled={$loading}>
			<RefreshCw class="w-4 h-4 {$loading ? 'animate-spin' : ''}" />
		</Button>
	</div>

	<!-- Error Display -->
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

	<!-- Quick Stats -->
	<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Recommendations</p>
						<p class="text-2xl font-bold">{$recommendations.length}</p>
					</div>
					<Target class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Active Topics</p>
						<p class="text-2xl font-bold">{$topicTrends.length}</p>
					</div>
					<BookOpen class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">Content Clusters</p>
						<p class="text-2xl font-bold">{$contentClusters.length}</p>
					</div>
					<BarChart3 class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>

		<Card>
			<CardContent class="pt-6">
				<div class="flex items-center justify-between">
					<div>
						<p class="text-sm text-muted-foreground">New Domains</p>
						<p class="text-2xl font-bold">{$newDomains.length}</p>
					</div>
					<Globe class="w-8 h-8 text-muted-foreground" />
				</div>
			</CardContent>
		</Card>
	</div>

	<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
		<!-- Personalized Recommendations -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<Star class="w-5 h-5" />
					Personalized Recommendations
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if $recommendations.length === 0}
					<div class="text-center py-8">
						<Lightbulb class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
						<p class="text-muted-foreground">No recommendations available yet</p>
						<p class="text-sm text-muted-foreground">Interact with content to get personalized suggestions</p>
					</div>
				{:else}
					<div class="space-y-4">
						{#each $recommendations.slice(0, 5) as rec}
							<div class="border rounded-lg p-4 hover:bg-accent/50 transition-colors">
								<div class="flex items-start justify-between">
									<div class="flex-1">
										<h3 class="font-medium line-clamp-2">{rec.title || 'Untitled'}</h3>
										<p class="text-sm text-muted-foreground mt-1 line-clamp-2">
											{rec.description || rec.content_preview}
										</p>
										<div class="flex items-center gap-2 mt-2">
											<Badge variant={getRecommendationTypeColor(rec.recommendation_type)}>
												{rec.recommendation_type.replace('_', ' ')}
											</Badge>
											<span class="text-xs text-muted-foreground">{rec.domain_name}</span>
											<span class="text-xs text-muted-foreground">Score: {(rec.score * 100).toFixed(0)}%</span>
										</div>
									</div>
									<Button variant="ghost" size="sm">
										<ExternalLink class="w-4 h-4" />
									</Button>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>

		<!-- Trending Topics -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<TrendingUp class="w-5 h-5" />
					Trending Topics
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if $topicTrends.length === 0}
					<div class="text-center py-8">
						<BarChart3 class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
						<p class="text-muted-foreground">No topic trends available</p>
					</div>
				{:else}
					<div class="space-y-3">
						{#each $topicTrends.slice(0, 6) as trend}
							<div class="flex items-center justify-between p-3 border rounded-lg">
								<div class="flex-1">
									<h4 class="font-medium">{trend.label}</h4>
									<div class="flex gap-1 mt-1">
										{#each trend.keywords.slice(0, 3) as keyword}
											<Badge variant="outline" class="text-xs">{keyword}</Badge>
										{/each}
									</div>
								</div>
								<div class="text-right">
									<div class="flex items-center gap-1 text-sm">
										<svelte:component this={getTrendIcon(trend.trend_direction)} class="w-3 h-3" />
										{formatNumber(trend.document_count)} docs
									</div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>

		<!-- Content Clusters -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<BarChart3 class="w-5 h-5" />
					Content Clusters
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if $contentClusters.length === 0}
					<div class="text-center py-8">
						<BarChart3 class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
						<p class="text-muted-foreground">No content clusters available</p>
					</div>
				{:else}
					<div class="space-y-3">
						{#each $contentClusters.slice(0, 5) as cluster}
							<div class="border rounded-lg p-3">
								<div class="flex items-center justify-between mb-2">
									<h4 class="font-medium">{cluster.label}</h4>
									<Badge variant="secondary">{formatNumber(cluster.document_count)} docs</Badge>
								</div>
								
								<div class="flex gap-1 mb-2">
									{#each cluster.top_terms.slice(0, 4) as term}
										<Badge variant="outline" class="text-xs">{term}</Badge>
									{/each}
								</div>
								
								<div class="flex items-center gap-2">
									<span class="text-xs text-muted-foreground">Cohesion:</span>
									<Progress value={cluster.cohesion_score * 100} max={100} class="flex-1 h-1" />
									<span class="text-xs text-muted-foreground">{(cluster.cohesion_score * 100).toFixed(0)}%</span>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>

		<!-- New Domain Suggestions -->
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<Globe class="w-5 h-5" />
					Explore New Domains
				</CardTitle>
			</CardHeader>
			<CardContent>
				{#if $newDomains.length === 0}
					<div class="text-center py-8">
						<Globe class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
						<p class="text-muted-foreground">No new domains to explore</p>
					</div>
				{:else}
					<div class="space-y-3">
						{#each $newDomains.slice(0, 5) as domain}
							<div class="flex items-center justify-between p-3 border rounded-lg hover:bg-accent/50 transition-colors">
								<div>
									<h4 class="font-medium">{domain.domain_name}</h4>
									<p class="text-sm text-muted-foreground">{domain.reason}</p>
								</div>
								<div class="text-right">
									<div class="text-sm font-medium">{formatNumber(domain.page_count)} pages</div>
									<Button variant="ghost" size="sm" class="mt-1">
										<ChevronRight class="w-4 h-4" />
									</Button>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>

	<!-- Trending Content -->
	{#if $trendingContent.length > 0}
		<Card>
			<CardHeader>
				<CardTitle class="flex items-center gap-2">
					<TrendingUp class="w-5 h-5" />
					Trending Content
				</CardTitle>
			</CardHeader>
			<CardContent>
				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
					{#each $trendingContent as content}
						<div class="border rounded-lg p-4 hover:bg-accent/50 transition-colors">
							<h3 class="font-medium line-clamp-2 mb-2">{content.title || 'Untitled'}</h3>
							<p class="text-sm text-muted-foreground line-clamp-3 mb-3">
								{content.description || content.content_preview}
							</p>
							<div class="flex items-center justify-between text-xs text-muted-foreground">
								<span>{content.domain_name}</span>
								<span>{content.word_count ? formatNumber(content.word_count) + ' words' : ''}</span>
							</div>
						</div>
					{/each}
				</div>
			</CardContent>
		</Card>
	{/if}
</div>