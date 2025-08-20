<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Progress } from '$lib/components/ui/progress';
	import { Badge } from '$lib/components/ui/badge';
	import { Button } from '$lib/components/ui/button';
	import { formatDateTime, formatNumber, formatBytes, getApiUrl } from '$lib/utils';
	import { LoaderCircle, AlertCircle, CircleCheck, CircleX, Pause, Play, Square } from 'lucide-svelte';

	export let taskId: string;
	export let domainName: string = '';
	export let projectName: string = '';

	interface TaskStatus {
		task_id: string;
		status: string;
		ready: boolean;
		successful?: boolean;
		failed?: boolean;
		result?: any;
		error?: string;
		progress?: {
			current: number;
			total: number;
			status: string;
			successful?: number;
			failed?: number;
		};
	}

	const taskStatus = writable<TaskStatus | null>(null);
	const isPolling = writable(true);
	let pollInterval: NodeJS.Timeout | null = null;

	async function fetchTaskStatus() {
		try {
			const response = await fetch(getApiUrl(`/api/v1/tasks/status/${taskId}`), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}

			const data = await response.json();
			taskStatus.set(data);

			// Stop polling if task is complete
			if (data.ready && data.status !== 'PROGRESS') {
				isPolling.set(false);
			}
		} catch (error) {
			console.error('Failed to fetch task status:', error);
		}
	}

	function startPolling() {
		fetchTaskStatus(); // Initial fetch
		pollInterval = setInterval(fetchTaskStatus, 2000); // Poll every 2 seconds
		isPolling.set(true);
	}

	function stopPolling() {
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
		isPolling.set(false);
	}

	async function cancelTask() {
		try {
			const response = await fetch(getApiUrl(`/api/v1/tasks/cancel/${taskId}`), {
				method: 'DELETE',
				credentials: 'include'
			});

			if (response.ok) {
				taskStatus.update(status => ({
					...status!,
					status: 'REVOKED'
				}));
				stopPolling();
			}
		} catch (error) {
			console.error('Failed to cancel task:', error);
		}
	}

	onMount(() => {
		startPolling();
	});

	onDestroy(() => {
		stopPolling();
	});

	$: status = $taskStatus;
	$: progress = status?.progress;
	$: progressPercentage = progress ? (progress.current / progress.total) * 100 : 0;

	function getStatusColor(status: string): 'default' | 'success' | 'destructive' | 'warning' | 'info' {
		switch (status) {
			case 'SUCCESS': return 'success';
			case 'FAILURE': return 'destructive';
			case 'REVOKED': return 'destructive';
			case 'PROGRESS': return 'info';
			case 'PENDING': return 'warning';
			default: return 'default';
		}
	}

	function getStatusIcon(status: string) {
		switch (status) {
			case 'SUCCESS': return CircleCheck;
			case 'FAILURE': return CircleX;
			case 'REVOKED': return Square;
			case 'PROGRESS': return LoaderCircle;
			case 'PENDING': return LoaderCircle;
			default: return AlertCircle;
		}
	}
</script>

