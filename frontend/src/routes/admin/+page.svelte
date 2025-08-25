<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Users,
		Settings,
		Shield,
		Plus,
		AlertTriangle,
		BarChart3,
		FileText,
		UserPlus,
		CheckCircle2,
		XCircle
	} from 'lucide-svelte';
	import { formatDateTime, formatNumber, getApiUrl } from '$lib/utils';
	import UserManagementTable from '$lib/components/admin/UserManagementTable.svelte';
	import UserAnalytics from '$lib/components/admin/UserAnalytics.svelte';

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

	interface AdminStats {
		total_users: number;
		active_users: number;
		pending_approvals: number;
		total_admins: number;
		new_users_today: number;
		new_users_week: number;
	}

	// State management
	const users = writable<User[]>([]);
	const adminSettings = writable<AdminSettings | null>(null);
	const adminStats = writable<AdminStats | null>(null);
	const loading = writable(false);
	const settingsLoading = writable(false);
	const error = writable<string | null>(null);
	const currentTab = writable('users');

	// Current user info
	let currentUser: any = null;

	onMount(async () => {
		try {
			// Check authentication and load initial data
			await checkAuth();
			if (currentUser) {
				await Promise.all([
					loadUsers(),
					loadAdminSettings(),
					loadAdminStats()
				]);
			}
		} catch (err) {
			console.error('Error initializing admin panel:', err);
			error.set(err instanceof Error ? err.message : 'Failed to initialize admin panel');
		}
	});

	async function checkAuth() {
		try {
			const response = await fetch(getApiUrl('/api/v1/auth/me'), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error('Authentication failed');
			}

			const userData = await response.json();

			if (!userData.is_admin && !userData.is_superuser) {
				throw new Error('Administrator privileges required');
			}

			currentUser = userData;
		} catch (err) {
			throw new Error('Access denied: ' + (err instanceof Error ? err.message : 'Unknown error'));
		}
	}

	async function loadUsers() {
		try {
			loading.set(true);
			const response = await fetch(getApiUrl('/api/v1/admin/users'), {
				credentials: 'include'
			});

			if (!response.ok) {
				throw new Error(`Failed to load users: HTTP ${response.status}`);
			}

			const data = await response.json();
			users.set(data);
		} catch (err) {
			console.error('Error loading users:', err);
			error.set(err instanceof Error ? err.message : 'Failed to load users');
		} finally {
			loading.set(false);
		}
	}

	async function loadAdminSettings() {
		try {
			const response = await fetch(getApiUrl('/api/v1/admin/settings'), {
				credentials: 'include'
			});

			if (response.ok) {
				const data = await response.json();
				adminSettings.set(data);
			} else {
				console.warn('Admin settings endpoint not available');
			}
		} catch (err) {
			console.error('Error loading admin settings:', err);
			// Don't set error for settings - they're optional
		}
	}

	async function loadAdminStats() {
		try {
			const currentUsers = $users;
			const now = new Date();
			const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			const weekStart = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

			const stats: AdminStats = {
				total_users: currentUsers.length,
				active_users: currentUsers.filter(u => u.is_active).length,
				pending_approvals: currentUsers.filter(u => u.approval_status === 'pending').length,
				total_admins: currentUsers.filter(u => u.is_admin).length,
				new_users_today: currentUsers.filter(u => 
					new Date(u.created_at) >= todayStart
				).length,
				new_users_week: currentUsers.filter(u => 
					new Date(u.created_at) >= weekStart
				).length,
			};

			adminStats.set(stats);
		} catch (err) {
			console.error('Error calculating admin stats:', err);
		}
	}

	async function updateAdminSetting(field: keyof AdminSettings, value: any) {
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
			// Reload settings to revert changes
			await loadAdminSettings();
		} finally {
			settingsLoading.set(false);
		}
	}

	function handleUserTableRefresh() {
		loadUsers().then(() => {
			loadAdminStats();
		});
	}

	function handleUserTableError(event: CustomEvent) {
		error.set(event.detail);
	}

	function handleUserEdit(event: CustomEvent) {
		const user = event.detail;
		// TODO: Implement user editing dialog
		console.log('Edit user:', user);
	}

	function handleUserDelete(event: CustomEvent) {
		const user = event.detail;
		// TODO: Implement user deletion confirmation
		console.log('Delete user:', user);
	}

	function handleUserToggleStatus(event: CustomEvent) {
		const user = event.detail;
		// TODO: Implement user status toggle
		console.log('Toggle user status:', user);
	}

	// Calculate dashboard stats reactively
	$: dashboardStats = $adminStats || {
		total_users: 0,
		active_users: 0,
		pending_approvals: 0,
		total_admins: 0,
		new_users_today: 0,
		new_users_week: 0
	};
</script>

<svelte:head>
	<title>Admin Panel - Chrono Scraper</title>
	<meta name="description" content="Administrator dashboard for user management and system settings" />
</svelte:head>

