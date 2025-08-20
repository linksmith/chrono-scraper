<script lang="ts">
    import { goto } from '$app/navigation';
    import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Label } from '$lib/components/ui/label/index.js';
	import { Textarea } from '$lib/components/ui/textarea/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card/index.js';
	import { Alert, AlertDescription } from '$lib/components/ui/alert/index.js';
	import { AlertCircle, CheckCircle2, Gift } from 'lucide-svelte';
    
    let invitationToken = '';
    let email = '';
    let password = '';
    let confirmPassword = '';
    let fullName = '';
    let institutionalEmail = '';
    let academicAffiliation = '';
    let researchInterests = '';
    let researchPurpose = '';
    let linkedinProfile = '';
    let orcidId = '';
    let professionalTitle = '';
    let organizationWebsite = '';
    let expectedUsage = '';
    let dataHandlingAgreement = false;
    let ethicsAgreement = false;
    
    let loading = false;
    let validatingToken = false;
    let tokenValid = false;
    let tokenError = '';
    let error = '';
    let success = false;
    
    // Auto-validate invitation token on input
    $: if (invitationToken && invitationToken.length > 10) {
        validateInvitationToken();
    }
    
    const validateInvitationToken = async () => {
        if (validatingToken) return;
        
        validatingToken = true;
        tokenError = '';
        tokenValid = false;
        
        try {
            const response = await fetch('/api/v1/invitations/validate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    token: invitationToken
                }),
            });
            
            if (response.ok) {
                tokenValid = true;
            } else {
                const data = await response.json();
                tokenError = data.detail || 'Invalid invitation code';
                tokenValid = false;
            }
        } catch (err) {
            tokenError = 'Failed to validate invitation code';
            tokenValid = false;
        } finally {
            validatingToken = false;
        }
    };
    
    const handleSubmit = async () => {
        if (!tokenValid) {
            error = 'Please enter a valid invitation code';
            return;
        }
        
        if (password !== confirmPassword) {
            error = 'Passwords do not match';
            return;
        }
        
        if (!dataHandlingAgreement || !ethicsAgreement) {
            error = 'You must agree to the data handling and ethics agreements';
            return;
        }
        
        loading = true;
        error = '';
        
        try {
            const response = await fetch('/api/v1/auth/register-with-invitation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    email,
                    password,
                    full_name: fullName,
                    institutional_email: institutionalEmail,
                    academic_affiliation: academicAffiliation,
                    research_interests: researchInterests,
                    research_purpose: researchPurpose,
                    linkedin_profile: linkedinProfile,
                    orcid_id: orcidId,
                    professional_title: professionalTitle,
                    organization_website: organizationWebsite,
                    expected_usage: expectedUsage,
                    data_handling_agreement: dataHandlingAgreement,
                    ethics_agreement: ethicsAgreement,
                    invitation_token: invitationToken
                }),
            });
            
            if (response.ok) {
                success = true;
            } else {
                const data = await response.json();
                error = data.detail || 'Registration failed';
            }
        } catch (err) {
            error = 'Network error occurred';
        } finally {
            loading = false;
        }
    };
</script>

