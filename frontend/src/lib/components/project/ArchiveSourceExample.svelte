<script lang="ts">
  import ArchiveSourceSelection from './ArchiveSourceSelection.svelte';
  import type { ArchiveConfiguration } from '$lib/types/archive';
  import { DEFAULT_ARCHIVE_CONFIG } from '$lib/types/archive';

  let archiveConfig: ArchiveConfiguration = {
    archive_source: 'hybrid',
    fallback_enabled: true,
    archive_config: { ...DEFAULT_ARCHIVE_CONFIG }
  };

  function handleArchiveUpdate(event: CustomEvent<ArchiveConfiguration>) {
    archiveConfig = event.detail;
    console.log('Archive configuration updated:', archiveConfig);
  }
</script>

<!-- Example usage of the ArchiveSourceSelection component -->
<div class="max-w-4xl mx-auto p-6 space-y-8">
  <h1 class="text-2xl font-bold">Archive Source Selection Examples</h1>
  
  <!-- Full Mode -->
  <section class="space-y-4">
    <h2 class="text-xl font-semibold">Full Mode (Default)</h2>
    <ArchiveSourceSelection
      bind:archive_source={archiveConfig.archive_source}
      bind:fallback_enabled={archiveConfig.fallback_enabled}
      bind:archive_config={archiveConfig.archive_config}
      on:update={handleArchiveUpdate}
    />
  </section>

  <!-- Compact Mode -->
  <section class="space-y-4">
    <h2 class="text-xl font-semibold">Compact Mode</h2>
    <ArchiveSourceSelection
      bind:archive_source={archiveConfig.archive_source}
      bind:fallback_enabled={archiveConfig.fallback_enabled}
      bind:archive_config={archiveConfig.archive_config}
      compact={true}
      on:update={handleArchiveUpdate}
    />
  </section>

  <!-- Configuration Display -->
  <section class="space-y-4">
    <h2 class="text-xl font-semibold">Current Configuration</h2>
    <div class="bg-gray-100 dark:bg-gray-800 p-4 rounded-lg">
      <pre class="text-sm">{JSON.stringify(archiveConfig, null, 2)}</pre>
    </div>
  </section>
</div>