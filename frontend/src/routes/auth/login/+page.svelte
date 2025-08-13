<script lang="ts">
    import { goto } from '$app/navigation';
    import { getApiUrl } from '$lib/utils';
	
	let email = '';
	let password = '';
	let error = '';
	let loading = false;
	
	async function handleLogin(event: Event) {
		event.preventDefault();
		loading = true;
		error = '';
		
		try {
            const response = await fetch(getApiUrl('/api/v1/auth/login'), {
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
				// Navigate to redirect target or projects
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

<div class="container mx-auto px-4 py-16">
	<div class="max-w-md mx-auto">
		<h1 class="text-3xl font-bold mb-8">Login</h1>
		
		<form on:submit={handleLogin} class="space-y-4">
			{#if error}
				<div class="bg-destructive/10 text-destructive px-4 py-3 rounded">
					{error}
				</div>
			{/if}
			
			<div>
				<label for="email" class="block text-sm font-medium mb-2">Email</label>
				<input
					type="email"
					id="email"
					bind:value={email}
					required
					class="w-full px-3 py-2 border rounded-md"
					placeholder="you@example.com"
				/>
			</div>
			
			<div>
				<label for="password" class="block text-sm font-medium mb-2">Password</label>
				<input
					type="password"
					id="password"
					bind:value={password}
					required
					class="w-full px-3 py-2 border rounded-md"
					placeholder="••••••••"
				/>
			</div>
			
			<button
				type="submit"
				disabled={loading}
				class="w-full bg-primary text-primary-foreground py-2 rounded-md hover:bg-primary/90 disabled:opacity-50"
			>
				{loading ? 'Logging in...' : 'Login'}
			</button>
		</form>
		
		<p class="mt-4 text-center text-sm text-muted-foreground">
			Don't have an account? <a href="/auth/register" class="text-primary hover:underline">Register</a>
		</p>
	</div>
</div>