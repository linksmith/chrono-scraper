<script lang="ts">
    import { Button } from '$lib/components/ui/button';
    
    let clickCount = 0;
    let message = '';
    
    const handleClick = () => {
        clickCount++;
        message = `Button clicked ${clickCount} time${clickCount === 1 ? '' : 's'}!`;
    };
    
    const handleSubmit = () => {
        message = 'Submit button clicked!';
    };
    
    const handleCancel = () => {
        message = 'Cancel button clicked!';
        clickCount = 0;
    };
</script>

<svelte:head>
    <title>Button Test - Chrono Scraper</title>
</svelte:head>

<div class="container mx-auto p-8 max-w-2xl">
    <h1 class="text-3xl font-bold mb-8">shadcn Button Component Test</h1>
    
    <div class="space-y-6">
        <!-- Test message display -->
        {#if message}
            <div class="p-4 bg-green-100 border border-green-300 rounded-md">
                <p class="text-green-800 font-medium">{message}</p>
            </div>
        {/if}
        
        <!-- Basic Button Tests -->
        <div class="space-y-4">
            <h2 class="text-xl font-semibold">Basic Button Tests</h2>
            
            <div class="flex gap-4 flex-wrap">
                <Button onclick={handleClick}>
                    Default Button (Clicked: {clickCount})
                </Button>
                
                <Button variant="outline" onclick={handleSubmit}>
                    Outline Button
                </Button>
                
                <Button variant="destructive" onclick={handleCancel}>
                    Destructive Button
                </Button>
                
                <Button variant="secondary" onclick={() => message = 'Secondary clicked!'}>
                    Secondary Button
                </Button>
                
                <Button variant="ghost" onclick={() => message = 'Ghost clicked!'}>
                    Ghost Button
                </Button>
                
                <Button variant="link" onclick={() => message = 'Link clicked!'}>
                    Link Button
                </Button>
            </div>
        </div>
        
        <!-- Size Tests -->
        <div class="space-y-4">
            <h2 class="text-xl font-semibold">Size Variants</h2>
            
            <div class="flex gap-4 items-center flex-wrap">
                <Button size="sm" onclick={() => message = 'Small button clicked!'}>
                    Small
                </Button>
                
                <Button size="default" onclick={() => message = 'Default size clicked!'}>
                    Default
                </Button>
                
                <Button size="lg" onclick={() => message = 'Large button clicked!'}>
                    Large
                </Button>
                
                <Button size="icon" onclick={() => message = 'Icon button clicked!'}>
                    ⭐
                </Button>
            </div>
        </div>
        
        <!-- Form Test -->
        <div class="space-y-4">
            <h2 class="text-xl font-semibold">Form Integration Test</h2>
            
            <form on:submit|preventDefault={() => message = 'Form submitted!'} class="space-y-4">
                <div>
                    <label for="test-input" class="block text-sm font-medium mb-2">Test Input:</label>
                    <input 
                        id="test-input"
                        type="text" 
                        placeholder="Type something..."
                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                </div>
                
                <div class="flex gap-4">
                    <Button type="submit">
                        Submit Form
                    </Button>
                    
                    <Button type="button" variant="outline" onclick={() => message = 'Form reset!'}>
                        Reset
                    </Button>
                </div>
            </form>
        </div>
        
        <!-- Disabled State Test -->
        <div class="space-y-4">
            <h2 class="text-xl font-semibold">Disabled State Test</h2>
            
            <div class="flex gap-4">
                <Button disabled onclick={() => message = 'This should not appear!'}>
                    Disabled Button
                </Button>
                
                <Button disabled variant="outline">
                    Disabled Outline
                </Button>
            </div>
        </div>
        
        <!-- Event Handler Test -->
        <div class="space-y-4">
            <h2 class="text-xl font-semibold">Event Handler Test</h2>
            <p class="text-sm text-gray-600">These test various onclick event patterns</p>
            
            <div class="flex gap-4 flex-wrap">
                <Button onclick={() => message = 'Arrow function works!'}>
                    Arrow Function
                </Button>
                
                <Button onclick={function() { message = 'Regular function works!'; }}>
                    Regular Function
                </Button>
                
                <Button onclick={handleClick}>
                    Function Reference
                </Button>
                
                <Button onclick={() => {
                    const now = new Date().toLocaleTimeString();
                    message = `Complex handler works! Time: ${now}`;
                }}>
                    Complex Handler
                </Button>
            </div>
        </div>
        
        <!-- Clear Message -->
        <div class="pt-4 border-t">
            <Button variant="outline" onclick={() => { message = ''; clickCount = 0; }}>
                Clear Message & Reset Count
            </Button>
        </div>
    </div>
</div>