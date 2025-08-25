<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { Input } from '$lib/components/ui/input';
	import { Checkbox } from '$lib/components/ui/checkbox';
	import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '$lib/components/ui/select';
	import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '$lib/components/ui/table';
	import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '$lib/components/ui/dialog';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import {
		Search,
		Filter,
		Users,
		Edit,
		Trash2,
		Eye,
		MoreHorizontal,
		ChevronLeft,
		ChevronRight,
		CheckCircle,
		XCircle,
		Clock,
		Shield,
		Mail
	} from 'lucide-svelte';
	import { formatDateTime, getApiUrl } from '$lib/utils';
	import BulkOperations from './BulkOperations.svelte';

	export let users: any[] = [];
	export let isLoading: boolean = false;
	export let error: string | null = null;

	const dispatch = createEventDispatcher();

	// Selection state
	let selectedUsers: number[] = [];
	let selectAllChecked = false;
	let selectAllIndeterminate = false;

	// Filtering and search
	let searchQuery = '';
	let statusFilter = 'all';
	let roleFilter = 'all';
	let sortBy = 'created_at';
	let sortOrder: 'asc' | 'desc' = 'desc';
	
	// Pagination
	let currentPage = 1;
	let itemsPerPage = 25;
	let totalItems = 0;

	// Dialogs
	const showUserDetails = writable(false);
	const selectedUser = writable<any>(null);

	// Available filter options
	const statusOptions = [
		{ value: 'all', label: 'All Users' },
		{ value: 'pending', label: 'Pending Approval' },
		{ value: 'approved', label: 'Approved' },
		{ value: 'rejected', label: 'Rejected' },
		{ value: 'active', label: 'Active' },
		{ value: 'inactive', label: 'Inactive' }
	];

	const roleOptions = [
		{ value: 'all', label: 'All Roles' },
		{ value: 'user', label: 'Users' },
		{ value: 'admin', label: 'Administrators' }
	];

	const sortOptions = [
		{ value: 'created_at', label: 'Created Date' },
		{ value: 'email', label: 'Email' },
		{ value: 'full_name', label: 'Name' },
		{ value: 'last_login', label: 'Last Login' },
		{ value: 'approval_status', label: 'Status' }
	];

	// Reactive filtering and pagination
	$: filteredUsers = users.filter(user => {
		// Search filter
		const searchMatch = !searchQuery || 
			user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
			(user.full_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
			user.username.toLowerCase().includes(searchQuery.toLowerCase());

		// Status filter
		const statusMatch = statusFilter === 'all' || 
			(statusFilter === 'active' && user.is_active) ||
			(statusFilter === 'inactive' && !user.is_active) ||
			user.approval_status === statusFilter;

		// Role filter
		const roleMatch = roleFilter === 'all' || 
			(roleFilter === 'admin' && user.is_admin) ||
			(roleFilter === 'user' && !user.is_admin);

		return searchMatch && statusMatch && roleMatch;
	});

	$: sortedUsers = [...filteredUsers].sort((a, b) => {
		let aVal = a[sortBy];
		let bVal = b[sortBy];

		// Handle null/undefined values
		if (aVal == null) aVal = '';
		if (bVal == null) bVal = '';

		// Convert to comparable values
		if (typeof aVal === 'string') {
			aVal = aVal.toLowerCase();
			bVal = bVal.toLowerCase();
		}

		const comparison = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
		return sortOrder === 'asc' ? comparison : -comparison;
	});

	$: totalItems = sortedUsers.length;
	$: totalPages = Math.ceil(totalItems / itemsPerPage);
	$: paginatedUsers = sortedUsers.slice(
		(currentPage - 1) * itemsPerPage,
		currentPage * itemsPerPage
	);

	// Selection management
	$: {
		const visibleUserIds = paginatedUsers.map(u => u.id);
		const visibleSelectedCount = selectedUsers.filter(id => visibleUserIds.includes(id)).length;
		
		selectAllChecked = visibleSelectedCount === paginatedUsers.length && paginatedUsers.length > 0;
		selectAllIndeterminate = visibleSelectedCount > 0 && visibleSelectedCount < paginatedUsers.length;
	}

	function toggleUserSelection(userId: number) {
		if (selectedUsers.includes(userId)) {
			selectedUsers = selectedUsers.filter(id => id !== userId);
		} else {
			selectedUsers = [...selectedUsers, userId];
		}
	}

	function toggleSelectAll() {
		const visibleUserIds = paginatedUsers.map(u => u.id);
		
		if (selectAllChecked) {
			// Deselect all visible users
			selectedUsers = selectedUsers.filter(id => !visibleUserIds.includes(id));
		} else {
			// Select all visible users
			const newSelections = visibleUserIds.filter(id => !selectedUsers.includes(id));
			selectedUsers = [...selectedUsers, ...newSelections];
		}
	}

	function clearSelection() {
		selectedUsers = [];
	}

	function selectByFilter() {
		// Select all filtered users (not just visible)
		const filteredUserIds = filteredUsers.map(u => u.id);
		selectedUsers = [...new Set([...selectedUsers, ...filteredUserIds])];
	}

	function viewUserDetails(user: any) {
		selectedUser.set(user);
		showUserDetails.set(true);
	}

	function editUser(user: any) {
		dispatch('edit', user);
	}

	function deleteUser(user: any) {
		dispatch('delete', user);
	}

	function toggleUserStatus(user: any) {
		dispatch('toggleStatus', user);
	}

	function refreshData() {
		dispatch('refresh');
	}

	function getStatusBadge(user: any) {
		if (!user.is_active) {
			return { variant: 'secondary', text: 'Inactive', icon: XCircle };
		}
		
		switch (user.approval_status) {
			case 'approved':
				return { variant: 'default', text: 'Approved', icon: CheckCircle };
			case 'pending':
				return { variant: 'outline', text: 'Pending', icon: Clock };
			case 'rejected':
				return { variant: 'destructive', text: 'Rejected', icon: XCircle };
			default:
				return { variant: 'secondary', text: 'Unknown', icon: Clock };
		}
	}

	function getRoleBadge(user: any) {
		if (user.is_admin) {
			return { variant: 'default', text: 'Admin', icon: Shield };
		} else {
			return { variant: 'outline', text: 'User', icon: Users };
		}
	}

	function handleSort(column: string) {
		if (sortBy === column) {
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			sortBy = column;
			sortOrder = 'asc';
		}
		currentPage = 1; // Reset to first page when sorting
	}

	// Keyboard shortcuts
	function handleKeydown(event: KeyboardEvent) {
		if (event.ctrlKey || event.metaKey) {
			switch (event.key) {
				case 'a':
					event.preventDefault();
					selectByFilter();
					break;
				case 'Escape':
					clearSelection();
					break;
			}
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="space-y-6">
	<!-- Bulk Operations Component -->
	<BulkOperations 
		bind:selectedUsers 
		bind:allUsers={users}
		bind:isLoading
		on:refresh={refreshData}
		on:error={(e) => dispatch('error', e.detail)}
	/>

	<!-- User Management Table -->
	<Card>
		<CardHeader>
			<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
				<div>
					<CardTitle class="flex items-center gap-2">
						<Users class="h-5 w-5" />
						User Management
					</CardTitle>
					<CardDescription>
						Manage user accounts, permissions, and access
					</CardDescription>
				</div>
				
				<!-- Search and Filters -->
				<div class="flex flex-col sm:flex-row gap-2">
					<div class="relative">
						<Search class="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
						<Input
							type="text"
							placeholder="Search users..."
							bind:value={searchQuery}
							class="pl-10 w-full sm:w-64"
						/>
					</div>
					
					<Select bind:value={statusFilter}>
						<SelectTrigger class="w-full sm:w-40">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							{#each statusOptions as option}
								<SelectItem value={option.value}>{option.label}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
					
					<Select bind:value={roleFilter}>
						<SelectTrigger class="w-full sm:w-32">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							{#each roleOptions as option}
								<SelectItem value={option.value}>{option.label}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
				</div>
			</div>
		</CardHeader>

		<CardContent>
			<!-- Selection Summary -->
			{#if selectedUsers.length > 0}
				<div class="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
					<div class="flex items-center justify-between">
						<div class="flex items-center gap-2">
							<Badge variant="secondary">{selectedUsers.length} selected</Badge>
							<span class="text-sm text-blue-700">
								{selectedUsers.length === 1 ? 'user' : 'users'} selected
							</span>
						</div>
						<div class="flex items-center gap-2">
							<Button variant="outline" size="sm" onclick={selectByFilter}>
								Select All Filtered ({filteredUsers.length})
							</Button>
							<Button variant="outline" size="sm" onclick={clearSelection}>
								Clear Selection
							</Button>
						</div>
					</div>
				</div>
			{/if}

			<!-- Table Controls -->
			<div class="flex items-center justify-between mb-4">
				<div class="flex items-center gap-2">
					<Select bind:value={sortBy}>
						<SelectTrigger class="w-40">
							<SelectValue />
						</SelectTrigger>
						<SelectContent>
							{#each sortOptions as option}
								<SelectItem value={option.value}>{option.label}</SelectItem>
							{/each}
						</SelectContent>
					</Select>
					
					<Button
						variant="outline"
						size="sm"
						onclick={() => sortOrder = sortOrder === 'asc' ? 'desc' : 'asc'}
					>
						{sortOrder === 'asc' ? '↑' : '↓'}
					</Button>
				</div>

				<div class="text-sm text-gray-600">
					Showing {paginatedUsers.length} of {totalItems} users
				</div>
			</div>

			<!-- Error Display -->
			{#if error}
				<Alert variant="destructive" class="mb-4">
					<XCircle class="h-4 w-4" />
					<AlertDescription>{error}</AlertDescription>
				</Alert>
			{/if}

			<!-- Users Table -->
			<div class="border rounded-lg overflow-hidden">
				<Table>
					<TableHeader>
						<TableRow>
							<TableHead class="w-12">
								<Checkbox
									checked={selectAllChecked}
									indeterminate={selectAllIndeterminate}
									onCheckedChange={toggleSelectAll}
									aria-label="Select all users"
								/>
							</TableHead>
							<TableHead class="cursor-pointer" onclick={() => handleSort('email')}>
								Email
								{#if sortBy === 'email'}
									<span class="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
								{/if}
							</TableHead>
							<TableHead class="cursor-pointer" onclick={() => handleSort('full_name')}>
								Name
								{#if sortBy === 'full_name'}
									<span class="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
								{/if}
							</TableHead>
							<TableHead>Status</TableHead>
							<TableHead>Role</TableHead>
							<TableHead class="cursor-pointer" onclick={() => handleSort('created_at')}>
								Created
								{#if sortBy === 'created_at'}
									<span class="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
								{/if}
							</TableHead>
							<TableHead class="cursor-pointer" onclick={() => handleSort('last_login')}>
								Last Login
								{#if sortBy === 'last_login'}
									<span class="ml-1">{sortOrder === 'asc' ? '↑' : '↓'}</span>
								{/if}
							</TableHead>
							<TableHead class="w-32">Actions</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{#if isLoading}
							<TableRow>
								<TableCell colspan="8" class="text-center py-8">
									Loading users...
								</TableCell>
							</TableRow>
						{:else if paginatedUsers.length === 0}
							<TableRow>
								<TableCell colspan="8" class="text-center py-8 text-gray-500">
									No users found matching your criteria
								</TableCell>
							</TableRow>
						{:else}
							{#each paginatedUsers as user (user.id)}
								<TableRow class="hover:bg-gray-50">
									<TableCell>
										<Checkbox
											checked={selectedUsers.includes(user.id)}
											onCheckedChange={() => toggleUserSelection(user.id)}
											aria-label="Select user {user.email}"
										/>
									</TableCell>
									<TableCell class="font-medium">
										<div class="flex items-center gap-2">
											{user.email}
											{#if user.is_verified}
												<Badge variant="outline" class="text-xs">
													<Mail class="h-3 w-3 mr-1" />
													Verified
												</Badge>
											{/if}
										</div>
									</TableCell>
									<TableCell>{user.full_name || '-'}</TableCell>
									<TableCell>
										{@const status = getStatusBadge(user)}
										<Badge variant={status.variant}>
											<svelte:component this={status.icon} class="h-3 w-3 mr-1" />
											{status.text}
										</Badge>
									</TableCell>
									<TableCell>
										{@const role = getRoleBadge(user)}
										<Badge variant={role.variant}>
											<svelte:component this={role.icon} class="h-3 w-3 mr-1" />
											{role.text}
										</Badge>
									</TableCell>
									<TableCell class="text-sm text-gray-600">
										{formatDateTime(user.created_at)}
									</TableCell>
									<TableCell class="text-sm text-gray-600">
										{user.last_login ? formatDateTime(user.last_login) : 'Never'}
									</TableCell>
									<TableCell>
										<div class="flex items-center gap-1">
											<Button
												variant="ghost"
												size="sm"
												onclick={() => viewUserDetails(user)}
												title="View Details"
											>
												<Eye class="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="sm"
												onclick={() => editUser(user)}
												title="Edit User"
											>
												<Edit class="h-4 w-4" />
											</Button>
											<Button
												variant="ghost"
												size="sm"
												onclick={() => deleteUser(user)}
												title="Delete User"
												disabled={user.id === 1} <!-- Protect admin user -->
											>
												<Trash2 class="h-4 w-4" />
											</Button>
										</div>
									</TableCell>
								</TableRow>
							{/each}
						{/if}
					</TableBody>
				</Table>
			</div>

			<!-- Pagination -->
			{#if totalPages > 1}
				<div class="flex items-center justify-between mt-4">
					<div class="text-sm text-gray-600">
						Page {currentPage} of {totalPages}
					</div>
					<div class="flex items-center gap-2">
						<Button
							variant="outline"
							size="sm"
							disabled={currentPage === 1}
							onclick={() => currentPage = Math.max(1, currentPage - 1)}
						>
							<ChevronLeft class="h-4 w-4" />
							Previous
						</Button>
						<Button
							variant="outline"
							size="sm"
							disabled={currentPage === totalPages}
							onclick={() => currentPage = Math.min(totalPages, currentPage + 1)}
						>
							Next
							<ChevronRight class="h-4 w-4" />
						</Button>
					</div>
				</div>
			{/if}
		</CardContent>
	</Card>
</div>

<!-- User Details Dialog -->
<Dialog bind:open={$showUserDetails}>
	<DialogContent class="max-w-2xl">
		<DialogHeader>
			<DialogTitle>User Details</DialogTitle>
			<DialogDescription>
				Detailed information about the selected user
			</DialogDescription>
		</DialogHeader>

		{#if $selectedUser}
			<div class="space-y-4">
				<div class="grid grid-cols-2 gap-4">
					<div>
						<Label class="text-sm font-medium">Email</Label>
						<div class="mt-1">{$selectedUser.email}</div>
					</div>
					<div>
						<Label class="text-sm font-medium">Full Name</Label>
						<div class="mt-1">{$selectedUser.full_name || 'Not provided'}</div>
					</div>
					<div>
						<Label class="text-sm font-medium">Status</Label>
						<div class="mt-1">
							{@const status = getStatusBadge($selectedUser)}
							<Badge variant={status.variant}>
								<svelte:component this={status.icon} class="h-3 w-3 mr-1" />
								{status.text}
							</Badge>
						</div>
					</div>
					<div>
						<Label class="text-sm font-medium">Role</Label>
						<div class="mt-1">
							{@const role = getRoleBadge($selectedUser)}
							<Badge variant={role.variant}>
								<svelte:component this={role.icon} class="h-3 w-3 mr-1" />
								{role.text}
							</Badge>
						</div>
					</div>
					<div>
						<Label class="text-sm font-medium">Created</Label>
						<div class="mt-1">{formatDateTime($selectedUser.created_at)}</div>
					</div>
					<div>
						<Label class="text-sm font-medium">Last Login</Label>
						<div class="mt-1">{$selectedUser.last_login ? formatDateTime($selectedUser.last_login) : 'Never'}</div>
					</div>
				</div>

				<div class="flex justify-end">
					<Button onclick={() => showUserDetails.set(false)}>Close</Button>
				</div>
			</div>
		{/if}
	</DialogContent>
</Dialog>

<style>
	/* Custom scrollbar for better UX */
	.overflow-y-auto::-webkit-scrollbar {
		width: 6px;
	}
	.overflow-y-auto::-webkit-scrollbar-track {
		background: #f1f1f1;
		border-radius: 3px;
	}
	.overflow-y-auto::-webkit-scrollbar-thumb {
		background: #c1c1c1;
		border-radius: 3px;
	}
	.overflow-y-auto::-webkit-scrollbar-thumb:hover {
		background: #a8a8a8;
	}
</style>