<Card class="w-full">
	<CardHeader class="pb-3">
		<div class="flex items-center justify-between">
			<div>
				<CardTitle class="text-lg">
					{#if domainName}
						Scraping {domainName}
					{:else}
						Scraping Progress
					{/if}
				</CardTitle>
				{#if projectName}
					<p class="text-sm text-muted-foreground mt-1">Project: {projectName}</p>
				{/if}
			</div>
			<div class="flex items-center gap-2">
				{#if status}
					<Badge variant={getStatusColor(status.status)}>
						<svelte:component 
							this={getStatusIcon(status.status)} 
							class="w-3 h-3 mr-1 {status.status === 'PROGRESS' || status.status === 'PENDING' ? 'animate-spin' : ''}"
						/>
						{status.status}
					</Badge>
				{/if}
				
				{#if status && !status.ready}
					<div class="flex gap-1">
						{#if $isPolling}
							<Button variant="outline" size="sm" onclick={stopPolling} title="Pause UI updates">
								<Pause class="w-3 h-3" />
							</Button>
						{:else}
							<Button variant="outline" size="sm" onclick={startPolling} title="Resume UI updates">
								<Play class="w-3 h-3" />
							</Button>
						{/if}
						<Button variant="destructive" size="sm" onclick={cancelTask} title="Stop scraping task">
							<Square class="w-3 h-3" />
							Stop
						</Button>
					</div>
				{/if}
			</div>
		</div>
	</CardHeader>

	<CardContent class="space-y-4">
		{#if status}
			<!-- Progress Bar -->
			{#if progress}
				<div class="space-y-2">
					<div class="flex justify-between text-sm">
						<span>{progress.status || 'Processing...'}</span>
						<span>{formatNumber(progress.current)} / {formatNumber(progress.total)}</span>
					</div>
					<Progress value={progress.current} max={progress.total} class="w-full" />
					<div class="flex justify-between text-xs text-muted-foreground">
						<span>{progressPercentage.toFixed(1)}% complete</span>
						{#if progress.successful !== undefined && progress.failed !== undefined}
							<span>
								✓ {formatNumber(progress.successful)} 
								✗ {formatNumber(progress.failed)}
							</span>
						{/if}
					</div>
				</div>
			{:else if status.status === 'PENDING'}
				<div class="flex items-center gap-2 text-sm text-muted-foreground">
					<LoaderCircle class="w-4 h-4 animate-spin" />
					Task is queued and waiting to start...
				</div>
			{/if}

			<!-- Task Results -->
			{#if status.ready}
				{#if status.successful && status.result}
					<div class="bg-green-50 dark:bg-green-950 border border-green-200 dark:border-green-800 rounded-lg p-4">
						<h4 class="font-medium text-green-800 dark:text-green-200 mb-2">
							<CircleCheck class="w-4 h-4 inline mr-1" />
							Scraping Completed Successfully
						</h4>
						<div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
							{#if status.result.pages_found}
								<div>
									<span class="text-muted-foreground">Pages Found:</span>
									<div class="font-medium">{formatNumber(status.result.pages_found)}</div>
								</div>
							{/if}
							{#if status.result.pages_created}
								<div>
									<span class="text-muted-foreground">Pages Created:</span>
									<div class="font-medium">{formatNumber(status.result.pages_created)}</div>
								</div>
							{/if}
							{#if status.result.successful}
								<div>
									<span class="text-muted-foreground">Successful:</span>
									<div class="font-medium text-green-600">{formatNumber(status.result.successful)}</div>
								</div>
							{/if}
							{#if status.result.failed}
								<div>
									<span class="text-muted-foreground">Failed:</span>
									<div class="font-medium text-red-600">{formatNumber(status.result.failed)}</div>
								</div>
							{/if}
							{#if status.result.tasks_queued}
								<div>
									<span class="text-muted-foreground">Tasks Queued:</span>
									<div class="font-medium">{formatNumber(status.result.tasks_queued)}</div>
								</div>
							{/if}
						</div>
					</div>
				{:else if status.failed}
					<div class="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg p-4">
						<h4 class="font-medium text-red-800 dark:text-red-200 mb-2">
							<CircleX class="w-4 h-4 inline mr-1" />
							Scraping Failed
						</h4>
						{#if status.error}
							<p class="text-sm text-red-700 dark:text-red-300 font-mono bg-red-100 dark:bg-red-900 p-2 rounded">
								{status.error}
							</p>
						{/if}
					</div>
				{:else if status.status === 'REVOKED'}
					<div class="bg-gray-50 dark:bg-gray-950 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
						<h4 class="font-medium text-gray-800 dark:text-gray-200 mb-2">
							<Square class="w-4 h-4 inline mr-1" />
							Task Cancelled
						</h4>
						<p class="text-sm text-gray-600 dark:text-gray-400">
							The scraping task was cancelled before completion.
						</p>
					</div>
				{/if}
			{/if}

			<!-- Task Details -->
			<details class="text-sm">
				<summary class="cursor-pointer text-muted-foreground hover:text-foreground">
					Task Details
				</summary>
				<div class="mt-2 space-y-1 text-xs font-mono bg-muted p-3 rounded">
					<div><span class="text-muted-foreground">Task ID:</span> {status.task_id}</div>
					<div><span class="text-muted-foreground">Status:</span> {status.status}</div>
					<div><span class="text-muted-foreground">Ready:</span> {status.ready}</div>
					{#if status.successful !== undefined}
						<div><span class="text-muted-foreground">Successful:</span> {status.successful}</div>
					{/if}
					{#if status.failed !== undefined}
						<div><span class="text-muted-foreground">Failed:</span> {status.failed}</div>
					{/if}
				</div>
			</details>
		{:else}
			<div class="flex items-center gap-2 text-sm text-muted-foreground">
				<LoaderCircle class="w-4 h-4 animate-spin" />
				Loading task status...
			</div>
		{/if}
	</CardContent>
</Card>