<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { Card, CardContent, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { Switch } from '$lib/components/ui/switch';
	import { Slider } from '$lib/components/ui/slider';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Separator } from '$lib/components/ui/separator';
	import { 
		Settings,
		Clock,
		Calendar,
		BarChart3,
		Zap,
		Target,
		AlertTriangle,
		CheckCircle2,
		Info,
		RefreshCw,
		Save
	} from 'lucide-svelte';
	
	import { incrementalScrapingApi, type IncrementalScrapingConfig } from '$lib/services/incrementalScrapingApi';

	export let domainId: number;
	export let config: any;
	export let canControl: boolean = true;

	const dispatch = createEventDispatcher();

	let localConfig: IncrementalScrapingConfig = {
		enabled: false,
		overlap_days: 3,
		auto_schedule: false,
		max_pages_per_run: 1000,
		run_frequency_hours: 24,
		priority_domains: [],
		gap_fill_threshold_days: 7
	};

	let isDirty = false;
	let isLoading = false;
	let isSaving = false;
	let error = '';
	let successMessage = '';

	// Initialize local config from props
	$: {
		if (config) {
			localConfig = {
				enabled: config.enabled || false,
				overlap_days: config.overlap_days || 3,
				auto_schedule: config.auto_schedule || false,
				max_pages_per_run: config.max_pages_per_run || 1000,
				run_frequency_hours: config.run_frequency_hours || 24,
				priority_domains: config.priority_domains || [],
				gap_fill_threshold_days: config.gap_fill_threshold_days || 7
			};
		}
	}

	// Track changes
	function markDirty() {
		isDirty = true;
		error = '';
		successMessage = '';
	}

	async function saveConfiguration() {
		if (!canControl || isSaving) return;
		
		try {
			isSaving = true;
			error = '';
			successMessage = '';
			
			const updatedStatus = await incrementalScrapingApi.updateDomainConfig(
				domainId,
				localConfig
			);
			
			isDirty = false;
			successMessage = 'Configuration updated successfully';
			
			dispatch('configUpdated', updatedStatus);
			
			// Clear success message after 3 seconds
			setTimeout(() => {
				successMessage = '';
			}, 3000);
			
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save configuration';
			console.error('Save configuration error:', e);
		} finally {
			isSaving = false;
		}
	}

	function resetConfiguration() {
		if (config) {
			localConfig = {
				enabled: config.enabled || false,
				overlap_days: config.overlap_days || 3,
				auto_schedule: config.auto_schedule || false,
				max_pages_per_run: config.max_pages_per_run || 1000,
				run_frequency_hours: config.run_frequency_hours || 24,
				priority_domains: config.priority_domains || [],
				gap_fill_threshold_days: config.gap_fill_threshold_days || 7
			};
		}
		isDirty = false;
		error = '';
		successMessage = '';
	}

	function getFrequencyLabel(hours: number) {
		if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''}`;
		const days = hours / 24;
		if (days === 1) return '1 day';
		if (days < 7) return `${days} days`;
		if (days === 7) return '1 week';
		return `${Math.floor(days / 7)} week${Math.floor(days / 7) !== 1 ? 's' : ''}`;
	}

	function getRecommendation(setting: string, value: any) {
		switch (setting) {
			case 'overlap_days':
				if (value < 1) return { type: 'warning', message: 'Too low - may miss content between runs' };
				if (value > 7) return { type: 'info', message: 'Higher overlap increases processing time' };
				return null;
			case 'max_pages_per_run':
				if (value < 100) return { type: 'warning', message: 'Very low - may limit effectiveness' };
				if (value > 5000) return { type: 'warning', message: 'Very high - may cause timeouts' };
				return null;
			case 'run_frequency_hours':
				if (value < 12) return { type: 'warning', message: 'Very frequent - may overwhelm server' };
				if (value > 168) return { type: 'info', message: 'Infrequent runs may miss time-sensitive content' };
				return null;
			case 'gap_fill_threshold_days':
				if (value < 3) return { type: 'info', message: 'Sensitive to small gaps' };
				if (value > 30) return { type: 'warning', message: 'May miss important gaps' };
				return null;
			default:
				return null;
		}
	}
</script>

<div class="space-y-6">
	{#if error}
		<Alert variant="destructive">
			<AlertTriangle class="h-4 w-4" />
			<AlertDescription>{error}</AlertDescription>
		</Alert>
	{/if}

	{#if successMessage}
		<Alert>
			<CheckCircle2 class="h-4 w-4" />
			<AlertDescription class="text-green-800">{successMessage}</AlertDescription>
		</Alert>
	{/if}

	<Card>
		<CardHeader>
			<CardTitle class="flex items-center justify-between">
				<div class="flex items-center space-x-2">
					<Settings class="h-5 w-5" />
					<span>Configuration</span>
				</div>
				{#if isDirty}
					<Badge variant="secondary">
						Unsaved Changes
					</Badge>
				{/if}
			</CardTitle>
		</CardHeader>
		<CardContent class="space-y-6">
			<!-- Basic Settings -->
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<div class="space-y-1">
						<Label class="text-base font-medium">Enable Incremental Scraping</Label>
						<p class="text-sm text-gray-600">
							Automatically maintain coverage by scraping new content and filling gaps
						</p>
					</div>
					<Switch
						checked={localConfig.enabled}
						onCheckedChange={(checked) => {
							localConfig.enabled = checked;
							markDirty();
						}}
						disabled={!canControl}
					/>
				</div>

				<Separator />

				<div class="flex items-center justify-between">
					<div class="space-y-1">
						<Label class="text-base font-medium">Auto-Schedule Runs</Label>
						<p class="text-sm text-gray-600">
							Automatically schedule regular incremental scraping based on frequency
						</p>
					</div>
					<Switch
						checked={localConfig.auto_schedule}
						onCheckedChange={(checked) => {
							localConfig.auto_schedule = checked;
							markDirty();
						}}
						disabled={!canControl || !localConfig.enabled}
					/>
				</div>
			</div>

			<Separator />

			<!-- Timing Configuration -->
			<div class="space-y-4">
				<h3 class="text-lg font-medium flex items-center space-x-2">
					<Clock class="h-5 w-5" />
					<span>Timing Settings</span>
				</h3>

				<!-- Overlap Days -->
				<div class="space-y-3">
					<div class="flex items-center justify-between">
						<Label class="font-medium">Overlap Days</Label>
						<span class="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
							{localConfig.overlap_days} day{localConfig.overlap_days !== 1 ? 's' : ''}
						</span>
					</div>
					<Slider
						bind:value={[localConfig.overlap_days]}
						min={0}
						max={14}
						step={1}
						disabled={!canControl || !localConfig.enabled}
						onValueChange={() => markDirty()}
						class="w-full"
					/>
					<p class="text-xs text-gray-600">
						Days of overlap with previous runs to ensure no content is missed
					</p>
					{#if getRecommendation('overlap_days', localConfig.overlap_days)}
						{@const rec = getRecommendation('overlap_days', localConfig.overlap_days)}
						<div class="flex items-center space-x-2 text-xs {rec.type === 'warning' ? 'text-yellow-600' : 'text-blue-600'}">
							<Info class="h-3 w-3" />
							<span>{rec.message}</span>
						</div>
					{/if}
				</div>

				<!-- Run Frequency -->
				<div class="space-y-3">
					<div class="flex items-center justify-between">
						<Label class="font-medium">Run Frequency</Label>
						<span class="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
							{getFrequencyLabel(localConfig.run_frequency_hours)}
						</span>
					</div>
					<Slider
						bind:value={[localConfig.run_frequency_hours]}
						min={6}
						max={168}
						step={6}
						disabled={!canControl || !localConfig.enabled || !localConfig.auto_schedule}
						onValueChange={() => markDirty()}
						class="w-full"
					/>
					<p class="text-xs text-gray-600">
						How often to run automatic incremental scraping
					</p>
					{#if getRecommendation('run_frequency_hours', localConfig.run_frequency_hours)}
						{@const rec = getRecommendation('run_frequency_hours', localConfig.run_frequency_hours)}
						<div class="flex items-center space-x-2 text-xs {rec.type === 'warning' ? 'text-yellow-600' : 'text-blue-600'}">
							<Info class="h-3 w-3" />
							<span>{rec.message}</span>
						</div>
					{/if}
				</div>
			</div>

			<Separator />

			<!-- Performance Configuration -->
			<div class="space-y-4">
				<h3 class="text-lg font-medium flex items-center space-x-2">
					<BarChart3 class="h-5 w-5" />
					<span>Performance Settings</span>
				</h3>

				<!-- Max Pages Per Run -->
				<div class="space-y-3">
					<Label class="font-medium">Max Pages Per Run</Label>
					<div class="flex items-center space-x-3">
						<Input
							type="number"
							bind:value={localConfig.max_pages_per_run}
							min="50"
							max="10000"
							step="50"
							disabled={!canControl || !localConfig.enabled}
							onchange={markDirty}
							class="w-32"
						/>
						<span class="text-sm text-gray-600">pages</span>
					</div>
					<p class="text-xs text-gray-600">
						Maximum number of pages to process in a single incremental run
					</p>
					{#if getRecommendation('max_pages_per_run', localConfig.max_pages_per_run)}
						{@const rec = getRecommendation('max_pages_per_run', localConfig.max_pages_per_run)}
						<div class="flex items-center space-x-2 text-xs {rec.type === 'warning' ? 'text-yellow-600' : 'text-blue-600'}">
							<Info class="h-3 w-3" />
							<span>{rec.message}</span>
						</div>
					{/if}
				</div>

				<!-- Gap Fill Threshold -->
				<div class="space-y-3">
					<div class="flex items-center justify-between">
						<Label class="font-medium">Gap Fill Threshold</Label>
						<span class="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
							{localConfig.gap_fill_threshold_days} day{localConfig.gap_fill_threshold_days !== 1 ? 's' : ''}
						</span>
					</div>
					<Slider
						bind:value={[localConfig.gap_fill_threshold_days]}
						min={1}
						max={60}
						step={1}
						disabled={!canControl || !localConfig.enabled}
						onValueChange={() => markDirty()}
						class="w-full"
					/>
					<p class="text-xs text-gray-600">
						Minimum gap size (in days) to trigger automatic gap filling
					</p>
					{#if getRecommendation('gap_fill_threshold_days', localConfig.gap_fill_threshold_days)}
						{@const rec = getRecommendation('gap_fill_threshold_days', localConfig.gap_fill_threshold_days)}
						<div class="flex items-center space-x-2 text-xs {rec.type === 'warning' ? 'text-yellow-600' : 'text-blue-600'}">
							<Info class="h-3 w-3" />
							<span>{rec.message}</span>
						</div>
					{/if}
				</div>
			</div>

			<Separator />

			<!-- Action Buttons -->
			<div class="flex items-center justify-between pt-4">
				<div class="text-sm text-gray-600">
					{#if isDirty}
						<span>You have unsaved changes</span>
					{:else}
						<span>Configuration is up to date</span>
					{/if}
				</div>
				
				<div class="flex items-center space-x-3">
					<Button
						variant="outline"
						onclick={resetConfiguration}
						disabled={!canControl || !isDirty}
					>
						<RefreshCw class="h-4 w-4 mr-2" />
						Reset
					</Button>
					
					<Button
						onclick={saveConfiguration}
						disabled={!canControl || !isDirty || isSaving}
					>
						{#if isSaving}
							<RefreshCw class="h-4 w-4 mr-2 animate-spin" />
						{:else}
							<Save class="h-4 w-4 mr-2" />
						{/if}
						Save Configuration
					</Button>
				</div>
			</div>

			<!-- Configuration Summary -->
			<Alert>
				<Info class="h-4 w-4" />
				<AlertDescription>
					<strong>Summary:</strong>
					{#if localConfig.enabled}
						Incremental scraping is <span class="text-green-600">enabled</span> with 
						{localConfig.overlap_days} day overlap,
						{#if localConfig.auto_schedule}
							running every {getFrequencyLabel(localConfig.run_frequency_hours)},
						{:else}
							manual scheduling,
						{/if}
						processing up to {localConfig.max_pages_per_run.toLocaleString()} pages per run.
						Gaps of {localConfig.gap_fill_threshold_days}+ days will be automatically filled.
					{:else}
						Incremental scraping is <span class="text-gray-600">disabled</span>.
						Enable it to maintain continuous coverage of this domain.
					{/if}
				</AlertDescription>
			</Alert>
		</CardContent>
	</Card>
</div>