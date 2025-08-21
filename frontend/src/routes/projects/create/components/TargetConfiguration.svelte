<script lang="ts">
  import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
  import { Input } from '$lib/components/ui/input';
  import { Label } from '$lib/components/ui/label';
  import { Button } from '$lib/components/ui/button';
  import { Badge } from '$lib/components/ui/badge';
  import { Plus, Trash2, Globe, Link, Calendar } from 'lucide-svelte';
  import { createEventDispatcher } from 'svelte';

  const dispatch = createEventDispatcher();

  export let targets = [{ value: '', type: 'domain', from_date: '', to_date: '' }];

  // Validation
  $: isValid = targets.some(target => target.value.trim().length > 0);
  $: validTargets = targets.filter(t => t.value.trim());

  // Dispatch changes to parent
  $: dispatch('update', { targets, isValid });

  const addTarget = () => {
    targets = [...targets, { value: '', type: 'domain', from_date: '', to_date: '' }];
  };

  const removeTarget = (index: number) => {
    if (targets.length > 1) {
      targets = targets.filter((_, i) => i !== index);
    }
  };

  const inferTargetType = (input: string): 'domain' | 'url' => {
    const raw = input?.trim();
    if (!raw) return 'domain';
    const token = raw.split(/\s+/)[0];
    const candidate = token.startsWith('http://') || token.startsWith('https://') ? token : `https://${token}`;
    try {
      const u = new URL(candidate);
      const hasNonRootPath = (u.pathname && u.pathname !== '/') || !!u.search || !!u.hash;
      return hasNonRootPath ? 'url' : 'domain';
    } catch (e) {
      const slashIndex = token.indexOf('/');
      if (slashIndex > -1 && slashIndex < token.length - 1) return 'url';
      return 'domain';
    }
  };

  const updateTargetValue = (index: number, value: string) => {
    const inferredType = inferTargetType(value);
    if (inferredType !== targets[index].type) {
      targets[index].type = inferredType;
    }
    targets[index].value = processInput(value, targets[index].type);
    targets = [...targets];
  };

  const updateTargetType = (index: number, type: 'domain' | 'url') => {
    targets[index].type = type;
    targets[index].value = processInput(targets[index].value, type);
    targets = [...targets];
  };

  const processInput = (input: string, type: 'domain' | 'url') => {
    if (!input.trim()) return input;
    
    if (type === 'domain') {
      // Remove protocols, www, and paths - keep just domain
      return input
        .replace(/^https?:\/\//, '')
        .replace(/^www\./, '')
        .split('/')[0]
        .toLowerCase();
    } else {
      // Ensure URL has protocol, validate full URL
      if (!input.startsWith('http://') && !input.startsWith('https://')) {
        return `https://${input}`;
      }
      return input;
    }
  };
</script>

<div class="space-y-6">
  <div class="text-center space-y-2">
    <h2 class="text-2xl font-bold font-space-grotesk text-emerald-600">
      Configure Your Targets
    </h2>
    <p class="text-muted-foreground">
      Specify the websites, domains, or URLs you want to scrape from the Wayback Machine
    </p>
  </div>

  <Card class="shadow-sm">
    <CardHeader>
      <CardTitle class="flex items-center gap-2">
        <div class="w-8 h-8 bg-emerald-100 rounded-full flex items-center justify-center">
          <span class="text-emerald-600 font-semibold">2</span>
        </div>
        Scraping Targets
      </CardTitle>
      <CardDescription>
        Add websites and domains to monitor. You can mix specific URLs with entire domains.
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-6">
      {#each targets as target, index}
        <div class="border border-border rounded-lg p-4 space-y-4">
          <div class="flex items-center justify-between">
            <h4 class="font-medium text-base">Target {index + 1}</h4>
            {#if targets.length > 1}
              <Button
                variant="ghost"
                size="sm"
                onclick={() => removeTarget(index)}
                class="text-destructive hover:text-destructive h-8 w-8 p-0"
              >
                <Trash2 class="h-4 w-4" />
              </Button>
            {/if}
          </div>

          <!-- Target Type Selection -->
          <div class="space-y-3">
            <Label class="text-sm font-medium">Target Type</Label>
            <div class="flex gap-4">
              <label class="flex items-center space-x-2 cursor-pointer">
                <input
                  type="radio"
                  name="target-type-{index}"
                  value="domain"
                  checked={target.type === 'domain'}
                  on:change={() => updateTargetType(index, 'domain')}
                  class="h-4 w-4 text-emerald-500 border-gray-300 focus:ring-emerald-500"
                />
                <Globe class="h-4 w-4 text-muted-foreground" />
                <span class="text-sm">Entire Domain</span>
              </label>
              <label class="flex items-center space-x-2 cursor-pointer">
                <input
                  type="radio"
                  name="target-type-{index}"
                  value="url"
                  checked={target.type === 'url'}
                  on:change={() => updateTargetType(index, 'url')}
                  class="h-4 w-4 text-emerald-500 border-gray-300 focus:ring-emerald-500"
                />
                <Link class="h-4 w-4 text-muted-foreground" />
                <span class="text-sm">Specific URL</span>
              </label>
            </div>
          </div>

          <!-- URL/Domain Input -->
          <div class="space-y-2">
            <Label for="target-{index}" class="text-sm font-medium">
              {target.type === 'domain' ? 'Domain Name' : 'Full URL'}
            </Label>
            <div class="relative">
              {#if target.type === 'domain'}
                <div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                  <span class="text-muted-foreground text-sm">https://</span>
                </div>
                <Input
                  id="target-{index}"
                  type="text"
                  value={target.value}
                  on:input={(e) => {
                    const inputEl = e.target as HTMLInputElement;
                    updateTargetValue(index, inputEl.value);
                  }}
                  placeholder="example.com"
                  class="pl-16"
                />
              {:else}
                <Input
                  id="target-{index}"
                  type="text"
                  value={target.value}
                  on:input={(e) => {
                    const inputEl = e.target as HTMLInputElement;
                    updateTargetValue(index, inputEl.value);
                  }}
                  placeholder="https://example.com/specific/path"
                />
              {/if}
            </div>
            <p class="text-xs text-muted-foreground">
              {#if target.type === 'domain'}
                Will capture all pages under this domain (e.g., example.com/*)
              {:else}
                Will capture this specific URL or path prefix
              {/if}
            </p>
          </div>

          <!-- Date Range -->
          <div class="space-y-3">
            <div class="flex items-center gap-2">
              <Calendar class="h-4 w-4 text-muted-foreground" />
              <Label class="text-sm font-medium">Date Range (Optional)</Label>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-1">
                <Label for="from-date-{index}" class="text-xs text-muted-foreground">From Date</Label>
                <Input
                  id="from-date-{index}"
                  type="date"
                  bind:value={target.from_date}
                  class="text-sm"
                />
              </div>
              <div class="space-y-1">
                <Label for="to-date-{index}" class="text-xs text-muted-foreground">To Date</Label>
                <Input
                  id="to-date-{index}"
                  type="date"
                  bind:value={target.to_date}
                  class="text-sm"
                />
              </div>
            </div>
            <p class="text-xs text-muted-foreground">
              Filter Wayback Machine snapshots to this date range. Leave empty for all available snapshots.
            </p>
          </div>
        </div>
      {/each}

      <!-- Add Target Button -->
      <Button
        variant="outline"
        onclick={addTarget}
        class="w-full border-dashed border-2 h-12 text-muted-foreground hover:text-emerald-600 hover:border-emerald-300"
      >
        <Plus class="h-4 w-4 mr-2" />
        Add Another Target
      </Button>

      <!-- Summary -->
      {#if validTargets.length > 0}
        <div class="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
          <h4 class="font-medium text-emerald-800 mb-2">📊 Target Summary</h4>
          <div class="space-y-1 text-sm text-emerald-700">
            <p><strong>{validTargets.length}</strong> target{validTargets.length !== 1 ? 's' : ''} configured</p>
            <div class="flex gap-2 mt-2">
              <Badge variant="secondary" class="bg-emerald-100 text-emerald-700">
                {validTargets.filter(t => t.type === 'domain').length} domains
              </Badge>
              <Badge variant="secondary" class="bg-emerald-100 text-emerald-700">
                {validTargets.filter(t => t.type === 'url').length} specific URLs
              </Badge>
            </div>
          </div>
        </div>
      {/if}
    </CardContent>
  </Card>
</div>