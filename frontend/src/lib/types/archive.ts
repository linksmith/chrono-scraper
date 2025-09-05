/**
 * Archive source configuration types for Chrono Scraper
 */

export type ArchiveSource = 'wayback' | 'commoncrawl' | 'hybrid';

export type FallbackStrategy = 'sequential' | 'parallel';

export interface ArchiveConfig {
  /** Strategy for fallback between archive sources */
  fallback_strategy: FallbackStrategy;
  
  /** Number of consecutive failures before switching to fallback archive */
  circuit_breaker_threshold: number;
  
  /** Delay in seconds before attempting fallback (0 for immediate) */
  fallback_delay: number;
  
  /** Time in seconds to wait before retrying a previously failed archive */
  recovery_time: number;
}

export interface ArchiveConfiguration {
  /** Selected archive source */
  archive_source: ArchiveSource;
  
  /** Whether automatic fallback is enabled */
  fallback_enabled: boolean;
  
  /** Advanced configuration for hybrid mode */
  archive_config: ArchiveConfig;
}

export interface ProjectFormData {
  // Project basics
  projectName: string;
  description: string;
  
  // Targets
  targets: ProjectTarget[];
  
  // Archive configuration
  archive_source: ArchiveSource;
  fallback_enabled: boolean;
  archive_config: ArchiveConfig;
  
  // Processing options
  auto_start_scraping: boolean;
  enable_attachment_download: boolean;
  extract_entities: boolean;
  
  // AI options
  langextractEnabled: boolean;
  langextractProvider: string;
  langextractModel: string;
  langextractCostEstimate: any;
}

export interface ProjectTarget {
  value: string;
  type: 'domain' | 'url';
  from_date?: string;
  to_date?: string;
}

export const DEFAULT_ARCHIVE_CONFIG: ArchiveConfig = {
  fallback_strategy: 'sequential',
  circuit_breaker_threshold: 3,
  fallback_delay: 2.0,
  recovery_time: 300
};

export const ARCHIVE_SOURCE_OPTIONS = [
  {
    value: 'wayback' as ArchiveSource,
    title: 'Wayback Machine (Internet Archive)',
    description: 'Most comprehensive coverage with decades of historical data. Ideal for finding older content and complete historical records.',
    icon: 'globe',
    color: 'blue'
  },
  {
    value: 'commoncrawl' as ArchiveSource,
    title: 'Common Crawl',
    description: 'Monthly web snapshots with faster queries and good coverage of recent content. Better performance for large-scale operations.',
    icon: 'database',
    color: 'green'
  },
  {
    value: 'hybrid' as ArchiveSource,
    title: 'Hybrid (Recommended)',
    description: 'Automatic fallback between archives for maximum reliability. Tries Common Crawl first for speed, falls back to Wayback Machine for comprehensive coverage.',
    icon: 'layers',
    color: 'emerald',
    recommended: true
  }
] as const;

export function getArchiveSourceName(source: ArchiveSource): string {
  switch (source) {
    case 'wayback': return 'Wayback Machine';
    case 'commoncrawl': return 'Common Crawl';
    case 'hybrid': return 'Hybrid Mode';
    default: return source;
  }
}

export function formatDelay(delay: number): string {
  return delay < 1 ? `${delay * 1000}ms` : `${delay}s`;
}

export function formatTime(seconds: number): string {
  if (seconds >= 3600) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  } else if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  } else {
    return `${seconds}s`;
  }
}

export function validateArchiveConfig(config: ArchiveConfig): string[] {
  const errors: string[] = [];
  
  if (config.circuit_breaker_threshold < 1 || config.circuit_breaker_threshold > 10) {
    errors.push('Error threshold must be between 1 and 10');
  }
  
  if (config.fallback_delay < 0 || config.fallback_delay > 30) {
    errors.push('Fallback delay must be between 0 and 30 seconds');
  }
  
  if (config.recovery_time < 30 || config.recovery_time > 3600) {
    errors.push('Recovery time must be between 30 and 3600 seconds');
  }
  
  return errors;
}