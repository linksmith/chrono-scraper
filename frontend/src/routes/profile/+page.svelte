<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import DashboardLayout from '$lib/components/layout/dashboard-layout.svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Tabs, TabsContent, TabsList, TabsTrigger } from '$lib/components/ui/tabs';
	import { Badge } from '$lib/components/ui/badge';
	import { Alert, AlertDescription } from '$lib/components/ui/alert';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { toast } from 'svelte-sonner';
	import { auth, user, isAuthenticated } from '$lib/stores/auth';
	import { 
		User, 
		Key, 
		CreditCard, 
		Shield, 
		Settings,
		Save,
		AlertCircle,
		CheckCircle2,
		Zap,
		Loader2
	} from 'lucide-svelte';
	
	let loading = true;
	let saving = false;
	let currentTab = 'personal';
	
	// Form data
	let personalInfo = {
		full_name: '',
		email: '',
		professional_title: '',
		organization_website: '',
		linkedin_profile: '',
		academic_affiliation: '',
		research_interests: ''
	};
	
	let apiKeys = {
		openrouter_api_key: '',
		proxy_api_key: ''
	};
	
	let passwordForm = {
		current_password: '',
		new_password: '',
		confirm_password: ''
	};
	
	let currentPlan = 'free';
	let availablePlans: any[] = [];
	
	onMount(async () => {
		if (!$isAuthenticated) {
			goto('/auth/login');
			return;
		}
		
		// Load user profile data
		try {
			const response = await fetch('/api/v1/profile/me', {
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('token')}`
				}
			});
			
			if (response.ok) {
				const userData = await response.json();
				personalInfo = {
					full_name: userData.full_name || '',
					email: userData.email || '',
					professional_title: userData.professional_title || '',
					organization_website: userData.organization_website || '',
					linkedin_profile: userData.linkedin_profile || '',
					academic_affiliation: userData.academic_affiliation || '',
					research_interests: userData.research_interests || ''
				};
				
				apiKeys = {
					openrouter_api_key: userData.openrouter_api_key || '',
					proxy_api_key: userData.proxy_api_key || ''
				};
				
				currentPlan = userData.current_plan || 'free';
			}
			
			// Load available plans
			const plansResponse = await fetch('/api/v1/profile/plans', {
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('token')}`
				}
			});
			
			if (plansResponse.ok) {
				availablePlans = await plansResponse.json();
			}
			
		} catch (error) {
			toast.error('Failed to load profile data');
			console.error('Profile load error:', error);
		} finally {
			loading = false;
		}
	});
	
	async function savePersonalInfo() {
		saving = true;
		try {
			const response = await fetch('/api/v1/profile/me', {
				method: 'PATCH',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('token')}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(personalInfo)
			});
			
			if (response.ok) {
				const updatedUser = await response.json();
				toast.success('Personal information updated successfully');
			} else {
				const error = await response.json();
				toast.error(error.detail || 'Failed to update personal information');
			}
		} catch (error) {
			toast.error('An error occurred while saving');
			console.error('Save error:', error);
		} finally {
			saving = false;
		}
	}
	
	async function saveApiKeys() {
		saving = true;
		try {
			const response = await fetch('/api/v1/profile/api-keys', {
				method: 'PATCH',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('token')}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify(apiKeys)
			});
			
			if (response.ok) {
				toast.success('API keys updated successfully');
			} else {
				const error = await response.json();
				toast.error(error.detail || 'Failed to update API keys');
			}
		} catch (error) {
			toast.error('An error occurred while saving API keys');
			console.error('Save error:', error);
		} finally {
			saving = false;
		}
	}
	
	async function changePassword() {
		if (passwordForm.new_password !== passwordForm.confirm_password) {
			toast.error('New passwords do not match');
			return;
		}
		
		if (passwordForm.new_password.length < 8) {
			toast.error('Password must be at least 8 characters long');
			return;
		}
		
		saving = true;
		try {
			const response = await fetch('/api/v1/profile/change-password', {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('token')}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({
					current_password: passwordForm.current_password,
					new_password: passwordForm.new_password
				})
			});
			
			if (response.ok) {
				toast.success('Password changed successfully');
				// Clear form
				passwordForm = {
					current_password: '',
					new_password: '',
					confirm_password: ''
				};
			} else {
				const error = await response.json();
				toast.error(error.detail || 'Failed to change password');
			}
		} catch (error) {
			toast.error('An error occurred while changing password');
			console.error('Password change error:', error);
		} finally {
			saving = false;
		}
	}
	
	async function changePlan(planName: string) {
		if (planName === currentPlan) {
			return;
		}
		
		saving = true;
		try {
			const response = await fetch('/api/v1/profile/change-plan', {
				method: 'POST',
				headers: {
					'Authorization': `Bearer ${localStorage.getItem('token')}`,
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ plan_name: planName })
			});
			
			if (response.ok) {
				currentPlan = planName;
				toast.success(`Successfully switched to ${planName} plan`);
			} else {
				const error = await response.json();
				toast.error(error.detail || 'Failed to change plan');
			}
		} catch (error) {
			toast.error('An error occurred while changing plan');
			console.error('Plan change error:', error);
		} finally {
			saving = false;
		}
	}
	
	function getPlanBadgeVariant(planName: string) {
		switch(planName) {
			case 'free': return 'secondary';
			case 'flash': return 'default';
			case 'blaze': return 'destructive';
			case 'lightning': return 'outline';
			default: return 'secondary';
		}
	}