<svelte:head>
    <title>Register with Invitation - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-muted/40 py-12">
    <div class="container mx-auto px-4 sm:px-6 lg:px-8">
        <div class="max-w-4xl mx-auto">
            <div class="text-center mb-8">
                <div class="mx-auto w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center mb-4">
                    <Gift class="w-8 h-8 text-primary" />
                </div>
                <h1 class="text-4xl font-bold tracking-tight">Join with Invitation</h1>
                <p class="mt-2 text-lg text-muted-foreground">
                    Fast-track registration with your invitation code
                </p>
                <p class="mt-2 text-sm text-muted-foreground">
                    Don't have an invitation?{' '}
                    <a href="/auth/register" class="font-medium text-primary hover:underline">
                        Apply for regular account
                    </a>
                    {' '}or{' '}
                    <a href="/auth/login" class="font-medium text-primary hover:underline">
                        Sign in
                    </a>
                </p>
            </div>

            <Card>
                <CardContent class="p-8">
                    {#if success}
                        <Alert class="border-green-200 bg-green-50">
                            <CheckCircle2 class="h-5 w-5 text-green-600" />
                            <AlertDescription class="text-green-800">
                                <div class="space-y-2">
                                    <p class="font-medium">Registration Successful!</p>
                                    <p class="text-sm">Your account has been created and approved. You can now sign in and start using Chrono Scraper.</p>
                                    <p class="text-sm">
                                        <a href="/auth/login" class="font-medium text-green-600 hover:text-green-500 underline">
                                            Sign in to your account
                                        </a>
                                    </p>
                                </div>
                            </AlertDescription>
                        </Alert>
                    {:else}
                        <form class="space-y-6" on:submit|preventDefault={handleSubmit}>
                            {#if error}
                                <Alert variant="destructive" class="mb-6">
                                    <AlertCircle class="h-4 w-4" />
                                    <AlertDescription>{error}</AlertDescription>
                                </Alert>
                            {/if}

                            <!-- Invitation Code -->
                            <div class="space-y-4">
                                <h3 class="text-lg font-semibold">Invitation Code</h3>
                                
                                <div class="space-y-2">
                                    <Label for="invitationToken">Invitation Code *</Label>
                                    <Input
                                        id="invitationToken"
                                        type="text"
                                        bind:value={invitationToken}
                                        placeholder="inv_xxxxxxxxxxxxxxxxxxxxxxxxx"
                                        required
                                        class="font-mono"
                                    />
                                    {#if validatingToken}
                                        <p class="text-sm text-muted-foreground">Validating invitation code...</p>
                                    {:else if tokenError}
                                        <p class="text-sm text-destructive">{tokenError}</p>
                                    {:else if tokenValid}
                                        <p class="text-sm text-green-600 flex items-center">
                                            <CheckCircle2 class="w-4 h-4 mr-1" />
                                            Valid invitation code
                                        </p>
                                    {/if}
                                </div>
                            </div>

                            {#if tokenValid}
                                <!-- Basic Information -->
                                <div class="space-y-4">
                                    <h3 class="text-lg font-semibold">Basic Information</h3>
                                    
                                    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                        <div class="space-y-2">
                                            <Label for="fullName">Full Name *</Label>
                                            <Input
                                                id="fullName"
                                                type="text"
                                                bind:value={fullName}
                                                placeholder="Dr. Jane Smith"
                                                required
                                            />
                                        </div>
                                        
                                        <div class="space-y-2">
                                            <Label for="email">Email Address *</Label>
                                            <Input
                                                id="email"
                                                type="email"
                                                bind:value={email}
                                                placeholder="jane.smith@university.edu"
                                                required
                                            />
                                        </div>
                                    </div>

                                    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                        <div class="space-y-2">
                                            <Label for="password">Password *</Label>
                                            <Input
                                                id="password"
                                                type="password"
                                                bind:value={password}
                                                required
                                                minlength="8"
                                            />
                                            <p class="text-sm text-muted-foreground">Minimum 8 characters</p>
                                        </div>
                                        
                                        <div class="space-y-2">
                                            <Label for="confirmPassword">Confirm Password *</Label>
                                            <Input
                                                id="confirmPassword"
                                                type="password"
                                                bind:value={confirmPassword}
                                                required
                                                minlength="8"
                                            />
                                        </div>
                                    </div>
                                </div>

                                <!-- Professional Information (Optional) -->
                                <div class="space-y-4">
                                    <h3 class="text-lg font-semibold">Professional Information <span class="text-sm text-muted-foreground font-normal">(Optional)</span></h3>
                                    
                                    <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                                        <div class="space-y-2">
                                            <Label for="professionalTitle">Professional Title</Label>
                                            <Input
                                                id="professionalTitle"
                                                type="text"
                                                bind:value={professionalTitle}
                                                placeholder="Research Scientist, Journalist, etc."
                                            />
                                        </div>
                                        
                                        <div class="space-y-2">
                                            <Label for="academicAffiliation">Academic/Organization Affiliation</Label>
                                            <Input
                                                id="academicAffiliation"
                                                type="text"
                                                bind:value={academicAffiliation}
                                                placeholder="University of Amsterdam"
                                            />
                                        </div>
                                    </div>

                                    <div class="space-y-2">
                                        <Label for="researchInterests">Research Interests</Label>
                                        <Textarea
                                            id="researchInterests"
                                            bind:value={researchInterests}
                                            rows="2"
                                            placeholder="Brief description of your research interests..."
                                            class="resize-none"
                                        />
                                    </div>
                                </div>

                                <!-- Agreements -->
                                <div class="space-y-4">
                                    <h3 class="text-lg font-semibold">Terms & Agreements</h3>
                                    
                                    <div class="space-y-4">
                                        <div class="flex items-start space-x-3">
                                            <Checkbox
                                                id="dataHandlingAgreement"
                                                bind:checked={dataHandlingAgreement}
                                                required
                                                class="mt-1"
                                            />
                                            <Label for="dataHandlingAgreement" class="text-sm leading-relaxed">
                                                I agree to the <a href="/terms" target="_blank" class="text-primary hover:underline">data handling and privacy policy</a> and understand that this platform is for legitimate research purposes only. *
                                            </Label>
                                        </div>

                                        <div class="flex items-start space-x-3">
                                            <Checkbox
                                                id="ethicsAgreement"
                                                bind:checked={ethicsAgreement}
                                                required
                                                class="mt-1"
                                            />
                                            <Label for="ethicsAgreement" class="text-sm leading-relaxed">
                                                I agree to use this platform ethically and in compliance with applicable laws and regulations. *
                                            </Label>
                                        </div>
                                    </div>
                                </div>

                                <div class="pt-4">
                                    <Button
                                        type="submit"
                                        disabled={loading}
                                        class="w-full h-12"
                                    >
                                        {#if loading}
                                            <svg class="animate-spin mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                            </svg>
                                            Creating Account...
                                        {:else}
                                            Create Account with Invitation
                                        {/if}
                                    </Button>
                                </div>

                                <div class="text-sm text-muted-foreground space-y-2 pt-4 border-t">
                                    <p>* Required fields</p>
                                    <div class="bg-green-50 border border-green-200 rounded-lg p-4">
                                        <p class="font-medium text-green-800 flex items-center">
                                            <Gift class="w-4 h-4 mr-2" />
                                            Invitation Benefits
                                        </p>
                                        <p class="text-green-700 text-sm">Your account will be automatically approved and you can start using the platform immediately after registration.</p>
                                    </div>
                                </div>
                            {/if}
                        </form>
                    {/if}
                </CardContent>
            </Card>
        </div>
    </div>
</div>