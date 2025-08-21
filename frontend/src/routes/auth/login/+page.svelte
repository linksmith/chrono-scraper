<script lang="ts">
    import { goto } from '$app/navigation';
	import { auth } from '$lib/stores/auth.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card/index.js';
	import { Alert, AlertDescription } from '$lib/components/ui/alert/index.js';
	import { AlertCircle } from 'lucide-svelte';
	import { base } from '$app/paths';
	
	let email = '';
	let password = '';
	let error = '';
	let loading = false;
	
	async function handleLogin(event: Event) {
		event.preventDefault();
		loading = true;
		error = '';
		
		try {
			const result = await auth.login(email, password);
			
			if (result.success) {
				// Navigate to redirect target or projects for verified users
				const url = new URL(window.location.href);
				const redirectTo = url.searchParams.get('redirect') || '/projects';
				await goto(redirectTo);
			} else {
				error = result.error || 'Login failed';
			}
		} catch (err) {
			error = 'Failed to connect to server';
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>Login - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-muted/40 grid lg:grid-cols-2">
	<!-- Left Panel - Form -->
	<div class="flex items-center justify-center py-12">
		<div class="mx-auto w-full max-w-sm space-y-6">
			<div class="flex justify-center">
				<img src={`${base}/logo/chrono-scraper-logo.png`} alt="" class="h-10 w-10" width="40" height="40" />
			</div>
			<div class="space-y-2 text-center">
				<h1 class="text-3xl font-bold">Welcome back</h1>
				<p class="text-muted-foreground">
					Sign in to your Chrono Scraper account
				</p>
			</div>
			
			<Card class="border-0 shadow-none bg-transparent">
				<CardContent class="p-0">
					<form on:submit={handleLogin} class="space-y-4">
						{#if error}
							<Alert variant="destructive">
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>{error}</AlertDescription>
							</Alert>
						{/if}
						
						<div class="space-y-2">
							<Label for="email">Email</Label>
							<Input
								id="email"
								type="email"
								bind:value={email}
								placeholder="researcher@university.edu"
								required
								class="h-11"
							/>
						</div>
						
						<div class="space-y-2">
							<div class="flex items-center justify-between">
								<Label for="password">Password</Label>
								<a 
									href="/auth/forgot-password" 
									class="text-sm text-muted-foreground hover:text-foreground"
								>
									Forgot password?
								</a>
							</div>
							<Input
								id="password"
								type="password"
								bind:value={password}
								required
								class="h-11"
							/>
						</div>
						
						<Button type="submit" class="w-full h-11" disabled={loading}>
							{loading ? 'Signing in...' : 'Sign in'}
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
						<!-- Future OAuth2 buttons will go here -->
						<p class="text-center text-sm text-muted-foreground">
							Don't have an account?{' '}
							<a href="/auth/register" class="underline underline-offset-4 hover:text-primary">
								Sign up
							</a>
						</p>
						
						<p class="text-center text-sm text-muted-foreground">
							Have an invitation code?{' '}
							<a href="/auth/register-invite" class="underline underline-offset-4 hover:text-primary">
								Register with invitation
							</a>
						</p>
					</div>
				</CardContent>
			</Card>
		</div>
	</div>
	
	<!-- Right Panel - Background -->
	<div class="hidden lg:block">
		<div class="h-full bg-gradient-to-br from-primary/20 via-primary/10 to-muted/50 flex items-center justify-center p-12">
			<div class="max-w-md text-center space-y-4">
				<div class="mx-auto w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
					<svg class="w-8 h-8 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
							d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
				</div>
				<h2 class="text-2xl font-bold text-foreground">
					Historical Web Research
				</h2>
				<p class="text-muted-foreground leading-relaxed">
					Access archived web content with intelligent scraping and comprehensive search capabilities. 
					Built for researchers, journalists, and investigators.
				</p>
				<div class="flex items-center justify-center space-x-2 text-sm text-muted-foreground">
					<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
							d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
					</svg>
					<span>Trusted by research institutions worldwide</span>
				</div>
			</div>
		</div>
	</div>
</div>