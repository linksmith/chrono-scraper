<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { formatDateTime, formatNumber, getApiUrl } from '$lib/utils';
	import { 
		Users, 
		Settings, 
		Shield, 
		Trash2, 
		Edit, 
		Plus, 
		Search,
		MoreHorizontal,
		AlertCircle,
		CheckCircle2,
		X,
		Save
	} from 'lucide-svelte';
	
	interface User {
		id: number;
		email: string;
		username: string;
		full_name?: string;
		is_active: boolean;
		is_admin: boolean;
		created_at: string;
		last_login?: string;
	}
	
	const users = writable<User[]>([]);
	const loading = writable(false);
	const error = writable<string | null>(null);
	
	// User management state
	let searchQuery = '';
	let selectedUsers: number[] = [];
	let showAddUserForm = false;
	let editingUserId: number | null = null;
	
	// Add user form
	let newUserForm = {
		email: '',
		username: '',
		full_name: '',
		password: '',
		is_admin: false,
		is_active: true
	};
	let newUserErrors: Record<string, string> = {};
	
	// Edit user form
	let editUserForm = {
		email: '',
		username: '',
		full_name: '',
		is_admin: false,
		is_active: true
	};
	let editUserErrors: Record<string, string> = {};
	
	$: filteredUsers = $users.filter(user => 
		user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
		user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
		(user.full_name || '').toLowerCase().includes(searchQuery.toLowerCase())
	);
	
	onMount(() => {
		loadUsers();
	});
	
	async function loadUsers() {
		loading.set(true);
		error.set(null);
		
		try {
			const response = await fetch(getApiUrl('/api/v1/admin/users'), {
				credentials: 'include'
			});
			
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}
			
			const data = await response.json();
			users.set(data);
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to load users');
		} finally {
			loading.set(false);
		}
	}
	
	function validateNewUserForm(): boolean {
		newUserErrors = {};
		
		if (!newUserForm.email.trim()) {
			newUserErrors.email = 'Email is required';
		} else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(newUserForm.email)) {
			newUserErrors.email = 'Invalid email format';
		}
		
		if (!newUserForm.username.trim()) {
			newUserErrors.username = 'Username is required';
		}
		
		if (!newUserForm.password.trim()) {
			newUserErrors.password = 'Password is required';
		} else if (newUserForm.password.length < 8) {
			newUserErrors.password = 'Password must be at least 8 characters';
		}
		
		return Object.keys(newUserErrors).length === 0;
	}
	
	async function createUser() {
		if (!validateNewUserForm()) return;
		
		loading.set(true);
		try {
			const response = await fetch(getApiUrl('/api/v1/admin/users'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({
					email: newUserForm.email.trim(),
					username: newUserForm.username.trim(),
					full_name: newUserForm.full_name.trim() || undefined,
					password: newUserForm.password,
					is_admin: newUserForm.is_admin,
					is_active: newUserForm.is_active
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}
			
			const newUser = await response.json();
			users.update(list => [...list, newUser]);
			
			// Reset form
			newUserForm = {
				email: '',
				username: '',
				full_name: '',
				password: '',
				is_admin: false,
				is_active: true
			};
			showAddUserForm = false;
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to create user');
		} finally {
			loading.set(false);
		}
	}
	
	function startEditUser(user: User) {
		editingUserId = user.id;
		editUserForm = {
			email: user.email,
			username: user.username,
			full_name: user.full_name || '',
			is_admin: user.is_admin,
			is_active: user.is_active
		};
		editUserErrors = {};
	}
	
	function cancelEditUser() {
		editingUserId = null;
		editUserErrors = {};
	}
	
	function validateEditUserForm(): boolean {
		editUserErrors = {};
		
		if (!editUserForm.email.trim()) {
			editUserErrors.email = 'Email is required';
		} else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editUserForm.email)) {
			editUserErrors.email = 'Invalid email format';
		}
		
		if (!editUserForm.username.trim()) {
			editUserErrors.username = 'Username is required';
		}
		
		return Object.keys(editUserErrors).length === 0;
	}
	
	async function updateUser() {
		if (!validateEditUserForm() || !editingUserId) return;
		
		loading.set(true);
		try {
			const response = await fetch(getApiUrl(`/api/v1/admin/users/${editingUserId}`), {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({
					email: editUserForm.email.trim(),
					username: editUserForm.username.trim(),
					full_name: editUserForm.full_name.trim() || undefined,
					is_admin: editUserForm.is_admin,
					is_active: editUserForm.is_active
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}
			
			const updatedUser = await response.json();
			users.update(list => 
				list.map(user => user.id === editingUserId ? updatedUser : user)
			);
			
			editingUserId = null;
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to update user');
		} finally {
			loading.set(false);
		}
	}
	
	async function deleteUser(userId: number) {
		if (!confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
			return;
		}
		
		loading.set(true);
		try {
			const response = await fetch(getApiUrl(`/api/v1/admin/users/${userId}`), {
				method: 'DELETE',
				credentials: 'include'
			});
			
			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}
			
			users.update(list => list.filter(user => user.id !== userId));
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to delete user');
		} finally {
			loading.set(false);
		}
	}
	
	async function toggleUserStatus(user: User) {
		loading.set(true);
		try {
			const response = await fetch(getApiUrl(`/api/v1/admin/users/${user.id}`), {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({
					is_active: !user.is_active
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}
			
			const updatedUser = await response.json();
			users.update(list => 
				list.map(u => u.id === user.id ? updatedUser : u)
			);
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to update user status');
		} finally {
			loading.set(false);
		}
	}
</script>

<div class="container mx-auto px-4 py-8">
	<div class="space-y-6">
		<!-- Header -->
		<div class="flex items-center justify-between">
			<div>
				<h1 class="text-3xl font-bold">Admin Panel</h1>
				<p class="text-muted-foreground">Manage users and system settings</p>
			</div>
			<Button on:click={() => showAddUserForm = !showAddUserForm}>
				<Plus class="w-4 h-4 mr-2" />
				Add User
			</Button>
		</div>
		
		<!-- Error Display -->
		{#if $error}
			<Card class="border-destructive">
				<CardContent class="pt-6">
					<div class="flex items-center gap-2 text-destructive">
						<AlertCircle class="w-4 h-4" />
						<span>{$error}</span>
					</div>
				</CardContent>
			</Card>
		{/if}
		
		<!-- Add User Form -->
		{#if showAddUserForm}
			<Card>
				<CardHeader>
					<CardTitle>Add New User</CardTitle>
				</CardHeader>
				<CardContent>
					<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
						<div>
							<label for="new-email" class="text-sm font-medium mb-2 block">
								Email *
							</label>
							<input
								id="new-email"
								type="email"
								bind:value={newUserForm.email}
								class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
								class:border-destructive={newUserErrors.email}
							/>
							{#if newUserErrors.email}
								<p class="text-destructive text-sm mt-1">{newUserErrors.email}</p>
							{/if}
						</div>
						
						<div>
							<label for="new-username" class="text-sm font-medium mb-2 block">
								Username *
							</label>
							<input
								id="new-username"
								type="text"
								bind:value={newUserForm.username}
								class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
								class:border-destructive={newUserErrors.username}
							/>
							{#if newUserErrors.username}
								<p class="text-destructive text-sm mt-1">{newUserErrors.username}</p>
							{/if}
						</div>
						
						<div>
							<label for="new-full-name" class="text-sm font-medium mb-2 block">
								Full Name
							</label>
							<input
								id="new-full-name"
								type="text"
								bind:value={newUserForm.full_name}
								class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
							/>
						</div>
						
						<div>
							<label for="new-password" class="text-sm font-medium mb-2 block">
								Password *
							</label>
							<input
								id="new-password"
								type="password"
								bind:value={newUserForm.password}
								class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
								class:border-destructive={newUserErrors.password}
							/>
							{#if newUserErrors.password}
								<p class="text-destructive text-sm mt-1">{newUserErrors.password}</p>
							{/if}
						</div>
						
						<div class="md:col-span-2 flex gap-4">
							<label class="flex items-center gap-2 text-sm cursor-pointer">
								<input
									type="checkbox"
									bind:checked={newUserForm.is_admin}
									class="rounded border-gray-300"
								/>
								Administrator
							</label>
							
							<label class="flex items-center gap-2 text-sm cursor-pointer">
								<input
									type="checkbox"
									bind:checked={newUserForm.is_active}
									class="rounded border-gray-300"
								/>
								Active
							</label>
						</div>
					</div>
					
					<div class="flex gap-2 mt-6">
						<Button on:click={createUser} disabled={$loading}>
							<Plus class="w-4 h-4 mr-2" />
							Create User
						</Button>
						<Button variant="outline" on:click={() => showAddUserForm = false}>
							Cancel
						</Button>
					</div>
				</CardContent>
			</Card>
		{/if}
		
		<!-- Users List -->
		<Card>
			<CardHeader>
				<div class="flex items-center justify-between">
					<CardTitle class="flex items-center gap-2">
						<Users class="w-5 h-5" />
						Users ({formatNumber($users.length)})
					</CardTitle>
					
					<!-- Search -->
					<div class="relative w-64">
						<Search class="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
						<input
							type="text"
							bind:value={searchQuery}
							placeholder="Search users..."
							class="w-full pl-10 pr-4 py-2 border border-input bg-background rounded-md text-sm"
						/>
					</div>
				</div>
			</CardHeader>
			<CardContent>
				{#if $loading && $users.length === 0}
					<div class="flex items-center justify-center py-12">
						<div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
						<span class="ml-2">Loading users...</span>
					</div>
				{:else if filteredUsers.length === 0}
					<div class="text-center py-12">
						<Users class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
						<h3 class="text-lg font-semibold mb-2">No users found</h3>
						<p class="text-muted-foreground">
							{searchQuery ? 'Try adjusting your search criteria' : 'No users have been created yet'}
						</p>
					</div>
				{:else}
					<div class="space-y-4">
						{#each filteredUsers as user (user.id)}
							<div class="border rounded-lg p-4">
								{#if editingUserId === user.id}
									<!-- Edit Mode -->
									<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
										<div>
											<label class="text-sm font-medium mb-1 block">Email</label>
											<input
												type="email"
												bind:value={editUserForm.email}
												class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
												class:border-destructive={editUserErrors.email}
											/>
											{#if editUserErrors.email}
												<p class="text-destructive text-xs mt-1">{editUserErrors.email}</p>
											{/if}
										</div>
										
										<div>
											<label class="text-sm font-medium mb-1 block">Username</label>
											<input
												type="text"
												bind:value={editUserForm.username}
												class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
												class:border-destructive={editUserErrors.username}
											/>
											{#if editUserErrors.username}
												<p class="text-destructive text-xs mt-1">{editUserErrors.username}</p>
											{/if}
										</div>
										
										<div>
											<label class="text-sm font-medium mb-1 block">Full Name</label>
											<input
												type="text"
												bind:value={editUserForm.full_name}
												class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
											/>
										</div>
										
										<div class="flex gap-4 items-center">
											<label class="flex items-center gap-2 text-sm cursor-pointer">
												<input
													type="checkbox"
													bind:checked={editUserForm.is_admin}
													class="rounded border-gray-300"
												/>
												Administrator
											</label>
											
											<label class="flex items-center gap-2 text-sm cursor-pointer">
												<input
													type="checkbox"
													bind:checked={editUserForm.is_active}
													class="rounded border-gray-300"
												/>
												Active
											</label>
										</div>
										
										<div class="md:col-span-2 flex gap-2">
											<Button size="sm" on:click={updateUser} disabled={$loading}>
												<Save class="w-3 h-3 mr-1" />
												Save
											</Button>
											<Button size="sm" variant="outline" on:click={cancelEditUser}>
												<X class="w-3 h-3 mr-1" />
												Cancel
											</Button>
										</div>
									</div>
								{:else}
									<!-- Display Mode -->
									<div class="flex items-center justify-between">
										<div class="flex items-center gap-4">
											<div>
												<div class="flex items-center gap-2">
													<h3 class="font-medium">{user.username}</h3>
													{#if user.is_admin}
														<Badge variant="default">
															<Shield class="w-3 h-3 mr-1" />
															Admin
														</Badge>
													{/if}
													<Badge variant={user.is_active ? 'success' : 'destructive'}>
														{user.is_active ? 'Active' : 'Inactive'}
													</Badge>
												</div>
												<p class="text-sm text-muted-foreground">{user.email}</p>
												{#if user.full_name}
													<p class="text-sm text-muted-foreground">{user.full_name}</p>
												{/if}
												<div class="text-xs text-muted-foreground mt-1">
													Created: {formatDateTime(user.created_at)}
													{#if user.last_login}
														• Last login: {formatDateTime(user.last_login)}
													{/if}
												</div>
											</div>
										</div>
										
										<div class="flex items-center gap-2">
											<Button size="sm" variant="outline" on:click={() => toggleUserStatus(user)}>
												{user.is_active ? 'Deactivate' : 'Activate'}
											</Button>
											<Button size="sm" variant="outline" on:click={() => startEditUser(user)}>
												<Edit class="w-3 h-3" />
											</Button>
											<Button size="sm" variant="outline" on:click={() => deleteUser(user.id)}>
												<Trash2 class="w-3 h-3" />
											</Button>
										</div>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>
</div>