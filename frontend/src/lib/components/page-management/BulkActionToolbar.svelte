<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { Star, Tag, CheckCircle, XCircle, FolderOpen, AlertCircle, Loader2 } from 'lucide-svelte';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Label } from '$lib/components/ui/label';
	import { Badge } from '$lib/components/ui/badge';
	import { 
		Select,
		SelectContent,
		SelectItem,
		SelectTrigger,
		SelectValue,
	} from '$lib/components/ui/select';
	import {
		Sheet,
		SheetContent,
		SheetHeader,
		SheetTitle,
		SheetTrigger
	} from '$lib/components/ui/sheet';
	import { cn } from '$lib/utils';
	import { 
		pageManagementActions,
		selectedPagesCount,
		bulkActionInProgress
	} from '$lib/stores/page-management';
	import TagAutocomplete from './TagAutocomplete.svelte';

	const dispatch = createEventDispatcher<{
		bulkAction: { action: string; data?: any };
		closeToolbar: void;
	}>();

	// State
	let showTagDialog = false;
	let showCategoryDialog = false;
	let showConfirmDialog = false;
	let pendingAction: { action: string; data?: any; confirmText?: string } | null = null;
	
	// Form states
	let tagsToAdd: string[] = [];
	let tagsToRemove: string[] = [];
	let selectedCategory = '';
	let selectedPriority = '';

	// Reactive state
	$: selectedCount = $selectedPagesCount;
	$: actionInProgress = $bulkActionInProgress;

	// Action handlers
	async function handleBulkStar() {
		await performAction('star', {});
	}

	async function handleBulkUnstar() {
		await performAction('unstar', {});
	}

	async function handleMarkRelevant() {
		await performAction('mark_relevant', { review_status: 'relevant' });
	}

	async function handleMarkIrrelevant() {
		const action = {
			action: 'mark_irrelevant',
			data: { review_status: 'irrelevant' },
			confirmText: `Mark ${selectedCount} page${selectedCount !== 1 ? 's' : ''} as irrelevant?`
		};
		showConfirmDialog = true;
		pendingAction = action;
	}

	function handleTagsAction() {
		showTagDialog = true;
	}

	function handleCategoryAction() {
		showCategoryDialog = true;
	}

	async function performAction(action: string, data: any) {
		try {
			await pageManagementActions.performBulkAction(action, data);
			dispatch('bulkAction', { action, data });
			
			// Show success message
			console.log(`Successfully applied ${action} to ${selectedCount} pages`);
		} catch (error) {
			console.error(`Failed to perform bulk action ${action}:`, error);
			// Could dispatch error event here for toast notifications
		}
	}

	async function confirmAction() {
		if (pendingAction) {
			await performAction(pendingAction.action, pendingAction.data);
			showConfirmDialog = false;
			pendingAction = null;
		}
	}

	async function applyTags() {
		if (tagsToAdd.length > 0) {
			await performAction('add_tags', { tags: tagsToAdd });
		}
		if (tagsToRemove.length > 0) {
			await performAction('remove_tags', { tags: tagsToRemove });
		}
		
		// Reset form
		tagsToAdd = [];
		tagsToRemove = [];
		showTagDialog = false;
	}

	async function applyCategory() {
		const data: any = {};
		if (selectedCategory) data.page_category = selectedCategory;
		if (selectedPriority) data.priority_level = selectedPriority;
		
		if (Object.keys(data).length > 0) {
			await performAction('set_category', data);
		}
		
		// Reset form
		selectedCategory = '';
		selectedPriority = '';
		showCategoryDialog = false;
	}

	function closeToolbar() {
		dispatch('closeToolbar');
	}
</script>

