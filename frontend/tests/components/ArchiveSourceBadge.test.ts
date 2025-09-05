/**
 * Unit tests for ArchiveSourceBadge component
 * 
 * Tests proper rendering and display of archive source badges
 * with correct styling and content for each archive source type.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import ArchiveSourceBadge from '$lib/components/project/ArchiveSourceBadge.svelte';
import type { ArchiveSource, ArchiveSourceMetrics } from '$lib/types/scraping';

// Mock Lucide Svelte icons
vi.mock('lucide-svelte', () => ({
  Archive: () => 'mocked-archive-icon',
  Globe: () => 'mocked-globe-icon', 
  Zap: () => 'mocked-zap-icon',
  Activity: () => 'mocked-activity-icon'
}));

describe('ArchiveSourceBadge', () => {
  it('renders Wayback Machine badge correctly', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      showTooltip: false
    });

    const badge = screen.getByText('Wayback');
    expect(badge).toBeInTheDocument();
    
    // Verify proper styling classes are applied
    const container = badge.closest('div');
    expect(container).toHaveClass('border-blue-200');
    expect(container).toHaveClass('bg-blue-50');
  });

  it('renders Common Crawl badge correctly', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'commoncrawl' as ArchiveSource,
      showTooltip: false
    });

    const badge = screen.getByText('CommonCrawl');
    expect(badge).toBeInTheDocument();
    
    // Verify proper styling classes are applied
    const container = badge.closest('div');
    expect(container).toHaveClass('border-green-200');
    expect(container).toHaveClass('bg-green-50');
  });

  it('renders Hybrid badge correctly', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'hybrid' as ArchiveSource,
      showTooltip: false
    });

    const badge = screen.getByText('Hybrid');
    expect(badge).toBeInTheDocument();
    
    // Verify proper styling classes are applied  
    const container = badge.closest('div');
    expect(container).toHaveClass('border-purple-200');
    expect(container).toHaveClass('bg-purple-50');
  });

  it('shows full labels when size is medium or large', () => {
    const { rerender } = render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      size: 'md',
      showTooltip: false
    });

    expect(screen.getByText('Wayback Machine')).toBeInTheDocument();

    rerender({
      archiveSource: 'commoncrawl' as ArchiveSource,
      size: 'lg',
      showTooltip: false
    });

    expect(screen.getByText('Common Crawl')).toBeInTheDocument();
  });

  it('shows short labels when size is small', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      size: 'sm',
      showTooltip: false
    });

    expect(screen.getByText('Wayback')).toBeInTheDocument();
  });

  it('displays fallback indicator for hybrid mode with fallback enabled', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'hybrid' as ArchiveSource,
      fallbackEnabled: true,
      showTooltip: false
    });

    // Should show the activity icon for fallback enabled
    expect(screen.getByText('Hybrid')).toBeInTheDocument();
    
    // Check for fallback indicator (Activity icon should be rendered)
    const container = screen.getByText('Hybrid').closest('div');
    expect(container?.innerHTML).toContain('mocked-activity-icon');
  });

  it('does not display fallback indicator for non-hybrid modes', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      fallbackEnabled: true,
      showTooltip: false
    });

    const container = screen.getByText('Wayback').closest('div');
    expect(container?.innerHTML).not.toContain('mocked-activity-icon');
  });

  it('displays metrics information when provided', () => {
    const mockMetrics: ArchiveSourceMetrics = {
      success_rate: 95.5,
      avg_response_time_ms: 250,
      circuit_breaker_status: 'closed',
      total_requests: 1000,
      failed_requests: 45
    };

    render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      metrics: mockMetrics,
      showTooltip: true
    });

    const container = screen.getByText('Wayback').closest('div');
    const tooltip = container?.getAttribute('title');
    
    expect(tooltip).toContain('Success Rate: 95.5%');
    expect(tooltip).toContain('Avg Response: 250ms');
  });

  it('displays circuit breaker status when not closed', () => {
    const mockMetrics: ArchiveSourceMetrics = {
      success_rate: 75.0,
      avg_response_time_ms: 500,
      circuit_breaker_status: 'open',
      total_requests: 100,
      failed_requests: 25
    };

    render(ArchiveSourceBadge, {
      archiveSource: 'commoncrawl' as ArchiveSource,
      metrics: mockMetrics,
      showTooltip: false
    });

    // Should display a status indicator dot
    const container = screen.getByText('CommonCrawl').closest('div');
    expect(container?.querySelector('.bg-red-500')).toBeInTheDocument();
  });

  it('displays half-open circuit breaker status correctly', () => {
    const mockMetrics: ArchiveSourceMetrics = {
      success_rate: 85.0,
      avg_response_time_ms: 350,
      circuit_breaker_status: 'half-open',
      total_requests: 200,
      failed_requests: 30
    };

    render(ArchiveSourceBadge, {
      archiveSource: 'hybrid' as ArchiveSource,
      metrics: mockMetrics,
      showTooltip: false
    });

    // Should display a yellow status indicator dot for half-open
    const container = screen.getByText('Hybrid').closest('div');
    expect(container?.querySelector('.bg-yellow-500')).toBeInTheDocument();
  });

  it('applies interactive styles when interactive prop is true', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      interactive: true,
      showTooltip: false
    });

    const container = screen.getByText('Wayback').closest('div');
    expect(container).toHaveAttribute('role', 'button');
    expect(container).toHaveAttribute('tabindex', '0');
    expect(container).toHaveClass('cursor-pointer');
  });

  it('does not apply interactive styles when interactive prop is false', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      interactive: false,
      showTooltip: false
    });

    const container = screen.getByText('Wayback').closest('div');
    expect(container).not.toHaveAttribute('role');
    expect(container).not.toHaveAttribute('tabindex');
    expect(container).not.toHaveClass('cursor-pointer');
  });

  it('generates proper tooltip content for hybrid mode with fallback', () => {
    render(ArchiveSourceBadge, {
      archiveSource: 'hybrid' as ArchiveSource,
      fallbackEnabled: true,
      showTooltip: true
    });

    const container = screen.getByText('Hybrid').closest('div');
    const tooltip = container?.getAttribute('title');
    
    expect(tooltip).toContain('Archive Source: Hybrid Mode');
    expect(tooltip).toContain('Fallback enabled for maximum reliability');
  });

  it('handles all archive source enum values correctly', () => {
    const archiveSources: Array<{ source: ArchiveSource; expectedText: string }> = [
      { source: 'wayback', expectedText: 'Wayback' },
      { source: 'commoncrawl', expectedText: 'CommonCrawl' }, 
      { source: 'hybrid', expectedText: 'Hybrid' }
    ];

    archiveSources.forEach(({ source, expectedText }) => {
      const { unmount } = render(ArchiveSourceBadge, {
        archiveSource: source,
        size: 'sm',
        showTooltip: false
      });

      expect(screen.getByText(expectedText)).toBeInTheDocument();
      unmount();
    });
  });

  it('applies correct size classes for different size props', () => {
    const { rerender } = render(ArchiveSourceBadge, {
      archiveSource: 'wayback' as ArchiveSource,
      size: 'sm',
      showTooltip: false
    });

    let container = screen.getByText('Wayback').closest('div');
    expect(container).toHaveClass('text-xs', 'px-1.5', 'py-0.5');

    rerender({
      archiveSource: 'wayback' as ArchiveSource,
      size: 'md',
      showTooltip: false
    });

    container = screen.getByText('Wayback Machine').closest('div');
    expect(container).toHaveClass('text-sm', 'px-2', 'py-1');

    rerender({
      archiveSource: 'wayback' as ArchiveSource,
      size: 'lg', 
      showTooltip: false
    });

    container = screen.getByText('Wayback Machine').closest('div');
    expect(container).toHaveClass('text-base', 'px-3', 'py-1.5');
  });
});