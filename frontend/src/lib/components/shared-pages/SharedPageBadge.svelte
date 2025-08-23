<script lang="ts">
	import { Badge } from '$lib/components/ui/badge';
	import { Users, Eye } from 'lucide-svelte';
	import type { SharedPageAssociation } from '$lib/services/sharedPagesApi';

	export let projectAssociations: SharedPageAssociation[] = [];
	export let totalProjects: number = 0;
	export let compact: boolean = false;

	$: isShared = totalProjects > 1;
	$: projectNames = projectAssociations.map(a => a.project_name).slice(0, 2);
	$: additionalCount = Math.max(0, totalProjects - 2);
</script>

{#if isShared}
	<div class="flex items-center gap-1 {compact ? 'text-xs' : 'text-sm'}">
		<Badge variant="secondary" class="flex items-center gap-1 {compact ? 'text-xs px-1' : ''}">
			<Users class="h-3 w-3" />
			{totalProjects} project{totalProjects !== 1 ? 's' : ''}
		</Badge>
		
		{#if !compact && projectNames.length > 0}
			<div class="text-xs text-muted-foreground" title={projectAssociations.map(a => a.project_name).join(', ')}>
				{projectNames.join(', ')}{#if additionalCount > 0} +{additionalCount} more{/if}
			</div>
		{/if}
	</div>
{:else}
	<div class="flex items-center gap-1 {compact ? 'text-xs' : 'text-sm'}">
		<Badge variant="outline" class="flex items-center gap-1 {compact ? 'text-xs px-1' : ''}">
			<Eye class="h-3 w-3" />
			Private
		</Badge>
	</div>
{/if}