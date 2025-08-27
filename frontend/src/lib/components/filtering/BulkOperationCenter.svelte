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
	import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '$lib/components/ui/sheet';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	
	// Icons
	import {
		Zap,
		Play,
		Pause,
		Square,
		RotateCcw,
		Filter,
		Shield,
		ShieldCheck,
		Target,
		AlertTriangle,
		CheckCircle,
		Clock,
		Activity,
		X,
		Settings,
		Download,
		FileText,
		BarChart3,
		TrendingUp,
		Eye,
		RefreshCw,
		Info,
		Layers,
		ArrowRight,
		ChevronRight,
		Users,
		Database,
		Trash2,
		Archive
	} from 'lucide-svelte';
	
	// Types
	import type { BulkActionType } from '$lib/types/scraping';
	
	export let selectedPageIds: number[];
	export let projectId: number;
	export let showPreview: boolean = true;
	export let maxWidth: string = 'max-w-4xl';
	
	const dispatch = createEventDispatcher<{
		bulkAction: {
			action: BulkActionType;
			pageIds: number[];
			data?: any;
		};
		preview: {
			action: BulkActionType;
			pageIds: number[];
			data?: any;
		};
		close: void;
		selectionChange: {
			pageIds: number[];
		};
	}>();
	
	// Component state
	let currentStep = 0;
	let selectedAction: BulkActionType | null = null;
	let actionData: any = {};
	let loading = false;
	let error: string | null = null;
	let previewData: any = null;
	let progressValue = 0;
	let progressMessage = '';
	let completedItems = 0;
	let isExecuting = false;
	let isPaused = false;
	let executionId: string | null = null;
	
	// Action configuration
	const bulkActions: Array<{
		id: BulkActionType;
		label: string;
		description: string;
		icon: any;
		color: string;
		requiresData: boolean;
		dangerLevel: 'safe' | 'warning' | 'danger';
		estimatedTime: string;
		maxItems: number | null;
	}> = [
		{
			id: 'override_filter',
			label: 'Override Filters',
			description: 'Manually override filtering decisions to allow processing',
			icon: ShieldCheck,
			color: 'text-green-600',
			requiresData: true,
			dangerLevel: 'safe',
			estimatedTime: '1-2 sec per item',
			maxItems: 1000
		},
		{
			id: 'restore_filter',
			label: 'Restore Original Filters',
			description: 'Remove manual overrides and restore original filtering decisions',
			icon: Filter,
			color: 'text-orange-600',
			requiresData: false,
			dangerLevel: 'warning',
			estimatedTime: '0.5-1 sec per item',
			maxItems: 1000
		},
		{
			id: 'priority',
			label: 'Update Priority',
			description: 'Change priority scores for better processing order',
			icon: Target,
			color: 'text-blue-600',
			requiresData: true,
			dangerLevel: 'safe',
			estimatedTime: '0.5 sec per item',
			maxItems: 5000
		},
		{
			id: 'retry',
			label: 'Retry Processing',
			description: 'Retry failed or skipped pages for processing',
			icon: RotateCcw,
			color: 'text-purple-600',
			requiresData: false,
			dangerLevel: 'safe',
			estimatedTime: '2-5 sec per item',
			maxItems: 500
		},
		{
			id: 'manual_process',
			label: 'Force Manual Processing',
			description: 'Force processing of filtered pages with manual approval',
			icon: Zap,
			color: 'text-amber-600',
			requiresData: true,
			dangerLevel: 'warning',
			estimatedTime: '3-8 sec per item',
			maxItems: 200
		},
		{
			id: 'skip',
			label: 'Skip Pages',
			description: 'Mark pages as skipped to exclude from processing',
			icon: Square,
			color: 'text-gray-600',
			requiresData: true,
			dangerLevel: 'warning',
			estimatedTime: '0.5 sec per item',
			maxItems: 10000
		},
		{
			id: 'view_errors',
			label: 'Export Error Report',
			description: 'Generate detailed error report for selected pages',
			icon: FileText,
			color: 'text-red-600',
			requiresData: false,
			dangerLevel: 'safe',
			estimatedTime: '1-3 sec per item',
			maxItems: 10000
		},
		{
			id: 'delete',
			label: 'Delete Pages',
			description: 'Permanently delete pages from the project',
			icon: Trash2,
			color: 'text-red-700',
			requiresData: true,
			dangerLevel: 'danger',
			estimatedTime: '1-2 sec per item',
			maxItems: 1000
		},
		{
			id: 'archive',
			label: 'Archive Pages',
			description: 'Archive pages to remove from active processing',
			icon: Archive,
			color: 'text-slate-600',
			requiresData: true,
			dangerLevel: 'warning',
			estimatedTime: '0.5-1 sec per item',
			maxItems: 5000
		}
	];
	
	// Steps configuration
	const steps = [
		{ id: 'select', label: 'Select Action', description: 'Choose the bulk operation to perform' },
		{ id: 'configure', label: 'Configure', description: 'Set parameters for the operation' },
		{ id: 'preview', label: 'Preview', description: 'Review changes before execution' },
		{ id: 'execute', label: 'Execute', description: 'Run the bulk operation' },
		{ id: 'complete', label: 'Complete', description: 'Review results and finish' }
	];
	
	// Form validation
	$: selectedActionConfig = selectedAction ? bulkActions.find(a => a.id === selectedAction) : null;
	$: canProceed = currentStep === 0 ? !!selectedAction : 
		currentStep === 1 ? validateActionData() : 
		currentStep === 2 ? !!previewData : 
		true;
	$: isOverLimit = selectedPageIds.length > (selectedActionConfig?.maxItems || Infinity);
	
	function validateActionData(): boolean {
		if (!selectedActionConfig?.requiresData) return true;
		
		switch (selectedAction) {
			case 'override_filter':
			case 'manual_process':
			case 'skip':
			case 'delete':
			case 'archive':
				return actionData.reasoning && actionData.reasoning.trim().length > 0;
			case 'priority':
				return actionData.priority_score >= 1 && actionData.priority_score <= 10;
			default:
				return true;
		}
	}
	
	async function handleNextStep() {
		if (currentStep === 2 && showPreview) {
			await loadPreview();
		} else if (currentStep === 3) {
			await executeOperation();
			return; // Don't advance step, let execution handler do it
		}
		
		currentStep = Math.min(currentStep + 1, steps.length - 1);
	}
	
	function handlePrevStep() {
		currentStep = Math.max(currentStep - 1, 0);
	}
	
	async function loadPreview() {
		if (!selectedAction) return;
		
		loading = true;
		error = null;
		
		try {
			const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages/bulk/${selectedAction}/preview`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				},
				body: JSON.stringify({
					page_ids: selectedPageIds,
					...actionData
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.error || `HTTP ${response.status}`);
			}
			
			previewData = await response.json();
			
			dispatch('preview', {
				action: selectedAction,
				pageIds: selectedPageIds,
				data: actionData
			});
			
		} catch (err) {
			console.error('Preview failed:', err);
			error = err instanceof Error ? err.message : 'Preview generation failed';
		} finally {
			loading = false;
		}
	}
	
	async function executeOperation() {
		if (!selectedAction) return;
		
		isExecuting = true;
		loading = true;
		error = null;
		progressValue = 0;
		completedItems = 0;
		progressMessage = 'Starting bulk operation...';
		
		try {
			// Start the bulk operation
			const response = await fetch(`/api/v1/projects/${projectId}/scrape-pages/bulk/${selectedAction}`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				},
				body: JSON.stringify({
					page_ids: selectedPageIds,
					...actionData
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json().catch(() => ({}));
				throw new Error(errorData.error || `HTTP ${response.status}`);
			}
			
			const result = await response.json();
			executionId = result.execution_id;
			
			// Monitor progress if we have an execution ID
			if (executionId) {
				await monitorProgress(executionId);
			} else {
				// Operation completed immediately
				progressValue = 100;
				completedItems = selectedPageIds.length;
				progressMessage = 'Operation completed successfully';
				
				dispatch('bulkAction', {
					action: selectedAction,
					pageIds: selectedPageIds,
					data: actionData
				});
				
				currentStep = 4; // Complete step
			}
			
		} catch (err) {
			console.error('Execution failed:', err);
			error = err instanceof Error ? err.message : 'Bulk operation failed';
		} finally {
			loading = false;
		}
	}
	
	async function monitorProgress(executionId: string) {
		const pollInterval = 1000; // 1 second
		let attempts = 0;
		const maxAttempts = 600; // 10 minutes max
		
		while (attempts < maxAttempts && isExecuting && !isPaused) {
			try {
				const response = await fetch(`/api/v1/projects/${projectId}/bulk-operations/${executionId}/status`, {
					headers: {
						'Authorization': `Bearer ${localStorage.getItem('authToken')}`
					}
				});
				
				if (!response.ok) break;
				
				const status = await response.json();
				
				progressValue = status.progress_percentage || 0;
				completedItems = status.completed_items || 0;
				progressMessage = status.message || 'Processing...';
				
				if (status.status === 'completed') {
					isExecuting = false;
					currentStep = 4;
					
					dispatch('bulkAction', {
						action: selectedAction!,
						pageIds: selectedPageIds,
						data: actionData
					});
					break;
				} else if (status.status === 'failed') {
					error = status.error || 'Bulk operation failed';
					isExecuting = false;
					break;
				}
				
				await new Promise(resolve => setTimeout(resolve, pollInterval));
				attempts++;
				
			} catch (err) {
				console.error('Progress monitoring error:', err);
				break;
			}
		}
		
		if (attempts >= maxAttempts) {
			error = 'Operation timed out after 10 minutes';
			isExecuting = false;
		}
	}
	
	async function pauseOperation() {
		if (!executionId) return;
		
		try {
			await fetch(`/api/v1/projects/${projectId}/bulk-operations/${executionId}/pause`, {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				}
			});
			isPaused = true;
		} catch (err) {
			console.error('Failed to pause operation:', err);
		}
	}
	
	async function resumeOperation() {
		if (!executionId) return;
		
		try {
			await fetch(`/api/v1/projects/${projectId}/bulk-operations/${executionId}/resume`, {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				}
			});
			isPaused = false;
		} catch (err) {
			console.error('Failed to resume operation:', err);
		}
	}
	
	async function cancelOperation() {
		if (!executionId) return;
		
		try {
			await fetch(`/api/v1/projects/${projectId}/bulk-operations/${executionId}/cancel`, {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('authToken')}`
				}
			});
			isExecuting = false;
			isPaused = false;
			dispatch('close');
		} catch (err) {
			console.error('Failed to cancel operation:', err);
		}
	}
	
	function resetWizard() {
		currentStep = 0;
		selectedAction = null;
		actionData = {};
		previewData = null;
		error = null;
		progressValue = 0;
		progressMessage = '';
		completedItems = 0;
		isExecuting = false;
		isPaused = false;
		executionId = null;
	}
	
	function handleClose() {
		if (isExecuting) {
			if (confirm('Are you sure you want to close? The operation will continue in the background.')) {
				dispatch('close');
			}
		} else {
			dispatch('close');
		}
	}
	
	function getStepIcon(stepIndex: number) {
		if (stepIndex < currentStep) return CheckCircle;
		if (stepIndex === currentStep) return Activity;
		return Clock;
	}
	
	function getStepColor(stepIndex: number) {
		if (stepIndex < currentStep) return 'text-green-600';
		if (stepIndex === currentStep) return 'text-blue-600';
		return 'text-gray-400';
	}
