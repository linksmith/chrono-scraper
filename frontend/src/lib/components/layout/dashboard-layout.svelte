<script lang="ts">
	import { onMount } from 'svelte';
	import { cn } from '$lib/utils';
	import { sidebarOpen } from '$lib/stores/sidebar';
	import { Button } from '$lib/components/ui/button';
	import { Separator } from '$lib/components/ui/separator';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb';
	import DashboardSidebar from './dashboard-sidebar.svelte';
	import { Menu, Home, FolderPlus } from 'lucide-svelte';
	import { page } from '$app/stores';
	
	let mounted = false;
	
	// Generate breadcrumbs based on current route
	$: breadcrumbs = generateBreadcrumbs($page.url.pathname);
	
	function generateBreadcrumbs(pathname: string) {
		const segments = pathname.split('/').filter(Boolean);
		const crumbs = [];
		
		// Start with Dashboard as the root for all dashboard pages
		if (pathname.startsWith('/dashboard') || pathname.startsWith('/projects') || pathname.startsWith('/search') || 
			pathname.startsWith('/analytics') || pathname.startsWith('/library') || pathname.startsWith('/extraction') || 
			pathname.startsWith('/investigations') || pathname.startsWith('/admin')) {
			crumbs.push({ href: '/dashboard', label: 'Dashboard' });
		}
		
		let currentPath = '';
		for (const segment of segments) {
			currentPath += `/${segment}`;
			if (segment === 'dashboard') continue; // Skip dashboard since it's already the root
			
			switch (segment) {
				case 'projects':
					crumbs.push({ href: '/projects', label: 'Projects' });
					break;
				case 'create':
					crumbs.push({ href: currentPath, label: 'Create Project' });
					break;
				case 'search':
					crumbs.push({ href: '/search', label: 'Search' });
					break;
				case 'analytics':
					crumbs.push({ href: '/analytics', label: 'Analytics' });
					break;
				case 'library':
					crumbs.push({ href: '/library', label: 'Library' });
					break;
				case 'extraction':
					crumbs.push({ href: '/extraction', label: 'Extraction' });
					break;
				case 'entities':
					crumbs.push({ href: '/entities', label: 'Entity Extraction' });
					break;
				case 'schemas':
					crumbs.push({ href: currentPath, label: 'Schemas' });
					break;
				case 'jobs':
					crumbs.push({ href: currentPath, label: 'Jobs' });
					break;
				case 'investigations':
					crumbs.push({ href: '/investigations', label: 'Investigations' });
					break;
				case 'admin':
					crumbs.push({ href: '/admin', label: 'Administration' });
					break;
				case 'users':
					crumbs.push({ href: currentPath, label: 'User Management' });
					break;
				case 'plans':
					crumbs.push({ href: currentPath, label: 'Plans' });
					break;
				default:
					crumbs.push({ href: currentPath, label: segment.charAt(0).toUpperCase() + segment.slice(1) });
			}
		}
		
		return crumbs;
	}
	
	onMount(() => {
		mounted = true;
		
		// Close sidebar on mobile when clicking outside
		const handleClickOutside = (event: MouseEvent) => {
			if ($sidebarOpen && !(event.target as Element)?.closest('.sidebar')) {
				sidebarOpen.set(false);
			}
		};
		
		// Keyboard shortcut to toggle sidebar (Cmd/Ctrl + B)
		const handleKeydown = (event: KeyboardEvent) => {
			if ((event.metaKey || event.ctrlKey) && event.key === 'b') {
				event.preventDefault();
				sidebarOpen.update(open => !open);
			}
		};
		
		document.addEventListener('click', handleClickOutside);
		document.addEventListener('keydown', handleKeydown);
		return () => {
			document.removeEventListener('click', handleClickOutside);
			document.removeEventListener('keydown', handleKeydown);
		};
	});
</script>

<!-- Sidebar-01 Pattern Implementation -->
<div class="flex min-h-screen">
	<!-- Mobile sidebar overlay -->
	{#if mounted && $sidebarOpen}
		<div class="fixed inset-0 z-40 lg:hidden">
			<div 
				class="fixed inset-0 bg-background/80 backdrop-blur-sm" 
				on:click={() => sidebarOpen.set(false)}
				role="button" 
				tabindex="-1"
				on:keydown={() => {}}
			></div>
		</div>
	{/if}
	
	<!-- Sidebar -->
	<div class={cn(
		"fixed inset-y-0 left-0 z-50 w-64 bg-background border-r transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0",
		$sidebarOpen ? "translate-x-0" : "-translate-x-full",
		"sidebar"
	)}>
		<DashboardSidebar />
	</div>
	
	<!-- Main content area -->
	<div class="flex-1 flex flex-col overflow-hidden">
		<!-- Header with sidebar trigger and breadcrumbs -->
		<header class="flex h-16 shrink-0 items-center gap-2 border-b px-4 bg-background">
			<Button
				variant="ghost"
				size="icon"
				class="lg:hidden touch-target-44"
				onclick={() => sidebarOpen.update(open => !open)}
			>
				<Menu class="h-4 w-4" />
				<span class="sr-only">Toggle sidebar</span>
			</Button>
			
			<Separator orientation="vertical" class="mr-2 h-4" />
			
			<!-- Breadcrumb Navigation -->
			<Breadcrumb.Root>
				<Breadcrumb.List>
					{#each breadcrumbs as crumb, i}
						<Breadcrumb.Item>
							{#if i === breadcrumbs.length - 1}
								<Breadcrumb.Page>{crumb.label}</Breadcrumb.Page>
							{:else}
								<Breadcrumb.Link href={crumb.href}>{crumb.label}</Breadcrumb.Link>
							{/if}
						</Breadcrumb.Item>
						
						{#if i < breadcrumbs.length - 1}
							<Breadcrumb.Separator />
						{/if}
					{/each}
				</Breadcrumb.List>
			</Breadcrumb.Root>
		</header>
		
		<!-- Page content - full width -->
		<main class="flex-1 overflow-y-auto p-6">
			<slot />
		</main>
	</div>
</div>