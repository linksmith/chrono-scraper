<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth';
	import { websocketStore, isConnected } from '$lib/stores/websocket';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Separator } from '$lib/components/ui/separator';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Skeleton } from '$lib/components/ui/skeleton';
	
	// Custom components
	import EnhancedURLProgressFilters from '$lib/components/project/EnhancedURLProgressFilters.svelte';
	import EnhancedStatusBadge from '$lib/components/filtering/EnhancedStatusBadge.svelte';
	import FilteringTransparencyPanel from '$lib/components/filtering/FilteringTransparencyPanel.svelte';
	import BulkOperationCenter from '$lib/components/filtering/BulkOperationCenter.svelte';
	import LoadingOverlay from '$lib/components/loading/LoadingOverlay.svelte';
	import ProgressBar from '$lib/components/loading/ProgressBar.svelte';
	
	// Icons
	import {
		Search,
		Filter,
		Eye,
		EyeOff,
		RefreshCw,
		Settings,
		Download,
		Upload,
		AlertCircle,
		CheckCircle,
		Clock,
		Activity,
		ChevronLeft,
		ChevronRight,
		ChevronsLeft,
		ChevronsRight,
		Info,
		Zap,
		Shield,
		AlertTriangle,
		Database,
		Users,
		Calendar,
		FileText,
		MoreHorizontal,
		ChevronDown,
		ChevronUp
	} from 'lucide-svelte';
	
	// Types
	import type {
		ScrapePage,
		ScrapeSession,
		EnhancedFilters,
		FilteringAnalysis,
		BulkActionType,
		ScrapePageStatus,
		TaskProgressPayload,
		ProjectUpdatePayload
	} from '$lib/types/scraping';
	
	// Get project ID from route params
	$: projectId = parseInt($page.params.id);
	
	// Component state
	let loading = false;
	let error: string | null = null;
	let pages: ScrapePage[] = [];
	let totalCount = 0;
	let hasMore = false;
	let nextCursor: string | null = null;
	
	// Pagination state
	let currentPage = 1;
	let pageSize = 50;
	let totalPages = 1;
	
	// Filter state
	let activeFilters: EnhancedFilters = {
		status: [],
		filterCategory: [],
		sessionId: null,
		searchQuery: '',
		dateRange: { from: null, to: null },
		contentType: [],
		hasErrors: null,
		isManuallyOverridden: null,
		priorityScore: { min: null, max: null },
		showOnlyProcessable: false
	};
	
	// Sessions data for filter
	let sessions: ScrapeSession[] = [];
	
	// Selection state
	let selectedPageIds = new Set<number>();
	let selectAllMode = false;
	let bulkMode = false;
	
	// View state
	let viewMode: 'list' | 'grid' | 'table' = 'table';
	let showFilters = true;
	let showBulkCenter = false;
	let expandedDetails = new Set<number>();
	
	// Statistics
	let statistics: FilteringAnalysis | null = null;
	let statusCounts: Record<string, number> = {};
	
	// WebSocket handling
	let webSocketUnsubscribe: (() => void) | null = null;
	
	// Real-time updates
	let isLoadingRealtime = false;
	let lastUpdateTime: string | null = null;
	
	onMount(async () => {
		if (!$auth.isAuthenticated) {
			goto('/auth/login');
			return;
		}
		
		await loadInitialData();
		setupWebSocketListeners();
	});
	
	onDestroy(() => {
		if (webSocketUnsubscribe) {
			webSocketUnsubscribe();
		}
	});
	
	async function loadInitialData() {
		loading = true;
		error = null;
		
		try {
			await Promise.all([
				loadPages(),
				loadSessions(),
				loadStatistics()
			]);
		} catch (err) {
			console.error('Failed to load initial data:', err);
			error = 'Failed to load data. Please try again.';
		} finally {
			loading = false;
		}
	}
	
	async function loadPages(resetPagination = true) {
		if (resetPagination) {
			currentPage = 1;
			nextCursor = null;
		}
		
		const params = new URLSearchParams({
			page: currentPage.toString(),
			limit: pageSize.toString(),
			...(activeFilters.sessionId && { scrape_session_id: activeFilters.sessionId.toString() }),
			...(activeFilters.searchQuery && { search_query: activeFilters.searchQuery }),
			...(activeFilters.hasErrors !== null && { has_errors: activeFilters.hasErrors.toString() }),
			...(activeFilters.isManuallyOverridden !== null && { is_manually_overridden: activeFilters.isManuallyOverridden.toString() }),
			...(activeFilters.showOnlyProcessable && { can_be_manually_processed: 'true' }),
			...(activeFilters.priorityScore.min !== null && { priority_min: activeFilters.priorityScore.min.toString() }),
			...(activeFilters.priorityScore.max !== null && { priority_max: activeFilters.priorityScore.max.toString() }),
			...(activeFilters.dateRange.from && { created_after: activeFilters.dateRange.from }),
			...(activeFilters.dateRange.to && { created_before: activeFilters.dateRange.to })
		});
		
		// Add status filters
		activeFilters.status.forEach(status => {
			params.append('status', status);
		});
		
		// Add filter category filters
		activeFilters.filterCategory.forEach(category => {
			params.append('filter_category', category);
		});
		
		// Add content type filters
		activeFilters.contentType.forEach(type => {
			params.append('content_type', type);
		});
		
		const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages?${params}`, {
			headers: {
				'Authorization': `Bearer ${$auth.token}`,
				'Content-Type': 'application/json'
			}
		});
		
		if (!response.ok) {
			const errorData = await response.json().catch(() => ({}));
			throw new Error(errorData.error || `HTTP ${response.status}`);
		}
		
		const data = await response.json();
		
		if (resetPagination) {
			pages = data.scrape_pages || [];
		} else {
			pages = [...pages, ...(data.scrape_pages || [])];
		}
		
		totalCount = data.total_count || 0;
		hasMore = data.has_more || false;
		nextCursor = data.next_cursor || null;
		totalPages = Math.ceil(totalCount / pageSize);
		statusCounts = data.status_counts || {};
		
		lastUpdateTime = new Date().toISOString();
	}
	
	async function loadSessions() {
		try {
			const response = await fetch(`/api/v1/projects/${projectId}/sessions`, {
				headers: {
					'Authorization': `Bearer ${$auth.token}`
				}
			});
			
			if (response.ok) {
				const data = await response.json();
				sessions = data.sessions || [];
			}
		} catch (err) {
			console.warn('Failed to load sessions:', err);
		}
	}
	
	async function loadStatistics() {
		try {
			const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages/statistics`, {
				headers: {
					'Authorization': `Bearer ${$auth.token}`
				}
			});
			
			if (response.ok) {
				statistics = await response.json();
			}
		} catch (err) {
			console.warn('Failed to load statistics:', err);
		}
	}
	
	function setupWebSocketListeners() {
		if (!$isConnected) {
			// Connect WebSocket if not already connected
			const wsUrl = `ws://localhost:8000/api/v1/ws/project/${projectId}/user/${$auth.user?.id}`;
			websocketStore.connect(wsUrl, '');
		}
		
		// Listen for WebSocket messages
		const handleWebSocketMessage = (event: CustomEvent) => {
			const message = event.detail;
			
			if (message.type === 'task_progress') {
				handleTaskProgressUpdate(message.payload);
			} else if (message.type === 'project_update') {
				handleProjectUpdate(message.payload);
			}
		};
		
		if (typeof window !== 'undefined') {
			window.addEventListener('websocket-message', handleWebSocketMessage as EventListener);
			
			webSocketUnsubscribe = () => {
				window.removeEventListener('websocket-message', handleWebSocketMessage as EventListener);
			};
		}
	}
	
	function handleTaskProgressUpdate(payload: TaskProgressPayload) {
		if (payload.project_id !== projectId) return;
		
		// Update page statuses in real-time
		if (payload.page_updates && payload.page_updates.length > 0) {
			pages = pages.map(page => {
				const update = payload.page_updates?.find(u => u.page_id === page.id);
				if (update) {
					return {
						...page,
						status: update.status,
						filter_reason: update.filter_reason || page.filter_reason,
						filter_category: update.filter_category || page.filter_category,
						is_manually_overridden: update.is_manually_overridden ?? page.is_manually_overridden,
						priority_score: update.priority_score ?? page.priority_score,
						error_message: update.error_message || page.error_message
					};
				}
				return page;
			});
		}
		
		// Update status counts
		if (payload.status_counts) {
			statusCounts = { ...statusCounts, ...payload.status_counts };
		}
		
		lastUpdateTime = new Date().toISOString();
	}
	
	function handleProjectUpdate(payload: ProjectUpdatePayload) {
		if (payload.project_id !== projectId) return;
		
		if (payload.should_reload_pages) {
			// Debounce page reloads
			setTimeout(() => {
				loadPages();
			}, 1000);
		}
		
		if (payload.stats) {
			// Update statistics if provided
			loadStatistics();
		}
	}
	
	// Filter handling
	function handleFiltersChange(event: CustomEvent<EnhancedFilters>) {
		activeFilters = event.detail;
		loadPages(true); // Reset pagination when filters change
	}
	
	// Selection handling
	function handlePageSelect(pageId: number, selected: boolean, shiftKey = false) {
		if (shiftKey && selectedPageIds.size > 0) {
			// Range selection
			const pageIds = pages.map(p => p.id);
			const currentIndex = pageIds.indexOf(pageId);
			const lastSelectedId = Array.from(selectedPageIds).pop();
			const lastIndex = lastSelectedId ? pageIds.indexOf(lastSelectedId) : -1;
			
			if (currentIndex !== -1 && lastIndex !== -1) {
				const start = Math.min(currentIndex, lastIndex);
				const end = Math.max(currentIndex, lastIndex);
				
				for (let i = start; i <= end; i++) {
					if (selected) {
						selectedPageIds.add(pageIds[i]);
					} else {
						selectedPageIds.delete(pageIds[i]);
					}
				}
			}
		} else {
			// Single selection
			if (selected) {
				selectedPageIds.add(pageId);
			} else {
				selectedPageIds.delete(pageId);
			}
		}
		
		selectedPageIds = new Set(selectedPageIds);
		selectAllMode = selectedPageIds.size === pages.length;
	}
	
	function handleSelectAll() {
		if (selectAllMode) {
			selectedPageIds.clear();
		} else {
			pages.forEach(page => selectedPageIds.add(page.id));
		}
		selectedPageIds = new Set(selectedPageIds);
		selectAllMode = !selectAllMode;
	}
	
	function clearSelection() {
		selectedPageIds.clear();
		selectedPageIds = new Set();
		selectAllMode = false;
	}
	
	// Bulk operations
	async function handleBulkAction(action: BulkActionType, pageIds: number[], data?: any) {
		if (pageIds.length === 0) return;
		
		isLoadingRealtime = true;
		
		try {
			const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages/bulk/${action}`, {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${$auth.token}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					page_ids: pageIds,
					...data
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.error || `HTTP ${response.status}`);
			}
			
			const result = await response.json();
			
			// Clear selection after successful bulk action
			clearSelection();
			
			// Reload pages to show updates
			await loadPages();
			
			// Show success message (could use toast notification)
			console.log(`Bulk ${action} completed:`, result);
			
		} catch (err) {
			console.error(`Bulk ${action} failed:`, err);
			error = `Bulk operation failed: ${err instanceof Error ? err.message : 'Unknown error'}`;
		} finally {
			isLoadingRealtime = false;
		}
	}
	
	// Pagination
	function goToPage(page: number) {
		if (page >= 1 && page <= totalPages) {
			currentPage = page;
			loadPages(false);
		}
	}
	
	function nextPage() {
		if (hasMore) goToPage(currentPage + 1);
	}
	
	function prevPage() {
		if (currentPage > 1) goToPage(currentPage - 1);
	}
	
	// Utility functions
	function formatDate(dateString: string) {
		return new Date(dateString).toLocaleString();
	}
	
	function formatBytes(bytes: number | null) {
		if (bytes === null) return 'N/A';
		const units = ['B', 'KB', 'MB', 'GB'];
		let size = bytes;
		let unitIndex = 0;
		
		while (size >= 1024 && unitIndex < units.length - 1) {
			size /= 1024;
			unitIndex++;
		}
		
		return `${size.toFixed(1)} ${units[unitIndex]}`;
	}
	
	function getStatusColor(status: ScrapePageStatus) {
		const colors = {
			pending: 'text-yellow-600',
			in_progress: 'text-blue-600',
			completed: 'text-green-600',
			failed: 'text-red-600',
			skipped: 'text-gray-600',
			filtered_duplicate: 'text-orange-600',
			filtered_list_page: 'text-purple-600',
			filtered_low_quality: 'text-amber-600',
			filtered_size: 'text-indigo-600',
			filtered_type: 'text-gray-600',
			filtered_custom: 'text-teal-600',
			awaiting_manual_review: 'text-amber-600',
			manually_approved: 'text-green-600'
		};
		return colors[status] || 'text-gray-600';
	}
	
	function toggleDetailExpansion(pageId: number) {
		if (expandedDetails.has(pageId)) {
			expandedDetails.delete(pageId);
		} else {
			expandedDetails.add(pageId);
		}
		expandedDetails = new Set(expandedDetails);
	}
	
	// Computed values
	$: selectedCount = selectedPageIds.size;
	$: canShowBulkOperations = selectedCount > 0;
	$: filteredPages = pages.filter(page => 
		activeFilters.status.length === 0 || 
		activeFilters.status.includes(page.status)
	);
</script>

<svelte:head>
	<title>Scrape Pages - Project {projectId} - Chrono Scraper</title>
</svelte:head>

{#if loading && pages.length === 0}
	<LoadingOverlay message="Loading scrape pages..." />
{/if}

<div class="container mx-auto px-4 py-6 space-y-6">
	<!-- Header Section -->
	<div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
		<div>
			<h1 class="text-2xl font-bold text-gray-900">
				Scrape Pages Management
			</h1>
			<p class="text-sm text-gray-600">
				Comprehensive filtering and management of discovered pages
				{#if lastUpdateTime}
					<span class="ml-2 text-xs text-gray-500">
						Last updated: {formatDate(lastUpdateTime)}
					</span>
				{/if}
			</p>
		</div>
		
		<div class="flex items-center gap-2">
			<!-- View Mode Toggle -->
			<div class="flex items-center border border-border rounded-md">
				<Button
					variant={viewMode === 'table' ? 'default' : 'ghost'}
					size="sm"
					onclick={() => viewMode = 'table'}
					class="h-8 px-3 rounded-r-none"
				>
					<Database class="h-4 w-4" />
				</Button>
				<Button
					variant={viewMode === 'list' ? 'default' : 'ghost'}
					size="sm"
					onclick={() => viewMode = 'list'}
					class="h-8 px-3 rounded-none border-x-0"
				>
					<FileText class="h-4 w-4" />
				</Button>
				<Button
					variant={viewMode === 'grid' ? 'default' : 'ghost'}
					size="sm"
					onclick={() => viewMode = 'grid'}
					class="h-8 px-3 rounded-l-none"
				>
					<Activity class="h-4 w-4" />
				</Button>
			</div>
			
			<!-- Filters Toggle -->
			<Button
				variant={showFilters ? 'default' : 'outline'}
				size="sm"
				onclick={() => showFilters = !showFilters}
			>
				{#if showFilters}
					<EyeOff class="h-4 w-4 mr-2" />
					Hide Filters
				{:else}
					<Eye class="h-4 w-4 mr-2" />
					Show Filters
				{/if}
			</Button>
			
			<!-- Refresh Button -->
			<Button
				variant="outline"
				size="sm"
				onclick={() => loadPages(true)}
				disabled={loading}
			>
				<RefreshCw class="h-4 w-4 mr-2 {loading ? 'animate-spin' : ''}" />
				Refresh
			</Button>
		</div>
	</div>
	
	<!-- Statistics Cards -->
	{#if statistics}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
			<Card>
				<CardContent class="p-4">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Total Pages</p>
							<p class="text-2xl font-bold">{statistics.totalPages.toLocaleString()}</p>
						</div>
						<Database class="h-8 w-8 text-muted-foreground" />
					</div>
				</CardContent>
			</Card>
			
			<Card>
				<CardContent class="p-4">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Filtered Pages</p>
							<p class="text-2xl font-bold">{statistics.filteredPages.toLocaleString()}</p>
							<p class="text-xs text-muted-foreground">
								{((statistics.filteredPages / statistics.totalPages) * 100).toFixed(1)}%
							</p>
						</div>
						<Filter class="h-8 w-8 text-amber-500" />
					</div>
				</CardContent>
			</Card>
			
			<Card>
				<CardContent class="p-4">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Processable</p>
							<p class="text-2xl font-bold">{statistics.processablePages.toLocaleString()}</p>
							<p class="text-xs text-muted-foreground">Can be manually processed</p>
						</div>
						<Zap class="h-8 w-8 text-blue-500" />
					</div>
				</CardContent>
			</Card>
			
			<Card>
				<CardContent class="p-4">
					<div class="flex items-center justify-between">
						<div>
							<p class="text-sm text-muted-foreground">Overridden</p>
							<p class="text-2xl font-bold">{statistics.overriddenPages.toLocaleString()}</p>
							<p class="text-xs text-muted-foreground">Manual overrides</p>
						</div>
						<Shield class="h-8 w-8 text-green-500" />
					</div>
				</CardContent>
			</Card>
		</div>
	{/if}
	
	<!-- Filters Panel -->
	{#if showFilters}
		<EnhancedURLProgressFilters
			{projectId}
			{sessions}
			on:filtersChange={handleFiltersChange}
		/>
	{/if}
	
	<!-- Bulk Operation Center -->
	{#if canShowBulkOperations && showBulkCenter}
		<BulkOperationCenter
			selectedPageIds={Array.from(selectedPageIds)}
			{projectId}
			on:bulkAction={(e) => handleBulkAction(e.detail.action, e.detail.pageIds, e.detail.data)}
			on:close={() => {
				showBulkCenter = false;
				clearSelection();
			}}
		/>
	{/if}
	
	<!-- Main Content Area -->
	<Card>
		<CardHeader class="pb-4">
			<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
				<CardTitle class="flex items-center gap-2">
					<FileText class="h-5 w-5" />
					Pages ({totalCount.toLocaleString()})
					{#if isLoadingRealtime}
						<Activity class="h-4 w-4 text-blue-500 animate-pulse" />
					{/if}
				</CardTitle>
				
				<div class="flex items-center gap-2">
					<!-- Selection Info -->
					{#if selectedCount > 0}
						<Badge variant="secondary" class="mr-2">
							{selectedCount} selected
						</Badge>
						
						<Button
							variant="outline"
							size="sm"
							onclick={() => showBulkCenter = true}
						>
							<Settings class="h-4 w-4 mr-2" />
							Bulk Actions
						</Button>
						
						<Button
							variant="ghost"
							size="sm"
							onclick={clearSelection}
						>
							Clear Selection
						</Button>
					{:else}
						<!-- Select All -->
						<Button
							variant="ghost"
							size="sm"
							onclick={handleSelectAll}
						>
							Select All
						</Button>
					{/if}
				</div>
			</div>
			
			<!-- Status Distribution -->
			{#if Object.keys(statusCounts).length > 0}
				<div class="flex flex-wrap gap-2 pt-2">
					{#each Object.entries(statusCounts) as [status, count]}
						<Badge variant="outline" class="text-xs {getStatusColor(status)}">
							{status.replace(/_/g, ' ')}: {count}
						</Badge>
					{/each}
				</div>
			{/if}
		</CardHeader>
		
		<CardContent>
			{#if error}
				<Alert class="mb-4">
					<AlertTriangle class="h-4 w-4" />
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{/if}
			
			{#if pages.length === 0 && !loading}
				<div class="text-center py-12">
					<Database class="h-12 w-12 text-muted-foreground mx-auto mb-4" />
					<h3 class="text-lg font-medium text-muted-foreground mb-2">No pages found</h3>
					<p class="text-sm text-muted-foreground mb-4">
						{#if Object.keys(activeFilters).some(key => 
							Array.isArray(activeFilters[key]) ? activeFilters[key].length > 0 : 
							activeFilters[key] !== null && activeFilters[key] !== ''
						)}
							Try adjusting your filters to see more results.
						{:else}
							No pages have been discovered for this project yet.
						{/if}
					</p>
					{#if Object.keys(activeFilters).some(key => 
						Array.isArray(activeFilters[key]) ? activeFilters[key].length > 0 : 
						activeFilters[key] !== null && activeFilters[key] !== ''
					)}
						<Button
							variant="outline"
							onclick={() => {
								activeFilters = {
									status: [],
									filterCategory: [],
									sessionId: null,
									searchQuery: '',
									dateRange: { from: null, to: null },
									contentType: [],
									hasErrors: null,
									isManuallyOverridden: null,
									priorityScore: { min: null, max: null },
									showOnlyProcessable: false
								};
								loadPages(true);
							}}
						>
							Clear All Filters
						</Button>
					{/if}
				</div>
			{:else}
				<!-- Table View -->
				{#if viewMode === 'table'}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="border-b">
									<th class="text-left p-2 w-12">
										<input
											type="checkbox"
											bind:checked={selectAllMode}
											on:change={handleSelectAll}
											class="w-4 h-4 rounded border-border"
										/>
									</th>
									<th class="text-left p-2">URL</th>
									<th class="text-left p-2">Status</th>
									<th class="text-left p-2">Filter Details</th>
									<th class="text-left p-2">Priority</th>
									<th class="text-left p-2">Size</th>
									<th class="text-left p-2">Created</th>
									<th class="text-right p-2">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#each pages as scrapePage (scrapePage.id)}
									<tr class="border-b hover:bg-muted/50 {selectedPageIds.has(scrapePage.id) ? 'bg-blue-50' : ''}">
										<td class="p-2">
											<input
												type="checkbox"
												checked={selectedPageIds.has(scrapePage.id)}
												on:change={(e) => handlePageSelect(scrapePage.id, e.currentTarget.checked, e.shiftKey)}
												class="w-4 h-4 rounded border-border"
											/>
										</td>
										<td class="p-2 max-w-md">
											<div class="truncate">
												<a
													href={scrapePage.original_url}
													target="_blank"
													rel="noopener noreferrer"
													class="text-blue-600 hover:underline text-sm"
													title={scrapePage.original_url}
												>
													{scrapePage.original_url}
												</a>
											</div>
											{#if scrapePage.title}
												<div class="text-xs text-muted-foreground truncate">
													{scrapePage.title}
												</div>
											{/if}
										</td>
										<td class="p-2">
											<EnhancedStatusBadge
												status={scrapePage.status}
												filterReason={scrapePage.filter_reason}
												filterCategory={scrapePage.filter_category}
												isManuallyOverridden={scrapePage.is_manually_overridden}
												size="sm"
											/>
										</td>
										<td class="p-2">
											{#if scrapePage.filter_details}
												<button
													onclick={() => toggleDetailExpansion(scrapePage.id)}
													class="text-xs text-blue-600 hover:underline flex items-center gap-1"
												>
													<Info class="h-3 w-3" />
													View Details
													{#if expandedDetails.has(scrapePage.id)}
														<ChevronUp class="h-3 w-3" />
													{:else}
														<ChevronDown class="h-3 w-3" />
													{/if}
												</button>
											{:else}
												<span class="text-xs text-muted-foreground">-</span>
											{/if}
										</td>
										<td class="p-2">
											{#if scrapePage.priority_score}
												<Badge variant="outline" class="text-xs">
													{scrapePage.priority_score}/10
												</Badge>
											{:else}
												<span class="text-xs text-muted-foreground">-</span>
											{/if}
										</td>
										<td class="p-2 text-xs text-muted-foreground">
											{formatBytes(scrapePage.content_length)}
										</td>
										<td class="p-2 text-xs text-muted-foreground">
											{formatDate(scrapePage.created_at)}
										</td>
										<td class="p-2 text-right">
											<Button
												variant="ghost"
												size="sm"
												onclick={() => toggleDetailExpansion(scrapePage.id)}
											>
												<MoreHorizontal class="h-4 w-4" />
											</Button>
										</td>
									</tr>
									
									<!-- Expanded Details Row -->
									{#if expandedDetails.has(scrapePage.id)}
										<tr class="bg-muted/25">
											<td colspan="8" class="p-4">
												<FilteringTransparencyPanel
													{scrapePage}
													{projectId}
													on:pageUpdated={() => loadPages()}
												/>
											</td>
										</tr>
									{/if}
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				
				<!-- List View -->
				{#if viewMode === 'list'}
					<div class="space-y-4">
						{#each pages as scrapePage (scrapePage.id)}
							<Card class="p-4 {selectedPageIds.has(scrapePage.id) ? 'ring-2 ring-blue-500 bg-blue-50' : ''}">
								<div class="flex items-start gap-4">
									<input
										type="checkbox"
										checked={selectedPageIds.has(scrapePage.id)}
										on:change={(e) => handlePageSelect(scrapePage.id, e.currentTarget.checked, e.shiftKey)}
										class="w-4 h-4 rounded border-border mt-1"
									/>
									
									<div class="flex-1 min-w-0">
										<div class="flex items-start justify-between gap-4">
											<div class="flex-1 min-w-0">
												<h4 class="font-medium text-sm truncate">
													{scrapePage.title || 'Untitled'}
												</h4>
												<a
													href={scrapePage.original_url}
													target="_blank"
													rel="noopener noreferrer"
													class="text-blue-600 hover:underline text-xs truncate block"
													title={scrapePage.original_url}
												>
													{scrapePage.original_url}
												</a>
											</div>
											
											<div class="flex items-center gap-2 flex-shrink-0">
												<EnhancedStatusBadge
													status={scrapePage.status}
													filterReason={scrapePage.filter_reason}
													filterCategory={scrapePage.filter_category}
													isManuallyOverridden={scrapePage.is_manually_overridden}
													size="sm"
												/>
												
												{#if scrapePage.priority_score}
													<Badge variant="outline" class="text-xs">
														Priority: {scrapePage.priority_score}/10
													</Badge>
												{/if}
											</div>
										</div>
										
										<div class="flex items-center gap-4 text-xs text-muted-foreground mt-2">
											<span>{formatBytes(scrapePage.content_length)}</span>
											<span>{formatDate(scrapePage.created_at)}</span>
											{#if scrapePage.error_message}
												<span class="text-red-600 flex items-center gap-1">
													<AlertTriangle class="h-3 w-3" />
													Error
												</span>
											{/if}
										</div>
										
										{#if expandedDetails.has(scrapePage.id) && scrapePage.filter_details}
											<div class="mt-4 pt-4 border-t">
												<FilteringTransparencyPanel
													{scrapePage}
													{projectId}
													on:pageUpdated={() => loadPages()}
												/>
											</div>
										{/if}
									</div>
									
									<Button
										variant="ghost"
										size="sm"
										onclick={() => toggleDetailExpansion(scrapePage.id)}
									>
										{#if expandedDetails.has(scrapePage.id)}
											<ChevronUp class="h-4 w-4" />
										{:else}
											<ChevronDown class="h-4 w-4" />
										{/if}
									</Button>
								</div>
							</Card>
						{/each}
					</div>
				{/if}
				
				<!-- Grid View -->
				{#if viewMode === 'grid'}
					<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
						{#each pages as scrapePage (scrapePage.id)}
							<Card class="p-4 {selectedPageIds.has(scrapePage.id) ? 'ring-2 ring-blue-500 bg-blue-50' : ''}">
								<div class="space-y-3">
									<div class="flex items-start justify-between">
										<input
											type="checkbox"
											checked={selectedPageIds.has(scrapePage.id)}
											on:change={(e) => handlePageSelect(scrapePage.id, e.currentTarget.checked, e.shiftKey)}
											class="w-4 h-4 rounded border-border"
										/>
										
										<EnhancedStatusBadge
											status={scrapePage.status}
											filterReason={scrapePage.filter_reason}
											filterCategory={scrapePage.filter_category}
											isManuallyOverridden={scrapePage.is_manually_overridden}
											size="sm"
										/>
									</div>
									
									<div>
										<h4 class="font-medium text-sm truncate">
											{scrapePage.title || 'Untitled'}
										</h4>
										<a
											href={scrapePage.original_url}
											target="_blank"
											rel="noopener noreferrer"
											class="text-blue-600 hover:underline text-xs truncate block"
											title={scrapePage.original_url}
										>
											{scrapePage.original_url}
										</a>
									</div>
									
									<div class="flex justify-between text-xs text-muted-foreground">
										<span>{formatBytes(scrapePage.content_length)}</span>
										{#if scrapePage.priority_score}
											<Badge variant="outline" class="text-xs">
												{scrapePage.priority_score}/10
											</Badge>
										{/if}
									</div>
									
									<div class="text-xs text-muted-foreground">
										{formatDate(scrapePage.created_at)}
									</div>
									
									{#if scrapePage.filter_details}
										<Button
											variant="outline"
											size="sm"
											onclick={() => toggleDetailExpansion(scrapePage.id)}
											class="w-full text-xs"
										>
											<Info class="h-3 w-3 mr-2" />
											Filter Details
										</Button>
									{/if}
								</div>
							</Card>
						{/each}
					</div>
				{/if}
				
				<!-- Pagination -->
				{#if totalPages > 1}
					<div class="flex items-center justify-between pt-4 border-t">
						<div class="text-sm text-muted-foreground">
							Showing {((currentPage - 1) * pageSize) + 1} to {Math.min(currentPage * pageSize, totalCount)} of {totalCount} results
						</div>
						
						<div class="flex items-center gap-2">
							<Button
								variant="outline"
								size="sm"
								onclick={() => goToPage(1)}
								disabled={currentPage === 1}
							>
								<ChevronsLeft class="h-4 w-4" />
							</Button>
							<Button
								variant="outline"
								size="sm"
								onclick={prevPage}
								disabled={currentPage === 1}
							>
								<ChevronLeft class="h-4 w-4" />
							</Button>
							
							<div class="flex items-center gap-2">
								<span class="text-sm">Page</span>
								<Input
									type="number"
									min="1"
									max={totalPages}
									bind:value={currentPage}
									on:change={() => goToPage(currentPage)}
									class="w-16 text-center text-sm h-8"
								/>
								<span class="text-sm">of {totalPages}</span>
							</div>
							
							<Button
								variant="outline"
								size="sm"
								onclick={nextPage}
								disabled={currentPage === totalPages}
							>
								<ChevronRight class="h-4 w-4" />
							</Button>
							<Button
								variant="outline"
								size="sm"
								onclick={() => goToPage(totalPages)}
								disabled={currentPage === totalPages}
							>
								<ChevronsRight class="h-4 w-4" />
							</Button>
						</div>
					</div>
				{/if}
			{/if}
		</CardContent>
	</Card>
</div>

<!-- Real-time Loading Overlay -->
{#if isLoadingRealtime}
	<div class="fixed bottom-4 right-4 z-50">
		<Card class="p-4">
			<div class="flex items-center gap-2">
				<Activity class="h-4 w-4 text-blue-500 animate-pulse" />
				<span class="text-sm">Updating pages...</span>
			</div>
		</Card>
	</div>
{/if}