<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import { Separator } from '$lib/components/ui/separator';
	import { 
		Clock,
		Activity,
		CheckCircle,
		AlertTriangle,
		Ban,
		X,
		Filter,
		Search,
		XCircle,
		AlertCircle,
		FileText,
		Eye,
		ShieldCheck,
		Info
	} from 'lucide-svelte';

	export let projectId: number;
	export let sessions: any[] = [];

	const dispatch = createEventDispatcher<{
		filtersChange: {
			status: string[];
			filterCategory: string[];
			sessionId: number | null;
			searchQuery: string;
			dateRange: { from: string | null; to: string | null };
			contentType: string[];
			hasErrors: boolean | null;
			isManuallyOverridden: boolean | null;
			priorityScore: { min: number | null; max: number | null };
			showOnlyProcessable: boolean;
		};
	}>();

	// Enhanced filter states
	let selectedStatuses: string[] = [];
	let selectedFilterCategories: string[] = [];
	let selectedSessionId: number | null = null;
	let searchQuery = '';
	let dateFrom = '';
	let dateTo = '';
	let selectedContentTypes: string[] = [];
	let hasErrors: boolean | null = null;
	let isManuallyOverridden: boolean | null = null;
	let minPriorityScore: number | null = null;
	let maxPriorityScore: number | null = null;
	let showOnlyProcessable = false;

	// Enhanced status options including filtering states
	const statusOptions = [
		{ value: 'pending', label: 'Pending', icon: Clock, color: 'default', group: 'active' },
		{ value: 'in_progress', label: 'In Progress', icon: Activity, color: 'default', group: 'active' },
		{ value: 'completed', label: 'Complete', icon: CheckCircle, color: 'success', group: 'complete' },
		{ value: 'failed', label: 'Failed', icon: AlertTriangle, color: 'destructive', group: 'complete' },
		{ value: 'skipped', label: 'Skipped', icon: Ban, color: 'secondary', group: 'complete' },
		{ value: 'filtered_duplicate', label: 'Duplicate', icon: XCircle, color: 'outline', group: 'filtered' },
		{ value: 'filtered_list_page', label: 'List Page', icon: Filter, color: 'outline', group: 'filtered' },
		{ value: 'filtered_low_quality', label: 'Low Quality', icon: AlertCircle, color: 'warning', group: 'filtered' },
		{ value: 'filtered_size', label: 'Size Filtered', icon: FileText, color: 'outline', group: 'filtered' },
		{ value: 'filtered_type', label: 'Type Filtered', icon: Ban, color: 'secondary', group: 'filtered' },
		{ value: 'filtered_custom', label: 'Custom Filter', icon: Filter, color: 'outline', group: 'filtered' },
		{ value: 'awaiting_manual_review', label: 'Awaiting Review', icon: Eye, color: 'warning', group: 'review' },
		{ value: 'manually_approved', label: 'Manually Approved', icon: ShieldCheck, color: 'success', group: 'review' }
	];

	const filterCategoryOptions = [
		{ value: 'content_quality', label: 'Content Quality', color: 'warning' },
		{ value: 'duplicate', label: 'Duplicate Content', color: 'outline' },
		{ value: 'format', label: 'File Format', color: 'secondary' },
		{ value: 'size', label: 'Content Size', color: 'outline' },
		{ value: 'custom', label: 'Custom Rules', color: 'default' },
		{ value: 'domain_rules', label: 'Domain Rules', color: 'default' },
		{ value: 'list_detection', label: 'List Detection', color: 'outline' }
	];

	const contentTypeOptions = [
		{ value: 'text/html', label: 'HTML' },
		{ value: 'application/pdf', label: 'PDF' },
		{ value: 'text/plain', label: 'Text' },
		{ value: 'application/json', label: 'JSON' },
		{ value: 'text/xml', label: 'XML' },
		{ value: 'application/msword', label: 'Word' },
		{ value: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', label: 'DOCX' }
	];

	// Group status options for better organization
	const statusGroups = {
		active: statusOptions.filter(s => s.group === 'active'),
		complete: statusOptions.filter(s => s.group === 'complete'),
		filtered: statusOptions.filter(s => s.group === 'filtered'),
		review: statusOptions.filter(s => s.group === 'review')
	};

	function toggleStatus(status: string) {
		if (selectedStatuses.includes(status)) {
			selectedStatuses = selectedStatuses.filter(s => s !== status);
		} else {
			selectedStatuses = [...selectedStatuses, status];
		}
		emitFiltersChange();
	}

	function toggleFilterCategory(category: string) {
		if (selectedFilterCategories.includes(category)) {
			selectedFilterCategories = selectedFilterCategories.filter(c => c !== category);
		} else {
			selectedFilterCategories = [...selectedFilterCategories, category];
		}
		emitFiltersChange();
	}

	function toggleContentType(contentType: string) {
		if (selectedContentTypes.includes(contentType)) {
			selectedContentTypes = selectedContentTypes.filter(ct => ct !== contentType);
		} else {
			selectedContentTypes = [...selectedContentTypes, contentType];
		}
		emitFiltersChange();
	}

	function clearFilters() {
		selectedStatuses = [];
		selectedFilterCategories = [];
		selectedSessionId = null;
		searchQuery = '';
		dateFrom = '';
		dateTo = '';
		selectedContentTypes = [];
		hasErrors = null;
		isManuallyOverridden = null;
		minPriorityScore = null;
		maxPriorityScore = null;
		showOnlyProcessable = false;
		emitFiltersChange();
	}

	function showAllUrls() {
		// Show everything including filtered content
		selectedStatuses = [];
		selectedFilterCategories = [];
		isManuallyOverridden = null;
		showOnlyProcessable = false;
		emitFiltersChange();
	}

	function showOnlyFiltered() {
		selectedStatuses = statusOptions.filter(s => s.group === 'filtered').map(s => s.value);
		emitFiltersChange();
	}

	function showOnlyActive() {
		selectedStatuses = statusOptions.filter(s => s.group === 'active').map(s => s.value);
		emitFiltersChange();
	}

	function showOnlyProcessablePages() {
		showOnlyProcessable = true;
		// Focus on filtered content that can be manually processed
		selectedStatuses = statusOptions.filter(s => s.group === 'filtered' || s.value === 'awaiting_manual_review').map(s => s.value);
		isManuallyOverridden = false;
		emitFiltersChange();
	}

	function emitFiltersChange() {
		dispatch('filtersChange', {
			status: selectedStatuses,
			filterCategory: selectedFilterCategories,
			sessionId: selectedSessionId,
			searchQuery: searchQuery.trim(),
			dateRange: {
				from: dateFrom || null,
				to: dateTo || null
			},
			contentType: selectedContentTypes,
			hasErrors: hasErrors,
			isManuallyOverridden: isManuallyOverridden,
			priorityScore: {
				min: minPriorityScore,
				max: maxPriorityScore
			},
			showOnlyProcessable: showOnlyProcessable
		});
	}

	// Emit changes when values change
	$: if (selectedSessionId !== null) emitFiltersChange();
	$: if (hasErrors !== null) emitFiltersChange();
	$: if (isManuallyOverridden !== null) emitFiltersChange();
	$: if (showOnlyProcessable) emitFiltersChange();
	
	// Debounce search query
	let searchTimeout: NodeJS.Timeout;
	$: {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			emitFiltersChange();
		}, 300);
	}

	$: activeFiltersCount = selectedStatuses.length + 
		selectedFilterCategories.length +
		selectedContentTypes.length + 
		(selectedSessionId ? 1 : 0) + 
		(searchQuery ? 1 : 0) + 
		(dateFrom || dateTo ? 1 : 0) + 
		(hasErrors !== null ? 1 : 0) + 
		(isManuallyOverridden !== null ? 1 : 0) +
		(minPriorityScore !== null || maxPriorityScore !== null ? 1 : 0) +
		(showOnlyProcessable ? 1 : 0);
