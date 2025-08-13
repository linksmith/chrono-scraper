<script lang="ts">
	import { goto } from '$app/navigation';
	import { getApiUrl } from '$lib/utils';
	import { auth } from '$lib/stores/auth';
	
	let resending = false;
	let resendSuccess = false;
	let resendError = '';
	
	async function resendVerification() {
		resending = true;
		resendSuccess = false;
		resendError = '';
		
		try {
			const response = await fetch(getApiUrl('/api/v1/auth/email/resend-current'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				credentials: 'include'
			});
			
			if (response.ok) {
				resendSuccess = true;
			} else {
				const data = await response.json();
				resendError = data.detail || 'Failed to resend verification email';
			}
		} catch (err) {
			resendError = 'Failed to connect to server';
		} finally {
			resending = false;
		}
	}
	
	function logout() {
		auth.logout();
	}
</script>

<div class="container mx-auto px-4 py-16">
	<div class="max-w-md mx-auto text-center">
		<h1 class="text-3xl font-bold mb-4 text-yellow-600">Email Verification Required</h1>
		
		<div class="bg-yellow-50 border border-yellow-200 text-yellow-800 px-6 py-4 rounded-lg mb-6">
			<p class="mb-4">
				Your account has been created successfully, but you need to verify your email address before you can access the application.
			</p>
			<p class="text-sm">
				Please check your email for a verification link. If you can't find it, check your spam folder.
			</p>
		</div>
		
		<div class="space-y-4">
			{#if resendSuccess}
				<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded">
					✓ Verification email sent! Please check your inbox.
				</div>
			{/if}
			
			{#if resendError}
				<div class="bg-destructive/10 text-destructive px-4 py-3 rounded">
					{resendError}
				</div>
			{/if}
			
			<button
				on:click={resendVerification}
				disabled={resending}
				class="w-full bg-primary text-primary-foreground py-2 rounded-md hover:bg-primary/90 disabled:opacity-50"
			>
				{resending ? 'Sending...' : 'Resend Verification Email'}
			</button>
			
			<button
				on:click={logout}
				class="w-full border border-input bg-background py-2 rounded-md hover:bg-accent"
			>
				Logout
			</button>
			
			<p class="text-sm text-muted-foreground">
				Already verified? <a href="/auth/login" class="text-primary hover:underline">Try logging in again</a>
			</p>
		</div>
	</div>
</div>