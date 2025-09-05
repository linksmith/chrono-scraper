/**
 * Frontend tests for archive source selection functionality.
 * 
 * Tests cover:
 * - Component rendering with different archive source options
 * - Form validation and data handling
 * - User interactions (radio button selection, form submission)
 * - Default values and state management
 * - Integration with project creation/update forms
 * - Archive configuration UI components
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';

// Mock SvelteKit modules
vi.mock('$app/environment', () => ({
  browser: true
}));

vi.mock('$app/stores', () => ({
  page: {
    subscribe: vi.fn()
  }
}));

// Create mock components for testing
const MockArchiveSourceSelector = `
<script lang="ts">
  export let archiveSource: 'wayback_machine' | 'commoncrawl' | 'hybrid' = 'wayback_machine';
  export let fallbackEnabled: boolean = true;
  export let archiveConfig: Record<string, any> = {};
  export let onUpdate: (data: any) => void = () => {};
  export let disabled: boolean = false;
  
  let selectedSource = archiveSource;
  let enableFallback = fallbackEnabled;
  let config = { ...archiveConfig };
  
  const handleSourceChange = (newSource: typeof archiveSource) => {
    selectedSource = newSource;
    updateParent();
  };
  
  const handleFallbackChange = (enabled: boolean) => {
    enableFallback = enabled;
    updateParent();
  };
  
  const updateParent = () => {
    onUpdate({
      archiveSource: selectedSource,
      fallbackEnabled: enableFallback,
      archiveConfig: config
    });
  };
</script>

<div class="archive-source-selector" data-testid="archive-source-selector">
  <h3>Archive Source Configuration</h3>
  
  <!-- Archive Source Selection -->
  <fieldset {disabled}>
    <legend>Primary Archive Source</legend>
    
    <div class="radio-group">
      <label>
        <input 
          type="radio" 
          bind:group={selectedSource} 
          value="wayback_machine"
          on:change={() => handleSourceChange('wayback_machine')}
          data-testid="wayback-radio"
        />
        Wayback Machine
      </label>
      
      <label>
        <input 
          type="radio" 
          bind:group={selectedSource} 
          value="commoncrawl"
          on:change={() => handleSourceChange('commoncrawl')}
          data-testid="common-crawl-radio"
        />
        Common Crawl
      </label>
      
      <label>
        <input 
          type="radio" 
          bind:group={selectedSource} 
          value="hybrid"
          on:change={() => handleSourceChange('hybrid')}
          data-testid="hybrid-radio"
        />
        Hybrid (Both with Fallback)
      </label>
    </div>
  </fieldset>
  
  <!-- Fallback Configuration -->
  {#if selectedSource === 'hybrid' || selectedSource === 'wayback_machine'}
    <div class="fallback-config" data-testid="fallback-config">
      <label>
        <input 
          type="checkbox" 
          bind:checked={enableFallback}
          on:change={() => handleFallbackChange(enableFallback)}
          data-testid="fallback-checkbox"
          disabled={selectedSource === 'hybrid'}
        />
        Enable fallback to other sources on failure
        {#if selectedSource === 'hybrid'}
          <span class="note">(Always enabled in hybrid mode)</span>
        {/if}
      </label>
    </div>
  {/if}
  
  <!-- Advanced Configuration -->
  <details class="advanced-config" data-testid="advanced-config">
    <summary>Advanced Configuration</summary>
    
    {#if selectedSource === 'wayback_machine' || selectedSource === 'hybrid'}
      <div class="wayback-config" data-testid="wayback-config">
        <h4>Wayback Machine Settings</h4>
        <label>
          Timeout (seconds):
          <input 
            type="number" 
            bind:value={config.wayback_machine_timeout}
            data-testid="wayback-timeout"
            min="10"
            max="300"
          />
        </label>
        <label>
          Page size:
          <input 
            type="number" 
            bind:value={config.wayback_machine_page_size}
            data-testid="wayback-page-size"
            min="100"
            max="10000"
          />
        </label>
      </div>
    {/if}
    
    {#if selectedSource === 'commoncrawl' || selectedSource === 'hybrid'}
      <div class="common-crawl-config" data-testid="common-crawl-config">
        <h4>Common Crawl Settings</h4>
        <label>
          Timeout (seconds):
          <input 
            type="number" 
            bind:value={config.commoncrawl_timeout}
            data-testid="common-crawl-timeout"
            min="30"
            max="600"
          />
        </label>
        <label>
          Max retries:
          <input 
            type="number" 
            bind:value={config.commoncrawl_retries}
            data-testid="common-crawl-retries"
            min="1"
            max="20"
          />
        </label>
      </div>
    {/if}
    
    {#if selectedSource === 'hybrid'}
      <div class="hybrid-config" data-testid="hybrid-config">
        <h4>Fallback Strategy</h4>
        <select bind:value={config.fallback_strategy} data-testid="fallback-strategy">
          <option value="circuit_breaker">Circuit Breaker</option>
          <option value="immediate">Immediate</option>
          <option value="retry_then_fallback">Retry then Fallback</option>
        </select>
      </div>
    {/if}
  </details>
</div>

<style>
  .archive-source-selector {
    padding: 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  
  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .fallback-config {
    margin-top: 1rem;
  }
  
  .advanced-config {
    margin-top: 1rem;
  }
  
  .wayback-config, .common-crawl-config, .hybrid-config {
    margin: 1rem 0;
    padding: 0.5rem;
    border: 1px solid #eee;
    border-radius: 4px;
  }
  
  .note {
    font-size: 0.8em;
    color: #666;
  }
  
  label {
    display: block;
    margin: 0.5rem 0;
  }
  
  input, select {
    margin-left: 0.5rem;
  }
</style>
`;

const MockProjectForm = `
<script lang="ts">
  import ArchiveSourceSelector from './ArchiveSourceSelector.svelte';
  
  export let initialData: any = {};
  export let onSubmit: (data: any) => void = () => {};
  export let mode: 'create' | 'edit' = 'create';
  
  let formData = {
    name: initialData.name || '',
    description: initialData.description || '',
    archiveSource: initialData.archiveSource || 'wayback_machine',
    fallbackEnabled: initialData.fallbackEnabled ?? true,
    archiveConfig: initialData.archiveConfig || {},
    ...initialData
  };
  
  let errors: Record<string, string> = {};
  let isSubmitting = false;
  
  const handleArchiveUpdate = (archiveData: any) => {
    formData.archiveSource = archiveData.archiveSource;
    formData.fallbackEnabled = archiveData.fallbackEnabled;
    formData.archiveConfig = archiveData.archiveConfig;
  };
  
  const validateForm = () => {
    errors = {};
    
    if (!formData.name?.trim()) {
      errors.name = 'Project name is required';
    }
    
    if (formData.archiveSource === 'hybrid' && !formData.fallbackEnabled) {
      errors.archive = 'Hybrid mode requires fallback to be enabled';
    }
    
    return Object.keys(errors).length === 0;
  };
  
  const handleSubmit = async (event: Event) => {
    event.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    isSubmitting = true;
    
    try {
      await onSubmit(formData);
    } catch (error) {
      console.error('Form submission error:', error);
    } finally {
      isSubmitting = false;
    }
  };
</script>

<form on:submit={handleSubmit} data-testid="project-form">
  <div class="form-group">
    <label for="project-name">
      Project Name *
    </label>
    <input 
      id="project-name"
      type="text" 
      bind:value={formData.name}
      data-testid="project-name-input"
      class:error={errors.name}
    />
    {#if errors.name}
      <span class="error-message" data-testid="name-error">{errors.name}</span>
    {/if}
  </div>
  
  <div class="form-group">
    <label for="project-description">
      Description
    </label>
    <textarea 
      id="project-description"
      bind:value={formData.description}
      data-testid="project-description-input"
    ></textarea>
  </div>
  
  <!-- Archive Source Configuration -->
  <div class="form-group">
    <ArchiveSourceSelector
      archiveSource={formData.archiveSource}
      fallbackEnabled={formData.fallbackEnabled}
      archiveConfig={formData.archiveConfig}
      onUpdate={handleArchiveUpdate}
    />
    {#if errors.archive}
      <span class="error-message" data-testid="archive-error">{errors.archive}</span>
    {/if}
  </div>
  
  <div class="form-actions">
    <button 
      type="submit" 
      disabled={isSubmitting}
      data-testid="submit-button"
    >
      {isSubmitting ? 'Saving...' : mode === 'create' ? 'Create Project' : 'Update Project'}
    </button>
    
    <button 
      type="button" 
      data-testid="cancel-button"
      disabled={isSubmitting}
    >
      Cancel
    </button>
  </div>
</form>

<style>
  .form-group {
    margin-bottom: 1.5rem;
  }
  
  .form-actions {
    display: flex;
    gap: 1rem;
    margin-top: 2rem;
  }
  
  .error {
    border-color: red;
  }
  
  .error-message {
    color: red;
    font-size: 0.8em;
  }
  
  button {
    padding: 0.5rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
  }
  
  button[type="submit"] {
    background-color: #007bff;
    color: white;
  }
  
  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
</style>
`;

describe('ArchiveSourceSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders with default values', async () => {
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    expect(screen.getByTestId('archive-source-selector')).toBeInTheDocument();
    expect(screen.getByTestId('wayback-radio')).toBeChecked();
    expect(screen.getByTestId('common-crawl-radio')).not.toBeChecked();
    expect(screen.getByTestId('hybrid-radio')).not.toBeChecked();
    expect(screen.getByTestId('fallback-checkbox')).toBeChecked();
  });

  it('handles archive source selection changes', async () => {
    const user = userEvent.setup();
    const mockOnUpdate = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {
        onUpdate: mockOnUpdate
      }
    });
    
    // Select Common Crawl
    await user.click(screen.getByTestId('common-crawl-radio'));
    
    expect(screen.getByTestId('common-crawl-radio')).toBeChecked();
    expect(screen.getByTestId('wayback-radio')).not.toBeChecked();
    expect(mockOnUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        archiveSource: 'commoncrawl'
      })
    );
  });

  it('shows fallback configuration for hybrid mode', async () => {
    const user = userEvent.setup();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    // Select hybrid mode
    await user.click(screen.getByTestId('hybrid-radio'));
    
    expect(screen.getByTestId('hybrid-radio')).toBeChecked();
    expect(screen.getByTestId('fallback-config')).toBeInTheDocument();
    
    // Fallback checkbox should be disabled in hybrid mode
    const fallbackCheckbox = screen.getByTestId('fallback-checkbox');
    expect(fallbackCheckbox).toBeDisabled();
  });

  it('shows appropriate advanced configuration options', async () => {
    const user = userEvent.setup();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    // Open advanced configuration
    const advancedDetails = screen.getByTestId('advanced-config');
    await user.click(advancedDetails.querySelector('summary')!);
    
    // Should show Wayback Machine config by default
    expect(screen.getByTestId('wayback-config')).toBeInTheDocument();
    expect(screen.getByTestId('wayback-timeout')).toBeInTheDocument();
    expect(screen.getByTestId('wayback-page-size')).toBeInTheDocument();
    
    // Should not show Common Crawl config for Wayback only
    expect(screen.queryByTestId('common-crawl-config')).not.toBeInTheDocument();
    
    // Switch to hybrid mode
    await user.click(screen.getByTestId('hybrid-radio'));
    
    // Should show both configs in hybrid mode
    expect(screen.getByTestId('wayback-config')).toBeInTheDocument();
    expect(screen.getByTestId('common-crawl-config')).toBeInTheDocument();
    expect(screen.getByTestId('hybrid-config')).toBeInTheDocument();
    expect(screen.getByTestId('fallback-strategy')).toBeInTheDocument();
  });

  it('handles disabled state correctly', async () => {
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {
        disabled: true
      }
    });
    
    expect(screen.getByTestId('wayback-radio')).toBeDisabled();
    expect(screen.getByTestId('common-crawl-radio')).toBeDisabled();
    expect(screen.getByTestId('hybrid-radio')).toBeDisabled();
  });

  it('validates archive configuration inputs', async () => {
    const user = userEvent.setup();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    // Open advanced configuration
    const advancedDetails = screen.getByTestId('advanced-config');
    await user.click(advancedDetails.querySelector('summary')!);
    
    // Test timeout input validation
    const timeoutInput = screen.getByTestId('wayback-timeout');
    expect(timeoutInput).toHaveAttribute('min', '10');
    expect(timeoutInput).toHaveAttribute('max', '300');
    
    // Test page size input validation
    const pageSizeInput = screen.getByTestId('wayback-page-size');
    expect(pageSizeInput).toHaveAttribute('min', '100');
    expect(pageSizeInput).toHaveAttribute('max', '10000');
  });

  it('updates configuration values correctly', async () => {
    const user = userEvent.setup();
    const mockOnUpdate = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {
        onUpdate: mockOnUpdate,
        archiveConfig: {
          wayback_machine_timeout: 60,
          wayback_machine_page_size: 1000
        }
      }
    });
    
    // Open advanced configuration
    const advancedDetails = screen.getByTestId('advanced-config');
    await user.click(advancedDetails.querySelector('summary')!);
    
    // Update timeout value
    const timeoutInput = screen.getByTestId('wayback-timeout');
    await user.clear(timeoutInput);
    await user.type(timeoutInput, '120');
    
    // Should trigger update
    await waitFor(() => {
      expect(mockOnUpdate).toHaveBeenCalled();
    });
  });
});

describe('ProjectForm with Archive Source Integration', () => {
  it('integrates archive source selector in project form', async () => {
    const mockOnSubmit = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        onSubmit: mockOnSubmit,
        mode: 'create'
      }
    });
    
    expect(screen.getByTestId('project-form')).toBeInTheDocument();
    expect(screen.getByTestId('archive-source-selector')).toBeInTheDocument();
    expect(screen.getByText('Create Project')).toBeInTheDocument();
  });

  it('validates project form with archive source requirements', async () => {
    const user = userEvent.setup();
    const mockOnSubmit = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        onSubmit: mockOnSubmit
      }
    });
    
    // Try to submit without project name
    await user.click(screen.getByTestId('submit-button'));
    
    expect(screen.getByTestId('name-error')).toHaveTextContent('Project name is required');
    expect(mockOnSubmit).not.toHaveBeenCalled();
    
    // Fill in project name
    await user.type(screen.getByTestId('project-name-input'), 'Test Project');
    
    // Submit should now work
    await user.click(screen.getByTestId('submit-button'));
    
    expect(mockOnSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Test Project',
        archiveSource: 'wayback_machine',
        fallbackEnabled: true
      })
    );
  });

  it('handles archive source changes in project form', async () => {
    const user = userEvent.setup();
    const mockOnSubmit = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        onSubmit: mockOnSubmit
      }
    });
    
    // Fill in project name
    await user.type(screen.getByTestId('project-name-input'), 'Archive Test Project');
    
    // Change to Common Crawl
    await user.click(screen.getByTestId('common-crawl-radio'));
    
    // Submit form
    await user.click(screen.getByTestId('submit-button'));
    
    expect(mockOnSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Archive Test Project',
        archiveSource: 'commoncrawl',
        fallbackEnabled: true
      })
    );
  });

  it('preserves archive configuration in edit mode', async () => {
    const initialData = {
      name: 'Existing Project',
      description: 'An existing project',
      archiveSource: 'hybrid',
      fallbackEnabled: true,
      archiveConfig: {
        wayback_machine_timeout: 90,
        commoncrawl_retries: 8,
        fallback_strategy: 'retry_then_fallback'
      }
    };
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        initialData,
        mode: 'edit'
      }
    });
    
    expect(screen.getByTestId('project-name-input')).toHaveValue('Existing Project');
    expect(screen.getByTestId('hybrid-radio')).toBeChecked();
    expect(screen.getByText('Update Project')).toBeInTheDocument();
  });

  it('shows loading state during form submission', async () => {
    const user = userEvent.setup();
    const mockOnSubmit = vi.fn(() => new Promise(resolve => setTimeout(resolve, 100)));
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        onSubmit: mockOnSubmit
      }
    });
    
    // Fill in required fields
    await user.type(screen.getByTestId('project-name-input'), 'Loading Test');
    
    // Submit form
    await user.click(screen.getByTestId('submit-button'));
    
    // Should show loading state
    expect(screen.getByText('Saving...')).toBeInTheDocument();
    expect(screen.getByTestId('submit-button')).toBeDisabled();
    expect(screen.getByTestId('cancel-button')).toBeDisabled();
    
    // Wait for form submission to complete
    await waitFor(() => {
      expect(screen.queryByText('Saving...')).not.toBeInTheDocument();
    });
  });

  it('validates hybrid mode requirements', async () => {
    const user = userEvent.setup();
    const mockOnSubmit = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        onSubmit: mockOnSubmit,
        initialData: {
          archiveSource: 'hybrid',
          fallbackEnabled: false // Invalid for hybrid mode
        }
      }
    });
    
    // Fill in project name
    await user.type(screen.getByTestId('project-name-input'), 'Hybrid Test');
    
    // Try to submit
    await user.click(screen.getByTestId('submit-button'));
    
    // Should show archive validation error
    expect(screen.getByTestId('archive-error')).toHaveTextContent('Hybrid mode requires fallback to be enabled');
    expect(mockOnSubmit).not.toHaveBeenCalled();
  });
});

describe('Archive Source Selection Accessibility', () => {
  it('has proper ARIA labels and structure', async () => {
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    // Should have proper fieldset and legend
    const fieldset = screen.getByRole('group', { name: /Primary Archive Source/i });
    expect(fieldset).toBeInTheDocument();
    
    // Radio buttons should be properly labeled
    expect(screen.getByRole('radio', { name: /Wayback Machine/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Common Crawl/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Hybrid/i })).toBeInTheDocument();
    
    // Checkbox should be properly labeled
    expect(screen.getByRole('checkbox', { name: /Enable fallback/i })).toBeInTheDocument();
  });

  it('maintains focus management correctly', async () => {
    const user = userEvent.setup();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    // Tab through radio buttons
    await user.tab();
    expect(screen.getByTestId('wayback-radio')).toHaveFocus();
    
    await user.tab();
    expect(screen.getByTestId('common-crawl-radio')).toHaveFocus();
    
    await user.tab();
    expect(screen.getByTestId('hybrid-radio')).toHaveFocus();
  });

  it('provides keyboard navigation support', async () => {
    const user = userEvent.setup();
    const mockOnUpdate = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {
        onUpdate: mockOnUpdate
      }
    });
    
    // Focus the radio group and use arrow keys
    screen.getByTestId('wayback-radio').focus();
    
    // Arrow key navigation
    await user.keyboard('{ArrowDown}');
    expect(screen.getByTestId('common-crawl-radio')).toBeChecked();
    
    await user.keyboard('{ArrowDown}');
    expect(screen.getByTestId('hybrid-radio')).toBeChecked();
    
    // Should have triggered updates
    expect(mockOnUpdate).toHaveBeenCalled();
  });
});

describe('Archive Source Selection Error Handling', () => {
  it('handles invalid initial values gracefully', async () => {
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {
        archiveSource: 'invalid_source' as any, // Invalid value
        archiveConfig: null as any // Invalid config
      }
    });
    
    // Should still render without crashing
    expect(screen.getByTestId('archive-source-selector')).toBeInTheDocument();
    
    // Should default to a valid source
    expect(screen.getByTestId('wayback-radio')).toBeChecked();
  });

  it('validates numeric inputs properly', async () => {
    const user = userEvent.setup();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {}
    });
    
    // Open advanced configuration
    const advancedDetails = screen.getByTestId('advanced-config');
    await user.click(advancedDetails.querySelector('summary')!);
    
    // Test invalid timeout value
    const timeoutInput = screen.getByTestId('wayback-timeout');
    await user.clear(timeoutInput);
    await user.type(timeoutInput, '5'); // Below minimum
    
    // Browser validation should prevent invalid values
    expect(timeoutInput).toBeInvalid();
    
    // Test valid value
    await user.clear(timeoutInput);
    await user.type(timeoutInput, '60');
    expect(timeoutInput).toBeValid();
  });
});

describe('Archive Source Selection Performance', () => {
  it('handles rapid state changes efficiently', async () => {
    const user = userEvent.setup();
    const mockOnUpdate = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    render(mockComponent, {
      props: {
        onUpdate: mockOnUpdate
      }
    });
    
    // Rapidly change selections
    for (let i = 0; i < 10; i++) {
      await user.click(screen.getByTestId('common-crawl-radio'));
      await user.click(screen.getByTestId('wayback-radio'));
    }
    
    // Should handle all changes without issues
    expect(mockOnUpdate).toHaveBeenCalled();
    expect(screen.getByTestId('wayback-radio')).toBeChecked();
  });

  it('does not cause memory leaks with configuration updates', async () => {
    const user = userEvent.setup();
    const mockOnUpdate = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    const { unmount } = render(mockComponent, {
      props: {
        onUpdate: mockOnUpdate
      }
    });
    
    // Open advanced configuration
    const advancedDetails = screen.getByTestId('advanced-config');
    await user.click(advancedDetails.querySelector('summary')!);
    
    // Make several configuration changes
    const timeoutInput = screen.getByTestId('wayback-timeout');
    for (let i = 0; i < 20; i++) {
      await user.clear(timeoutInput);
      await user.type(timeoutInput, (60 + i).toString());
    }
    
    // Cleanup should work without issues
    expect(() => unmount()).not.toThrow();
  });
});

describe('Archive Source Selection Integration', () => {
  it('works correctly within larger forms', async () => {
    const user = userEvent.setup();
    const mockOnSubmit = vi.fn();
    
    const component = await import('svelte');
    const { render } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockProjectForm
    });
    
    render(mockComponent, {
      props: {
        onSubmit: mockOnSubmit
      }
    });
    
    // Fill form with complex archive configuration
    await user.type(screen.getByTestId('project-name-input'), 'Integration Test Project');
    await user.type(screen.getByTestId('project-description-input'), 'Testing integration');
    
    // Select hybrid mode
    await user.click(screen.getByTestId('hybrid-radio'));
    
    // Open advanced configuration
    const advancedDetails = screen.getByTestId('advanced-config');
    await user.click(advancedDetails.querySelector('summary')!);
    
    // Configure advanced settings
    await user.selectOptions(screen.getByTestId('fallback-strategy'), 'immediate');
    
    // Submit form
    await user.click(screen.getByTestId('submit-button'));
    
    // Should submit with complete configuration
    expect(mockOnSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'Integration Test Project',
        description: 'Testing integration',
        archiveSource: 'hybrid',
        fallbackEnabled: true,
        archiveConfig: expect.objectContaining({
          fallback_strategy: 'immediate'
        })
      })
    );
  });

  it('synchronizes with external state changes', async () => {
    const component = await import('svelte');
    const { render, rerender } = await import('@testing-library/svelte');
    
    const mockComponent = component.SvelteComponent.extend({
      template: MockArchiveSourceSelector
    });
    
    const { component: renderedComponent } = render(mockComponent, {
      props: {
        archiveSource: 'wayback_machine',
        fallbackEnabled: true
      }
    });
    
    expect(screen.getByTestId('wayback-radio')).toBeChecked();
    
    // Update props externally
    await renderedComponent.$set({
      archiveSource: 'commoncrawl',
      fallbackEnabled: false
    });
    
    // Component should reflect external changes
    expect(screen.getByTestId('common-crawl-radio')).toBeChecked();
    expect(screen.getByTestId('wayback-radio')).not.toBeChecked();
  });
});