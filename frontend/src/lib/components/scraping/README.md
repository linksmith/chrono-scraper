# Incremental Scraping Components

This directory contains comprehensive frontend UI components for the incremental scraping feature. These components provide a complete interface for managing, monitoring, and configuring incremental scraping operations.

## Overview

The incremental scraping system maintains continuous coverage of domains by automatically filling gaps in historical data and keeping content up-to-date. These components provide the user interface for this functionality.

## Components

### Core Components

#### 1. `IncrementalScrapingPanel.svelte`
Main control panel for domain-level incremental scraping management.

**Props:**
- `domainId: number` - ID of the domain to manage
- `projectId: number` - Parent project ID
- `domainName?: string` - Display name for the domain
- `canControl?: boolean` - Whether user can modify settings (default: true)

**Events:**
- `incrementalUpdate` - Real-time updates during scraping
- `scrapeTriggered` - When scraping is manually triggered
- `configUpdated` - When configuration is changed

**Features:**
- Coverage percentage and gaps visualization
- Manual trigger controls
- Real-time status updates via WebSocket
- Configuration management
- History tracking

#### 2. `CoverageVisualization.svelte`
Visual representation of coverage gaps and timeline analysis.

**Props:**
- `domainId: number` - Domain to visualize
- `projectId: number` - Parent project ID

**Events:**
- `gapSelected` - When user selects gaps to fill

**Features:**
- Gap timeline visualization
- Priority scoring display
- Bulk gap selection and filling
- Estimated page counts
- Interactive gap management

#### 3. `IncrementalHistory.svelte`
History of incremental scraping runs with detailed metrics.

**Props:**
- `domainId: number` - Domain to show history for

**Events:**
- `runSelected` - When user clicks on a run
- `runCancelled` - When user cancels a running job

**Features:**
- Paginated run history
- Run status and performance metrics
- Cancel active runs
- Filter by run type and status
- Detailed error information

#### 4. `IncrementalConfig.svelte`
Configuration panel for incremental scraping settings.

**Props:**
- `domainId: number` - Domain to configure
- `config: IncrementalScrapingStatus` - Current configuration
- `canControl?: boolean` - Whether user can edit

**Events:**
- `configUpdated` - When settings are changed

**Features:**
- Overlap days configuration
- Auto-scheduling settings
- Performance limits (pages per run)
- Gap fill thresholds
- Real-time validation and recommendations

### Dashboard Components

#### 5. `IncrementalScrapingDashboard.svelte`
Project-wide incremental scraping overview and management.

**Props:**
- `projectId: number` - Project to display
- `projectName?: string` - Display name
- `showDomainBreakdown?: boolean` - Show per-domain statistics

**Events:**
- `scrapeTriggered` - Project-wide scraping triggered
- `viewSchedule` - User wants to view schedule
- `fillAllGaps` - Bulk gap filling requested
- `configureSchedule` - Schedule configuration requested

**Features:**
- System health indicators
- Project-wide statistics
- Active run monitoring
- Quick action buttons
- Domain status overview

### Integration Components

#### 6. `ProjectIncrementalTab.svelte`
Complete tab component for integration into project pages.

**Props:**
- `projectId: number` - Project ID
- `projectName?: string` - Display name

**Events:**
- `scrapeTriggered` - Forwarded from child components
- `configUpdated` - Configuration changes
- `incrementalUpdate` - Real-time updates

**Features:**
- Multi-tab interface (Overview, Domains, History)
- Domain selection and configuration
- Project-wide dashboard integration
- Automatic domain loading and status

#### 7. `EnhancedDomainCard.svelte`
Enhanced domain card with integrated incremental scraping panel.

**Props:**
- `domain: DomainObject` - Domain data
- `projectId: number` - Parent project
- `projectName?: string` - Display name
- `isScrapingActive?: boolean` - Whether scraping is running
- `canControl?: boolean` - User permissions

**Features:**
- Collapsible detailed view
- Tabbed interface (Overview, Incremental, Analytics)
- Integrated scraping controls
- Real-time status updates

## API Service

### `incrementalScrapingApi.ts`
Comprehensive API service for all incremental scraping operations.

