<script lang="ts">
    import { goto } from '$app/navigation';
    import { getApiUrl } from '$lib/utils';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card/index.js';
	
	let email = '';
	let password = '';
	let error = '';
	let loading = false;
	
	async function handleLogin(event: Event) {
		event.preventDefault();
		loading = true;
		error = '';
		
		try {
            const response = await fetch('/api/v1/auth/login', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
				},
				body: new URLSearchParams({
					username: email,
					password: password,
				}),
			});
			
			if (response.ok) {
				const data = await response.json();
				// Store token in cookie for SSR and API calls
				document.cookie = `access_token=${data.access_token}; Path=/; SameSite=Lax`;
				
				// Check if user is verified by fetching user data with cookie
				const userResponse = await fetch('/api/v1/auth/me', {
					credentials: 'include'
				});
				
				if (userResponse.ok) {
					const userData = await userResponse.json();
					if (!userData.is_verified) {
						// Redirect unverified users to verification notice page
						await goto('/auth/unverified');
						return;
					}
				}
				
				// Navigate to redirect target or projects for verified users
				const url = new URL(window.location.href);
				const redirectTo = url.searchParams.get('redirect') || '/projects';
				await goto(redirectTo);
			} else {
				error = 'Invalid email or password';
			}
		} catch (err) {
			error = 'Failed to connect to server';
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-svh w-full items-center justify-center p-6 md:p-10">
	<div class="w-full max-w-sm">
		<Card>
			<CardHeader>
				<CardTitle class="text-2xl">Login</CardTitle>
				<CardDescription>
					Enter your email below to login to your account
				</CardDescription>
			</CardHeader>
			<CardContent>
				<form on:submit={handleLogin} class="grid gap-4">
					{#if error}
						<div class="bg-destructive/10 text-destructive px-4 py-3 rounded border border-destructive/20">
							{error}
						</div>
					{/if}
					
					<div class="grid gap-2">
						<label for="email" class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
							Email
						</label>
						<Input
							id="email"
							type="email"
							bind:value={email}
							placeholder="m@example.com"
							required
						/>
					</div>
					
					<div class="grid gap-2">
						<div class="flex items-center">
							<label for="password" class="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
								Password
							</label>
						</div>
						<Input
							id="password"
							type="password"
							bind:value={password}
							required
						/>
					</div>
					
					<Button type="submit" class="w-full" disabled={loading}>
						{loading ? 'Logging in...' : 'Login'}
					</Button>
				</form>
				
				<div class="mt-4 text-center text-sm">
					Don't have an account?{' '}
					<a href="/auth/register" class="underline">
						Sign up
					</a>
				</div>
			</CardContent>
		</Card>
	</div>
</div>