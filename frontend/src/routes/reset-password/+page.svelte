<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Card, CardContent } from '$lib/components/ui/card/index.js';
	import { Alert, AlertDescription } from '$lib/components/ui/alert/index.js';
	import { AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-svelte';
	import { base } from '$app/paths';
	import { onMount } from 'svelte';
	
	let token = '';
	let newPassword = '';
	let confirmPassword = '';
	let error = '';
	let success = false;
	let loading = false;
	let showPassword = false;
	let showConfirmPassword = false;
	let validToken = false;
	let checkingToken = true;
	
	$: passwordMatch = newPassword === confirmPassword;
	$: passwordValid = newPassword.length >= 8;
	$: formValid = passwordValid && passwordMatch && newPassword && confirmPassword;
	
	onMount(() => {
		// Get token from URL parameter
		token = $page.url.searchParams.get('token') || '';
		
		if (!token) {
			error = 'Invalid reset link. Please request a new password reset.';
			checkingToken = false;
			return;
		}
		
		// For now, assume token format is valid if it exists
		// In a production app, you might want to validate the token format
		validToken = true;
		checkingToken = false;
	});
	
	async function handlePasswordReset(event: Event) {
		event.preventDefault();
		
		if (!formValid) {
			return;
		}
		
		loading = true;
		error = '';
		
		try {
			const response = await fetch('/api/v1/auth/password-reset-confirm', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({ 
					token, 
					new_password: newPassword 
				})
			});
			
			if (response.ok) {
				success = true;
				// Redirect to login after 3 seconds
				setTimeout(() => {
					goto('/auth/login');
				}, 3000);
			} else {
				const data = await response.json();
				error = data.detail || 'Failed to reset password';
			}
		} catch (err) {
			error = 'Failed to connect to server';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Set New Password - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-muted/40 grid lg:grid-cols-2">
	<!-- Left Panel - Form -->
	<div class="flex items-center justify-center py-12">
		<div class="mx-auto w-full max-w-sm space-y-6">
			<div class="flex justify-center">
				<img src={`${base}/logo/chrono-scraper-logo.png`} alt="" class="h-10 w-10" width="40" height="40" />
			</div>
			
			{#if checkingToken}
				<div class="space-y-2 text-center">
					<h1 class="text-3xl font-bold">Validating reset link...</h1>
					<p class="text-muted-foreground">
						Please wait while we verify your reset token.
					</p>
				</div>
			{:else if !validToken || (!success && error && (error.includes('Invalid') || error.includes('expired')))}
				<div class="space-y-2 text-center">
					<h1 class="text-3xl font-bold">Invalid reset link</h1>
					<p class="text-muted-foreground">
						This password reset link is invalid or has expired.
					</p>
				</div>
				
				<Card class="border-0 shadow-none bg-transparent">
					<CardContent class="p-0">
						<Alert variant="destructive">
							<AlertCircle class="h-4 w-4" />
							<AlertDescription>
								{error || 'Invalid or expired reset token'}
							</AlertDescription>
						</Alert>
						
						<div class="space-y-4 mt-6">
							<Button onclick={() => goto('/auth/password-reset')} class="w-full h-11">
								Request new reset link
							</Button>
							
							<p class="text-center text-sm text-muted-foreground">
								<a href="/auth/login" class="underline underline-offset-4 hover:text-primary">
									Back to sign in
								</a>
							</p>
						</div>
					</CardContent>
				</Card>
			{:else if !success}
				<div class="space-y-2 text-center">
					<h1 class="text-3xl font-bold">Set new password</h1>
					<p class="text-muted-foreground">
						Please enter your new password below.
					</p>
				</div>
				
				<Card class="border-0 shadow-none bg-transparent">
					<CardContent class="p-0">
						<form on:submit={handlePasswordReset} class="space-y-4">
							{#if error}
								<Alert variant="destructive">
									<AlertCircle class="h-4 w-4" />
									<AlertDescription data-testid="error-message">{error}</AlertDescription>
								</Alert>
							{/if}
							
							<div class="space-y-2">
								<Label for="new-password">New Password</Label>
								<div class="relative">
									<Input
										id="new-password"
										data-testid="password-input"
										type={showPassword ? 'text' : 'password'}
										bind:value={newPassword}
										placeholder="Enter your new password"
										required
										class="h-11 pr-10"
									/>
									<button
										type="button"
										class="absolute inset-y-0 right-0 flex items-center pr-3"
										onclick={() => showPassword = !showPassword}
									>
										{#if showPassword}
											<EyeOff class="h-4 w-4 text-muted-foreground" />
										{:else}
											<Eye class="h-4 w-4 text-muted-foreground" />
										{/if}
									</button>
								</div>
								{#if newPassword && !passwordValid}
									<p class="text-sm text-destructive">Password must be at least 8 characters long</p>
								{/if}
							</div>
							
							<div class="space-y-2">
								<Label for="confirm-password">Confirm New Password</Label>
								<div class="relative">
									<Input
										id="confirm-password"
										data-testid="confirm-password-input"
										type={showConfirmPassword ? 'text' : 'password'}
										bind:value={confirmPassword}
										placeholder="Confirm your new password"
										required
										class="h-11 pr-10"
									/>
									<button
										type="button"
										class="absolute inset-y-0 right-0 flex items-center pr-3"
										onclick={() => showConfirmPassword = !showConfirmPassword}
									>
										{#if showConfirmPassword}
											<EyeOff class="h-4 w-4 text-muted-foreground" />
										{:else}
											<Eye class="h-4 w-4 text-muted-foreground" />
										{/if}
									</button>
								</div>
								{#if confirmPassword && !passwordMatch}
									<p class="text-sm text-destructive">Passwords do not match</p>
								{/if}
							</div>
							
							<Button 
								type="submit" 
								class="w-full h-11" 
								disabled={loading || !formValid}
								data-testid="reset-button"
							>
								{loading ? 'Updating password...' : 'Update password'}
							</Button>
						</form>
					</CardContent>
				</Card>
			{:else}
				<div class="space-y-2 text-center">
					<div class="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
						<CheckCircle class="w-8 h-8 text-green-600" />
					</div>
					<h1 class="text-3xl font-bold">Password updated</h1>
					<p class="text-muted-foreground">
						Your password has been successfully updated. You will be redirected to the login page shortly.
					</p>
					<Alert data-testid="success-message" class="mt-4">
						<CheckCircle class="h-4 w-4" />
						<AlertDescription>Password has been reset successfully</AlertDescription>
					</Alert>
				</div>
				
				<div class="space-y-4">
					<Button onclick={() => goto('/auth/login')} class="w-full h-11">
						Continue to sign in
					</Button>
				</div>
			{/if}
		</div>
	</div>
	
	<!-- Right Panel - Background -->
	<div class="hidden lg:block">
		<div class="h-full bg-gradient-to-br from-primary/20 via-primary/10 to-muted/50 flex items-center justify-center p-12">
			<div class="max-w-md text-center space-y-4">
				<div class="mx-auto w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
					<svg class="w-8 h-8 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
							d="M9 12l2 2 4-4m5.5-4L12 15l-7-7" />
					</svg>
				</div>
				<h2 class="text-2xl font-bold text-foreground">
					Almost There!
				</h2>
				<p class="text-muted-foreground leading-relaxed">
					Create a strong password to secure your account. We recommend using a mix of letters, numbers, and symbols.
				</p>
				<div class="flex items-center justify-center space-x-2 text-sm text-muted-foreground">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
							d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
					</svg>
					<span>Your new password is encrypted and secure</span>
				</div>
			</div>
		</div>
	</div>
</div>