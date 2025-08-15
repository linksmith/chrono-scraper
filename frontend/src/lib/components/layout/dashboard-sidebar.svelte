<script lang="ts">
	import { page } from '$app/stores';
	import { cn } from '$lib/utils';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import { Badge } from '$lib/components/ui/badge';
	import { Avatar, AvatarFallback, AvatarImage } from '$lib/components/ui/avatar';
	import { auth, isAuthenticated, user } from '$lib/stores/auth';
	import { onMount } from 'svelte';
	import { 
		Home, 
		FolderOpen, 
		Search, 
		BarChart3, 
		Library, 
		Settings, 
		Users,
		Zap,
		Database,
		FileText,
		Target,
		Menu,
		LogOut,
		User
	} from 'lucide-svelte';
	
	import { sidebarOpen } from '$lib/stores/sidebar';
	
	let showUserMenu = false;
	
	onMount(() => {
		const handleClickOutside = (event: MouseEvent) => {
			const target = event.target as Element;
			if (showUserMenu && !target?.closest('.user-menu')) {
				showUserMenu = false;
			}
		};
		
		document.addEventListener('click', handleClickOutside);
		return () => document.removeEventListener('click', handleClickOutside);
	});
	
	function getInitials(name: string): string {
		return name
			.split(' ')
			.map(n => n[0])
			.join('')
			.toUpperCase()
			.slice(0, 2);
	}
	
	$: userInitials = $user?.full_name ? getInitials($user.full_name) : 
		$user?.email ? getInitials($user.email) : 'U';
	
	const navigationItems = [
		{
			title: "Dashboard",
			href: "/dashboard",
			icon: Home
		},
		{
			title: "Projects",
			href: "/projects",
			icon: FolderOpen
		},
		{
			title: "Search",
			href: "/search",
			icon: Search
		},
		{
			title: "Analytics",
			href: "/analytics",
			icon: BarChart3
		},
		{
			title: "Library",
			href: "/library",
			icon: Library
		}
	];
	
	const extractionItems = [
		{
			title: "Entity Extraction",
			href: "/entities",
			icon: Target
		},
		{
			title: "Schemas",
			href: "/extraction/schemas",
			icon: FileText
		},
		{
			title: "Jobs",
			href: "/extraction/jobs",
			icon: Database
		}
	];
	
	const adminItems = [
		{
			title: "User Management",
			href: "/admin/users",
			icon: Users
		},
		{
			title: "Plans",
			href: "/admin/plans",
			icon: Zap
		}
	];
	
	
	$: currentPath = $page.url.pathname;
	
	function isActive(href: string): boolean {
		if (href === '/dashboard') {
			return currentPath === href;
		}
		return currentPath.startsWith(href);
	}
</script>

<div class="flex flex-col h-full w-64 bg-background">
	<!-- Header Section -->
	<div class="flex items-center justify-between p-4">
		<div class="flex items-center space-x-2">
			<span class="text-xl font-bold">Chrono Scraper</span>
		</div>
		<Button
			variant="ghost"
			size="sm"
			class="lg:hidden"
			on:click={() => sidebarOpen.update(open => !open)}
		>
			<Menu class="h-4 w-4" />
		</Button>
	</div>
	
	<!-- Main Navigation -->
	<div class="flex-1 overflow-auto px-4">
		<div class="space-y-4">
			<!-- Main Navigation Items - No Header -->
			<div class="space-y-1 py-2">
				{#each navigationItems as item}
					<Button
						variant={isActive(item.href) ? "secondary" : "ghost"}
						class={cn(
							"w-full justify-start",
							isActive(item.href) && "bg-secondary"
						)}
						href={item.href}
					>
						<svelte:component this={item.icon} class="mr-2 h-4 w-4" />
						{item.title}
					</Button>
				{/each}
			</div>
			
			<!-- Extraction Section -->
			<div class="space-y-1">
				<h2 class="mb-2 px-2 text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center">
					Extraction
					<Badge variant="secondary" class="ml-2 text-xs">Beta</Badge>
				</h2>
				<div class="space-y-1">
					{#each extractionItems as item}
						<Button
							variant={isActive(item.href) ? "secondary" : "ghost"}
							class={cn(
								"w-full justify-start",
								isActive(item.href) && "bg-secondary"
							)}
							href={item.href}
						>
							<svelte:component this={item.icon} class="mr-2 h-4 w-4" />
							{item.title}
						</Button>
					{/each}
				</div>
			</div>
			
			<!-- Administration Section -->
			<div class="space-y-1">
				<h2 class="mb-2 px-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
					Administration
				</h2>
				<div class="space-y-1">
					{#each adminItems as item}
						<Button
							variant={isActive(item.href) ? "secondary" : "ghost"}
							class={cn(
								"w-full justify-start",
								isActive(item.href) && "bg-secondary"
							)}
							href={item.href}
						>
							<svelte:component this={item.icon} class="mr-2 h-4 w-4" />
							{item.title}
						</Button>
					{/each}
				</div>
			</div>
		</div>
	</div>
	
	<!-- Bottom Section -->
	<div class="border-t p-4">
		{#if $isAuthenticated}
			<!-- User Profile -->
			<div class="relative user-menu">
				<div class="flex items-center">
					<!-- Profile Link (Main Area) -->
					<a 
						href="/profile" 
						class="flex-1 flex items-center p-2 rounded-md hover:bg-accent transition-colors"
					>
						<Avatar class="h-8 w-8 mr-2">
							<AvatarImage src="" alt={$user?.full_name || $user?.email || 'User'} />
							<AvatarFallback class="text-xs">{userInitials}</AvatarFallback>
						</Avatar>
						<div class="flex flex-col items-start text-left">
							<p class="text-sm font-medium leading-none">
								{$user?.full_name || 'User'}
							</p>
							<p class="text-xs leading-none text-muted-foreground mt-1">
								{$user?.email}
							</p>
						</div>
					</a>
					
					<!-- Menu Toggle Button -->
					<Button
						variant="ghost"
						size="sm"
						class="p-2 ml-1"
						on:click={() => showUserMenu = !showUserMenu}
					>
						<Menu class="h-4 w-4" />
					</Button>
				</div>
				
				{#if showUserMenu}
					<div class="absolute bottom-full left-0 mb-2 w-56 bg-popover border rounded-md shadow-lg z-50">
						<div class="py-1">
							<a 
								href="/settings" 
								class="flex items-center px-4 py-2 text-sm hover:bg-accent"
								on:click={() => showUserMenu = false}
							>
								<Settings class="w-4 h-4 mr-2" />
								Settings
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
			<div class="space-y-2">
				<Button href="/auth/login" variant="ghost" class="w-full justify-start">
					Login
				</Button>
				<Button href="/auth/register" class="w-full">
					Sign up
				</Button>
			</div>
		{/if}
	</div>
</div>