</script>

<div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
	<Card class="w-full {maxWidth} max-h-[90vh] overflow-y-auto">
		<CardHeader class="pb-4">
			<div class="flex items-center justify-between">
				<CardTitle class="flex items-center gap-2">
					<Zap class="h-5 w-5 text-blue-600" />
					Bulk Operations Center
					<Badge variant="secondary" class="text-xs">
						{selectedPageIds.length} pages selected
					</Badge>
				</CardTitle>
				
				<Button variant="ghost" size="sm" onclick={handleClose}>
					<X class="h-4 w-4" />
				</Button>
			</div>
			
			<!-- Progress Steps -->
			<div class="flex items-center gap-4 mt-4">
				{#each steps as step, index}
					<div class="flex items-center gap-2">
						{#if index > 0}
							<ChevronRight class="h-3 w-3 text-gray-400" />
						{/if}
						
						<div class="flex items-center gap-2 {index === currentStep ? 'font-semibold' : ''}">
							<svelte:component 
								this={getStepIcon(index)} 
								class="h-4 w-4 {getStepColor(index)}" 
							/>
							<span class="text-sm {getStepColor(index)}">{step.label}</span>
						</div>
					</div>
				{/each}
			</div>
		</CardHeader>
		
		<CardContent>
			{#if error}
				<Alert class="mb-4">
					<AlertTriangle class="h-4 w-4" />
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{/if}
			
			<!-- Step 0: Select Action -->
			{#if currentStep === 0}
				<div class="space-y-4">
					<div>
						<h3 class="text-lg font-semibold mb-2">Select Bulk Operation</h3>
						<p class="text-sm text-muted-foreground">Choose the operation you want to perform on {selectedPageIds.length} selected pages.</p>
					</div>
					
					<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
						{#each bulkActions as action}
							{@const isDisabled = selectedPageIds.length > (action.maxItems || Infinity)}
							<button
								class="text-left p-4 border rounded-lg hover:border-blue-500 transition-colors {selectedAction === action.id ? 'border-blue-500 bg-blue-50' : ''} {isDisabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}"
								onclick={() => !isDisabled && (selectedAction = action.id)}
								disabled={isDisabled}
							>
								<div class="flex items-start gap-3">
									<div class="flex-shrink-0">
										<svelte:component this={action.icon} class="h-5 w-5 {action.color}" />
									</div>
									<div class="flex-1 min-w-0">
										<h4 class="font-medium text-sm mb-1">{action.label}</h4>
										<p class="text-xs text-muted-foreground mb-2">{action.description}</p>
										
										<div class="flex items-center gap-2 text-xs">
											<Badge variant={action.dangerLevel === 'safe' ? 'default' : action.dangerLevel === 'warning' ? 'outline' : 'destructive'} class="text-xs">
												{action.dangerLevel}
											</Badge>
											<span class="text-muted-foreground">{action.estimatedTime}</span>
										</div>
										
										{#if isDisabled}
											<p class="text-xs text-red-600 mt-1">
												Limit: {action.maxItems?.toLocaleString()} pages
											</p>
										{/if}
									</div>
								</div>
							</button>
						{/each}
					</div>
					
					{#if isOverLimit}
						<Alert>
							<AlertTriangle class="h-4 w-4" />
							<AlertDescription>
								The selected action has a limit of {selectedActionConfig?.maxItems?.toLocaleString()} pages, 
								but you have {selectedPageIds.length} pages selected. Please reduce your selection.
							</AlertDescription>
						</Alert>
					{/if}
				</div>
			{/if}
			
			<!-- Step 1: Configure -->
			{#if currentStep === 1}
				<div class="space-y-4">
					<div>
						<h3 class="text-lg font-semibold mb-2">Configure Operation</h3>
						<p class="text-sm text-muted-foreground">
							Set parameters for the <strong>{selectedActionConfig?.label}</strong> operation.
						</p>
					</div>
					
					{#if selectedAction === 'override_filter'}
						<div class="space-y-3">
							<div>
								<Label for="reasoning">Override Reasoning (Required)</Label>
								<Textarea
									id="reasoning"
									bind:value={actionData.reasoning}
									placeholder="Explain why these pages should be processed despite filters..."
									class="mt-1"
									rows="3"
									required
								/>
							</div>
							
							<div>
								<Label for="priority">Set Priority Score (Optional)</Label>
								<Input
									id="priority"
									type="number"
									min="1"
									max="10"
									bind:value={actionData.priority_score}
									placeholder="Leave empty to keep current priority"
									class="mt-1 w-32"
								/>
							</div>
						</div>
					{:else if selectedAction === 'priority'}
						<div class="space-y-3">
							<div>
								<Label for="priority">New Priority Score (Required)</Label>
								<div class="flex items-center gap-4 mt-1">
									<Input
										id="priority"
										type="number"
										min="1"
										max="10"
										bind:value={actionData.priority_score}
										placeholder="1-10"
										class="w-20"
										required
									/>
									<Progress value={(actionData.priority_score || 0) * 10} class="flex-1 h-2" />
									<span class="text-sm font-medium">{actionData.priority_score || 0}/10</span>
								</div>
							</div>
							
							<div class="text-xs text-muted-foreground">
								<strong>Priority Guidelines:</strong>
								<ul class="list-disc list-inside mt-1 space-y-1">
									<li>1-3: Low priority - process when resources available</li>
									<li>4-6: Normal priority - standard processing queue</li>
									<li>7-10: High priority - process as soon as possible</li>
								</ul>
							</div>
						</div>
					{:else if selectedAction === 'manual_process'}
						<div class="space-y-3">
							<div>
								<Label for="reasoning">Manual Processing Justification (Required)</Label>
								<Textarea
									id="reasoning"
									bind:value={actionData.reasoning}
									placeholder="Explain why these filtered pages need manual processing..."
									class="mt-1"
									rows="3"
									required
								/>
							</div>
							
							<div>
								<Label for="force_mode">Processing Mode</Label>
								<Select bind:value={actionData.force_mode}>
									<SelectTrigger class="mt-1">
										<SelectValue placeholder="Select processing mode" />
									</SelectTrigger>
									<SelectContent>
										<SelectItem value="standard">Standard Processing</SelectItem>
										<SelectItem value="aggressive">Aggressive Processing (ignore most filters)</SelectItem>
										<SelectItem value="bypass_all">Bypass All Filters (use with caution)</SelectItem>
									</SelectContent>
								</Select>
							</div>
						</div>
					{:else if selectedAction === 'skip' || selectedAction === 'delete' || selectedAction === 'archive'}
						<div class="space-y-3">
							<div>
								<Label for="reasoning">Reason for {selectedAction.replace('_', ' ')} (Required)</Label>
								<Textarea
									id="reasoning"
									bind:value={actionData.reasoning}
									placeholder="Explain why these pages should be {selectedAction === 'delete' ? 'permanently deleted' : selectedAction}d..."
									class="mt-1"
									rows="3"
									required
								/>
							</div>
							
							{#if selectedAction === 'delete'}
								<Alert>
									<AlertTriangle class="h-4 w-4" />
									<AlertDescription>
										<strong>Warning:</strong> This action permanently deletes pages and cannot be undone.
										Make sure you have backups if needed.
									</AlertDescription>
								</Alert>
							{/if}
						</div>
					{:else}
						<Alert>
							<Info class="h-4 w-4" />
							<AlertDescription>
								This operation doesn't require additional configuration. Click Next to continue.
							</AlertDescription>
						</Alert>
					{/if}
				</div>
			{/if}
			
			<!-- Step 2: Preview -->
			{#if currentStep === 2}
				<div class="space-y-4">
					<div>
						<h3 class="text-lg font-semibold mb-2">Preview Changes</h3>
						<p class="text-sm text-muted-foreground">
							Review the changes that will be made to {selectedPageIds.length} pages.
						</p>
					</div>
					
					{#if loading}
						<div class="flex items-center justify-center py-8">
							<RefreshCw class="h-6 w-6 animate-spin mr-2" />
							<span>Generating preview...</span>
						</div>
					{:else if previewData}
						<div class="space-y-4">
							<!-- Summary -->
							<Card class="p-4">
								<h4 class="font-semibold mb-3">Operation Summary</h4>
								<div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
									<div>
										<Label class="text-xs text-muted-foreground">Operation</Label>
										<p class="font-medium">{selectedActionConfig?.label}</p>
									</div>
									<div>
										<Label class="text-xs text-muted-foreground">Pages Affected</Label>
										<p class="font-medium">{previewData.affected_count || selectedPageIds.length}</p>
									</div>
									<div>
										<Label class="text-xs text-muted-foreground">Estimated Time</Label>
										<p class="font-medium">{previewData.estimated_duration || selectedActionConfig?.estimatedTime}</p>
									</div>
								</div>
							</Card>
							
							<!-- Changes Preview -->
							{#if previewData.changes && previewData.changes.length > 0}
								<Card class="p-4">
									<h4 class="font-semibold mb-3">Proposed Changes</h4>
									<div class="max-h-64 overflow-y-auto space-y-2">
										{#each previewData.changes.slice(0, 10) as change}
											<div class="flex items-center gap-3 text-sm p-2 bg-muted rounded">
												<Badge variant="outline" class="text-xs">
													{change.field}
												</Badge>
												<span class="text-muted-foreground truncate">{change.url}</span>
												<ArrowRight class="h-3 w-3 text-muted-foreground" />
												<span class="font-medium">{change.new_value}</span>
											</div>
										{/each}
										
										{#if previewData.changes.length > 10}
											<p class="text-xs text-muted-foreground text-center">
												...and {previewData.changes.length - 10} more changes
											</p>
										{/if}
									</div>
								</Card>
							{/if}
							
							<!-- Warnings -->
							{#if previewData.warnings && previewData.warnings.length > 0}
								<Alert>
									<AlertTriangle class="h-4 w-4" />
									<AlertDescription>
										<strong>Warnings:</strong>
										<ul class="list-disc list-inside mt-2">
											{#each previewData.warnings as warning}
												<li class="text-sm">{warning}</li>
											{/each}
										</ul>
									</AlertDescription>
								</Alert>
							{/if}
						</div>
					{/if}
				</div>
			{/if}
			
			<!-- Step 3: Execute -->
			{#if currentStep === 3}
				<div class="space-y-4">
					<div>
						<h3 class="text-lg font-semibold mb-2">Execute Operation</h3>
						<p class="text-sm text-muted-foreground">
							{#if isExecuting}
								Operation in progress...
							{:else}
								Click Execute to start the bulk operation.
							{/if}
						</p>
					</div>
					
					{#if isExecuting}
						<!-- Progress Display -->
						<Card class="p-4">
							<div class="space-y-4">
								<div class="flex items-center justify-between">
									<h4 class="font-semibold">Progress</h4>
									<Badge variant={isPaused ? 'outline' : 'default'}>
										{isPaused ? 'Paused' : 'Running'}
									</Badge>
								</div>
								
								<div class="space-y-2">
									<div class="flex justify-between text-sm">
										<span>Completed: {completedItems} / {selectedPageIds.length}</span>
										<span>{Math.round(progressValue)}%</span>
									</div>
									<Progress value={progressValue} class="h-2" />
									<p class="text-xs text-muted-foreground">{progressMessage}</p>
								</div>
								
								<!-- Control Buttons -->
								<div class="flex gap-2">
									{#if isPaused}
										<Button size="sm" onclick={resumeOperation}>
											<Play class="h-3 w-3 mr-1" />
											Resume
										</Button>
									{:else}
										<Button variant="outline" size="sm" onclick={pauseOperation}>
											<Pause class="h-3 w-3 mr-1" />
											Pause
										</Button>
									{/if}
									
									<Button variant="destructive" size="sm" onclick={cancelOperation}>
										<Square class="h-3 w-3 mr-1" />
										Cancel
									</Button>
								</div>
							</div>
						</Card>
					{:else}
						<!-- Execution Summary -->
						<Card class="p-4">
							<div class="space-y-3">
								<h4 class="font-semibold">Ready to Execute</h4>
								
								<div class="grid grid-cols-2 gap-4 text-sm">
									<div>
										<Label class="text-xs text-muted-foreground">Operation</Label>
										<p class="font-medium">{selectedActionConfig?.label}</p>
									</div>
									<div>
										<Label class="text-xs text-muted-foreground">Pages</Label>
										<p class="font-medium">{selectedPageIds.length}</p>
									</div>
								</div>
								
								{#if actionData.reasoning}
									<div>
										<Label class="text-xs text-muted-foreground">Reasoning</Label>
										<p class="text-sm bg-muted p-2 rounded">{actionData.reasoning}</p>
									</div>
								{/if}
							</div>
						</Card>
					{/if}
				</div>
			{/if}
			
			<!-- Step 4: Complete -->
			{#if currentStep === 4}
				<div class="space-y-4">
					<div class="text-center">
						<CheckCircle class="h-12 w-12 text-green-600 mx-auto mb-4" />
						<h3 class="text-lg font-semibold mb-2">Operation Complete!</h3>
						<p class="text-sm text-muted-foreground">
							Successfully processed {completedItems} out of {selectedPageIds.length} pages.
						</p>
					</div>
					
					<Card class="p-4">
						<h4 class="font-semibold mb-3">Summary</h4>
						<div class="grid grid-cols-2 gap-4 text-sm">
							<div>
								<Label class="text-xs text-muted-foreground">Operation</Label>
								<p class="font-medium">{selectedActionConfig?.label}</p>
							</div>
							<div>
								<Label class="text-xs text-muted-foreground">Success Rate</Label>
								<p class="font-medium">{Math.round((completedItems / selectedPageIds.length) * 100)}%</p>
							</div>
						</div>
					</Card>
					
					<div class="flex gap-2 justify-center">
						<Button onclick={() => dispatch('close')}>
							Close
						</Button>
						<Button variant="outline" onclick={resetWizard}>
							Start New Operation
						</Button>
					</div>
				</div>
			{/if}
			
			<!-- Navigation Buttons -->
			{#if currentStep < 4}
				<div class="flex justify-between pt-6 border-t">
					<Button 
						variant="outline" 
						onclick={handlePrevStep}
						disabled={currentStep === 0 || loading || isExecuting}
					>
						Previous
					</Button>
					
					<Button 
						onclick={handleNextStep}
						disabled={!canProceed || loading || isExecuting}
						class={currentStep === 3 && !isExecuting ? 'bg-red-600 hover:bg-red-700' : ''}
					>
						{#if loading}
							<RefreshCw class="h-3 w-3 mr-2 animate-spin" />
						{/if}
						{currentStep === 3 ? 'Execute' : 'Next'}
					</Button>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>