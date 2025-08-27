<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Progress } from '$lib/components/ui/progress';
	import { TimeSeriesChart, PerformanceBarChart } from '$lib/components/charts';
	import {
		Search,
		Edit3,
		TrendingUp,
		TrendingDown,
		AlertTriangle,
		CheckCircle,
		Target,
		Filter,
		Play,
		Save,
		RotateCcw,
		Lightbulb,
		BarChart3,
		Calendar,
		Settings
	} from 'lucide-svelte';
	import {
		projectAnalytics,
		analyticsService,
		type PatternAnalytics,
		formatAnalyticsNumber,
		formatPercentage
	} from '$lib/stores/analytics';

	export let projectId: number;

	// Local state
	const selectedPattern = writable<PatternAnalytics | null>(null);
	const testPattern = writable('');
	const testResults = writable<any>(null);
	const searchQuery = writable('');
	const categoryFilter = writable<string>('all');
	const sortBy = writable<'effectiveness' | 'matches' | 'confidence' | 'false_positives'>('effectiveness');
	const sortOrder = writable<'asc' | 'desc'>('desc');

	// Pattern categories
	const categories = [
		{ value: 'all', label: 'All Categories' },
		{ value: 'list_page', label: 'List Pages' },
		{ value: 'quality', label: 'Quality Filters' },
		{ value: 'duplicate', label: 'Duplicates' },
		{ value: 'attachment', label: 'Attachments' }
	];

	// Get patterns from analytics store
	$: allPatterns = $projectAnalytics?.filterAnalysis?.patternEffectiveness || [];

	// Filter and sort patterns
	$: filteredPatterns = allPatterns
		.filter(pattern => {
			const matchesSearch = !$searchQuery || 
				pattern.pattern.toLowerCase().includes($searchQuery.toLowerCase());
			const matchesCategory = $categoryFilter === 'all' || 
				pattern.category === $categoryFilter;
			return matchesSearch && matchesCategory;
		})
		.sort((a, b) => {
			const aVal = getPatternValue(a, $sortBy);
			const bVal = getPatternValue(b, $sortBy);
			return $sortOrder === 'asc' ? aVal - bVal : bVal - aVal;
		});

	function getPatternValue(pattern: PatternAnalytics, sortKey: string): number {
		switch (sortKey) {
			case 'effectiveness': return pattern.effectivenessScore;
			case 'matches': return pattern.totalMatches;
			case 'confidence': return pattern.avgConfidence;
			case 'false_positives': return pattern.falsePositiveRate;
			default: return 0;
		}
	}

	function getPatternStatusColor(pattern: PatternAnalytics): string {
		if (pattern.effectivenessScore >= 0.8 && pattern.falsePositiveRate <= 0.1) {
			return 'hsl(var(--success))';
		} else if (pattern.effectivenessScore >= 0.6 && pattern.falsePositiveRate <= 0.2) {
			return 'hsl(var(--warning))';
		} else {
			return 'hsl(var(--destructive))';
		}
	}

	function getRecommendationBadge(recommendation: string) {
		switch (recommendation) {
			case 'keep':
				return { variant: 'default', text: 'Keep', color: 'hsl(var(--success))' };
			case 'refine':
				return { variant: 'secondary', text: 'Refine', color: 'hsl(var(--warning))' };
			case 'remove':
				return { variant: 'destructive', text: 'Remove', color: 'hsl(var(--destructive))' };
			default:
				return { variant: 'outline', text: 'Review', color: 'hsl(var(--muted-foreground))' };
		}
	}

	async function testPatternPreview() {
		if (!$testPattern.trim()) return;

		try {
			// Mock test results - in real implementation, this would call the backend
			const mockResults = {
				matches: Math.floor(Math.random() * 1000) + 100,
				samples: [
					{ url: 'https://example.com/page1', title: 'Sample Page 1', matched: true },
					{ url: 'https://example.com/page2', title: 'Sample Page 2', matched: false },
					{ url: 'https://example.com/page3', title: 'Sample Page 3', matched: true }
				],
				confidence: Math.random() * 0.4 + 0.6,
				estimatedFalsePositives: Math.floor(Math.random() * 50)
			};

			testResults.set(mockResults);
		} catch (error) {
			console.error('Failed to test pattern:', error);
		}
	}

	function editPattern(pattern: PatternAnalytics) {
		selectedPattern.set(pattern);
		testPattern.set(pattern.pattern);
		testResults.set(null);
	}

	function resetEditor() {
		selectedPattern.set(null);
		testPattern.set('');
		testResults.set(null);
	}

	// Chart data for pattern trends
	$: patternTrendsData = filteredPatterns.slice(0, 10).length ? {
		labels: filteredPatterns.slice(0, 10).map(p => p.pattern.substring(0, 20) + '...'),
		datasets: [
			{
				label: 'Effectiveness Score',
				data: filteredPatterns.slice(0, 10).map(p => p.effectivenessScore * 100),
				backgroundColor: filteredPatterns.slice(0, 10).map(p => getPatternStatusColor(p))
			}
		]
	} : null;

	// Historical performance mockup
	$: patternHistoryData = $selectedPattern ? {
		labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
		datasets: [
			{
				label: 'Effectiveness (%)',
				data: [85, 87, 82, ($selectedPattern.effectivenessScore * 100)],
				borderColor: 'hsl(var(--primary))',
				backgroundColor: 'hsl(var(--primary) / 0.1)',
				fill: true
			},
			{
				label: 'False Positives (%)',
				data: [12, 10, 15, ($selectedPattern.falsePositiveRate * 100)],
				borderColor: 'hsl(var(--destructive))',
				backgroundColor: 'hsl(var(--destructive) / 0.1)',
				fill: true
			}
		]
	} : null;
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h2 class="text-2xl font-bold flex items-center gap-2">
				<Target class="w-6 h-6" />
				Pattern Effectiveness Analysis
			</h2>
			<p class="text-muted-foreground">
				Analyze, test, and optimize filtering patterns
			</p>
		</div>
	</div>

	<!-- Controls -->
	<div class="flex flex-wrap items-center gap-4 p-4 border rounded-lg bg-muted/50">
		<div class="flex-1 min-w-64">
			<Input 
				placeholder="Search patterns..." 
				bind:value={$searchQuery}
				class="w-full"
			>
				<Search class="w-4 h-4 mr-2" />
			</Input>
		</div>

		<Select bind:value={$categoryFilter}>
			<SelectTrigger class="w-48">
				<SelectValue placeholder="Filter by category" />
			</SelectTrigger>
			<SelectContent>
				{#each categories as category}
					<SelectItem value={category.value}>{category.label}</SelectItem>
				{/each}
			</SelectContent>
		</Select>

		<Select bind:value={$sortBy}>
			<SelectTrigger class="w-48">
				<SelectValue placeholder="Sort by" />
			</SelectTrigger>
			<SelectContent>
				<SelectItem value="effectiveness">Effectiveness</SelectItem>
				<SelectItem value="matches">Match Count</SelectItem>
				<SelectItem value="confidence">Confidence</SelectItem>
				<SelectItem value="false_positives">False Positives</SelectItem>
			</SelectContent>
		</Select>

		<Button
			variant="outline"
			onclick={() => sortOrder.update(order => order === 'asc' ? 'desc' : 'asc')}
		>
			{$sortOrder === 'asc' ? 'Ascending' : 'Descending'}
		</Button>
	</div>

	<div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
		<!-- Pattern List -->
		<div class="xl:col-span-2">
			<Card>
				<CardHeader>
					<div class="flex items-center justify-between">
						<CardTitle>Pattern Performance ({filteredPatterns.length})</CardTitle>
						{#if patternTrendsData}
							<Button variant="outline" size="sm">
								<BarChart3 class="w-4 h-4 mr-2" />
								View Chart
							</Button>
						{/if}
					</div>
				</CardHeader>
				<CardContent>
					<div class="space-y-3 max-h-96 overflow-y-auto">
						{#each filteredPatterns as pattern}
							<div 
								class="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 cursor-pointer transition-colors"
								onclick={() => editPattern(pattern)}
							>
								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-2 mb-1">
										<Badge variant="outline" class="text-xs">
											{pattern.category}
										</Badge>
										{@const rec = getRecommendationBadge(pattern.recommendation)}
										<Badge variant={rec.variant} class="text-xs">
											{rec.text}
										</Badge>
									</div>
									
									<div class="font-mono text-sm truncate mb-2">
										{pattern.pattern}
									</div>
									
									<div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs text-muted-foreground">
										<div>
											<span class="font-medium">Matches:</span>
											{formatAnalyticsNumber(pattern.totalMatches)}
										</div>
										<div>
											<span class="font-medium">Confidence:</span>
											{(pattern.avgConfidence * 100).toFixed(1)}%
										</div>
										<div>
											<span class="font-medium">False Pos:</span>
											{(pattern.falsePositiveRate * 100).toFixed(1)}%
										</div>
										<div>
											<span class="font-medium">Last Used:</span>
											{new Date(pattern.lastUsed).toLocaleDateString()}
										</div>
									</div>
								</div>
								
								<div class="text-right ml-4">
									<div class="text-lg font-bold" style="color: {getPatternStatusColor(pattern)}">
										{(pattern.effectivenessScore * 100).toFixed(1)}%
									</div>
									<Progress 
										value={pattern.effectivenessScore * 100} 
										max={100} 
										class="w-20 mt-1"
									/>
								</div>
							</div>
						{/each}

						{#if filteredPatterns.length === 0}
							<div class="text-center py-8 text-muted-foreground">
								<Filter class="w-12 h-12 mx-auto mb-4" />
								<p>No patterns match your criteria</p>
								<p class="text-sm">Try adjusting your search or filters</p>
							</div>
						{/if}
					</div>
				</CardContent>
			</Card>
		</div>

		<!-- Pattern Editor/Viewer -->
		<div class="space-y-4">
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Edit3 class="w-4 h-4" />
						Pattern {$selectedPattern ? 'Editor' : 'Tester'}
					</CardTitle>
				</CardHeader>
				<CardContent class="space-y-4">
					{#if $selectedPattern}
						<Alert>
							<Settings class="w-4 h-4" />
							<AlertDescription>
								<strong>Editing:</strong> {$selectedPattern.category} pattern
								<br />
								<strong>Current Score:</strong> {($selectedPattern.effectivenessScore * 100).toFixed(1)}%
							</AlertDescription>
						</Alert>
					{/if}

					<div class="space-y-2">
						<label class="text-sm font-medium">Pattern Expression</label>
						<Textarea 
							bind:value={$testPattern}
							placeholder="Enter a pattern to test..."
							rows="3"
							class="font-mono text-sm"
						/>
					</div>

					<div class="flex gap-2">
						<Button onclick={testPatternPreview} disabled={!$testPattern.trim()}>
							<Play class="w-4 h-4 mr-2" />
							Test Pattern
						</Button>
						
						{#if $selectedPattern}
							<Button variant="outline" onclick={resetEditor}>
								<RotateCcw class="w-4 h-4 mr-2" />
								Reset
							</Button>
						{/if}
					</div>

					{#if $testResults}
						<div class="space-y-3">
							<div class="border-t pt-3">
								<h4 class="font-medium mb-2">Test Results</h4>
								
								<div class="grid grid-cols-2 gap-2 text-sm">
									<div class="flex justify-between">
										<span>Matches:</span>
										<Badge variant="outline">{$testResults.matches}</Badge>
									</div>
									<div class="flex justify-between">
										<span>Confidence:</span>
										<Badge variant="outline">{($testResults.confidence * 100).toFixed(1)}%</Badge>
									</div>
									<div class="flex justify-between">
										<span>Est. False Pos:</span>
										<Badge variant="outline">{$testResults.estimatedFalsePositives}</Badge>
									</div>
								</div>
							</div>

							<div class="border-t pt-3">
								<h5 class="font-medium mb-2">Sample Matches</h5>
								<div class="space-y-1 text-xs">
									{#each $testResults.samples as sample}
										<div class="flex items-center gap-2">
											{#if sample.matched}
												<CheckCircle class="w-3 h-3 text-green-500" />
											{:else}
												<AlertTriangle class="w-3 h-3 text-yellow-500" />
											{/if}
											<span class="truncate">{sample.title}</span>
										</div>
									{/each}
								</div>
							</div>
						</div>
					{/if}
				</CardContent>
			</Card>

			<!-- Pattern Insights -->
			{#if $selectedPattern}
				<Card>
					<CardHeader>
						<CardTitle class="flex items-center gap-2">
							<Lightbulb class="w-4 h-4" />
							Insights & Recommendations
						</CardTitle>
					</CardHeader>
					<CardContent class="space-y-3">
						<div class="text-sm">
							<div class="font-medium mb-1">Current Recommendation:</div>
							{@const rec = getRecommendationBadge($selectedPattern.recommendation)}
							<Badge variant={rec.variant}>{rec.text}</Badge>
						</div>

						{#if $selectedPattern.suggestedImprovement}
							<Alert>
								<Lightbulb class="w-4 h-4" />
								<AlertDescription class="text-sm">
									{$selectedPattern.suggestedImprovement}
								</AlertDescription>
							</Alert>
						{/if}

						<div class="space-y-2 text-sm">
							<div class="flex justify-between">
								<span>Total Matches:</span>
								<span class="font-medium">{formatAnalyticsNumber($selectedPattern.totalMatches)}</span>
							</div>
							<div class="flex justify-between">
								<span>False Positives:</span>
								<span class="font-medium">{formatAnalyticsNumber($selectedPattern.falsePositiveCount)}</span>
							</div>
							<div class="flex justify-between">
								<span>Effectiveness:</span>
								<span class="font-medium">{($selectedPattern.effectivenessScore * 100).toFixed(1)}%</span>
							</div>
							<div class="flex justify-between">
								<span>Avg Confidence:</span>
								<span class="font-medium">{($selectedPattern.avgConfidence * 100).toFixed(1)}%</span>
							</div>
						</div>

						{#if patternHistoryData}
							<div class="border-t pt-3">
								<h5 class="font-medium mb-2">4-Week Trend</h5>
								<TimeSeriesChart 
									data={patternHistoryData} 
									height={200}
								/>
							</div>
						{/if}
					</CardContent>
				</Card>
			{/if}
		</div>
	</div>

	<!-- Pattern Performance Chart -->
	{#if patternTrendsData}
		<Card>
			<CardHeader>
				<CardTitle>Top Pattern Performance Comparison</CardTitle>
			</CardHeader>
			<CardContent>
				<PerformanceBarChart 
					data={patternTrendsData} 
					height={300}
					orientation="horizontal"
				/>
			</CardContent>
		</Card>
	{/if}
</div>