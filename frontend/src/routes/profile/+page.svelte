<script lang="ts">
	import { onMount } from 'svelte';
	import { auth, user, authError } from '$lib/stores/auth';
	import { Card, CardHeader, CardTitle, CardContent } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { formatDateTime } from '$lib/utils';
	import { 
		User, 
		Mail, 
		Calendar, 
		Shield, 
		Edit, 
		Save, 
		X, 
		Eye, 
		EyeOff,
		AlertCircle,
		CheckCircle2
	} from 'lucide-svelte';
	
	// Profile editing state
	let editing = false;
	let editForm = {
		username: '',
		full_name: '',
		email: ''
	};
	
	// Password change state
	let showPasswordForm = false;
	let passwordForm = {
		currentPassword: '',
		newPassword: '',
		confirmPassword: ''
	};
	let showCurrentPassword = false;
	let showNewPassword = false;
	let showConfirmPassword = false;
	let passwordError = '';
	let passwordSuccess = false;
	
	// Form validation
	let formErrors: Record<string, string> = {};
	let saving = false;
	
	$: if ($user && !editing) {
		editForm = {
			username: $user.username || '',
			full_name: $user.full_name || '',
			email: $user.email || ''
		};
	}
	
	function startEditing() {
		editing = true;
		formErrors = {};
	}
	
	function cancelEditing() {
		editing = false;
		formErrors = {};
		if ($user) {
			editForm = {
				username: $user.username || '',
				full_name: $user.full_name || '',
				email: $user.email || ''
			};
		}
	}
	
	function validateForm(): boolean {
		formErrors = {};
		
		if (!editForm.username.trim()) {
			formErrors.username = 'Username is required';
		}
		
		if (!editForm.email.trim()) {
			formErrors.email = 'Email is required';
		} else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editForm.email)) {
			formErrors.email = 'Invalid email format';
		}
		
		return Object.keys(formErrors).length === 0;
	}
	
	async function saveProfile() {
		if (!validateForm()) return;
		
		saving = true;
		const result = await auth.updateProfile({
			username: editForm.username.trim(),
			full_name: editForm.full_name.trim() || undefined,
			email: editForm.email.trim()
		});
		
		saving = false;
		
		if (result.success) {
			editing = false;
		}
	}
	
	function validatePassword(): boolean {
		passwordError = '';
		
		if (!passwordForm.currentPassword) {
			passwordError = 'Current password is required';
			return false;
		}
		
		if (!passwordForm.newPassword) {
			passwordError = 'New password is required';
			return false;
		}
		
		if (passwordForm.newPassword.length < 8) {
			passwordError = 'New password must be at least 8 characters';
			return false;
		}
		
		if (passwordForm.newPassword !== passwordForm.confirmPassword) {
			passwordError = 'Passwords do not match';
			return false;
		}
		
		return true;
	}
	
	async function changePassword() {
		if (!validatePassword()) return;
		
		saving = true;
		const result = await auth.changePassword(
			passwordForm.currentPassword,
			passwordForm.newPassword
		);
		
		saving = false;
		
		if (result.success) {
			passwordSuccess = true;
			passwordForm = {
				currentPassword: '',
				newPassword: '',
				confirmPassword: ''
			};
			showPasswordForm = false;
			
			// Clear success message after 3 seconds
			setTimeout(() => {
				passwordSuccess = false;
			}, 3000);
		} else {
			passwordError = result.error || 'Password change failed';
		}
	}
	
	function cancelPasswordChange() {
		showPasswordForm = false;
		passwordError = '';
		passwordForm = {
			currentPassword: '',
			newPassword: '',
			confirmPassword: ''
		};
	}
</script>

