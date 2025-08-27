// Enhanced types for the scraping system with filtering transparency

export type ScrapePageStatus = 
	| 'pending'
	| 'in_progress'
	| 'completed'
	| 'failed'
	| 'retry'
	| 'skipped'
	// Enhanced filtering statuses
	| 'filtered_duplicate'
	| 'filtered_list_page'
	| 'filtered_low_quality'
	| 'filtered_size'
	| 'filtered_type'
	| 'filtered_custom'
	| 'awaiting_manual_review'
	| 'manually_approved';

export type FilterCategory = 
	| 'content_quality'
	| 'duplicate'
	| 'format'
	| 'size'
	| 'custom'
	| 'domain_rules'
	| 'list_detection';

export type FilterReason = 
	| 'duplicate_content'
	| 'list_page_pattern'
	| 'low_quality_content'
	| 'size_threshold'
	| 'file_type_excluded'
	| 'custom_rule'
	| 'domain_blacklist'
	| 'insufficient_text'
	| 'navigation_pattern'
	| 'error_page_detected';

export interface ScrapePage {
	id: number;
	domain_id: number;
	scrape_session_id: number | null;
	page_id: number | null;
	
	// Basic page information
	original_url: string;
	content_url: string;
	wayback_url?: string;
	unix_timestamp: string;
	mime_type: string;
	status_code: number;
	content_length: number | null;
	digest_hash: string | null;
	
	// Content extraction fields
	title: string | null;
	extracted_text: string | null;
	extracted_content: string | null;
	markdown_content: string | null;
	
	// Processing flags
	is_pdf: boolean;
	is_duplicate: boolean;
	is_list_page: boolean;
	extraction_method: string | null;
	
	// Enhanced filtering system fields
	status: ScrapePageStatus;
	filter_reason: FilterReason | null;
	filter_category: FilterCategory | null;
	filter_details: string | null;
	is_manually_overridden: boolean;
	original_filter_decision: string | null;
	priority_score: number | null;
	can_be_manually_processed: boolean;
	
	// Error tracking
	error_message: string | null;
	error_type: string | null;
	retry_count: number;
	max_retries: number;
	
	// Performance metrics
	fetch_time: number | null;
	extraction_time: number | null;
	total_processing_time: number | null;
	
	// Timestamps
	first_seen_at: string;
	last_attempt_at: string | null;
	completed_at: string | null;
	created_at: string;
	updated_at: string;
	
	// Domain information (populated by joins)
	domain_name?: string;
}

export interface URLGroup {
	url: string;
	domain: string;
	captures: ScrapePage[];
	expanded: boolean;
	selected: boolean;
	
	// Status analysis
	hasFailures: boolean;
	hasPending: boolean;
	hasCompleted: boolean;
	hasFiltered: boolean;
	hasManuallyOverridden: boolean;
	canBeManuallyProcessed: boolean;
	
	// Detailed breakdowns
	filterBreakdown: Record<string, number>;
	statusBreakdown: Record<string, number>;
	priorityDistribution: {
		high: number; // 7-10
		normal: number; // 4-6
		low: number; // 1-3
	};
	
	// Statistics
	totalCaptures: number;
	completedCaptures: number;
	failedCaptures: number;
	filteredCaptures: number;
	overriddenCaptures: number;
}

export interface EnhancedFilters {
	status: ScrapePageStatus[];
	filterCategory: FilterCategory[];
	sessionId: number | null;
	searchQuery: string;
	dateRange: { 
		from: string | null; 
		to: string | null; 
	};
	contentType: string[];
	hasErrors: boolean | null;
	isManuallyOverridden: boolean | null;
	priorityScore: { 
		min: number | null; 
		max: number | null; 
	};
	showOnlyProcessable: boolean;
}

export interface BulkAction {
	action: 'retry' | 'skip' | 'priority' | 'manual_process' | 'override_filter' | 'restore_filter' | 'view_errors';
	pageIds: number[];
	data?: any;
}

export interface PageAction {
	type: 'retry' | 'skip' | 'priority' | 'view' | 'manual_process' | 'override_filter';
	pageId: number;
	data?: any;
}

