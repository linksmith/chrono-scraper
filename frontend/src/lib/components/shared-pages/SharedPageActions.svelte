<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Button } from '$lib/components/ui/button';
	import { Badge } from '$lib/components/ui/badge';
	import { 
		Star, 
		CheckCircle, 
		XCircle, 
		AlertTriangle,
		Copy,
		Share,
		Eye,
		MoreHorizontal
	} from 'lucide-svelte';
	import {
		DropdownMenu,
		DropdownMenuContent,
		DropdownMenuItem,
		DropdownMenuLabel,
		DropdownMenuSeparator,
		DropdownMenuTrigger
	} from '$lib/components/ui/dropdown-menu';
	import type { SharedPageAssociation } from '$lib/services/sharedPagesApi';

	export let pageId: number;
	export let projectAssociations: SharedPageAssociation[] = [];
	export let currentProjectId: number | undefined = undefined;
	export let compact: boolean = false;

	const dispatch = createEventDispatcher<{
		star: { pageId: number; isStarred: boolean; projectId: number };
		review: { pageId: number; reviewStatus: string; projectId: number };
		view: { pageId: number };
		share: { pageId: number };
		copyUrl: { pageId: number; url: string };
		switchProject: { pageId: number; projectId: number };
	}>();

	$: currentAssociation = currentProjectId 
		? projectAssociations.find(a => a.project_id === currentProjectId)
		: projectAssociations[0];
	
	$: otherProjects = projectAssociations.filter(a => a.project_id !== currentProjectId);

	function handleStar() {
		if (currentProjectId && currentAssociation) {
			dispatch('star', {
				pageId,
				isStarred: !currentAssociation.is_starred,
				projectId: currentProjectId
			});
		}
	}

	function handleReview(status: string) {
		if (currentProjectId) {
			dispatch('review', {
				pageId,
				reviewStatus: status,
				projectId: currentProjectId
			});
		}
	}

	function handleView() {
		dispatch('view', { pageId });
	}

	function handleShare() {
		dispatch('share', { pageId });
	}

	function handleCopyUrl(url: string) {
		navigator.clipboard.writeText(url);
		dispatch('copyUrl', { pageId, url });
	}

	function handleSwitchProject(projectId: number) {
		dispatch('switchProject', { pageId, projectId });
	}

	function getReviewStatusIcon(status: string) {
		switch (status) {
			case 'relevant': return CheckCircle;
			case 'irrelevant': return XCircle;
			case 'needs_review': return AlertTriangle;
			default: return CheckCircle;
		}
	}

	function getReviewStatusColor(status: string) {
		switch (status) {
			case 'relevant': return 'text-green-500';
			case 'irrelevant': return 'text-red-500';
			case 'needs_review': return 'text-yellow-500';
			default: return 'text-gray-500';
		}
	}
</script>

<div class="flex items-center gap-1">
	<!-- Star Button -->
	{#if currentAssociation}
		<Button
			variant="ghost"
			size={compact ? "sm" : "default"}
			class="{compact ? 'h-8 w-8 p-0' : 'h-9 w-9 p-0'} {currentAssociation.is_starred ? 'text-yellow-500' : 'text-muted-foreground'}"
			onclick={handleStar}
		>
			<Star class="{compact ? 'h-3 w-3' : 'h-4 w-4'} {currentAssociation.is_starred ? 'fill-current' : ''}" />
		</Button>
	{/if}

	<!-- Review Status -->
	{#if currentAssociation && !compact}
		<DropdownMenu>
			<DropdownMenuTrigger asChild let:builder>
				<Button
					builders={[builder]}
					variant="ghost"
					size="sm"
					class="h-8 px-2 {getReviewStatusColor(currentAssociation.review_status)}"
				>
					{#if currentAssociation.review_status}
						{@const Icon = getReviewStatusIcon(currentAssociation.review_status)}
						<Icon class="h-3 w-3 mr-1" />
						{currentAssociation.review_status.replace('_', ' ')}
					{:else}
						<CheckCircle class="h-3 w-3 mr-1" />
						Review
					{/if}
				</Button>
			</DropdownMenuTrigger>
			<DropdownMenuContent align="end">
				<DropdownMenuLabel>Review Status</DropdownMenuLabel>
				<DropdownMenuSeparator />
				<DropdownMenuItem onclick={() => handleReview('relevant')}>
					<CheckCircle class="h-4 w-4 mr-2 text-green-500" />
					Relevant
				</DropdownMenuItem>
				<DropdownMenuItem onclick={() => handleReview('needs_review')}>
					<AlertTriangle class="h-4 w-4 mr-2 text-yellow-500" />
					Needs Review
				</DropdownMenuItem>
				<DropdownMenuItem onclick={() => handleReview('irrelevant')}>
					<XCircle class="h-4 w-4 mr-2 text-red-500" />
					Irrelevant
				</DropdownMenuItem>
			</DropdownMenuContent>
		</DropdownMenu>
	{/if}

	<!-- More Actions -->
	<DropdownMenu>
		<DropdownMenuTrigger asChild let:builder>
			<Button
				builders={[builder]}
				variant="ghost"
				size={compact ? "sm" : "default"}
				class="{compact ? 'h-8 w-8 p-0' : 'h-9 w-9 p-0'}"
			>
				<MoreHorizontal class="{compact ? 'h-3 w-3' : 'h-4 w-4'}" />
			</Button>
		</DropdownMenuTrigger>
		<DropdownMenuContent align="end">
			<DropdownMenuLabel>Page Actions</DropdownMenuLabel>
			<DropdownMenuSeparator />
			
			<DropdownMenuItem onclick={handleView}>
				<Eye class="h-4 w-4 mr-2" />
				View Content
			</DropdownMenuItem>
			
			<DropdownMenuItem onclick={handleShare}>
				<Share class="h-4 w-4 mr-2" />
				Share Page
			</DropdownMenuItem>
			
			<!-- Project Switching -->
			{#if otherProjects.length > 0}
				<DropdownMenuSeparator />
				<DropdownMenuLabel>Switch Project Context</DropdownMenuLabel>
				{#each otherProjects as association}
					<DropdownMenuItem onclick={() => handleSwitchProject(association.project_id)}>
						<div class="flex items-center justify-between w-full">
							<span>{association.project_name}</span>
							<div class="flex items-center gap-1">
								{#if association.is_starred}
									<Star class="h-3 w-3 fill-current text-yellow-500" />
								{/if}
								<Badge variant="outline" class="text-xs">
									{association.review_status || 'unreviewed'}
								</Badge>
							</div>
						</div>
					</DropdownMenuItem>
				{/each}
			{/if}
		</DropdownMenuContent>
	</DropdownMenu>
</div>