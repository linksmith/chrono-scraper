import { writable, derived, type Writable } from 'svelte/store';
import { getApiUrl } from '$lib/utils';

// Types for analytics data
export interface AnalyticsTimeRange {
	value: '7d' | '30d' | '90d' | '1y' | 'custom';
	label: string;
	days?: number;
}

export interface PatternAnalytics {
	pattern: string;
	category: 'list_page' | 'quality' | 'duplicate' | 'attachment';
	totalMatches: number;
	falsePositiveCount: number;
	falsePositiveRate: number;
	effectivenessScore: number;
	avgConfidence: number;
	lastUsed: string;
	recommendation: 'keep' | 'refine' | 'remove';
	suggestedImprovement?: string;
}

export interface TimeSeriesDataPoint {
	date: string;
	totalPages: number;
	filteredPages: number;
	processedPages: number;
	manualOverrides: number;
	avgProcessingTime: number;
	successRate: number;
}

export interface DomainAnalytics {
	domainId: number;
	domainName: string;
	totalPages: number;
	successRate: number;
	avgProcessingTime: number;
	errorRate: number;
	commonPatterns: string[];
	uniqueChallenges: string[];
	performanceScore: number;
}

export interface FilteringInsights {
	totalPagesAnalyzed: number;
	filteringEffectiveness: number;
	falsePositiveRate: number;
	manualOverrideRate: number;
	topFilterPatterns: PatternAnalytics[];
	confidenceDistribution: { [range: string]: number };
	processingTimeByType: { [type: string]: number };
	qualityScoreTrends: TimeSeriesDataPoint[];
}

export interface ProjectAnalytics {
	projectId: number;
	basicStats: {
		totalPages: number;
		statusCounts: { [status: string]: number };
		filterCategoryCounts: { [category: string]: number };
		priorityDistribution: { [priority: number]: number };
		successRate: number;
		retryRate: number;
		filterRate: number;
		manualReviewPending: number;
		manuallyOverridden: number;
		canBeManuallyProcessed: number;
		pagesLast24h: number;
		pagesLastWeek: number;
		pagesLastMonth: number;
	};
	filterAnalysis: {
		totalFiltered: number;
		filterCategories: { [category: string]: number };
		avgConfidence: number;
		falsePositiveRate: number;
		patternEffectiveness: PatternAnalytics[];
	};
	dailyStats: TimeSeriesDataPoint[];
	domainPerformance: DomainAnalytics[];
	insights: FilteringInsights;
}

export interface AnalyticsState {
	loading: boolean;
	error: string | null;
	timeRange: AnalyticsTimeRange;
	customDateRange?: { start: string; end: string };
	lastUpdated: Date | null;
	autoRefresh: boolean;
	refreshInterval: number; // in seconds
}

export interface ExportOptions {
	format: 'csv' | 'json' | 'pdf';
	sections: string[];
	timeRange: AnalyticsTimeRange;
	includeCharts: boolean;
}

// Default time ranges
export const TIME_RANGES: AnalyticsTimeRange[] = [
	{ value: '7d', label: 'Last 7 days', days: 7 },
	{ value: '30d', label: 'Last 30 days', days: 30 },
	{ value: '90d', label: 'Last 90 days', days: 90 },
	{ value: '1y', label: 'Last year', days: 365 },
	{ value: 'custom', label: 'Custom range' }
];

// Create stores
export const analyticsState: Writable<AnalyticsState> = writable({
	loading: false,
	error: null,
	timeRange: TIME_RANGES[1], // Default to 30 days
	lastUpdated: null,
	autoRefresh: false,
	refreshInterval: 60
});

export const projectAnalytics: Writable<ProjectAnalytics | null> = writable(null);

// Derived stores for chart data transformation
export const statusDistributionChartData = derived(
	projectAnalytics,
	($analytics) => {
		if (!$analytics?.basicStats?.statusCounts) return null;

		const statusCounts = $analytics.basicStats.statusCounts;
		return {
			labels: Object.keys(statusCounts),
			datasets: [
				{
					data: Object.values(statusCounts),
					label: 'Page Status Distribution'
				}
			]
		};
	}
);

