<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Textarea } from '$lib/components/ui/textarea';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '$lib/components/ui/dialog';
	import { Progress } from '$lib/components/ui/progress';
	import { Separator } from '$lib/components/ui/separator';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Users,
		UserCheck,
		UserX,
		UserPlus,
		UserMinus,
		Shield,
		ShieldOff,
		Mail,
		Download,
		Upload,
		Trash2,
		AlertTriangle,
		CheckCircle,
		Clock,
		XCircle,
		Settings
	} from 'lucide-svelte';
	import { getApiUrl } from '$lib/utils';

	export let selectedUsers: number[] = [];
	export let allUsers: any[] = [];
	export let isLoading: boolean = false;

	const dispatch = createEventDispatcher();

	interface BulkOperationProgress {
		operation_id: string;
		status: 'pending' | 'running' | 'completed' | 'failed' | 'partially_completed';
		progress_percentage: number;
		current_step: string;
		items_processed: number;
		items_total: number;
		errors_count: number;
		last_error?: string;
	}

	interface BulkOperationResult {
		operation_id: string;
		operation_type: string;
		status: string;
		total_requested: number;
		total_successful: number;
		total_failed: number;
		successful_ids: number[];
		failed_ids: number[];
		failed_reasons: Record<number, string>;
		duration_seconds: number;
	}

	// State management
	const showBulkDialog = writable(false);
	const showProgressDialog = writable(false);
	const showResultDialog = writable(false);
	const currentOperation = writable<string>('');
	const operationProgress = writable<BulkOperationProgress | null>(null);
	const operationResult = writable<BulkOperationResult | null>(null);
	const operationError = writable<string | null>(null);

	// Form state
	let selectedOperation = '';
	let operationReason = '';
	let confirmDestructive = false;
	let roleToAssign = 'user';
	let customMessage = '';

	// Available bulk operations
	const bulkOperations = [
		{
			id: 'approve',
			label: 'Approve Users',
			description: 'Approve pending user applications',
			icon: UserCheck,
			variant: 'default',
			destructive: false
		},
		{
			id: 'deny',
			label: 'Deny Users',
			description: 'Reject user applications',
			icon: UserX,
			variant: 'destructive',
			destructive: false
		},
		{
			id: 'activate',
			label: 'Activate Users',
			description: 'Enable user accounts',
			icon: UserPlus,
			variant: 'default',
			destructive: false
		},
		{
			id: 'deactivate',
			label: 'Deactivate Users',
			description: 'Disable user accounts',
			icon: UserMinus,
			variant: 'secondary',
			destructive: false
		},
		{
			id: 'delete',
			label: 'Delete Users',
			description: 'Permanently delete user accounts',
			icon: Trash2,
			variant: 'destructive',
			destructive: true
		},
		{
			id: 'assign_role',
			label: 'Assign Role',
			description: 'Change user roles',
			icon: Shield,
			variant: 'default',
			destructive: false
		},
		{
			id: 'verify_email',
			label: 'Verify Emails',
			description: 'Mark emails as verified',
			icon: Mail,
			variant: 'default',
			destructive: false
		}
	];

	$: selectedUsersData = allUsers.filter(user => selectedUsers.includes(user.id));
	$: selectedOperation_data = bulkOperations.find(op => op.id === selectedOperation);

	function openBulkDialog() {
		if (selectedUsers.length === 0) {
			dispatch('error', 'Please select users to perform bulk operations');
			return;
		}
		showBulkDialog.set(true);
		resetForm();
	}

	function closeBulkDialog() {
		showBulkDialog.set(false);
		resetForm();
	}

	function resetForm() {
		selectedOperation = '';
		operationReason = '';
		confirmDestructive = false;
		roleToAssign = 'user';
		customMessage = '';
		operationError.set(null);
	}

	async function executeBulkOperation() {
		if (!selectedOperation) return;

		const operation = bulkOperations.find(op => op.id === selectedOperation);
		if (!operation) return;

		// Validation
		if (operation.destructive && !confirmDestructive) {
			operationError.set('You must confirm destructive operations');
			return;
		}

		try {
			operationError.set(null);
			const requestBody = {
				user_ids: selectedUsers,
				operation: selectedOperation,
				reason: operationReason || undefined,
				role: selectedOperation === 'assign_role' ? roleToAssign : undefined,
				custom_message: customMessage || undefined,
				confirm_destructive: operation.destructive ? confirmDestructive : undefined
			};

			const response = await fetch(getApiUrl('/api/v1/admin/bulk-operation'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify(requestBody)
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || 'Operation failed');
			}

			const result: BulkOperationResult = await response.json();
			
			// Close bulk dialog and show progress
			closeBulkDialog();
			currentOperation.set(result.operation_id);
			operationResult.set(result);

			// If operation completed immediately, show results
			if (result.status === 'completed' || result.status === 'failed' || result.status === 'partially_completed') {
				showResultDialog.set(true);
			} else {
				// Start polling for progress
				showProgressDialog.set(true);
				pollOperationProgress(result.operation_id);
			}

			// Refresh users list
			dispatch('refresh');

		} catch (error) {
			console.error('Bulk operation error:', error);
			operationError.set(error instanceof Error ? error.message : 'Unknown error occurred');
		}
	}

	async function pollOperationProgress(operationId: string) {
		const pollInterval = setInterval(async () => {
			try {
				const response = await fetch(
					getApiUrl(`/api/v1/admin/bulk-operation/${operationId}/progress`),
					{
						credentials: 'include'
					}
				);

				if (!response.ok) {
					if (response.status === 404) {
						// Operation completed or not found, stop polling
						clearInterval(pollInterval);
						showProgressDialog.set(false);
						showResultDialog.set(true);
						return;
					}
					throw new Error('Failed to get progress');
				}

				const progress: BulkOperationProgress = await response.json();
				operationProgress.set(progress);

				// Stop polling if completed
				if (progress.status === 'completed' || progress.status === 'failed' || progress.status === 'partially_completed') {
					clearInterval(pollInterval);
					showProgressDialog.set(false);
					showResultDialog.set(true);
					
					// Refresh users list
					dispatch('refresh');
				}
			} catch (error) {
				console.error('Progress polling error:', error);
				clearInterval(pollInterval);
				showProgressDialog.set(false);
				operationError.set('Failed to track operation progress');
			}
		}, 2000); // Poll every 2 seconds

		// Stop polling after 5 minutes
		setTimeout(() => {
			clearInterval(pollInterval);
			showProgressDialog.set(false);
		}, 300000);
	}

	function getOperationStatusIcon(status: string) {
		switch (status) {
			case 'completed':
				return CheckCircle;
			case 'failed':
				return XCircle;
			case 'partially_completed':
				return AlertTriangle;
			case 'running':
				return Clock;
			default:
				return Clock;
		}
	}

	function getOperationStatusColor(status: string) {
		switch (status) {
			case 'completed':
				return 'text-green-500';
			case 'failed':
				return 'text-red-500';
			case 'partially_completed':
				return 'text-yellow-500';
			case 'running':
				return 'text-blue-500';
			default:
				return 'text-gray-500';
		}
	}
