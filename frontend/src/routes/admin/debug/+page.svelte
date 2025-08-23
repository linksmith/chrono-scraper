<script lang="ts">
	import { onMount } from 'svelte';
	import { writable } from 'svelte/store';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { formatDateTime, formatNumber, getApiUrl } from '$lib/utils';
	import { Users } from 'lucide-svelte';
	
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
	
	onMount(async () => {
		console.log('Debug: Starting onMount');
		
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
			console.log('Debug: Auth data:', userData);
			
			if (!userData.is_admin && !userData.is_superuser) {
				error.set('Not admin');
				return;
			}
			
			// Load users
			loading.set(true);
			const response = await fetch(getApiUrl('/api/v1/admin/users'), {
				credentials: 'include'
			});
			
			if (!response.ok) {
				throw new Error(`HTTP ${response.status}`);
			}
			
			const data = await response.json();
			console.log('Debug: Users data:', data);
			users.set(data);
			console.log('Debug: Users set successfully');
			
		} catch (err) {
			console.error('Debug: Error:', err);
			error.set(err instanceof Error ? err.message : 'Unknown error');
		} finally {
			loading.set(false);
		}
	});
	
	// Test different components one by one
	let step = 1;
	
	function nextStep() {
		step++;
		console.log('Debug: Moving to step', step);
	}
</script>

<div class="container mx-auto px-4 py-8">
	<div class="space-y-6">
		<h1 class="text-3xl font-bold">Debug Admin Panel - Step {step}</h1>
		
		{#if $error}
			<div class="text-red-500 p-4 border border-red-300 rounded">
				Error: {$error}
			</div>
		{:else if $loading}
			<div class="p-4">Loading...</div>
		{:else}
			<div class="p-4 border border-green-300 rounded bg-green-50">
				Success! Loaded {$users.length} users.
				{#if $users.length > 0}
					First user: {$users[0].email}
				{/if}
			</div>
			
			<button 
				onclick={nextStep}
				class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
			>
				Next Step
			</button>
			
			<!-- Step 1: Basic user count -->
			{#if step >= 1}
				<Card>
					<CardHeader>
						<CardTitle class="flex items-center gap-2">
							<Users class="w-5 h-5" />
							Step 1: Users ({$users.length})
						</CardTitle>
					</CardHeader>
					<CardContent>
						<p>Total users loaded: {$users.length}</p>
					</CardContent>
				</Card>
			{/if}
			
			<!-- Step 2: Use formatNumber function -->
			{#if step >= 2}
				<Card>
					<CardHeader>
						<CardTitle>Step 2: Format Number Test</CardTitle>
					</CardHeader>
					<CardContent>
						<p>Formatted count: {formatNumber($users.length)}</p>
					</CardContent>
				</Card>
			{/if}
			
			<!-- Step 3: Basic user list without formatting -->
			{#if step >= 3}
				<Card>
					<CardHeader>
						<CardTitle>Step 3: Basic User List</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="space-y-2">
							{#each $users.slice(0, 3) as user}
								<div class="border p-2 rounded">
									<p><strong>Email:</strong> {user.email}</p>
									<p><strong>Active:</strong> {user.is_active}</p>
									<p><strong>Admin:</strong> {user.is_admin}</p>
								</div>
							{/each}
						</div>
					</CardContent>
				</Card>
			{/if}
			
			<!-- Step 4: Add date formatting -->
			{#if step >= 4}
				<Card>
					<CardHeader>
						<CardTitle>Step 4: Date Formatting Test</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="space-y-2">
							{#each $users.slice(0, 3) as user}
								<div class="border p-2 rounded">
									<p><strong>Email:</strong> {user.email}</p>
									<p><strong>Created:</strong> 
										{#if user.created_at}
											{formatDateTime(user.created_at)}
										{:else}
											No date
										{/if}
									</p>
									<p><strong>Last Login:</strong> 
										{#if user.last_login}
											{formatDateTime(user.last_login)}
										{:else}
											Never
										{/if}
									</p>
								</div>
							{/each}
						</div>
					</CardContent>
				</Card>
			{/if}
			
			<!-- Step 5: Full user list -->
			{#if step >= 5}
				<Card>
					<CardHeader>
						<CardTitle>Step 5: Full User List</CardTitle>
					</CardHeader>
					<CardContent>
						<div class="space-y-2">
							{#each $users as user}
								<div class="border p-2 rounded">
									<p><strong>Email:</strong> {user.email}</p>
									<p><strong>Full Name:</strong> {user.full_name || 'N/A'}</p>
									<p><strong>Active:</strong> {user.is_active}</p>
									<p><strong>Admin:</strong> {user.is_admin}</p>
									<p><strong>Created:</strong> 
										{#if user.created_at}
											{formatDateTime(user.created_at)}
										{:else}
											No date
										{/if}
									</p>
								</div>
							{/each}
						</div>
					</CardContent>
				</Card>
			{/if}
		{/if}
	</div>
</div>