export const timeSeriesChartData = derived(
	projectAnalytics,
	($analytics) => {
		if (!$analytics?.dailyStats?.length) return null;

		const dailyStats = $analytics.dailyStats;
		const dates = dailyStats.map((d) => d.date);

		return {
			labels: dates,
			datasets: [
				{
					label: 'Processed Pages',
					data: dailyStats.map((d) => ({ x: d.date, y: d.processedPages })),
					borderColor: 'hsl(var(--primary))',
					backgroundColor: 'hsl(var(--primary) / 0.1)',
					fill: true
				},
				{
					label: 'Filtered Pages',
					data: dailyStats.map((d) => ({ x: d.date, y: d.filteredPages })),
					borderColor: 'hsl(var(--warning))',
					backgroundColor: 'hsl(var(--warning) / 0.1)',
					fill: true
				},
				{
					label: 'Manual Overrides',
					data: dailyStats.map((d) => ({ x: d.date, y: d.manualOverrides })),
					borderColor: 'hsl(var(--destructive))',
					backgroundColor: 'hsl(var(--destructive) / 0.1)',
					fill: false
				}
			]
		};
	}
);

export const domainPerformanceChartData = derived(
	projectAnalytics,
	($analytics) => {
		if (!$analytics?.domainPerformance?.length) return null;

		const domains = $analytics.domainPerformance;
		return {
			labels: domains.map((d) => d.domainName),
			datasets: [
				{
					label: 'Success Rate (%)',
					data: domains.map((d) => d.successRate * 100),
					backgroundColor: domains.map((d) => 
						d.successRate >= 0.9 
							? 'hsl(var(--success))' 
							: d.successRate >= 0.7 
							? 'hsl(var(--warning))' 
							: 'hsl(var(--destructive))'
					)
				}
			]
		};
	}
);

export const patternEffectivenessHeatmapData = derived(
	projectAnalytics,
	($analytics) => {
		if (!$analytics?.filterAnalysis?.patternEffectiveness?.length) return [];

		return $analytics.filterAnalysis.patternEffectiveness.map((pattern) => ({
			x: pattern.category,
			y: pattern.pattern.substring(0, 20) + (pattern.pattern.length > 20 ? '...' : ''),
			v: pattern.effectivenessScore
		}));
	}
);

// Analytics service class
class AnalyticsService {
	private refreshTimeoutId: number | null = null;