<div class="container mx-auto px-4 py-8">
	<div class="space-y-6">
		<!-- Header -->
		<div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
			<div>
				<h1 class="text-3xl font-bold flex items-center gap-2">
					<Shield class="h-8 w-8 text-blue-600" />
					Admin Panel
				</h1>
				<p class="text-muted-foreground mt-1">
					Comprehensive user management and system administration
				</p>
			</div>
			{#if currentUser}
				<div class="flex items-center gap-2">
					<Badge variant="secondary">
						<Users class="h-3 w-3 mr-1" />
						{currentUser.email}
					</Badge>
					<Badge variant="default">
						<Shield class="h-3 w-3 mr-1" />
						Admin
					</Badge>
				</div>
			{/if}
		</div>

		<!-- Error Display -->
		{#if $error}
			<Alert variant="destructive">
				<AlertTriangle class="h-4 w-4" />
				<AlertDescription>{$error}</AlertDescription>
			</Alert>
		{/if}

		{#if currentUser}
			<!-- Dashboard Overview -->
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
				<Card>
					<CardContent class="p-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-medium text-gray-600">Total Users</p>
								<p class="text-2xl font-bold">{formatNumber(dashboardStats.total_users)}</p>
							</div>
							<Users class="h-8 w-8 text-blue-600" />
						</div>
						<div class="mt-2 text-sm text-gray-600">
							+{dashboardStats.new_users_week} this week
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardContent class="p-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-medium text-gray-600">Active Users</p>
								<p class="text-2xl font-bold text-green-600">{formatNumber(dashboardStats.active_users)}</p>
							</div>
							<CheckCircle2 class="h-8 w-8 text-green-600" />
						</div>
						<div class="mt-2 text-sm text-gray-600">
							{((dashboardStats.active_users / Math.max(dashboardStats.total_users, 1)) * 100).toFixed(1)}% of total
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardContent class="p-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-medium text-gray-600">Pending Approvals</p>
								<p class="text-2xl font-bold text-yellow-600">{formatNumber(dashboardStats.pending_approvals)}</p>
							</div>
							<XCircle class="h-8 w-8 text-yellow-600" />
						</div>
						<div class="mt-2 text-sm text-gray-600">
							Awaiting review
						</div>
					</CardContent>
				</Card>

				<Card>
					<CardContent class="p-6">
						<div class="flex items-center justify-between">
							<div>
								<p class="text-sm font-medium text-gray-600">Administrators</p>
								<p class="text-2xl font-bold text-purple-600">{formatNumber(dashboardStats.total_admins)}</p>
							</div>
							<Shield class="h-8 w-8 text-purple-600" />
						</div>
						<div class="mt-2 text-sm text-gray-600">
							System admins
						</div>
					</CardContent>
				</Card>
			</div>

			<!-- Main Content Tabs -->
			<Tabs bind:value={$currentTab} class="w-full">
				<TabsList class="grid w-full grid-cols-4">
					<TabsTrigger value="users" class="flex items-center gap-2">
						<Users class="h-4 w-4" />
						User Management
					</TabsTrigger>
					<TabsTrigger value="analytics" class="flex items-center gap-2">
						<BarChart3 class="h-4 w-4" />
						Analytics
					</TabsTrigger>
					<TabsTrigger value="settings" class="flex items-center gap-2">
						<Settings class="h-4 w-4" />
						Settings
					</TabsTrigger>
					<TabsTrigger value="audit" class="flex items-center gap-2">
						<FileText class="h-4 w-4" />
						Audit Log
					</TabsTrigger>
				</TabsList>

				<!-- User Management Tab -->
				<TabsContent value="users" class="space-y-6">
					<UserManagementTable
						users={$users}
						isLoading={$loading}
						error={$error}
						on:refresh={handleUserTableRefresh}
						on:error={handleUserTableError}
						on:edit={handleUserEdit}
						on:delete={handleUserDelete}
						on:toggleStatus={handleUserToggleStatus}
					/>
				</TabsContent>

				<!-- Analytics Tab -->
				<TabsContent value="analytics" class="space-y-6">
					<UserAnalytics />
				</TabsContent>

				<!-- Settings Tab -->
				<TabsContent value="settings" class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle class="flex items-center gap-2">
								<Settings class="h-5 w-5" />
								System Settings
							</CardTitle>
							<CardDescription>
								Configure system-wide settings and policies
							</CardDescription>
						</CardHeader>
						<CardContent>
							{#if $adminSettings}
								<div class="space-y-6">
									<!-- User Registration Setting -->
									<div class="flex items-center justify-between p-4 border rounded-lg">
										<div class="space-y-1">
											<div class="flex items-center gap-2">
												<UserPlus class="h-4 w-4 text-muted-foreground" />
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
												<Shield class="h-4 w-4 text-muted-foreground" />
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

									<div class="pt-4 text-sm text-gray-600">
										<p><strong>Last updated:</strong> {formatDateTime($adminSettings.updated_at)}</p>
									</div>
								</div>
							{:else}
								<div class="text-center py-8">
									<Settings class="h-12 w-12 mx-auto mb-4 text-gray-400" />
									<p class="text-gray-600">Admin settings not available</p>
									<Button variant="outline" onclick={loadAdminSettings} class="mt-4">
										Retry Loading Settings
									</Button>
								</div>
							{/if}
						</CardContent>
					</Card>
				</TabsContent>

				<!-- Audit Log Tab -->
				<TabsContent value="audit" class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle class="flex items-center gap-2">
								<FileText class="h-5 w-5" />
								Audit Log
							</CardTitle>
							<CardDescription>
								Track administrative actions and system events
							</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="text-center py-12">
								<FileText class="h-12 w-12 mx-auto mb-4 text-gray-400" />
								<p class="text-gray-600 mb-4">Audit logging is available</p>
								<p class="text-sm text-gray-500">
									View detailed logs of all administrative actions, bulk operations, and system events.
								</p>
							</div>
						</CardContent>
					</Card>
				</TabsContent>
			</Tabs>
		{:else}
			<!-- Loading State -->
			<div class="text-center py-12">
				<Shield class="h-12 w-12 mx-auto mb-4 text-gray-400 animate-pulse" />
				<p class="text-gray-600">Verifying administrator privileges...</p>
			</div>
		{/if}
	</div>
</div>

<style>
	/* Enhance checkbox styling */
	input[type="checkbox"] {
		@apply w-4 h-4;
	}
</style>