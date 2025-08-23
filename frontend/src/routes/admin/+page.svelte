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
		Plus, 
		Search,
		Edit,
		Trash2,
		X,
		Save,
		UserPlus,
		CheckCircle2,
		AlertCircle
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
		approval_status?: string;
		is_verified?: boolean;
	}

	interface AdminSettings {
		id: number;
		users_open_registration: boolean;
		allow_invitation_tokens: boolean;
		updated_at: string;
		updated_by_id?: number;
	}
	
	const users = writable<User[]>([]);
	const adminSettings = writable<AdminSettings | null>(null);
	const loading = writable(false);
	const settingsLoading = writable(false);
	const error = writable<string | null>(null);
	
	// User management state
	let searchQuery = '';
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
	
	onMount(async () => {
		try {
			// Check auth
			const authResponse = await fetch(getApiUrl('/api/v1/auth/me'), {
				credentials: 'include'
			});
			
			if (!authResponse.ok) {
				error.set('Authentication failed');
				return;
			}
			
			const userData = await authResponse.json();
			
			if (!userData.is_admin && !userData.is_superuser) {
				error.set('Administrator privileges required');
				return;
			}
			
			// Load data
			loading.set(true);
			await Promise.all([loadUsers(), loadAdminSettings()]);
			
		} catch (err) {
			console.error('Error:', err);
			error.set(err instanceof Error ? err.message : 'Unknown error');
		} finally {
			loading.set(false);
		}
	});
	
	async function loadUsers() {
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
			console.error('Error loading users:', err);
			throw err;
		}
	}
	
	async function loadAdminSettings() {
		try {
			const response = await fetch(getApiUrl('/api/v1/admin/settings'), {
				credentials: 'include'
			});
			
			if (!response.ok) {
				// Settings endpoint might not exist, don't fail silently
				console.warn('Admin settings endpoint not found');
				return;
			}
			
			const data = await response.json();
			adminSettings.set(data);
		} catch (err) {
			console.error('Error loading admin settings:', err);
			// Don't fail the whole page if settings fail
		}
	}
	
	async function updateAdminSetting(field: 'users_open_registration' | 'allow_invitation_tokens', value: boolean) {
		if (!$adminSettings) return;
		
		settingsLoading.set(true);
		
		try {
			const response = await fetch(getApiUrl('/api/v1/admin/settings'), {
				method: 'PATCH',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({
					[field]: value
				})
			});
			
			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.detail || `HTTP ${response.status}`);
			}
			
			const updatedSettings = await response.json();
			adminSettings.set(updatedSettings);
		} catch (err) {
			error.set(err instanceof Error ? err.message : 'Failed to update setting');
			// Revert the setting on error
			await loadAdminSettings();
		} finally {
			settingsLoading.set(false);
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
			<Button onclick={() => showAddUserForm = !showAddUserForm}>
				<Plus class="w-4 h-4 mr-2" />
				Add User
			</Button>
		</div>
		
		{#if $error}
			<div class="text-red-500 p-4 border border-red-300 rounded">
				Error: {$error}
			</div>
		{:else if $loading}
			<div class="p-4">Loading...</div>
		{:else}
			<!-- Admin Settings -->
			<Card>
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<Settings class="w-5 h-5" />
						System Settings
					</CardTitle>
				</CardHeader>
				<CardContent>
					{#if $adminSettings}
						<div class="space-y-6">
							<!-- User Registration Setting -->
							<div class="flex items-center justify-between p-4 border rounded-lg">
								<div class="space-y-1">
									<div class="flex items-center gap-2">
										<UserPlus class="w-4 h-4 text-muted-foreground" />
										<h4 class="font-medium">Open User Registration</h4>
									</div>
									<p class="text-sm text-muted-foreground">
										Allow new users to register via the standard registration form
									</p>
								</div>
								<div class="flex items-center gap-2">
									<label class="flex items-center gap-2 cursor-pointer">
										<input
											type="checkbox"
											bind:checked={$adminSettings.users_open_registration}
											on:change={(e) => updateAdminSetting('users_open_registration', e.target.checked)}
											disabled={$settingsLoading}
											class="rounded border-gray-300"
										/>
										<span class="text-sm">
											{$adminSettings.users_open_registration ? 'Enabled' : 'Disabled'}
										</span>
									</label>
								</div>
							</div>
							
							<!-- Invitation Tokens Setting -->
							<div class="flex items-center justify-between p-4 border rounded-lg">
								<div class="space-y-1">
									<div class="flex items-center gap-2">
										<Shield class="w-4 h-4 text-muted-foreground" />
										<h4 class="font-medium">Allow Invitation Tokens</h4>
									</div>
									<p class="text-sm text-muted-foreground">
										Enable administrators to create invitation tokens for new users
									</p>
								</div>
								<div class="flex items-center gap-2">
									<label class="flex items-center gap-2 cursor-pointer">
										<input
											type="checkbox"
											bind:checked={$adminSettings.allow_invitation_tokens}
											on:change={(e) => updateAdminSetting('allow_invitation_tokens', e.target.checked)}
											disabled={$settingsLoading}
											class="rounded border-gray-300"
										/>
										<span class="text-sm">
											{$adminSettings.allow_invitation_tokens ? 'Enabled' : 'Disabled'}
										</span>
									</label>
								</div>
							</div>
						</div>
					{:else}
						<p class="text-muted-foreground">Admin settings not available</p>
					{/if}
				</CardContent>
			</Card>
			
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
					<div class="space-y-4">
						<p>Total users: {$users.length} | Filtered: {filteredUsers.length}</p>
						{#each filteredUsers.slice(0, 10) as user}
							<div class="border rounded-lg p-4">
								<div class="flex items-center justify-between">
									<div>
										<h4 class="font-semibold">{user.email}</h4>
										<p class="text-sm text-muted-foreground">{user.full_name || 'No name'}</p>
										<p class="text-xs text-muted-foreground">
											Created: {user.created_at ? formatDateTime(user.created_at) : 'Unknown'}
										</p>
									</div>
									<div class="flex gap-2">
										{#if user.is_admin}
											<Badge variant="secondary">
												<Shield class="w-3 h-3 mr-1" />
												Admin
											</Badge>
										{/if}
										{#if user.is_active}
											<Badge variant="outline">
												<CheckCircle2 class="w-3 h-3 mr-1" />
												Active
											</Badge>
										{:else}
											<Badge variant="destructive">
												<AlertCircle class="w-3 h-3 mr-1" />
												Inactive
											</Badge>
										{/if}
									</div>
								</div>
							</div>
						{/each}
					</div>
				</CardContent>
			</Card>
		{/if}
	</div>
</div>