**Key Methods:**
- `getDomainStatus(domainId)` - Get current status and configuration
- `updateDomainConfig(domainId, config)` - Update domain settings
- `getDomainGaps(domainId)` - Retrieve coverage gaps
- `getDomainHistory(domainId)` - Get scraping run history
- `triggerIncrementalScraping(projectId, options)` - Start scraping
- `fillCoverageGaps(gapIds)` - Fill specific gaps
- `getProjectStats(projectId)` - Project-wide statistics

## Usage Examples

### Basic Integration

```svelte
<script>
  import { IncrementalScrapingPanel } from '$lib/components/scraping';
  
  let domainId = 123;
  let projectId = 456;
</script>

<IncrementalScrapingPanel 
  {domainId} 
  {projectId}
  domainName="example.com"
  on:scrapeTriggered={(e) => console.log('Scraping started:', e.detail)}
/>
```

### Project Dashboard Integration

```svelte
<script>
  import { ProjectIncrementalTab } from '$lib/components/project';
  
  let projectId = 456;
</script>

<Tabs>
  <TabsList>
    <TabsTrigger value="incremental">Incremental Scraping</TabsTrigger>
  </TabsList>
  
  <TabsContent value="incremental">
    <ProjectIncrementalTab 
      {projectId}
      projectName="My Project"
      on:configUpdated={handleConfigUpdate}
    />
  </TabsContent>
</Tabs>
```

### Enhanced Domain Management

```svelte
<script>
  import { EnhancedDomainCard } from '$lib/components/domains';
  
  let domains = [/* domain objects */];
</script>

{#each domains as domain}
  <EnhancedDomainCard 
    {domain}
    projectId={123}
    on:incrementalUpdate={handleUpdate}
  />
{/each}
```

## WebSocket Integration

Components automatically connect to WebSocket for real-time updates:

```typescript
// WebSocket message handling
websocket.subscribe((message) => {
  if (message?.type === 'task_progress' && 
      message.payload?.task_type === 'incremental_scraping') {
    // Update UI with real-time progress
    handleIncrementalUpdate(message.payload);
  }
});
```

## Configuration Options

### Incremental Scraping Config
```typescript
interface IncrementalScrapingConfig {
  enabled: boolean;                    // Enable/disable incremental scraping
  overlap_days: number;               // Days of overlap with previous runs (0-14)
  auto_schedule: boolean;             // Automatic scheduling
  max_pages_per_run: number;          // Performance limit (50-10000)
  run_frequency_hours: number;        // How often to run (6-168 hours)
  gap_fill_threshold_days: number;    // Minimum gap size to fill (1-60)
}
```

### Coverage Gap Analysis
```typescript
interface CoverageGap {
  id: number;
  domain_id: number;
  gap_start: string;                  // ISO date string
  gap_end: string;                    // ISO date string
  days_missing: number;               // Duration of gap
  priority_score: number;             // 0-10 priority rating
  estimated_pages: number;            // Expected content volume
}
```

## Error Handling

All components include comprehensive error handling:

- **Network errors**: Displayed with retry options
- **Validation errors**: Real-time field validation
- **Permission errors**: Graceful degradation of controls
- **WebSocket disconnections**: Automatic reconnection

## Accessibility

Components follow WCAG 2.1 guidelines:

- **Keyboard navigation**: Full keyboard support
- **Screen readers**: ARIA labels and descriptions
- **Color contrast**: Sufficient contrast ratios
- **Focus management**: Proper focus indicators

## Performance Considerations

- **Lazy loading**: Components load data on-demand
- **Debounced updates**: Configuration changes are debounced
- **Virtual scrolling**: History lists use virtual scrolling for large datasets
- **Caching**: API responses are cached where appropriate

## Testing

Components include comprehensive test coverage:

- **Unit tests**: Individual component functionality
- **Integration tests**: Component interaction
- **E2E tests**: Full user workflows
- **Accessibility tests**: WCAG compliance verification

## Styling

Components use:
- **Tailwind CSS**: Utility-first styling
- **shadcn-svelte**: Consistent design system
- **Lucide icons**: Consistent iconography
- **CSS variables**: Theme customization support

## Browser Support

- **Modern browsers**: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- **WebSocket support**: Required for real-time updates
- **ES2020 features**: Modern JavaScript syntax used

## Future Enhancements

Planned improvements:
- **Advanced analytics**: Detailed performance metrics
- **Custom scheduling**: Complex scheduling rules
- **Batch operations**: Multi-domain operations
- **Export capabilities**: Data export functionality
- **Mobile optimization**: Enhanced mobile experience