<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import { 
		Clock,
		Activity,
		CheckCircle,
		AlertTriangle,
		Ban,
		X,
		Filter,
		Search
	} from 'lucide-svelte';

	export let projectId: number;
	export let sessions: any[] = [];

	const dispatch = createEventDispatcher<{
		filtersChange: {
			status: string[];
			sessionId: number | null;
			searchQuery: string;
			dateRange: { from: string | null; to: string | null };
			contentType: string[];
			hasErrors: boolean | null;
		};
	}>();

	// Filter states
	let selectedStatuses: string[] = [];
	let selectedSessionId: number | null = null;
	let searchQuery = '';
	let dateFrom = '';
	let dateTo = '';
	let selectedContentTypes: string[] = [];
	let hasErrors: boolean | null = null;
	let showOnlyRetries = false;

	// Available status options
	const statusOptions = [
		{ value: 'pending', label: 'Pending', icon: Clock, color: 'default' },
		{ value: 'in_progress', label: 'In Progress', icon: Activity, color: 'default' },
		{ value: 'completed', label: 'Completed', icon: CheckCircle, color: 'outline' },
		{ value: 'failed', label: 'Failed', icon: AlertTriangle, color: 'destructive' },
		{ value: 'skipped', label: 'Skipped', icon: Ban, color: 'secondary' }
	];

	const contentTypeOptions = [
		{ value: 'text/html', label: 'HTML' },
		{ value: 'application/pdf', label: 'PDF' },
		{ value: 'text/plain', label: 'Text' },
		{ value: 'application/json', label: 'JSON' },
		{ value: 'text/xml', label: 'XML' }
	];

	function toggleStatus(status: string) {
		if (selectedStatuses.includes(status)) {
			selectedStatuses = selectedStatuses.filter(s => s !== status);
		} else {
			selectedStatuses = [...selectedStatuses, status];
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
		selectedSessionId = null;
		searchQuery = '';
		dateFrom = '';
		dateTo = '';
		selectedContentTypes = [];
		hasErrors = null;
		showOnlyRetries = false;
		emitFiltersChange();
	}

	function emitFiltersChange() {
		dispatch('filtersChange', {
			status: selectedStatuses,
			sessionId: selectedSessionId,
			searchQuery: searchQuery.trim(),
			dateRange: {
				from: dateFrom || null,
				to: dateTo || null
			},
			contentType: selectedContentTypes,
			hasErrors: hasErrors
		});
	}

	// Emit changes when values change
	$: if (selectedSessionId !== null) emitFiltersChange();
	$: if (hasErrors !== null) emitFiltersChange();
	
	// Debounce search query
	let searchTimeout: NodeJS.Timeout;
	$: {
		clearTimeout(searchTimeout);
		searchTimeout = setTimeout(() => {
			emitFiltersChange();
		}, 300);
	}

	$: activeFiltersCount = selectedStatuses.length + 
		selectedContentTypes.length + 
		(selectedSessionId ? 1 : 0) + 
		(searchQuery ? 1 : 0) + 
		(dateFrom || dateTo ? 1 : 0) + 
		(hasErrors !== null ? 1 : 0);
</script>

<Card class="w-full">
	<CardHeader class="pb-3">
		<div class="flex items-center justify-between">
			<CardTitle class="text-base flex items-center gap-2">
				<Filter class="h-4 w-4" />
				Filters
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

	<CardContent class="space-y-4">
		<!-- Search -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Search URLs</Label>
			<div class="relative">
				<Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
				<Input
					bind:value={searchQuery}
					placeholder="Search by URL, domain, or error message..."
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

		<!-- Status Filters -->
		<div class="space-y-2">
			<Label class="text-sm font-medium">Status</Label>
			<div class="flex flex-wrap gap-2">
				{#each statusOptions as status}
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
					Has Errors
				</button>
				<button
					class="px-2.5 py-1.5 rounded-md text-xs border transition-colors
					{hasErrors === false 
						? 'bg-green-500 text-white border-green-500' 
						: 'bg-background hover:bg-muted border-border'}"
					onclick={() => hasErrors = hasErrors === false ? null : false}
				>
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

		<!-- Active Filters Summary -->
		{#if activeFiltersCount > 0}
			<div class="pt-2 border-t">
				<Label class="text-xs text-muted-foreground mb-2 block">Active Filters:</Label>
				<div class="flex flex-wrap gap-1">
					{#each selectedStatuses as status}
						<Badge variant="secondary" class="text-xs">
							{status}
							<button onclick={() => toggleStatus(status)} class="ml-1 hover:text-destructive">
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
				</div>
			</div>
		{/if}
	</CardContent>
</Card>