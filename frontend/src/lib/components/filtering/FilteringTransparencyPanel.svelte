<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Separator } from '$lib/components/ui/separator';
	import { Progress } from '$lib/components/ui/progress';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	
	// Icons
	import {
		Shield,
		Filter,
		Eye,
		Edit3,
		Save,
		X,
		Info,
		AlertTriangle,
		CheckCircle,
		Clock,
		Zap,
		Target,
		Layers,
		FileText,
		Code,
		BarChart3,
		TrendingUp,
		TrendingDown,
		ShieldCheck,
		RefreshCw,
		ExternalLink,
		Copy,
		Download,
		History,
		Settings
	} from 'lucide-svelte';
	
	// Types
	import type { ScrapePage, FilterReason, FilterCategory } from '$lib/types/scraping';
	
	export let scrapePage: ScrapePage;
	export let projectId: number;
	export let showActions: boolean = true;
	export let expandedView: boolean = true;
	
	const dispatch = createEventDispatcher<{
		pageUpdated: {
			pageId: number;
			updates: Partial<ScrapePage>;
		};
		manualOverride: {
			pageId: number;
			action: 'override' | 'restore';
			reasoning?: string;
		};
		priorityChange: {
			pageId: number;
			newPriority: number;
		};
		close: void;
	}>();
	
	// Component state
	let loading = false;
	let error: string | null = null;
	let showEditForm = false;
	let overrideReasoning = '';
	let newPriority = scrapePage.priority_score || 5;
	let activeTab = 'details';
	
	// Parsed filter details
	let filterDetailsObj: any = null;
	
	$: {
		if (scrapePage.filter_details) {
			try {
				filterDetailsObj = JSON.parse(scrapePage.filter_details);
			} catch (e) {
				filterDetailsObj = { raw: scrapePage.filter_details };
			}
		}
	}
	
	// Status analysis
	$: isFiltered = scrapePage.status.startsWith('filtered_') || scrapePage.status === 'awaiting_manual_review';
	$: canOverride = isFiltered && scrapePage.can_be_manually_processed;
	$: hasOverride = scrapePage.is_manually_overridden;
	$: hasError = scrapePage.error_message !== null;
	$: isProcessed = scrapePage.status === 'completed' || scrapePage.status === 'manually_approved';
	
	// Filter analysis helpers
	function getFilterSeverity(reason: FilterReason | null): 'low' | 'medium' | 'high' {
		if (!reason) return 'low';
		
		const highSeverity = ['duplicate_content', 'error_page_detected'];
		const mediumSeverity = ['list_page_pattern', 'low_quality_content', 'insufficient_text'];
		
		if (highSeverity.includes(reason)) return 'high';
		if (mediumSeverity.includes(reason)) return 'medium';
		return 'low';
	}
	
	function getRecommendation(): { action: string; reason: string; confidence: number } {
		if (!isFiltered) {
			return { action: 'none', reason: 'Page is not filtered', confidence: 0 };
		}
		
		if (hasOverride) {
			return { action: 'review', reason: 'Already overridden - review effectiveness', confidence: 0.7 };
		}
		
		if (!canOverride) {
			return { action: 'none', reason: 'Cannot be manually processed', confidence: 0.9 };
		}
		
		const severity = getFilterSeverity(scrapePage.filter_reason);
		const priority = scrapePage.priority_score || 0;
		
		if (severity === 'low' && priority >= 6) {
			return { action: 'override', reason: 'Low severity filter with high priority', confidence: 0.8 };
		}
		
		if (severity === 'high') {
			return { action: 'keep', reason: 'High severity filter - likely correct', confidence: 0.9 };
		}
		
		return { action: 'review', reason: 'Manual review recommended', confidence: 0.6 };
	}
	
	// Actions
	async function handleManualOverride(action: 'override' | 'restore') {
		if (!canOverride && action === 'override') return;
		
		loading = true;
		error = null;
		
		try {
			const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages/${scrapePage.id}/manual-override`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				},
				body: JSON.stringify({
					action,
					reasoning: overrideReasoning.trim() || undefined
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.error || `HTTP ${response.status}`);
			}
			
			const result = await response.json();
			
			dispatch('manualOverride', {
				pageId: scrapePage.id,
				action,
				reasoning: overrideReasoning.trim() || undefined
			});
			
			dispatch('pageUpdated', {
				pageId: scrapePage.id,
				updates: result.updated_page || {}
			});
			
			// Reset form
			showEditForm = false;
			overrideReasoning = '';
			
		} catch (err) {
			console.error('Manual override failed:', err);
			error = err instanceof Error ? err.message : 'Override operation failed';
		} finally {
			loading = false;
		}
	}
	
	async function handlePriorityChange() {
		if (newPriority === scrapePage.priority_score) return;
		
		loading = true;
		error = null;
		
		try {
			const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages/${scrapePage.id}/priority`, {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				},
				body: JSON.stringify({
					priority_score: newPriority
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.error || `HTTP ${response.status}`);
			}
			
			dispatch('priorityChange', {
				pageId: scrapePage.id,
				newPriority
			});
			
			dispatch('pageUpdated', {
				pageId: scrapePage.id,
				updates: { priority_score: newPriority }
			});
			
		} catch (err) {
			console.error('Priority change failed:', err);
			error = err instanceof Error ? err.message : 'Priority update failed';
		} finally {
			loading = false;
		}
	}
	
	function copyToClipboard(text: string) {
		navigator.clipboard.writeText(text).catch(console.error);
	}
	
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
	
	// Computed values
	$: recommendation = getRecommendation();
	$: filterSeverity = getFilterSeverity(scrapePage.filter_reason);
	$: confidencePercentage = filterDetailsObj?.confidence ? Math.round(filterDetailsObj.confidence * 100) : null;
	$: matchedPatterns = filterDetailsObj?.matched_patterns || [];
	$: filterMetrics = filterDetailsObj?.metrics || {};