</script>

<svelte:head>
	<title>Profile Settings - Chrono Scraper</title>
</svelte:head>

<DashboardLayout>
	{#if loading}
		<div class="space-y-6">
			<div>
				<Skeleton class="h-8 w-48 mb-2" />
				<Skeleton class="h-4 w-96" />
			</div>
			
			<Card>
				<CardHeader>
					<Skeleton class="h-6 w-32 mb-2" />
					<Skeleton class="h-4 w-64" />
				</CardHeader>
				<CardContent class="space-y-4">
					{#each Array(5) as _}
						<div>
							<Skeleton class="h-4 w-24 mb-2" />
							<Skeleton class="h-10 w-full" />
						</div>
					{/each}
				</CardContent>
			</Card>
		</div>
	{:else}
		<div class="space-y-6">
			<!-- Header -->
			<div>
				<h2 class="text-3xl font-bold tracking-tight">Profile Settings</h2>
				<p class="text-muted-foreground">
					Manage your account settings and preferences
				</p>
			</div>
			
			<!-- Tabs -->
			<Tabs bind:value={currentTab} class="space-y-4">
				<TabsList class="grid w-full grid-cols-4">
					<TabsTrigger value="personal">
						<User class="h-4 w-4 mr-2" />
						Personal Info
					</TabsTrigger>
					<TabsTrigger value="api-keys">
						<Key class="h-4 w-4 mr-2" />
						API Keys
					</TabsTrigger>
					<TabsTrigger value="security">
						<Shield class="h-4 w-4 mr-2" />
						Security
					</TabsTrigger>
					<TabsTrigger value="plan">
						<CreditCard class="h-4 w-4 mr-2" />
						Plan
					</TabsTrigger>
				</TabsList>
				
				<!-- Personal Information Tab -->
				<TabsContent value="personal" class="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle>Personal Information</CardTitle>
							<CardDescription>
								Update your personal details and professional information
							</CardDescription>
						</CardHeader>
						<CardContent class="space-y-4">
							<div class="grid gap-4 md:grid-cols-2">
								<div class="space-y-2">
									<Label for="full_name">Full Name</Label>
									<Input
										id="full_name"
										bind:value={personalInfo.full_name}
										placeholder="John Doe"
									/>
								</div>
								
								<div class="space-y-2">
									<Label for="email">Email</Label>
									<Input
										id="email"
										type="email"
										bind:value={personalInfo.email}
										placeholder="john@example.com"
									/>
								</div>
								
								<div class="space-y-2">
									<Label for="professional_title">Professional Title</Label>
									<Input
										id="professional_title"
										bind:value={personalInfo.professional_title}
										placeholder="Research Analyst"
									/>
								</div>
								
								<div class="space-y-2">
									<Label for="academic_affiliation">Academic Affiliation</Label>
									<Input
										id="academic_affiliation"
										bind:value={personalInfo.academic_affiliation}
										placeholder="University Name"
									/>
								</div>
								
								<div class="space-y-2">
									<Label for="organization_website">Organization Website</Label>
									<Input
										id="organization_website"
										type="url"
										bind:value={personalInfo.organization_website}
										placeholder="https://example.org"
									/>
								</div>
								
								<div class="space-y-2">
									<Label for="linkedin_profile">LinkedIn Profile</Label>
									<Input
										id="linkedin_profile"
										type="url"
										bind:value={personalInfo.linkedin_profile}
										placeholder="https://linkedin.com/in/username"
									/>
								</div>
							</div>
							
							<div class="space-y-2">
								<Label for="research_interests">Research Interests</Label>
								<textarea
									id="research_interests"
									bind:value={personalInfo.research_interests}
									placeholder="Describe your research interests..."
									class="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
								/>
							</div>
							
							<Button 
								onclick={savePersonalInfo} 
								disabled={saving}
								class="w-full sm:w-auto"
							>
								{#if saving}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Saving...
								{:else}
									<Save class="mr-2 h-4 w-4" />
									Save Changes
								{/if}
							</Button>
						</CardContent>
					</Card>
				</TabsContent>
				
				<!-- API Keys Tab -->
				<TabsContent value="api-keys" class="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle>API Keys</CardTitle>
							<CardDescription>
								Configure your personal API keys for enhanced functionality
							</CardDescription>
						</CardHeader>
						<CardContent class="space-y-4">
							<Alert>
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>
									These API keys are stored securely and used only for your personal scraping operations.
									They allow you to use your own resources instead of shared ones.
								</AlertDescription>
							</Alert>
							
							<div class="space-y-4">
								<div class="space-y-2">
									<Label for="openrouter_key">OpenRouter API Key</Label>
									<Input
										id="openrouter_key"
										type="password"
										bind:value={apiKeys.openrouter_api_key}
										placeholder="sk-or-..."
									/>
									<p class="text-sm text-muted-foreground">
										Used for advanced AI-powered content extraction and analysis
									</p>
								</div>
								
								<div class="space-y-2">
									<Label for="proxy_key">Proxy API Key</Label>
									<Input
										id="proxy_key"
										type="password"
										bind:value={apiKeys.proxy_api_key}
										placeholder="Your proxy service API key"
									/>
									<p class="text-sm text-muted-foreground">
										Used for enhanced scraping capabilities and avoiding rate limits
									</p>
								</div>
							</div>
							
							<Button 
								onclick={saveApiKeys} 
								disabled={saving}
								class="w-full sm:w-auto"
							>
								{#if saving}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Saving...
								{:else}
									<Save class="mr-2 h-4 w-4" />
									Save API Keys
								{/if}
							</Button>
						</CardContent>
					</Card>
				</TabsContent>
				
				<!-- Security Tab -->
				<TabsContent value="security" class="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle>Change Password</CardTitle>
							<CardDescription>
								Update your account password
							</CardDescription>
						</CardHeader>
						<CardContent class="space-y-4">
							<div class="space-y-4">
								<div class="space-y-2">
									<Label for="current_password">Current Password</Label>
									<Input
										id="current_password"
										type="password"
										bind:value={passwordForm.current_password}
										placeholder="Enter current password"
									/>
								</div>
								
								<div class="space-y-2">
									<Label for="new_password">New Password</Label>
									<Input
										id="new_password"
										type="password"
										bind:value={passwordForm.new_password}
										placeholder="Enter new password"
									/>
									<p class="text-sm text-muted-foreground">
										Must be at least 8 characters with uppercase, lowercase, number, and special character
									</p>
								</div>
								
								<div class="space-y-2">
									<Label for="confirm_password">Confirm New Password</Label>
									<Input
										id="confirm_password"
										type="password"
										bind:value={passwordForm.confirm_password}
										placeholder="Confirm new password"
									/>
								</div>
							</div>
							
							<Button 
								onclick={changePassword} 
								disabled={saving || !passwordForm.current_password || !passwordForm.new_password}
								class="w-full sm:w-auto"
							>
								{#if saving}
									<Loader2 class="mr-2 h-4 w-4 animate-spin" />
									Changing...
								{:else}
									<Shield class="mr-2 h-4 w-4" />
									Change Password
								{/if}
							</Button>
						</CardContent>
					</Card>
					
					<Card>
						<CardHeader>
							<CardTitle>Two-Factor Authentication</CardTitle>
							<CardDescription>
								Add an extra layer of security to your account
							</CardDescription>
						</CardHeader>
						<CardContent>
							<Alert>
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>
									Two-factor authentication will be available soon
								</AlertDescription>
							</Alert>
						</CardContent>
					</Card>
				</TabsContent>
				
				<!-- Plan Tab -->
				<TabsContent value="plan" class="space-y-4">
					<Card>
						<CardHeader>
							<CardTitle>
								Current Plan
								<Badge variant={getPlanBadgeVariant(currentPlan)} class="ml-2">
									{currentPlan.toUpperCase()}
								</Badge>
							</CardTitle>
							<CardDescription>
								Manage your subscription and billing
							</CardDescription>
						</CardHeader>
						<CardContent>
							<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
								{#each availablePlans as plan}
									<Card class={currentPlan === plan.name ? 'border-primary' : ''}>
										<CardHeader>
											<CardTitle class="flex items-center justify-between">
												{plan.display_name}
												{#if currentPlan === plan.name}
													<Badge variant="default">Current</Badge>
												{/if}
											</CardTitle>
											<CardDescription>
												${plan.price_monthly}/month
											</CardDescription>
										</CardHeader>
										<CardContent>
											<ul class="text-sm space-y-2">
												<li>• {plan.pages_per_month.toLocaleString()} pages/month</li>
												<li>• {plan.projects_limit === -1 ? 'Unlimited' : plan.projects_limit} projects</li>
												<li>• {plan.rate_limit_per_minute} req/min</li>
												{#if plan.features}
													{#each plan.features.slice(0, 3) as feature}
														<li>• {feature}</li>
													{/each}
												{/if}
											</ul>
											
											{#if currentPlan !== plan.name}
												<Button
													variant="outline"
													class="w-full mt-4"
													onclick={() => changePlan(plan.name)}
													disabled={saving}
												>
													{#if saving}
														<Loader2 class="mr-2 h-4 w-4 animate-spin" />
													{:else}
														<Zap class="mr-2 h-4 w-4" />
													{/if}
													Switch to {plan.display_name}
												</Button>
											{/if}
										</CardContent>
									</Card>
								{/each}
							</div>
						</CardContent>
					</Card>
					
					<Card>
						<CardHeader>
							<CardTitle>Billing History</CardTitle>
							<CardDescription>
								View your past invoices and payments
							</CardDescription>
						</CardHeader>
						<CardContent>
							<Alert>
								<AlertCircle class="h-4 w-4" />
								<AlertDescription>
									Billing history will be available once payment processing is enabled
								</AlertDescription>
							</Alert>
						</CardContent>
					</Card>
				</TabsContent>
			</Tabs>
		</div>
	{/if}
</DashboardLayout>