{#if selectedCount > 0}
	<div class="bg-background border-t border-border p-4 shadow-lg">
		<div class="flex items-center justify-between">
			<div class="flex items-center space-x-2">
				<span class="text-sm font-medium">
					{selectedCount} page{selectedCount !== 1 ? 's' : ''} selected
				</span>
				
				{#if actionInProgress}
					<div class="flex items-center space-x-2 text-muted-foreground">
						<Loader2 class="h-4 w-4 animate-spin" />
						<span class="text-sm">Processing...</span>
					</div>
				{/if}
			</div>

			<div class="flex items-center space-x-2">
				<!-- Quick Actions -->
				<Button
					variant="outline"
					size="sm"
					onclick={handleBulkStar}
					disabled={actionInProgress}
					class="space-x-1"
				>
					<Star class="h-4 w-4" />
					<span>Star</span>
				</Button>

				<Button
					variant="outline"
					size="sm"
					onclick={handleBulkUnstar}
					disabled={actionInProgress}
					class="space-x-1"
				>
					<Star class="h-4 w-4 fill-current" />
					<span>Unstar</span>
				</Button>

				<Button
					variant="outline"
					size="sm"
					onclick={handleMarkRelevant}
					disabled={actionInProgress}
					class="space-x-1 text-green-600 hover:text-green-700"
				>
					<CheckCircle class="h-4 w-4" />
					<span>Relevant</span>
				</Button>

				<Button
					variant="outline"
					size="sm"
					onclick={handleMarkIrrelevant}
					disabled={actionInProgress}
					class="space-x-1 text-red-600 hover:text-red-700"
				>
					<XCircle class="h-4 w-4" />
					<span>Irrelevant</span>
				</Button>

				<Button
					variant="outline"
					size="sm"
					onclick={handleTagsAction}
					disabled={actionInProgress}
					class="space-x-1"
				>
					<Tag class="h-4 w-4" />
					<span>Tags</span>
				</Button>

				<Button
					variant="outline"
					size="sm"
					onclick={handleCategoryAction}
					disabled={actionInProgress}
					class="space-x-1"
				>
					<FolderOpen class="h-4 w-4" />
					<span>Category</span>
				</Button>

				<!-- Close button -->
				<Button
					variant="ghost"
					size="sm"
					onclick={closeToolbar}
					disabled={actionInProgress}
				>
					✕
				</Button>
			</div>
		</div>
	</div>
{/if}

<!-- Tags Sheet -->
<Sheet bind:open={showTagDialog}>
	<SheetContent class="max-w-md">
		<SheetHeader>
			<SheetTitle>Manage Tags</SheetTitle>
			<p class="text-sm text-muted-foreground">
				Add or remove tags for {selectedCount} selected page{selectedCount !== 1 ? 's' : ''}
			</p>
		</SheetHeader>

		<div class="space-y-4 mt-6">
			<div>
				<Label for="tags-add">Add Tags</Label>
				<TagAutocomplete
					bind:selectedTags={tagsToAdd}
					placeholder="Type to add tags..."
				/>
			</div>

			<div>
				<Label for="tags-remove">Remove Tags</Label>
				<TagAutocomplete
					bind:selectedTags={tagsToRemove}
					placeholder="Type to remove tags..."
				/>
			</div>
		</div>

		<div class="flex justify-end space-x-2 mt-6">
			<Button variant="outline" onclick={() => showTagDialog = false}>
				Cancel
			</Button>
			<Button onclick={applyTags} disabled={tagsToAdd.length === 0 && tagsToRemove.length === 0}>
				Apply Changes
			</Button>
		</div>
	</SheetContent>
</Sheet>

<!-- Category Sheet -->
<Sheet bind:open={showCategoryDialog}>
	<SheetContent class="max-w-md">
		<SheetHeader>
			<SheetTitle>Set Category & Priority</SheetTitle>
			<p class="text-sm text-muted-foreground">
				Update category and priority for {selectedCount} selected page{selectedCount !== 1 ? 's' : ''}
			</p>
		</SheetHeader>

		<div class="space-y-4 mt-6">
			<div>
				<Label for="category">Category</Label>
				<Select bind:value={selectedCategory}>
					<SelectTrigger>
						<SelectValue placeholder="Select category..." />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="government">Government</SelectItem>
						<SelectItem value="research">Research</SelectItem>
						<SelectItem value="news">News</SelectItem>
						<SelectItem value="blog">Blog</SelectItem>
						<SelectItem value="commercial">Commercial</SelectItem>
						<SelectItem value="personal">Personal</SelectItem>
						<SelectItem value="social_media">Social Media</SelectItem>
						<SelectItem value="academic">Academic</SelectItem>
						<SelectItem value="legal">Legal</SelectItem>
						<SelectItem value="technical">Technical</SelectItem>
					</SelectContent>
				</Select>
			</div>

			<div>
				<Label for="priority">Priority Level</Label>
				<Select bind:value={selectedPriority}>
					<SelectTrigger>
						<SelectValue placeholder="Select priority..." />
					</SelectTrigger>
					<SelectContent>
						<SelectItem value="low">Low</SelectItem>
						<SelectItem value="medium">Medium</SelectItem>
						<SelectItem value="high">High</SelectItem>
						<SelectItem value="critical">Critical</SelectItem>
					</SelectContent>
				</Select>
			</div>
		</div>

		<div class="flex justify-end space-x-2 mt-6">
			<Button variant="outline" onclick={() => showCategoryDialog = false}>
				Cancel
			</Button>
			<Button onclick={applyCategory} disabled={!selectedCategory && !selectedPriority}>
				Apply Changes
			</Button>
		</div>
	</SheetContent>
</Sheet>

<!-- Confirmation Sheet -->
<Sheet bind:open={showConfirmDialog}>
	<SheetContent class="max-w-md">
		<SheetHeader>
			<SheetTitle class="flex items-center space-x-2">
				<AlertCircle class="h-5 w-5 text-orange-500" />
				<span>Confirm Action</span>
			</SheetTitle>
			<p class="text-sm text-muted-foreground">
				{pendingAction?.confirmText || 'Are you sure you want to perform this action?'}
			</p>
		</SheetHeader>

		<div class="flex justify-end space-x-2 mt-6">
			<Button variant="outline" onclick={() => { showConfirmDialog = false; pendingAction = null; }}>
				Cancel
			</Button>
			<Button onclick={confirmAction} variant="destructive">
				Confirm
			</Button>
		</div>
	</SheetContent>
</Sheet>

<style>
	/* Ensure toolbar stays at bottom of viewport when fixed */
	:global(.bulk-action-toolbar-fixed) {
		position: fixed;
		bottom: 0;
		left: 0;
		right: 0;
		z-index: 50;
	}
</style>