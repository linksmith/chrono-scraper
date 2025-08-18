<script lang="ts">
    import { goto } from '$app/navigation';
    import { getApiUrl } from '$lib/utils';
    
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
    let error = '';
    let success = false;
    
    const handleSubmit = async () => {
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
            const response = await fetch(getApiUrl('/api/v1/auth/register'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
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
                    ethics_agreement: ethicsAgreement
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
    <title>Register - Chrono Scraper</title>
</svelte:head>

<div class="min-h-screen bg-gray-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
    <div class="sm:mx-auto sm:w-full sm:max-w-2xl">
        <div class="flex justify-center">
            <h1 class="text-3xl font-bold tracking-tight text-gray-900">Chrono Scraper</h1>
        </div>
        <h2 class="mt-6 text-center text-2xl font-bold text-gray-900">
            Create your research account
        </h2>
        <p class="mt-2 text-center text-sm text-gray-600">
            Already have an account? 
            <a href="/auth/login" class="font-medium text-blue-600 hover:text-blue-500">
                Sign in
            </a>
        </p>
    </div>

    <div class="mt-8 sm:mx-auto sm:w-full sm:max-w-2xl">
        <div class="bg-white py-8 px-4 shadow sm:rounded-lg sm:px-10">
            {#if success}
                <div class="rounded-md bg-green-50 p-4 mb-6">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <svg class="h-5 w-5 text-green-400" viewBox="0 0 20 20" fill="currentColor">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                            </svg>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-sm font-medium text-green-800">
                                Registration Successful!
                            </h3>
                            <div class="mt-2 text-sm text-green-700">
                                <p>Your account has been created and is pending approval. You will receive an email once your account is approved.</p>
                                <p class="mt-2">
                                    <a href="/auth/login" class="font-medium text-green-600 hover:text-green-500">
                                        Return to login
                                    </a>
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            {:else}
                <form class="space-y-6" on:submit|preventDefault={handleSubmit}>
                    {#if error}
                        <div class="rounded-md bg-red-50 p-4">
                            <div class="flex">
                                <div class="flex-shrink-0">
                                    <svg class="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                                        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                                    </svg>
                                </div>
                                <div class="ml-3">
                                    <h3 class="text-sm font-medium text-red-800">Registration Error</h3>
                                    <div class="mt-2 text-sm text-red-700">
                                        <p>{error}</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    {/if}

                    <!-- Basic Information -->
                    <div class="space-y-4">
                        <h3 class="text-lg font-medium text-gray-900">Basic Information</h3>
                        
                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label for="fullName" class="block text-sm font-medium text-gray-700">
                                    Full Name *
                                </label>
                                <input
                                    id="fullName"
                                    type="text"
                                    bind:value={fullName}
                                    required
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    data-testid="full-name-input"
                                />
                            </div>
                            
                            <div>
                                <label for="email" class="block text-sm font-medium text-gray-700">
                                    Email Address *
                                </label>
                                <input
                                    id="email"
                                    type="email"
                                    bind:value={email}
                                    required
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    data-testid="email-input"
                                />
                            </div>
                        </div>

                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label for="password" class="block text-sm font-medium text-gray-700">
                                    Password *
                                </label>
                                <input
                                    id="password"
                                    type="password"
                                    bind:value={password}
                                    required
                                    minlength="8"
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    data-testid="password-input"
                                />
                            </div>
                            
                            <div>
                                <label for="confirmPassword" class="block text-sm font-medium text-gray-700">
                                    Confirm Password *
                                </label>
                                <input
                                    id="confirmPassword"
                                    type="password"
                                    bind:value={confirmPassword}
                                    required
                                    minlength="8"
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    data-testid="confirm-password-input"
                                />
                            </div>
                        </div>
                    </div>

                    <!-- Professional Information -->
                    <div class="space-y-4">
                        <h3 class="text-lg font-medium text-gray-900">Professional Information</h3>
                        
                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label for="professionalTitle" class="block text-sm font-medium text-gray-700">
                                    Professional Title
                                </label>
                                <input
                                    id="professionalTitle"
                                    type="text"
                                    bind:value={professionalTitle}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="e.g., Research Scientist, Journalist, Graduate Student"
                                />
                            </div>
                            
                            <div>
                                <label for="academicAffiliation" class="block text-sm font-medium text-gray-700">
                                    Academic/Organization Affiliation
                                </label>
                                <input
                                    id="academicAffiliation"
                                    type="text"
                                    bind:value={academicAffiliation}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="e.g., University of Amsterdam, News Organization"
                                />
                            </div>
                        </div>

                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label for="institutionalEmail" class="block text-sm font-medium text-gray-700">
                                    Institutional Email
                                </label>
                                <input
                                    id="institutionalEmail"
                                    type="email"
                                    bind:value={institutionalEmail}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="name@university.edu"
                                />
                            </div>
                            
                            <div>
                                <label for="organizationWebsite" class="block text-sm font-medium text-gray-700">
                                    Organization Website
                                </label>
                                <input
                                    id="organizationWebsite"
                                    type="url"
                                    bind:value={organizationWebsite}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="https://university.edu"
                                />
                            </div>
                        </div>

                        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <div>
                                <label for="linkedinProfile" class="block text-sm font-medium text-gray-700">
                                    LinkedIn Profile
                                </label>
                                <input
                                    id="linkedinProfile"
                                    type="url"
                                    bind:value={linkedinProfile}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="https://linkedin.com/in/yourprofile"
                                />
                            </div>
                            
                            <div>
                                <label for="orcidId" class="block text-sm font-medium text-gray-700">
                                    ORCID ID
                                </label>
                                <input
                                    id="orcidId"
                                    type="text"
                                    bind:value={orcidId}
                                    class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                    placeholder="0000-0000-0000-0000"
                                />
                            </div>
                        </div>
                    </div>

                    <!-- Research Information -->
                    <div class="space-y-4">
                        <h3 class="text-lg font-medium text-gray-900">Research Information</h3>
                        
                        <div>
                            <label for="researchInterests" class="block text-sm font-medium text-gray-700">
                                Research Interests
                            </label>
                            <textarea
                                id="researchInterests"
                                bind:value={researchInterests}
                                rows="3"
                                class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                placeholder="Describe your research interests and areas of study..."
                            ></textarea>
                        </div>

                        <div>
                            <label for="researchPurpose" class="block text-sm font-medium text-gray-700">
                                Intended Use of Chrono Scraper
                            </label>
                            <textarea
                                id="researchPurpose"
                                bind:value={researchPurpose}
                                rows="3"
                                class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                placeholder="Please describe how you plan to use Chrono Scraper for your research..."
                            ></textarea>
                        </div>

                        <div>
                            <label for="expectedUsage" class="block text-sm font-medium text-gray-700">
                                Expected Usage Pattern
                            </label>
                            <textarea
                                id="expectedUsage"
                                bind:value={expectedUsage}
                                rows="2"
                                class="mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                                placeholder="How frequently do you expect to use the platform? What scale of data collection?"
                            ></textarea>
                        </div>
                    </div>

                    <!-- Agreements -->
                    <div class="space-y-4">
                        <h3 class="text-lg font-medium text-gray-900">Terms & Agreements</h3>
                        
                        <div class="space-y-3">
                            <div class="flex items-start">
                                <input
                                    id="dataHandlingAgreement"
                                    type="checkbox"
                                    bind:checked={dataHandlingAgreement}
                                    required
                                    class="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                />
                                <label for="dataHandlingAgreement" class="ml-3 text-sm text-gray-700">
                                    I agree to the <a href="/terms" target="_blank" class="text-blue-600 hover:text-blue-500">data handling and privacy policy</a> and understand that this platform is for legitimate research purposes only. *
                                </label>
                            </div>

                            <div class="flex items-start">
                                <input
                                    id="ethicsAgreement"
                                    type="checkbox"
                                    bind:checked={ethicsAgreement}
                                    required
                                    class="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                />
                                <label for="ethicsAgreement" class="ml-3 text-sm text-gray-700">
                                    I agree to use this platform ethically and in compliance with applicable laws and regulations, including respecting robots.txt and terms of service of websites being analyzed. *
                                </label>
                            </div>
                        </div>
                    </div>

                    <div>
                        <button
                            type="submit"
                            disabled={loading}
                            class="w-full flex justify-center py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50"
                            data-testid="register-button"
                        >
                            {#if loading}
                                <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                </svg>
                                Creating Account...
                            {:else}
                                Create Account
                            {/if}
                        </button>
                    </div>

                    <div class="text-sm text-gray-600">
                        <p>* Required fields</p>
                        <p class="mt-2">All accounts are subject to approval. You will be notified via email once your account is reviewed.</p>
                    </div>
                </form>
            {/if}
        </div>
    </div>
</div>

<style>
    input, textarea {
        border: 1px solid #d1d5db;
        border-radius: 0.375rem;
        padding: 0.5rem 0.75rem;
        font-size: 0.875rem;
        line-height: 1.25rem;
    }
    
    input:focus, textarea:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }
</style>