</script>

<Card class="w-full">
	<CardHeader class="pb-3">
		<div class="flex items-center justify-between">
			<CardTitle class="text-base flex items-center gap-2">
				<Filter class="h-4 w-4" />
				Enhanced Filters
				{#if activeFiltersCount > 0}
					<Badge variant="secondary" class="text-xs">{activeFiltersCount}</Badge>
				{/if}
			</CardTitle>
			{#if activeFiltersCount > 0}
				<Button variant="ghost" size="sm" onclick={clearFilters} class="h-6 text-xs">
					Clear All
				</Button>
			{/if}
		</div>
	</CardHeader>

	<CardContent class="space-y-6">
		<!-- Quick Filter Actions -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Quick Actions</Label>
			<div class="flex flex-wrap gap-2">
				<Button
					variant="outline"
					size="sm"
					onclick={showAllUrls}
					class="h-7 px-3 text-xs"
				>
					<Eye class="h-3 w-3 mr-1" />
					Show All URLs
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={showOnlyFiltered}
					class="h-7 px-3 text-xs"
				>
					<Filter class="h-3 w-3 mr-1" />
					Filtered Only
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={showOnlyActive}
					class="h-7 px-3 text-xs"
				>
					<Activity class="h-3 w-3 mr-1" />
					Active Only
				</Button>
				<Button
					variant="outline"
					size="sm"
					onclick={showOnlyProcessablePages}
					class="h-7 px-3 text-xs bg-green-50 hover:bg-green-100 border-green-200"
				>
					<ShieldCheck class="h-3 w-3 mr-1" />
					Can Override
				</Button>
			</div>
		</div>

		<Separator />

		<!-- Search -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Search URLs</Label>
			<div class="relative">
				<Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
				<Input
					bind:value={searchQuery}
					placeholder="Search by URL, domain, filter reason, or error message..."
					class="pl-10 text-sm"
					on:keydown={(e) => {
						if (e.key === 'Enter') {
							clearTimeout(searchTimeout);
							emitFiltersChange();
						}
					}}
				/>
			</div>
		</div>

		<!-- Processing Status Filters -->
		<div class="space-y-3">
			<Label class="text-sm font-medium">Processing Status</Label>
			
			<!-- Active Processing -->
			<div class="space-y-2">
				<Label class="text-xs text-muted-foreground font-medium">Active</Label>
				<div class="flex flex-wrap gap-2">
					{#each statusGroups.active as status}
						{@const isSelected = selectedStatuses.includes(status.value)}
						<button
							class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs border transition-colors
							{isSelected 
								? 'bg-primary text-primary-foreground border-primary' 
								: 'bg-background hover:bg-muted border-border'}"
							onclick={() => toggleStatus(status.value)}
						>
							<svelte:component this={status.icon} class="h-3 w-3" />
							{status.label}
						</button>
					{/each}
				</div>
			</div>

			<!-- Completed Processing -->
			<div class="space-y-2">
				<Label class="text-xs text-muted-foreground font-medium">Completed</Label>
				<div class="flex flex-wrap gap-2">
					{#each statusGroups.complete as status}
						{@const isSelected = selectedStatuses.includes(status.value)}
						<button
							class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs border transition-colors
							{isSelected 
								? 'bg-primary text-primary-foreground border-primary' 
								: 'bg-background hover:bg-muted border-border'}"
							onclick={() => toggleStatus(status.value)}
						>
							<svelte:component this={status.icon} class="h-3 w-3" />
							{status.label}
						</button>
					{/each}
				</div>
			</div>

			<!-- Filtered Content -->
			<div class="space-y-2">
				<Label class="text-xs text-muted-foreground font-medium">Filtered Content</Label>
				<div class="flex flex-wrap gap-2">
					{#each statusGroups.filtered as status}
						{@const isSelected = selectedStatuses.includes(status.value)}
						<button
							class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs border transition-colors
							{isSelected 
								? 'bg-amber-500 text-white border-amber-500' 
								: 'bg-amber-50 hover:bg-amber-100 border-amber-200 text-amber-800'}"
							onclick={() => toggleStatus(status.value)}
						>
							<svelte:component this={status.icon} class="h-3 w-3" />
							{status.label}
						</button>
					{/each}
				</div>
			</div>

			<!-- Manual Review -->
			<div class="space-y-2">
				<Label class="text-xs text-muted-foreground font-medium">Manual Review</Label>
				<div class="flex flex-wrap gap-2">
					{#each statusGroups.review as status}
						{@const isSelected = selectedStatuses.includes(status.value)}
						<button
							class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs border transition-colors
							{isSelected 
								? 'bg-green-500 text-white border-green-500' 
								: 'bg-green-50 hover:bg-green-100 border-green-200 text-green-800'}"
							onclick={() => toggleStatus(status.value)}
						>
							<svelte:component this={status.icon} class="h-3 w-3" />
							{status.label}
						</button>
					{/each}
				</div>
			</div>
		</div>

		<!-- Filter Categories -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Filter Categories</Label>
			<div class="flex flex-wrap gap-2">
				{#each filterCategoryOptions as category}
					{@const isSelected = selectedFilterCategories.includes(category.value)}
					<button
						class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
						{isSelected 
							? 'bg-primary text-primary-foreground border-primary' 
							: 'bg-background hover:bg-muted border-border'}"
						onclick={() => toggleFilterCategory(category.value)}
					>
						{category.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- Manual Override Status -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Override Status</Label>
			<div class="flex gap-2">
				<button
					class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
					{isManuallyOverridden === true 
						? 'bg-green-500 text-white border-green-500' 
						: 'bg-background hover:bg-muted border-border'}"
					onclick={() => isManuallyOverridden = isManuallyOverridden === true ? null : true}
				>
					<ShieldCheck class="h-3 w-3 mr-1 inline" />
					Overridden
				</button>
				<button
					class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
					{isManuallyOverridden === false 
						? 'bg-amber-500 text-white border-amber-500' 
						: 'bg-background hover:bg-muted border-border'}"
					onclick={() => isManuallyOverridden = isManuallyOverridden === false ? null : false}
				>
					<Filter class="h-3 w-3 mr-1 inline" />
					Original Filter
				</button>
			</div>
		</div>

		<!-- Priority Score Range -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Priority Score</Label>
			<div class="grid grid-cols-2 gap-2">
				<div>
					<Label class="text-xs text-muted-foreground">Min</Label>
					<Input
						type="number"
						min="1"
						max="10"
						bind:value={minPriorityScore}
						placeholder="1"
						class="text-sm"
						on:change={emitFiltersChange}
					/>
				</div>
				<div>
					<Label class="text-xs text-muted-foreground">Max</Label>
					<Input
						type="number"
						min="1"
						max="10"
						bind:value={maxPriorityScore}
						placeholder="10"
						class="text-sm"
						on:change={emitFiltersChange}
					/>
				</div>
			</div>
			<div class="text-xs text-muted-foreground">
				1-3: Low priority, 4-6: Normal, 7-10: High priority
			</div>
		</div>

		<!-- Session Filter -->
		{#if sessions.length > 0}
			<div class="space-y-2">
				<Label class="text-sm font-medium">Scrape Session</Label>
				<select
					bind:value={selectedSessionId}
					class="w-full px-3 py-1.5 text-sm border border-border rounded-md bg-background"
				>
					<option value={null}>All Sessions</option>
					{#each sessions as session}
						<option value={session.id}>
							Session #{session.id} ({session.name || 'Unnamed'}) - {session.status}
						</option>
					{/each}
				</select>
			</div>
		{/if}

		<!-- Content Type Filters -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Content Type</Label>
			<div class="flex flex-wrap gap-2">
				{#each contentTypeOptions as contentType}
					{@const isSelected = selectedContentTypes.includes(contentType.value)}
					<button
						class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
						{isSelected 
							? 'bg-primary text-primary-foreground border-primary' 
							: 'bg-background hover:bg-muted border-border'}"
						onclick={() => toggleContentType(contentType.value)}
					>
						{contentType.label}
					</button>
				{/each}
			</div>
		</div>

		<!-- Error Filters -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Error Status</Label>
			<div class="flex gap-2">
				<button
					class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
					{hasErrors === true 
						? 'bg-destructive text-destructive-foreground border-destructive' 
						: 'bg-background hover:bg-muted border-border'}"
					onclick={() => hasErrors = hasErrors === true ? null : true}
				>
					<AlertTriangle class="h-3 w-3 mr-1 inline" />
					Has Errors
				</button>
				<button
					class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
					{hasErrors === false 
						? 'bg-green-500 text-white border-green-500' 
						: 'bg-background hover:bg-muted border-border'}"
					onclick={() => hasErrors = hasErrors === false ? null : false}
				>
					<CheckCircle class="h-3 w-3 mr-1 inline" />
					No Errors
				</button>
			</div>
		</div>

		<!-- Date Range -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Date Range (Capture Date)</Label>
			<div class="grid grid-cols-2 gap-2">
				<div>
					<Label class="text-xs text-muted-foreground">From</Label>
					<Input
						type="date"
						bind:value={dateFrom}
						class="text-sm"
						on:change={emitFiltersChange}
					/>
				</div>
				<div>
					<Label class="text-xs text-muted-foreground">To</Label>
					<Input
						type="date"
						bind:value={dateTo}
						class="text-sm"
						on:change={emitFiltersChange}
					/>
				</div>
			</div>
		</div>

		<!-- Processing Options -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Processing Options</Label>
			<div class="space-y-2">
				<label class="flex items-center space-x-2 cursor-pointer">
					<input
						type="checkbox"
						bind:checked={showOnlyProcessable}
						class="w-4 h-4 rounded border-border"
					/>
					<span class="text-sm">Show only pages that can be manually processed</span>
				</label>
			</div>
		</div>

		<!-- Active Filters Summary -->
		{#if activeFiltersCount > 0}
			<div class="pt-4 border-t">
				<Label class="text-xs text-muted-foreground mb-2 block">Active Filters:</Label>
				<div class="flex flex-wrap gap-1">
					{#each selectedStatuses as status}
						<Badge variant="secondary" class="text-xs">
							{statusOptions.find(s => s.value === status)?.label || status}
							<button onclick={() => toggleStatus(status)} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/each}
					{#each selectedFilterCategories as category}
						<Badge variant="secondary" class="text-xs">
							{filterCategoryOptions.find(c => c.value === category)?.label || category}
							<button onclick={() => toggleFilterCategory(category)} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/each}
					{#each selectedContentTypes as contentType}
						<Badge variant="secondary" class="text-xs">
							{contentTypeOptions.find(ct => ct.value === contentType)?.label || contentType}
							<button onclick={() => toggleContentType(contentType)} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/each}
					{#if searchQuery}
						<Badge variant="secondary" class="text-xs">
							Search: "{searchQuery}"
							<button onclick={() => { searchQuery = ''; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
					{#if selectedSessionId}
						<Badge variant="secondary" class="text-xs">
							Session #{selectedSessionId}
							<button onclick={() => { selectedSessionId = null; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
					{#if dateFrom || dateTo}
						<Badge variant="secondary" class="text-xs">
							Date: {dateFrom || '∞'} - {dateTo || '∞'}
							<button onclick={() => { dateFrom = ''; dateTo = ''; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
					{#if hasErrors !== null}
						<Badge variant="secondary" class="text-xs">
							{hasErrors ? 'Has Errors' : 'No Errors'}
							<button onclick={() => { hasErrors = null; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
					{#if isManuallyOverridden !== null}
						<Badge variant="secondary" class="text-xs">
							{isManuallyOverridden ? 'Overridden' : 'Original Filter'}
							<button onclick={() => { isManuallyOverridden = null; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
					{#if minPriorityScore !== null || maxPriorityScore !== null}
						<Badge variant="secondary" class="text-xs">
							Priority: {minPriorityScore || 1}-{maxPriorityScore || 10}
							<button onclick={() => { minPriorityScore = null; maxPriorityScore = null; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
					{#if showOnlyProcessable}
						<Badge variant="secondary" class="text-xs">
							Processable Only
							<button onclick={() => { showOnlyProcessable = false; emitFiltersChange(); }} class="ml-1 hover:text-destructive">
								<X class="h-2 w-2" />
							</button>
						</Badge>
					{/if}
				</div>
			</div>
		{/if}
	</CardContent>
</Card>