</script>

<Card class="mb-6">
	<CardHeader>
		<div class="flex items-center justify-between">
			<div>
				<CardTitle class="flex items-center gap-2">
					<Settings class="h-5 w-5" />
					Bulk Operations
				</CardTitle>
				<CardDescription>
					Perform actions on multiple users at once
				</CardDescription>
			</div>
			<Badge variant="secondary" class="text-sm">
				{selectedUsers.length} selected
			</Badge>
		</div>
	</CardHeader>
	<CardContent>
		<div class="space-y-4">
			{#if selectedUsers.length === 0}
				<Alert>
					<AlertTriangle class="h-4 w-4" />
					<AlertDescription>
						Select users from the table below to enable bulk operations.
					</AlertDescription>
				</Alert>
			{:else}
				<div class="grid grid-cols-2 md:grid-cols-4 gap-2">
					{#each bulkOperations as operation}
						<Button
							variant={operation.variant}
							size="sm"
							disabled={isLoading}
							onclick={() => {
								selectedOperation = operation.id;
								openBulkDialog();
							}}
							class="flex items-center gap-2 h-auto p-3"
						>
							<svelte:component this={operation.icon} class="h-4 w-4" />
							<div class="text-left">
								<div class="font-medium text-xs">{operation.label}</div>
								<div class="text-xs opacity-70">{selectedUsers.length} users</div>
							</div>
						</Button>
					{/each}
				</div>
			{/if}
		</div>
	</CardContent>
</Card>

<!-- Bulk Operation Dialog -->
<Dialog bind:open={$showBulkDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle class="flex items-center gap-2">
				{#if selectedOperation_data}
					<svelte:component this={selectedOperation_data.icon} class="h-5 w-5" />
					{selectedOperation_data.label}
				{:else}
					Bulk Operation
				{/if}
			</DialogTitle>
			<DialogDescription>
				{#if selectedOperation_data}
					{selectedOperation_data.description} for {selectedUsers.length} selected users
				{:else}
					Configure bulk operation settings
				{/if}
			</DialogDescription>
		</DialogHeader>

		<div class="space-y-6">
			<!-- Selected Users Preview -->
			<div>
				<Label class="text-sm font-medium">Selected Users ({selectedUsers.length})</Label>
				<div class="mt-2 max-h-32 overflow-y-auto border rounded-md p-2 bg-gray-50">
					<div class="space-y-1">
						{#each selectedUsersData.slice(0, 10) as user}
							<div class="text-sm flex items-center justify-between">
								<span>{user.email}</span>
								<Badge variant="outline" size="sm">
									{user.approval_status || 'unknown'}
								</Badge>
							</div>
						{/each}
						{#if selectedUsersData.length > 10}
							<div class="text-sm text-gray-500 italic">
								...and {selectedUsersData.length - 10} more users
							</div>
						{/if}
					</div>
				</div>
			</div>

			<!-- Operation-specific settings -->
			{#if selectedOperation === 'assign_role'}
				<div>
					<Label for="role-select">Role to Assign</Label>
					<Select bind:value={roleToAssign}>
						<SelectTrigger>
							<SelectValue placeholder="Select role" />
						</SelectTrigger>
						<SelectContent>
							<SelectItem value="user">User</SelectItem>
							<SelectItem value="superuser">Superuser</SelectItem>
						</SelectContent>
					</Select>
				</div>
			{/if}

			<!-- Reason -->
			<div>
				<Label for="operation-reason">Reason (Optional)</Label>
				<Textarea
					id="operation-reason"
					bind:value={operationReason}
					placeholder="Provide a reason for this bulk operation..."
					class="mt-1"
					rows="2"
				/>
			</div>

			<!-- Custom Message -->
			{#if selectedOperation === 'deny' || selectedOperation === 'deactivate'}
				<div>
					<Label for="custom-message">Custom Message (Optional)</Label>
					<Textarea
						id="custom-message"
						bind:value={customMessage}
						placeholder="Custom message to include in notifications..."
						class="mt-1"
						rows="2"
					/>
				</div>
			{/if}

			<!-- Destructive Operation Confirmation -->
			{#if selectedOperation_data?.destructive}
				<Alert variant="destructive">
					<AlertTriangle class="h-4 w-4" />
					<AlertDescription>
						<div class="space-y-2">
							<p><strong>Warning:</strong> This is a destructive operation that cannot be undone.</p>
							<div class="flex items-center space-x-2">
								<Checkbox
									id="confirm-destructive"
									bind:checked={confirmDestructive}
								/>
								<Label for="confirm-destructive" class="text-sm">
									I understand this operation is permanent and cannot be undone
								</Label>
							</div>
						</div>
					</AlertDescription>
				</Alert>
			{/if}

			<!-- Error Display -->
			{#if $operationError}
				<Alert variant="destructive">
					<XCircle class="h-4 w-4" />
					<AlertDescription>{$operationError}</AlertDescription>
				</Alert>
			{/if}

			<!-- Action Buttons -->
			<div class="flex justify-end space-x-2">
				<Button variant="outline" onclick={closeBulkDialog} disabled={isLoading}>
					Cancel
				</Button>
				<Button
					variant={selectedOperation_data?.destructive ? 'destructive' : 'default'}
					onclick={executeBulkOperation}
					disabled={isLoading || !selectedOperation || (selectedOperation_data?.destructive && !confirmDestructive)}
				>
					{#if isLoading}
						Processing...
					{:else if selectedOperation_data}
						{selectedOperation_data.label}
					{:else}
						Execute Operation
					{/if}
				</Button>
			</div>
		</div>
	</DialogContent>
</Dialog>

<!-- Progress Dialog -->
<Dialog bind:open={$showProgressDialog}>
	<DialogContent class="max-w-md">
		<DialogHeader>
			<DialogTitle class="flex items-center gap-2">
				<Clock class="h-5 w-5 animate-spin" />
				Operation in Progress
			</DialogTitle>
			<DialogDescription>
				Please wait while the bulk operation is being processed...
			</DialogDescription>
		</DialogHeader>

		{#if $operationProgress}
			<div class="space-y-4">
				<div>
					<div class="flex justify-between text-sm mb-2">
						<span>Progress</span>
						<span>{Math.round($operationProgress.progress_percentage)}%</span>
					</div>
					<Progress value={$operationProgress.progress_percentage} class="w-full" />
				</div>

				<div class="text-sm space-y-1">
					<div><strong>Status:</strong> {$operationProgress.current_step}</div>
					<div><strong>Processed:</strong> {$operationProgress.items_processed} / {$operationProgress.items_total}</div>
					{#if $operationProgress.errors_count > 0}
						<div class="text-red-600">
							<strong>Errors:</strong> {$operationProgress.errors_count}
						</div>
					{/if}
				</div>

				{#if $operationProgress.last_error}
					<Alert variant="destructive">
						<AlertTriangle class="h-4 w-4" />
						<AlertDescription>{$operationProgress.last_error}</AlertDescription>
					</Alert>
				{/if}
			</div>
		{/if}
	</DialogContent>
</Dialog>

<!-- Results Dialog -->
<Dialog bind:open={$showResultDialog}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle class="flex items-center gap-2">
				{#if $operationResult}
					<svelte:component 
						this={getOperationStatusIcon($operationResult.status)} 
						class="h-5 w-5 {getOperationStatusColor($operationResult.status)}" 
					/>
					Operation {$operationResult.status === 'completed' ? 'Complete' : 
							  $operationResult.status === 'failed' ? 'Failed' : 
							  'Partially Complete'}
				{:else}
					Operation Results
				{/if}
			</DialogTitle>
		</DialogHeader>

		{#if $operationResult}
			<div class="space-y-6">
				<!-- Summary Stats -->
				<div class="grid grid-cols-3 gap-4">
					<Card>
						<CardContent class="p-4 text-center">
							<div class="text-2xl font-bold text-green-600">{$operationResult.total_successful}</div>
							<div class="text-sm text-gray-600">Successful</div>
						</CardContent>
					</Card>
					<Card>
						<CardContent class="p-4 text-center">
							<div class="text-2xl font-bold text-red-600">{$operationResult.total_failed}</div>
							<div class="text-sm text-gray-600">Failed</div>
						</CardContent>
					</Card>
					<Card>
						<CardContent class="p-4 text-center">
							<div class="text-2xl font-bold text-blue-600">{$operationResult.total_requested}</div>
							<div class="text-sm text-gray-600">Total</div>
						</CardContent>
					</Card>
				</div>

				<!-- Detailed Results -->
				{#if $operationResult.total_failed > 0}
					<div>
						<h4 class="font-medium text-red-600 mb-2">Failed Operations ({$operationResult.total_failed})</h4>
						<div class="max-h-40 overflow-y-auto border rounded-md p-2 bg-red-50">
							{#each Object.entries($operationResult.failed_reasons) as [userId, reason]}
								<div class="text-sm py-1 border-b border-red-200 last:border-b-0">
									<span class="font-medium">User {userId}:</span> {reason}
								</div>
							{/each}
						</div>
					</div>
				{/if}

				<div class="text-sm text-gray-600">
					<strong>Operation completed in:</strong> {($operationResult.duration_seconds || 0).toFixed(2)} seconds
				</div>

				<div class="flex justify-end">
					<Button onclick={() => showResultDialog.set(false)}>
						Close
					</Button>
				</div>
			</div>
		{/if}
	</DialogContent>
</Dialog>