export interface FilteringAnalysis {
	totalPages: number;
	filteredPages: number;
	processablePages: number;
	overriddenPages: number;
	
	statusDistribution: Record<ScrapePageStatus, number>;
	filterReasonDistribution: Record<FilterReason, number>;
	filterCategoryDistribution: Record<FilterCategory, number>;
	
	priorityDistribution: {
		high: number;
		normal: number;
		low: number;
	};
	
	canBeProcessedCount: number;
	alreadyOverriddenCount: number;
	
	// Recommendations
	recommendations: {
		type: 'manual_review' | 'bulk_override' | 'adjust_filters' | 'priority_boost';
		message: string;
		count: number;
	}[];
}

export interface ScrapeSession {
	id: number;
	name: string | null;
	status: string;
	created_at: string;
	updated_at: string;
	completed_at: string | null;
}

// Event types for component communication
export interface ViewModeChangeEvent {
	mode: 'list' | 'grid';
}

export interface BulkActionsToggleEvent {
	enabled: boolean;
}

export interface ShowAllUrlsToggleEvent {
	showAll: boolean;
}

export interface PageSelectEvent {
	pageId: number;
	selected: boolean;
	shiftKey?: boolean;
}

export interface GroupSelectEvent {
	urlGroup: string;
	selected: boolean;
}

export interface GroupActionEvent {
	action: string;
	urlGroup: string;
	pageIds: number[];
	data?: any;
}

// Filter status badge configuration
export interface StatusBadgeConfig {
	label: string;
	variant: 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning';
	icon: any; // Lucide icon component
	color: string;
	bgColor: string;
	borderColor: string;
}

// API response types
export interface ScrapePageResponse {
	scrape_pages: ScrapePage[];
	status_counts: Record<string, number>;
	total_count: number;
	has_more: boolean;
	next_cursor?: string;
}

export interface ProjectStatsResponse {
	total_pages: number;
	indexed_pages: number;
	failed_pages: number;
	total_domains: number;
	active_sessions: number;
	storage_used: number;
	last_scrape: string | null;
	success_rate: number;
	
	// Enhanced filtering statistics
	filtered_pages: number;
	processable_pages: number;
	overridden_pages: number;
	filter_breakdown: Record<FilterReason, number>;
}

export interface BulkActionResponse {
	success: boolean;
	processed_count: number;
	updated_pages: number[];
	errors: Array<{
		page_id: number;
		error: string;
	}>;
	message: string;
}

// Enhanced WebSocket message types for real-time updates
export interface WebSocketMessage {
	id?: string;
	type: 'heartbeat' | 'task_progress' | 'project_update' | 'user_message' | 'error' | 'reconnect' | 'batch';
	payload?: any;
	timestamp: string;
}

export interface ProjectUpdatePayload {
	project_id: number;
	project_status?: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
	stats?: Partial<ProjectStatsResponse>;
	should_reload_pages?: boolean;
	message?: string;
}

export interface TaskProgressPayload {
	project_id: number;
	task_type: 'scraping' | 'indexing' | 'processing';
	page_updates?: Array<{
		page_id: number;
		status: ScrapePageStatus;
		filter_reason?: FilterReason;
		filter_category?: FilterCategory;
		is_manually_overridden?: boolean;
		priority_score?: number;
		error_message?: string;
	}>;
	status_counts?: Record<string, number>;
	progress_percentage?: number;
	estimated_completion?: string;
}

// Enhanced form validation types
export interface ValidationResult {
	isValid: boolean;
	errors: Record<string, string[]>;
	warnings: Record<string, string[]>;
}

export interface FormState<T> {
	data: T;
	errors: Record<keyof T, string[]>;
	warnings: Record<keyof T, string[]>;
	isSubmitting: boolean;
	isDirty: boolean;
	isValid: boolean;
}

// Enhanced API request/response types
export interface ApiResponse<T = any> {
	success: boolean;
	data?: T;
	error?: string;
	message?: string;
	timestamp: string;
	request_id?: string;
}

export interface PaginatedResponse<T = any> {
	items: T[];
	total_count: number;
	page: number;
	page_size: number;
	has_more: boolean;
	next_cursor?: string;
	prev_cursor?: string;
}