</script>

<Card class="w-full">
	<CardHeader class="pb-3">
		<div class="flex items-center justify-between">
			<CardTitle class="text-base flex items-center gap-2">
				<Layers class="h-4 w-4" />
				Filtering Transparency
				{#if isFiltered}
					<Badge variant="outline" class="text-xs">
						{scrapePage.filter_category?.replace('_', ' ') || 'Filtered'}
					</Badge>
				{/if}
			</CardTitle>
			
			{#if showActions}
				<Button variant="ghost" size="sm" onclick={() => dispatch('close')}>
					<X class="h-4 w-4" />
				</Button>
			{/if}
		</div>
	</CardHeader>
	
	<CardContent>
		{#if error}
			<Alert class="mb-4">
				<AlertTriangle class="h-4 w-4" />
				<AlertDescription>{error}</AlertDescription>
			</Alert>
		{/if}
		
		<Tabs bind:value={activeTab} class="w-full">
			<TabsList class="grid w-full grid-cols-4">
				<TabsTrigger value="details" class="text-xs">
					<Info class="h-3 w-3 mr-1" />
					Details
				</TabsTrigger>
				<TabsTrigger value="analysis" class="text-xs">
					<BarChart3 class="h-3 w-3 mr-1" />
					Analysis
				</TabsTrigger>
				<TabsTrigger value="actions" class="text-xs" disabled={!canOverride}>
					<Settings class="h-3 w-3 mr-1" />
					Actions
				</TabsTrigger>
				<TabsTrigger value="history" class="text-xs">
					<History class="h-3 w-3 mr-1" />
					History
				</TabsTrigger>
			</TabsList>
			
			<!-- Details Tab -->
			<TabsContent value="details" class="space-y-4">
				<!-- Basic Information -->
				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					<div class="space-y-3">
						<div>
							<Label class="text-xs font-medium text-muted-foreground">Current Status</Label>
							<div class="flex items-center gap-2 mt-1">
								<Badge variant={isFiltered ? 'outline' : 'default'}>
									{scrapePage.status.replace('_', ' ')}
								</Badge>
								{#if hasOverride}
									<Badge variant="success" class="text-xs">
										<ShieldCheck class="h-3 w-3 mr-1" />
										Overridden
									</Badge>
								{/if}
							</div>
						</div>
						
						{#if scrapePage.filter_reason}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Filter Reason</Label>
								<p class="text-sm mt-1">{scrapePage.filter_reason.replace(/_/g, ' ')}</p>
							</div>
						{/if}
						
						{#if scrapePage.filter_category}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Category</Label>
								<p class="text-sm mt-1">{scrapePage.filter_category.replace(/_/g, ' ')}</p>
							</div>
						{/if}
						
						{#if scrapePage.priority_score !== null}
							<div>
								<Label class="text-xs font-medium text-muted-foreground">Priority Score</Label>
								<div class="flex items-center gap-2 mt-1">
									<Progress value={scrapePage.priority_score * 10} class="flex-1 h-2" />
									<span class="text-sm font-medium">{scrapePage.priority_score}/10</span>
								</div>
							</div>
						{/if}
					</div>
					
					<div class="space-y-3">
						<div>
							<Label class="text-xs font-medium text-muted-foreground">URL</Label>
							<div class="flex items-center gap-2 mt-1">
								<p class="text-sm truncate flex-1" title={scrapePage.original_url}>
									{scrapePage.original_url}
								</p>
								<Button variant="ghost" size="sm" onclick={() => copyToClipboard(scrapePage.original_url)}>
									<Copy class="h-3 w-3" />
								</Button>
								<Button variant="ghost" size="sm" onclick={() => window.open(scrapePage.original_url, '_blank')}>
									<ExternalLink class="h-3 w-3" />
								</Button>
							</div>
						</div>
						
						<div>
							<Label class="text-xs font-medium text-muted-foreground">Content Size</Label>
							<p class="text-sm mt-1">{formatBytes(scrapePage.content_length)}</p>
						</div>
						
						<div>
							<Label class="text-xs font-medium text-muted-foreground">MIME Type</Label>
							<p class="text-sm mt-1">{scrapePage.mime_type || 'Unknown'}</p>
						</div>
						
						<div>
							<Label class="text-xs font-medium text-muted-foreground">Created</Label>
							<p class="text-sm mt-1">{formatDate(scrapePage.created_at)}</p>
						</div>
					</div>
				</div>
				
				<!-- Filter Details -->
				{#if filterDetailsObj}
					<Separator />
					<div>
						<Label class="text-sm font-medium mb-3 block">Filter Details</Label>
						
						{#if confidencePercentage !== null}
							<div class="mb-3">
								<Label class="text-xs font-medium text-muted-foreground">Filter Confidence</Label>
								<div class="flex items-center gap-2 mt-1">
									<Progress value={confidencePercentage} class="flex-1 h-2" />
									<span class="text-sm font-medium">{confidencePercentage}%</span>
								</div>
							</div>
						{/if}
						
						{#if matchedPatterns.length > 0}
							<div class="mb-3">
								<Label class="text-xs font-medium text-muted-foreground">Matched Patterns</Label>
								<div class="flex flex-wrap gap-1 mt-1">
									{#each matchedPatterns as pattern}
										<Badge variant="outline" class="text-xs">{pattern}</Badge>
									{/each}
								</div>
							</div>
						{/if}
						
						{#if Object.keys(filterMetrics).length > 0}
							<div class="mb-3">
								<Label class="text-xs font-medium text-muted-foreground">Metrics</Label>
								<div class="grid grid-cols-2 gap-2 mt-1 text-xs">
									{#each Object.entries(filterMetrics) as [key, value]}
										<div class="flex justify-between">
											<span class="text-muted-foreground">{key.replace(/_/g, ' ')}:</span>
											<span class="font-medium">{value}</span>
										</div>
									{/each}
								</div>
							</div>
						{/if}
						
						<div class="bg-muted rounded-md p-3">
							<div class="flex items-center justify-between mb-2">
								<Label class="text-xs font-medium">Raw Filter Data</Label>
								<Button variant="ghost" size="sm" onclick={() => copyToClipboard(JSON.stringify(filterDetailsObj, null, 2))}>
									<Copy class="h-3 w-3" />
								</Button>
							</div>
							<pre class="text-xs font-mono overflow-x-auto whitespace-pre-wrap">{JSON.stringify(filterDetailsObj, null, 2)}</pre>
						</div>
					</div>
				{/if}
			</TabsContent>
			
			<!-- Analysis Tab -->
			<TabsContent value="analysis" class="space-y-4">
				<!-- Recommendation Card -->
				<Card class="p-4">
					<div class="flex items-start gap-3">
						<div class="flex-shrink-0">
							{#if recommendation.action === 'override'}
								<div class="w-8 h-8 rounded-full bg-green-100 dark:bg-green-900/20 flex items-center justify-center">
									<TrendingUp class="h-4 w-4 text-green-600 dark:text-green-400" />
								</div>
							{:else if recommendation.action === 'keep'}
								<div class="w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/20 flex items-center justify-center">
									<TrendingDown class="h-4 w-4 text-red-600 dark:text-red-400" />
								</div>
							{:else}
								<div class="w-8 h-8 rounded-full bg-yellow-100 dark:bg-yellow-900/20 flex items-center justify-center">
									<Eye class="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
								</div>
							{/if}
						</div>
						
						<div class="flex-1">
							<h4 class="font-semibold text-sm mb-1">
								{#if recommendation.action === 'override'}
									Recommend Override
								{:else if recommendation.action === 'keep'}
									Recommend Keep Filter
								{:else if recommendation.action === 'review'}
									Recommend Manual Review
								{:else}
									No Action Needed
								{/if}
							</h4>
							<p class="text-sm text-muted-foreground mb-2">{recommendation.reason}</p>
							<div class="flex items-center gap-2">
								<Label class="text-xs">Confidence:</Label>
								<Progress value={recommendation.confidence * 100} class="w-20 h-1.5" />
								<span class="text-xs font-medium">{Math.round(recommendation.confidence * 100)}%</span>
							</div>
						</div>
					</div>
				</Card>
				
				<!-- Analysis Metrics -->
				<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
					<Card class="p-4">
						<div class="flex items-center gap-2 mb-2">
							<Target class="h-4 w-4 text-blue-500" />
							<Label class="text-sm font-medium">Filter Severity</Label>
						</div>
						<div class="flex items-center gap-2">
							<Badge variant={filterSeverity === 'high' ? 'destructive' : filterSeverity === 'medium' ? 'outline' : 'secondary'}>
								{filterSeverity}
							</Badge>
						</div>
					</Card>
					
					<Card class="p-4">
						<div class="flex items-center gap-2 mb-2">
							<Zap class="h-4 w-4 text-green-500" />
							<Label class="text-sm font-medium">Processing Status</Label>
						</div>
						<div class="flex items-center gap-2">
							<Badge variant={canOverride ? 'success' : 'secondary'}>
								{canOverride ? 'Can Process' : 'Cannot Process'}
							</Badge>
						</div>
					</Card>
					
					<Card class="p-4">
						<div class="flex items-center gap-2 mb-2">
							<Shield class="h-4 w-4 text-purple-500" />
							<Label class="text-sm font-medium">Override Status</Label>
						</div>
						<div class="flex items-center gap-2">
							<Badge variant={hasOverride ? 'success' : 'outline'}>
								{hasOverride ? 'Overridden' : 'Original'}
							</Badge>
						</div>
					</Card>
				</div>
				
				<!-- Pattern Analysis -->
				{#if matchedPatterns.length > 0}
					<Card class="p-4">
						<Label class="text-sm font-medium mb-3 block">Pattern Analysis</Label>
						<div class="space-y-2">
							{#each matchedPatterns as pattern, index}
								<div class="flex items-center justify-between p-2 bg-muted rounded">
									<code class="text-xs font-mono">{pattern}</code>
									<Badge variant="outline" class="text-xs">Match {index + 1}</Badge>
								</div>
							{/each}
						</div>
					</Card>
				{/if}
			</TabsContent>
			
			<!-- Actions Tab -->
			<TabsContent value="actions" class="space-y-4">
				{#if canOverride}
					<Card class="p-4">
						<div class="space-y-4">
							<div class="flex items-center justify-between">
								<h4 class="font-semibold">Manual Override Controls</h4>
								<Badge variant={hasOverride ? 'success' : 'outline'}>
									{hasOverride ? 'Override Active' : 'Filter Active'}
								</Badge>
							</div>
							
							{#if showEditForm}
								<div class="space-y-3">
									<div>
										<Label for="reasoning" class="text-sm">Override Reasoning (Optional)</Label>
										<Textarea
											id="reasoning"
											bind:value={overrideReasoning}
											placeholder="Explain why this page should be processed despite the filter..."
											class="mt-1 text-sm"
											rows="3"
										/>
									</div>
									
									<div class="flex gap-2">
										{#if !hasOverride}
											<Button
												onclick={() => handleManualOverride('override')}
												disabled={loading}
												class="text-sm"
											>
												{#if loading}
													<RefreshCw class="h-3 w-3 mr-2 animate-spin" />
												{:else}
													<ShieldCheck class="h-3 w-3 mr-2" />
												{/if}
												Override Filter
											</Button>
										{:else}
											<Button
												variant="outline"
												onclick={() => handleManualOverride('restore')}
												disabled={loading}
												class="text-sm"
											>
												{#if loading}
													<RefreshCw class="h-3 w-3 mr-2 animate-spin" />
												{:else}
													<Filter class="h-3 w-3 mr-2" />
												{/if}
												Restore Filter
											</Button>
										{/if}
										
										<Button variant="ghost" onclick={() => showEditForm = false} disabled={loading}>
											Cancel
										</Button>
									</div>
								</div>
							{:else}
								<div class="flex gap-2">
									{#if !hasOverride}
										<Button variant="outline" onclick={() => showEditForm = true}>
											<Edit3 class="h-3 w-3 mr-2" />
											Override Filter
										</Button>
									{:else}
										<Button variant="outline" onclick={() => showEditForm = true}>
											<Filter class="h-3 w-3 mr-2" />
											Restore Original Filter
										</Button>
									{/if}
								</div>
							{/if}
						</div>
					</Card>
					
					<!-- Priority Adjustment -->
					<Card class="p-4">
						<div class="space-y-4">
							<h4 class="font-semibold">Priority Adjustment</h4>
							
							<div class="space-y-2">
								<Label for="priority" class="text-sm">Priority Score (1-10)</Label>
								<div class="flex items-center gap-4">
									<Input
										id="priority"
										type="number"
										min="1"
										max="10"
										bind:value={newPriority}
										class="w-20 text-sm"
									/>
									<Progress value={newPriority * 10} class="flex-1 h-2" />
									<span class="text-sm font-medium">{newPriority}/10</span>
								</div>
								
								{#if newPriority !== scrapePage.priority_score}
									<Button
										size="sm"
										onclick={handlePriorityChange}
										disabled={loading}
										class="text-xs"
									>
										{#if loading}
											<RefreshCw class="h-3 w-3 mr-1 animate-spin" />
										{:else}
											<Save class="h-3 w-3 mr-1" />
										{/if}
										Update Priority
									</Button>
								{/if}
							</div>
						</div>
					</Card>
				{:else}
					<Alert>
						<Info class="h-4 w-4" />
						<AlertDescription>
							This page cannot be manually processed due to system constraints or filter configuration.
						</AlertDescription>
					</Alert>
				{/if}
			</TabsContent>
			
			<!-- History Tab -->
			<TabsContent value="history" class="space-y-4">
				<Card class="p-4">
					<h4 class="font-semibold mb-3">Processing Timeline</h4>
					
					<div class="space-y-3">
						<div class="flex items-center gap-3 text-sm">
							<div class="w-2 h-2 rounded-full bg-blue-500"></div>
							<span class="text-muted-foreground">{formatDate(scrapePage.created_at)}</span>
							<span>Page discovered</span>
						</div>
						
						{#if scrapePage.first_seen_at !== scrapePage.created_at}
							<div class="flex items-center gap-3 text-sm">
								<div class="w-2 h-2 rounded-full bg-yellow-500"></div>
								<span class="text-muted-foreground">{formatDate(scrapePage.first_seen_at)}</span>
								<span>First seen in CDX</span>
							</div>
						{/if}
						
						{#if scrapePage.last_attempt_at}
							<div class="flex items-center gap-3 text-sm">
								<div class="w-2 h-2 rounded-full bg-orange-500"></div>
								<span class="text-muted-foreground">{formatDate(scrapePage.last_attempt_at)}</span>
								<span>Last processing attempt</span>
							</div>
						{/if}
						
						{#if scrapePage.completed_at}
							<div class="flex items-center gap-3 text-sm">
								<div class="w-2 h-2 rounded-full bg-green-500"></div>
								<span class="text-muted-foreground">{formatDate(scrapePage.completed_at)}</span>
								<span>Processing completed</span>
							</div>
						{/if}
						
						{#if hasOverride}
							<div class="flex items-center gap-3 text-sm">
								<div class="w-2 h-2 rounded-full bg-purple-500"></div>
								<span class="text-muted-foreground">{formatDate(scrapePage.updated_at)}</span>
								<span>Filter manually overridden</span>
							</div>
						{/if}
					</div>
				</Card>
				
				<!-- Performance Metrics -->
				{#if scrapePage.fetch_time || scrapePage.extraction_time || scrapePage.total_processing_time}
					<Card class="p-4">
						<h4 class="font-semibold mb-3">Performance Metrics</h4>
						
						<div class="grid grid-cols-3 gap-4 text-sm">
							{#if scrapePage.fetch_time}
								<div>
									<Label class="text-xs text-muted-foreground">Fetch Time</Label>
									<p class="font-medium">{scrapePage.fetch_time}ms</p>
								</div>
							{/if}
							
							{#if scrapePage.extraction_time}
								<div>
									<Label class="text-xs text-muted-foreground">Extraction Time</Label>
									<p class="font-medium">{scrapePage.extraction_time}ms</p>
								</div>
							{/if}
							
							{#if scrapePage.total_processing_time}
								<div>
									<Label class="text-xs text-muted-foreground">Total Time</Label>
									<p class="font-medium">{scrapePage.total_processing_time}ms</p>
								</div>
							{/if}
						</div>
					</Card>
				{/if}
				
				<!-- Retry Information -->
				{#if scrapePage.retry_count > 0 || hasError}
					<Card class="p-4">
						<h4 class="font-semibold mb-3">Error & Retry Information</h4>
						
						<div class="space-y-2 text-sm">
							<div class="flex justify-between">
								<span class="text-muted-foreground">Retry Count:</span>
								<span>{scrapePage.retry_count} / {scrapePage.max_retries}</span>
							</div>
							
							{#if hasError}
								<div>
									<Label class="text-xs text-muted-foreground">Error Message</Label>
									<p class="text-sm text-destructive mt-1">{scrapePage.error_message}</p>
								</div>
								
								{#if scrapePage.error_type}
									<div>
										<Label class="text-xs text-muted-foreground">Error Type</Label>
										<p class="text-sm mt-1">{scrapePage.error_type}</p>
									</div>
								{/if}
							{/if}
						</div>
					</Card>
				{/if}
			</TabsContent>
		</Tabs>
	</CardContent>
</Card>