	async loadProjectAnalytics(projectId: number, timeRange: AnalyticsTimeRange): Promise<void> {
		analyticsState.update(state => ({ ...state, loading: true, error: null }));

		try {
			// Load basic statistics
			const statsResponse = await fetch(
				getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/analytics/statistics`),
				{ credentials: 'include' }
			);

			if (!statsResponse.ok) {
				throw new Error(`HTTP ${statsResponse.status}: Failed to load analytics statistics`);
			}

			// Load comprehensive analytics
			const analyticsResponse = await fetch(
				getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/analytics/comprehensive`),
				{ credentials: 'include' }
			);

			if (!analyticsResponse.ok) {
				throw new Error(`HTTP ${analyticsResponse.status}: Failed to load analytics data`);
			}

			const [statsData, analyticsData] = await Promise.all([
				statsResponse.json(),
				analyticsResponse.json()
			]);

			// Transform and combine data
			const combinedAnalytics: ProjectAnalytics = {
				projectId,
				basicStats: statsData,
				filterAnalysis: analyticsData.filter_analysis || {
					totalFiltered: 0,
					filterCategories: {},
					avgConfidence: 0,
					falsePositiveRate: 0,
					patternEffectiveness: []
				},
				dailyStats: analyticsData.daily_stats || [],
				domainPerformance: Object.entries(analyticsData.domain_performance || {}).map(([domainId, data]: [string, any]) => ({
					domainId: parseInt(domainId),
					domainName: data.domain_name || `Domain ${domainId}`,
					totalPages: data.total_pages || 0,
					successRate: data.success_rate || 0,
					avgProcessingTime: data.avg_processing_time || 0,
					errorRate: data.error_rate || 0,
					commonPatterns: data.common_patterns || [],
					uniqueChallenges: data.unique_challenges || [],
					performanceScore: data.performance_score || 0
				})),
				insights: {
					totalPagesAnalyzed: statsData.total_pages,
					filteringEffectiveness: (1 - (analyticsData.filter_analysis?.falsePositiveRate || 0)) * 100,
					falsePositiveRate: analyticsData.filter_analysis?.falsePositiveRate || 0,
					manualOverrideRate: statsData.manually_overridden / Math.max(statsData.total_pages, 1),
					topFilterPatterns: analyticsData.filter_analysis?.patternEffectiveness || [],
					confidenceDistribution: {},
					processingTimeByType: {},
					qualityScoreTrends: analyticsData.daily_stats || []
				}
			};

			projectAnalytics.set(combinedAnalytics);
			analyticsState.update(state => ({
				...state,
				loading: false,
				lastUpdated: new Date(),
				timeRange
			}));

		} catch (error) {
			console.error('Failed to load analytics:', error);
			analyticsState.update(state => ({
				...state,
				loading: false,
				error: error instanceof Error ? error.message : 'Failed to load analytics data'
			}));
		}
	}

	async exportAnalytics(projectId: number, options: ExportOptions): Promise<void> {
		try {
			const response = await fetch(
				getApiUrl(`/api/v1/projects/${projectId}/scrape-pages/analytics/export`),
				{
					method: 'POST',
					headers: {
						'Content-Type': 'application/json'
					},
					body: JSON.stringify(options),
					credentials: 'include'
				}
			);

			if (!response.ok) {
				throw new Error('Failed to export analytics data');
			}

			// Handle file download
			const blob = await response.blob();
			const url = window.URL.createObjectURL(blob);
			const a = document.createElement('a');
			a.href = url;
			a.download = `analytics-export-${projectId}-${options.timeRange.value}.${options.format}`;
			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);
			window.URL.revokeObjectURL(url);

		} catch (error) {
			console.error('Failed to export analytics:', error);
			throw error;
		}
	}

	startAutoRefresh(projectId: number): void {
		analyticsState.update(state => ({ ...state, autoRefresh: true }));
		this.scheduleRefresh(projectId);
	}

	stopAutoRefresh(): void {
		analyticsState.update(state => ({ ...state, autoRefresh: false }));
		if (this.refreshTimeoutId) {
			clearTimeout(this.refreshTimeoutId);
			this.refreshTimeoutId = null;
		}
	}

	private scheduleRefresh(projectId: number): void {
		analyticsState.subscribe(state => {
			if (!state.autoRefresh) return;

			if (this.refreshTimeoutId) {
				clearTimeout(this.refreshTimeoutId);
			}

			this.refreshTimeoutId = setTimeout(() => {
				this.loadProjectAnalytics(projectId, state.timeRange);
				this.scheduleRefresh(projectId);
			}, state.refreshInterval * 1000) as any;
		});
	}

	// Utility methods for pattern analysis
	calculatePatternRecommendation(pattern: PatternAnalytics): 'keep' | 'refine' | 'remove' {
		if (pattern.effectivenessScore >= 0.8 && pattern.falsePositiveRate <= 0.1) {
			return 'keep';
		} else if (pattern.effectivenessScore >= 0.6 && pattern.falsePositiveRate <= 0.2) {
			return 'refine';
		} else {
			return 'remove';
		}
	}

	generatePatternImprovement(pattern: PatternAnalytics): string {
		if (pattern.falsePositiveRate > 0.2) {
			return 'Consider making pattern more specific to reduce false positives';
		} else if (pattern.effectivenessScore < 0.6) {
			return 'Pattern may be too restrictive - consider broadening criteria';
		} else if (pattern.avgConfidence < 0.7) {
			return 'Review pattern logic to improve confidence scoring';
		}
		return 'Pattern performing well - monitor for consistency';
	}
}

// Export singleton instance
export const analyticsService = new AnalyticsService();

// Utility functions for components
export function formatAnalyticsNumber(value: number): string {
	if (value >= 1000000) {
		return (value / 1000000).toFixed(1) + 'M';
	} else if (value >= 1000) {
		return (value / 1000).toFixed(1) + 'K';
	}
	return value.toLocaleString();
}

export function formatPercentage(value: number, total: number): string {
	if (total === 0) return '0%';
	return ((value / total) * 100).toFixed(1) + '%';
}

export function formatDuration(seconds: number): string {
	if (seconds >= 3600) {
		return (seconds / 3600).toFixed(1) + 'h';
	} else if (seconds >= 60) {
		return (seconds / 60).toFixed(1) + 'm';
	}
	return seconds.toFixed(1) + 's';
}

export function getStatusColor(status: string): string {
	const statusColors: { [key: string]: string } = {
		completed: 'hsl(var(--success))',
		pending: 'hsl(var(--warning))',
		failed: 'hsl(var(--destructive))',
		filtered: 'hsl(var(--muted-foreground))',
		in_progress: 'hsl(var(--info))',
		retry: 'hsl(var(--accent))',
		skipped: 'hsl(var(--muted))',
		manual_review: 'hsl(var(--secondary))',
		manually_overridden: 'hsl(var(--primary))'
	};
	return statusColors[status] || 'hsl(var(--muted-foreground))';
}