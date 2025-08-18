<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  
  let projectId: string;
  $: projectId = $page.params.id;
  
  onMount(() => {
    // Redirect to the manage page instead
    goto(`/projects/${projectId}/manage`);
  });
</script>

<!-- This page redirects to manage page -->