<div class="container mx-auto px-4 py-8 max-w-4xl">
	<div class="space-y-6">
		<!-- Header -->
		<div>
			<h1 class="text-3xl font-bold">Profile Settings</h1>
			<p class="text-muted-foreground">Manage your account settings and preferences</p>
		</div>
		
		<!-- Success Messages -->
		{#if passwordSuccess}
			<Card class="border-green-200 bg-green-50">
				<CardContent class="pt-6">
					<div class="flex items-center gap-2 text-green-700">
						<CheckCircle2 class="w-5 h-5" />
						<span>Password changed successfully</span>
					</div>
				</CardContent>
			</Card>
		{/if}
		
		<!-- Error Messages -->
		{#if $authError}
			<Card class="border-destructive">
				<CardContent class="pt-6">
					<div class="flex items-center gap-2 text-destructive">
						<AlertCircle class="w-5 h-5" />
						<span>{$authError}</span>
					</div>
				</CardContent>
			</Card>
		{/if}
		
		{#if $user}
			<div class="grid gap-6 lg:grid-cols-3">
				<!-- Profile Information -->
				<div class="lg:col-span-2 space-y-6">
					<Card>
						<CardHeader class="flex flex-row items-center justify-between">
							<CardTitle class="flex items-center gap-2">
								<User class="w-5 h-5" />
								Profile Information
							</CardTitle>
							{#if !editing}
								<Button variant="outline" size="sm" on:click={startEditing}>
									<Edit class="w-4 h-4 mr-2" />
									Edit
								</Button>
							{/if}
						</CardHeader>
						<CardContent class="space-y-4">
							{#if editing}
								<!-- Edit Form -->
								<div class="space-y-4">
									<div>
										<label for="username" class="text-sm font-medium mb-2 block">
											Username *
										</label>
										<input
											id="username"
											type="text"
											bind:value={editForm.username}
											class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
											class:border-destructive={formErrors.username}
										/>
										{#if formErrors.username}
											<p class="text-destructive text-sm mt-1">{formErrors.username}</p>
										{/if}
									</div>
									
									<div>
										<label for="full_name" class="text-sm font-medium mb-2 block">
											Full Name
										</label>
										<input
											id="full_name"
											type="text"
											bind:value={editForm.full_name}
											class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
										/>
									</div>
									
									<div>
										<label for="email" class="text-sm font-medium mb-2 block">
											Email *
										</label>
										<input
											id="email"
											type="email"
											bind:value={editForm.email}
											class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm"
											class:border-destructive={formErrors.email}
										/>
										{#if formErrors.email}
											<p class="text-destructive text-sm mt-1">{formErrors.email}</p>
										{/if}
									</div>
									
									<div class="flex gap-2 pt-4">
										<Button on:click={saveProfile} disabled={saving}>
											<Save class="w-4 h-4 mr-2" />
											{saving ? 'Saving...' : 'Save Changes'}
										</Button>
										<Button variant="outline" on:click={cancelEditing}>
											<X class="w-4 h-4 mr-2" />
											Cancel
										</Button>
									</div>
								</div>
							{:else}
								<!-- Display Mode -->
								<div class="space-y-4">
									<div class="flex items-center justify-between">
										<span class="text-sm font-medium">Username</span>
										<span class="text-sm">{$user.username}</span>
									</div>
									
									<div class="flex items-center justify-between">
										<span class="text-sm font-medium">Full Name</span>
										<span class="text-sm">{$user.full_name || 'Not set'}</span>
									</div>
									
									<div class="flex items-center justify-between">
										<span class="text-sm font-medium">Email</span>
										<span class="text-sm flex items-center gap-2">
											<Mail class="w-4 h-4 text-muted-foreground" />
											{$user.email}
										</span>
									</div>
								</div>
							{/if}
						</CardContent>
					</Card>
					
					<!-- Security Settings -->
					<Card>
						<CardHeader>
							<CardTitle class="flex items-center gap-2">
								<Shield class="w-5 h-5" />
								Security
							</CardTitle>
						</CardHeader>
						<CardContent class="space-y-4">
							{#if !showPasswordForm}
								<div class="flex items-center justify-between">
									<div>
										<p class="font-medium">Password</p>
										<p class="text-sm text-muted-foreground">
											Change your password to keep your account secure
										</p>
									</div>
									<Button variant="outline" on:click={() => showPasswordForm = true}>
										Change Password
									</Button>
								</div>
							{:else}
								<!-- Password Change Form -->
								<div class="space-y-4">
									<div>
										<label for="current_password" class="text-sm font-medium mb-2 block">
											Current Password
										</label>
										<div class="relative">
											<input
												id="current_password"
												type={showCurrentPassword ? 'text' : 'password'}
												bind:value={passwordForm.currentPassword}
												class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm pr-10"
											/>
											<button
												type="button"
												class="absolute right-3 top-1/2 transform -translate-y-1/2"
												on:click={() => showCurrentPassword = !showCurrentPassword}
											>
												{#if showCurrentPassword}
													<EyeOff class="w-4 h-4 text-muted-foreground" />
												{:else}
													<Eye class="w-4 h-4 text-muted-foreground" />
												{/if}
											</button>
										</div>
									</div>
									
									<div>
										<label for="new_password" class="text-sm font-medium mb-2 block">
											New Password
										</label>
										<div class="relative">
											<input
												id="new_password"
												type={showNewPassword ? 'text' : 'password'}
												bind:value={passwordForm.newPassword}
												class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm pr-10"
											/>
											<button
												type="button"
												class="absolute right-3 top-1/2 transform -translate-y-1/2"
												on:click={() => showNewPassword = !showNewPassword}
											>
												{#if showNewPassword}
													<EyeOff class="w-4 h-4 text-muted-foreground" />
												{:else}
													<Eye class="w-4 h-4 text-muted-foreground" />
												{/if}
											</button>
										</div>
									</div>
									
									<div>
										<label for="confirm_password" class="text-sm font-medium mb-2 block">
											Confirm New Password
										</label>
										<div class="relative">
											<input
												id="confirm_password"
												type={showConfirmPassword ? 'text' : 'password'}
												bind:value={passwordForm.confirmPassword}
												class="w-full px-3 py-2 border border-input bg-background rounded-md text-sm pr-10"
											/>
											<button
												type="button"
												class="absolute right-3 top-1/2 transform -translate-y-1/2"
												on:click={() => showConfirmPassword = !showConfirmPassword}
											>
												{#if showConfirmPassword}
													<EyeOff class="w-4 h-4 text-muted-foreground" />
												{:else}
													<Eye class="w-4 h-4 text-muted-foreground" />
												{/if}
											</button>
										</div>
									</div>
									
									{#if passwordError}
										<div class="flex items-center gap-2 text-destructive text-sm">
											<AlertCircle class="w-4 h-4" />
											<span>{passwordError}</span>
										</div>
									{/if}
									
									<div class="flex gap-2 pt-2">
										<Button on:click={changePassword} disabled={saving}>
											<Save class="w-4 h-4 mr-2" />
											{saving ? 'Changing...' : 'Change Password'}
										</Button>
										<Button variant="outline" on:click={cancelPasswordChange}>
											<X class="w-4 h-4 mr-2" />
											Cancel
										</Button>
									</div>
								</div>
							{/if}
						</CardContent>
					</Card>
				</div>
				
				<!-- Account Overview -->
				<div class="space-y-6">
					<Card>
						<CardHeader>
							<CardTitle>Account Overview</CardTitle>
						</CardHeader>
						<CardContent class="space-y-4">
							<div class="space-y-3">
								<div class="flex items-center gap-2">
									<Shield class="w-4 h-4 text-muted-foreground" />
									<span class="text-sm">Role</span>
									<Badge variant={$user.is_admin ? 'default' : 'secondary'}>
										{$user.is_admin ? 'Administrator' : 'User'}
									</Badge>
								</div>
								
								<div class="flex items-center gap-2">
									<Calendar class="w-4 h-4 text-muted-foreground" />
									<span class="text-sm">Member since</span>
									<span class="text-sm text-muted-foreground">
										{formatDateTime($user.created_at)}
									</span>
								</div>
								
								{#if $user.last_login}
									<div class="flex items-center gap-2">
										<Calendar class="w-4 h-4 text-muted-foreground" />
										<span class="text-sm">Last login</span>
										<span class="text-sm text-muted-foreground">
											{formatDateTime($user.last_login)}
										</span>
									</div>
								{/if}
								
								<div class="flex items-center gap-2">
									<div class={`w-2 h-2 rounded-full ${$user.is_active ? 'bg-green-500' : 'bg-red-500'}`}></div>
									<span class="text-sm">Status</span>
									<Badge variant={$user.is_active ? 'success' : 'destructive'}>
										{$user.is_active ? 'Active' : 'Inactive'}
									</Badge>
								</div>
							</div>
						</CardContent>
					</Card>
				</div>
			</div>
		{/if}
	</div>
</div>