/**
 * API service for incremental scraping functionality
 */

import { getApiUrl, apiFetch } from '$lib/utils';

export interface IncrementalScrapingStatus {
	enabled: boolean;
	last_run_date: string | null;
	next_run_date: string | null;
	coverage_percentage: number;
	total_gaps: number;
	overlap_days: number;
	auto_schedule: boolean;
	max_pages_per_run: number;
	run_frequency_hours: number;
}

export interface CoverageGap {
	domain_id: number;
	domain_name: string;
	gap_start: string;
	gap_end: string;
	days_missing: number;
	priority_score: number;
	estimated_pages: number;
}

export interface IncrementalRun {
	id: number;
	domain_id: number;
	run_type: 'scheduled' | 'manual' | 'gap_fill';
	status: 'pending' | 'running' | 'completed' | 'failed';
	coverage_start: string;
	coverage_end: string;
	pages_discovered: number;
	pages_processed: number;
	gaps_filled: number;
	duration_seconds: number | null;
	created_at: string;
	completed_at: string | null;
	error_message: string | null;
}

export interface IncrementalScrapingConfig {
	enabled: boolean;
	overlap_days: number;
	auto_schedule: boolean;
	max_pages_per_run: number;
	run_frequency_hours: number;
	priority_domains: number[];
	gap_fill_threshold_days: number;
}

export interface TriggerIncrementalScrapingRequest {
	run_type: 'scheduled' | 'manual' | 'gap_fill';
	domain_ids?: number[];
	force_full_coverage?: boolean;
	priority_boost?: boolean;
}

export interface IncrementalScrapingStats {
	total_domains: number;
	enabled_domains: number;
	avg_coverage_percentage: number;
	total_gaps: number;
	last_run_date: string | null;
	next_scheduled_run: string | null;
	active_runs: number;
	completed_runs_24h: number;
	failed_runs_24h: number;
}

export class IncrementalScrapingApiService {
	/**
	 * Get incremental scraping status for a domain
	 */
	async getDomainStatus(domainId: number): Promise<IncrementalScrapingStatus> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/domains/${domainId}/status`),
			{
				method: 'GET',
				headers: { 'Content-Type': 'application/json' }
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to fetch domain status');
		}

		return response.json();
	}

	/**
	 * Update incremental scraping configuration for a domain
	 */
	async updateDomainConfig(
		domainId: number,
		config: Partial<IncrementalScrapingConfig>
	): Promise<IncrementalScrapingStatus> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/domains/${domainId}/config`),
			{
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(config)
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to update domain configuration');
		}

		return response.json();
	}

	/**
	 * Get coverage gaps for a domain
	 */
	async getDomainGaps(domainId: number): Promise<CoverageGap[]> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/domains/${domainId}/gaps`),
			{
				method: 'GET',
				headers: { 'Content-Type': 'application/json' }
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to fetch coverage gaps');
		}

		return response.json();
	}

	/**
	 * Get incremental scraping history for a domain
	 */
	async getDomainHistory(
		domainId: number,
		limit: number = 50,
		offset: number = 0
	): Promise<{
		runs: IncrementalRun[];
		total_count: number;
		has_more: boolean;
	}> {
		const params = new URLSearchParams({
			limit: limit.toString(),
			offset: offset.toString()
		});

		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/domains/${domainId}/history?${params}`),
			{
				method: 'GET',
				headers: { 'Content-Type': 'application/json' }
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to fetch scraping history');
		}

		return response.json();
	}

	/**
	 * Trigger incremental scraping for specific domains or project
	 */
	async triggerIncrementalScraping(
		projectId: number,
		request: TriggerIncrementalScrapingRequest
	): Promise<{ task_id: string; run_ids: number[] }> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/projects/${projectId}/trigger`),
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(request)
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to trigger incremental scraping');
		}

		return response.json();
	}

	/**
	 * Fill specific coverage gaps
	 */
	async fillCoverageGaps(gapIds: number[]): Promise<{ task_id: string; run_ids: number[] }> {
		const response = await apiFetch(
			getApiUrl('/api/v1/incremental-scraping/gaps/fill'),
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ gap_ids: gapIds })
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to fill coverage gaps');
		}

		return response.json();
	}

	/**
	 * Get project-wide incremental scraping statistics
	 */
	async getProjectStats(projectId: number): Promise<IncrementalScrapingStats> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/projects/${projectId}/stats`),
			{
				method: 'GET',
				headers: { 'Content-Type': 'application/json' }
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to fetch project statistics');
		}

		return response.json();
	}

	/**
	 * Cancel a running incremental scraping job
	 */
	async cancelRun(runId: number): Promise<{ success: boolean; message: string }> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/runs/${runId}/cancel`),
			{
				method: 'POST',
				headers: { 'Content-Type': 'application/json' }
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to cancel scraping run');
		}

		return response.json();
	}

	/**
	 * Get details for a specific incremental run
	 */
	async getRunDetails(runId: number): Promise<IncrementalRun> {
		const response = await apiFetch(
			getApiUrl(`/api/v1/incremental-scraping/runs/${runId}`),
			{
				method: 'GET',
				headers: { 'Content-Type': 'application/json' }
			}
		);

		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.detail || 'Failed to fetch run details');
		}

		return response.json();
	}
}

// Export singleton instance
export const incrementalScrapingApi = new IncrementalScrapingApiService();