export interface ErrorResponse {
	success: false;
	error: string;
	error_code?: string;
	details?: Record<string, any>;
	timestamp: string;
	request_id?: string;
}

// Enhanced project and domain types
export interface Project {
	id: number;
	name: string;
	description: string | null;
	status: 'active' | 'paused' | 'completed' | 'archived';
	created_at: string;
	updated_at: string;
	owner_id: number;
	is_shared: boolean;
	scraping_config: ScrapingConfig;
	statistics: ProjectStatistics;
}

export interface ScrapingConfig {
	max_pages_per_domain?: number;
	crawl_delay_seconds?: number;
	respect_robots_txt: boolean;
	enable_intelligent_filtering: boolean;
	custom_filter_rules: FilterRule[];
	priority_domains: string[];
	excluded_patterns: string[];
}

export interface FilterRule {
	id: string;
	name: string;
	pattern: string;
	action: 'include' | 'exclude' | 'priority_boost' | 'priority_reduce';
	category: FilterCategory;
	enabled: boolean;
	created_at: string;
}

export interface ProjectStatistics {
	total_domains: number;
	total_urls_discovered: number;
	total_pages_scraped: number;
	success_rate: number;
	average_quality_score: number;
	filtering_effectiveness: number;
	storage_used_bytes: number;
	last_activity: string | null;
}

// User interface and accessibility types
export interface AccessibilityOptions {
	reduceMotion: boolean;
	highContrast: boolean;
	screenReader: boolean;
	keyboardNavigation: boolean;
	fontSize: 'small' | 'medium' | 'large' | 'extra-large';
}

export interface UIPreferences {
	theme: 'light' | 'dark' | 'auto';
	density: 'compact' | 'comfortable' | 'spacious';
	sidebar_collapsed: boolean;
	default_view_mode: 'list' | 'grid' | 'table';
	items_per_page: number;
	show_advanced_filters: boolean;
	enable_keyboard_shortcuts: boolean;
}

// Component prop types for better type safety
export interface EnhancedFilterProps {
	projectId: number;
	sessions: ScrapeSession[];
	initialFilters?: Partial<EnhancedFilters>;
	onFiltersChange: (filters: EnhancedFilters) => void;
	disabled?: boolean;
	showAdvanced?: boolean;
}

export interface BulkActionToolbarProps {
	selectedCount: number;
	selectedPages: ScrapePage[];
	showToolbar: boolean;
	availableActions?: BulkActionType[];
	onBulkAction: (action: BulkActionType, pageIds: number[], data?: any) => void;
	onClearSelection: () => void;
	onSelectAll: () => void;
	onSelectNone: () => void;
}

export interface FilteringStatusBadgeProps {
	status: ScrapePageStatus;
	filterReason?: FilterReason | null;
	filterCategory?: FilterCategory | null;
	isManuallyOverridden?: boolean;
	size?: 'sm' | 'md' | 'lg';
	showIcon?: boolean;
	showTooltip?: boolean;
}

export type BulkActionType = 'retry' | 'skip' | 'priority' | 'manual_process' | 'override_filter' | 'restore_filter' | 'view_errors' | 'delete' | 'archive';

// Incremental Scraping Types
export type IncrementalRunType = 'scheduled' | 'manual' | 'gap_fill';

export type IncrementalRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

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
	id: number;
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
	run_type: IncrementalRunType;
	status: IncrementalRunStatus;
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

export interface TriggerIncrementalScrapingRequest {
	run_type: IncrementalRunType;
	domain_ids?: number[];
	force_full_coverage?: boolean;
	priority_boost?: boolean;
}

// Component prop types for incremental scraping
export interface IncrementalScrapingPanelProps {
	domainId: number;
	projectId: number;
	domainName?: string;
	canControl?: boolean;
}

export interface CoverageVisualizationProps {
	domainId: number;
	projectId: number;
}

export interface IncrementalHistoryProps {
	domainId: number;
}

export interface IncrementalConfigProps {
	domainId: number;
	config: IncrementalScrapingStatus;
	canControl?: boolean;
}