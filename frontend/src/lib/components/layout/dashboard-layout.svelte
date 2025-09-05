<script lang="ts">
	import { Separator } from '$lib/components/ui/separator';
	import * as Breadcrumb from '$lib/components/ui/breadcrumb';
	import * as Sheet from '$lib/components/ui/sheet';
	import DashboardSidebar from './dashboard-sidebar.svelte';
	import ThemeToggle from '$lib/components/ui/theme-toggle.svelte';
	import { Menu } from 'lucide-svelte';
	import { page } from '$app/stores';
	
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
	
</script>

<!-- Sheet-based mobile navigation (working overlay) -->
<div class="flex min-h-screen">
	<!-- Desktop Sidebar - always visible on large screens -->
	<div class="hidden lg:block lg:w-64 lg:shrink-0">
		<div class="flex flex-col h-full bg-background border-r">
			<DashboardSidebar />
		</div>
	</div>
	
	<!-- Main content area -->
	<div class="flex-1 flex flex-col overflow-hidden">
		<!-- Header with mobile sheet trigger, breadcrumbs, and theme toggle -->
		<header class="flex h-16 shrink-0 items-center justify-between border-b px-4 bg-background">
			<!-- Left side: Mobile navigation and breadcrumbs -->
			<div class="flex items-center gap-2">
				<!-- Mobile Navigation Sheet -->
				<Sheet.Sheet>
					<Sheet.SheetTrigger 
						class="lg:hidden inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 hover:bg-accent hover:text-accent-foreground h-10 w-10"
					>
						<Menu class="h-4 w-4" />
						<span class="sr-only">Toggle navigation menu</span>
					</Sheet.SheetTrigger>
					<Sheet.SheetContent side="left" class="w-64 z-[60] bg-background">
						<Sheet.SheetHeader>
							<Sheet.SheetTitle>Navigation</Sheet.SheetTitle>
						</Sheet.SheetHeader>
						<div class="mt-4">
							<nav class="space-y-2">
								<a href="/dashboard" class="flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-accent">
									<span>Dashboard</span>
								</a>
								<a href="/projects" class="flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-accent">
									<span>Projects</span>
								</a>
								<a href="/search" class="flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-accent">
									<span>Search</span>
								</a>
								<a href="/analytics" class="flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-accent">
									<span>Analytics</span>
								</a>
								<a href="/library" class="flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-accent">
									<span>Library</span>
								</a>
								<a href="/entities" class="flex items-center space-x-3 px-3 py-2 rounded-md hover:bg-accent">
									<span>Entity Extraction</span>
								</a>
							</nav>
						</div>
					</Sheet.SheetContent>
				</Sheet.Sheet>
				
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
			</div>

			<!-- Right side: Theme toggle -->
			<div class="flex items-center">
				<ThemeToggle />
			</div>
		</header>
		
		<!-- Page content -->
		<main class="flex-1 overflow-y-auto p-3 sm:p-4 lg:p-6">
			<slot />
		</main>
	</div>
</div>