<script lang="ts">
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getApiUrl } from '$lib/utils';

	let verifying = true;
	let success = false;
	let error = '';
	let showResendForm = false;
	let resendEmail = '';
	let resending = false;
	let resendSuccess = false;
	let resendError = '';

	onMount(async () => {
		const token = $page.url.searchParams.get('token');
		
		if (!token) {
			error = 'No verification token provided';
			verifying = false;
			return;
		}

		try {
			const response = await fetch(getApiUrl(`/api/v1/auth/email/verify?token=${token}`), {
				method: 'GET',
				headers: {
					'Content-Type': 'application/json'
				}
			});

			const data = await response.json();

			if (response.ok) {
				success = true;
			} else {
				error = data.detail || 'Verification failed. The link may be expired or invalid.';
			}
		} catch (err) {
			error = 'Failed to connect to the server. Please try again later.';
		} finally {
			verifying = false;
		}
	});

	function handleContinue() {
		goto('/auth/login');
	}

	async function requestNewLink() {
		if (!resendEmail.trim()) {
			resendError = 'Please enter your email address';
			return;
		}

		resending = true;
		resendError = '';
		resendSuccess = false;

		try {
			const response = await fetch(getApiUrl('/api/v1/auth/email/resend'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ email: resendEmail })
			});

			if (response.ok) {
				resendSuccess = true;
				showResendForm = false;
			} else {
				const data = await response.json();
				resendError = data.detail || 'Failed to send verification email';
			}
		} catch (err) {
			resendError = 'Failed to connect to server';
		} finally {
			resending = false;
		}
	}
</script>

<div class="container mx-auto px-4 py-16">
	<div class="max-w-md mx-auto">
		<h1 class="text-3xl font-bold mb-2 text-center">Email Verification</h1>
		<p class="text-center text-muted-foreground mb-8">
			{#if verifying}
				Verifying your email address...
			{:else if success}
				Your email has been verified successfully!
			{:else}
				Verification failed
			{/if}
		</p>

		<div class="space-y-4">
			{#if verifying}
				<div class="flex flex-col items-center space-y-4">
					<div class="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
					<p class="text-sm text-muted-foreground">Please wait while we verify your email...</p>
				</div>
			{:else if success}
				<div class="space-y-4">
					<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded">
						✓ Your email has been successfully verified. You can now log in to your account.
					</div>
					<button
						on:click={handleContinue}
						class="w-full bg-primary text-primary-foreground py-2 rounded-md hover:bg-primary/90"
					>
						Continue to Login
					</button>
				</div>
			{:else}
				<div class="space-y-4">
					<div class="bg-destructive/10 text-destructive px-4 py-3 rounded">
						{error}
					</div>
					
					{#if error.includes('Invalid or expired')}
						<div class="bg-blue-50 border border-blue-200 text-blue-800 px-4 py-3 rounded text-sm">
							<p class="font-semibold mb-2">What to do next:</p>
							<ul class="list-disc list-inside space-y-1">
								<li>The verification link may have expired (links expire after 24 hours)</li>
								<li>The link may have already been used</li>
								<li>Try logging in - your email might already be verified</li>
								<li>If login fails, you can request a new verification link below</li>
							</ul>
						</div>
					{/if}

					{#if resendSuccess}
						<div class="bg-green-50 border border-green-200 text-green-800 px-4 py-3 rounded">
							✓ New verification email sent! Please check your inbox and spam folder.
						</div>
					{/if}

					{#if showResendForm}
						<div class="border border-input rounded-md p-4 space-y-3">
							<h3 class="font-semibold">Request New Verification Link</h3>
							
							{#if resendError}
								<div class="bg-destructive/10 text-destructive px-3 py-2 rounded text-sm">
									{resendError}
								</div>
							{/if}
							
							<div>
								<label for="resendEmail" class="block text-sm font-medium mb-1">Email Address</label>
								<input
									id="resendEmail"
									type="email"
									bind:value={resendEmail}
									placeholder="Enter your email address"
									class="w-full px-3 py-2 border rounded-md text-sm"
									required
								/>
							</div>
							
							<div class="flex gap-2">
								<button
									on:click={requestNewLink}
									disabled={resending}
									class="flex-1 bg-primary text-primary-foreground py-2 rounded-md hover:bg-primary/90 disabled:opacity-50 text-sm"
								>
									{resending ? 'Sending...' : 'Send Link'}
								</button>
								<button
									on:click={() => { showResendForm = false; resendError = ''; }}
									class="px-4 py-2 border border-input rounded-md hover:bg-accent text-sm"
								>
									Cancel
								</button>
							</div>
						</div>
					{/if}
					
					<div class="flex flex-col space-y-2">
						<button
							on:click={() => goto('/auth/login')}
							class="w-full bg-primary text-primary-foreground py-2 rounded-md hover:bg-primary/90"
						>
							Try Logging In
						</button>
						
						{#if error.includes('Invalid or expired') && !showResendForm && !resendSuccess}
							<button
								on:click={() => showResendForm = true}
								class="w-full border border-primary text-primary py-2 rounded-md hover:bg-primary/10"
							>
								Request New Verification Link
							</button>
						{/if}
						
						<button
							on:click={() => goto('/auth/register')}
							class="w-full border border-input bg-background py-2 rounded-md hover:bg-accent"
						>
							Back to Registration
						</button>
					</div>
				</div>
			{/if}
		</div>
	</div>
</div>