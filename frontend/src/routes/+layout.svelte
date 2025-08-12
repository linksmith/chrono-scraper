<script lang="ts">
	import '../app.css';
	import { ModeWatcher } from 'mode-watcher';
	import { onMount } from 'svelte';
	import { auth, isAuthenticated, user } from '$lib/stores/auth';
	import { Button } from '$lib/components/ui/button';
	import { 
		User, 
		LogOut, 
		Settings, 
		ChevronDown 
	} from 'lucide-svelte';
	
	onMount(() => {
		auth.init();
		
		// Close user menu when clicking outside
		const handleClickOutside = (event: MouseEvent) => {
			if (showUserMenu && !(event.target as Element)?.closest('.user-menu')) {
				showUserMenu = false;
			}
		};
		
		document.addEventListener('click', handleClickOutside);
		return () => document.removeEventListener('click', handleClickOutside);
	});
	
	let showUserMenu = false;
</script>

<ModeWatcher />

<div class="min-h-screen bg-background">
	<nav class="border-b">
		<div class="container mx-auto px-4 py-4">
			<div class="flex items-center justify-between">
				<a href="/" class="text-2xl font-bold">Chrono Scraper</a>
				<div class="flex items-center gap-4">
					{#if $isAuthenticated}
						<a href="/projects" class="hover:text-primary">Projects</a>
						<a href="/search" class="hover:text-primary">Search</a>
						<a href="/analytics" class="hover:text-primary">Analytics</a>
						
						<!-- User Menu -->
						<div class="relative user-menu">
							<Button 
								variant="ghost" 
								class="flex items-center gap-2"
								on:click={() => showUserMenu = !showUserMenu}
							>
								<User class="w-4 h-4" />
								{$user?.username || $user?.email}
								<ChevronDown class="w-3 h-3" />
							</Button>
							
							{#if showUserMenu}
								<div class="absolute right-0 mt-2 w-48 bg-popover border rounded-md shadow-lg z-50">
									<div class="py-1">
										<a 
											href="/profile" 
											class="flex items-center px-4 py-2 text-sm hover:bg-accent"
											on:click={() => showUserMenu = false}
										>
											<Settings class="w-4 h-4 mr-2" />
											Profile Settings
										</a>
										{#if $user?.is_admin}
											<a 
												href="/admin" 
												class="flex items-center px-4 py-2 text-sm hover:bg-accent"
												on:click={() => showUserMenu = false}
											>
												<Settings class="w-4 h-4 mr-2" />
												Admin Panel
											</a>
										{/if}
										<hr class="my-1" />
										<button 
											class="flex items-center w-full px-4 py-2 text-sm hover:bg-accent text-left"
											on:click={() => { auth.logout(); showUserMenu = false; }}
										>
											<LogOut class="w-4 h-4 mr-2" />
											Logout
										</button>
									</div>
								</div>
							{/if}
						</div>
					{:else}
						<a href="/auth/login" class="hover:text-primary">Login</a>
						<a href="/auth/register" class="hover:text-primary">Register</a>
					{/if}
				</div>
			</div>
		</div>
	</nav>
	
	<main>
		<slot />
	</main>
	
	<footer class="border-t mt-auto">
		<div class="container mx-auto px-4 py-4 text-center text-sm text-muted-foreground">
			&copy; 2024 Chrono Scraper. All rights reserved.
		</div>
	</footer>
</div>