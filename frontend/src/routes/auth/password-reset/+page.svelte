<script lang="ts">
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card/index.js';
	import { Alert, AlertDescription } from '$lib/components/ui/alert/index.js';
	import { AlertCircle, CheckCircle, ArrowLeft } from 'lucide-svelte';
	import { base } from '$app/paths';
	
	let email = '';
	let error = '';
	let success = false;
	let loading = false;
	
	async function handlePasswordReset(event: Event) {
		event.preventDefault();
		loading = true;
		error = '';
		
		try {
			const response = await fetch('/api/v1/auth/password-reset', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include',
				body: JSON.stringify({ email })
			});
			
			if (response.ok) {
				success = true;
			} else {
				const data = await response.json();
				error = data.detail || 'Failed to send password reset email';
			}
		} catch (err) {
			error = 'Failed to connect to server';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Reset Password - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-muted/40 grid lg:grid-cols-2">
	<!-- Left Panel - Form -->
	<div class="flex items-center justify-center py-12">
		<div class="mx-auto w-full max-w-sm space-y-6">
			<div class="flex justify-center">
				<img src={`${base}/logo/chrono-scraper-logo.png`} alt="" class="h-10 w-10" width="40" height="40" />
			</div>
			
			{#if !success}
				<div class="space-y-2 text-center">
					<h1 class="text-3xl font-bold">Reset your password</h1>
					<p class="text-muted-foreground">
						Enter your email address and we'll send you a link to reset your password.
					</p>
				</div>
				
				<Card class="border-0 shadow-none bg-transparent">
					<CardContent class="p-0">
						<form onsubmit={handlePasswordReset} class="space-y-4">
							{#if error}
								<Alert variant="destructive">
									<AlertCircle class="h-4 w-4" />
									<AlertDescription data-testid="error-message">{error}</AlertDescription>
								</Alert>
							{/if}
							
							<div class="space-y-2">
								<Label for="email">Email</Label>
								<Input
									id="email"
									data-testid="email-input"
									type="email"
									bind:value={email}
									placeholder="researcher@university.edu"
									required
									class="h-11"
								/>
							</div>
							
							<Button 
								type="submit" 
								class="w-full h-11" 
								disabled={loading}
								data-testid="reset-button"
							>
								{loading ? 'Sending...' : 'Send reset link'}
							</Button>
						</form>
						
						<div class="relative my-6">
							<div class="absolute inset-0 flex items-center">
								<span class="w-full border-t"></span>
							</div>
							<div class="relative flex justify-center text-xs uppercase">
								<span class="bg-background px-3 text-muted-foreground">
									or
								</span>
							</div>
						</div>
						
						<div class="space-y-4">
							<p class="text-center text-sm text-muted-foreground">
								Remember your password?{' '}
								<a href="/auth/login" class="underline underline-offset-4 hover:text-primary">
									Back to sign in
								</a>
							</p>
						</div>
					</CardContent>
				</Card>
			{:else}
				<div class="space-y-2 text-center">
					<div class="mx-auto w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
						<CheckCircle class="w-8 h-8 text-green-600" />
					</div>
					<h1 class="text-3xl font-bold">Check your email</h1>
					<p class="text-muted-foreground">
						If an account with that email exists, we've sent you a password reset link.
					</p>
					<Alert data-testid="success-message" class="mt-4">
						<CheckCircle class="h-4 w-4" />
						<AlertDescription>Password reset email sent</AlertDescription>
					</Alert>
				</div>
				
				<div class="space-y-4">
					<p class="text-center text-sm text-muted-foreground">
						Didn't receive an email? Check your spam folder or{' '}
						<button 
							onclick={() => {success = false; email = '';}}
							class="underline underline-offset-4 hover:text-primary cursor-pointer"
						>
							try again
						</button>
					</p>
					
					<p class="text-center text-sm text-muted-foreground">
						<a href="/auth/login" class="underline underline-offset-4 hover:text-primary inline-flex items-center gap-1">
							<ArrowLeft class="w-3 h-3" />
							Back to sign in
						</a>
					</p>
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
							d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
					</svg>
				</div>
				<h2 class="text-2xl font-bold text-foreground">
					Secure Reset Process
				</h2>
				<p class="text-muted-foreground leading-relaxed">
					We'll send you a secure link to reset your password. The link expires in 48 hours for your security.
				</p>
				<div class="flex items-center justify-center space-x-2 text-sm text-muted-foreground">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
							d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<span>Your data is protected with industry-standard security</span>
				</div>
			</div>
		</div>
	</div>
</div>