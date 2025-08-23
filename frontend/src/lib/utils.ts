/**
 * Utility functions for the frontend application
 */

import { browser } from '$app/environment';
import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Combines class names with clsx and tailwind-merge
 */
export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

/**
 * Get the full API URL for a given endpoint
 */
export function getApiUrl(endpoint: string): string {
    // For browser environment, ALWAYS use relative URLs that proxy through Vite
    // This fixes the CORS issue where Docker API_BASE_URL was overriding browser behavior
    if (typeof window !== 'undefined') {
        console.log(`[getApiUrl] Browser context: returning endpoint ${endpoint}`);
        return endpoint;
    }
    
    // For SSR only, use the backend URL directly (internal Docker network)
    const baseUrl = process.env.API_BASE_URL || 'http://localhost:8000';
    console.log(`[getApiUrl] SSR context: returning ${baseUrl}${endpoint}`);
    return `${baseUrl}${endpoint}`;
}

// CSRF/session-aware fetch utilities for session auth
let cachedCsrfToken: string | null = null;

async function refreshCsrfToken(): Promise<string | null> {
    try {
        const endpoint = '/api/v1/csrf-token';
        const url = getApiUrl(endpoint);
        console.log(`[refreshCsrfToken] Using URL: ${url}`);
        
        const res = await fetch(url, {
            method: 'GET',
            credentials: 'include'
        });
        const tokenFromHeader = res.headers.get('X-CSRF-Token');
        if (tokenFromHeader) {
            cachedCsrfToken = tokenFromHeader;
            return cachedCsrfToken;
        }
        return cachedCsrfToken;
    } catch {
        return cachedCsrfToken;
    }
}

function isProtectedMethod(method?: string): boolean {
    const m = (method || 'GET').toUpperCase();
    return m === 'POST' || m === 'PUT' || m === 'PATCH' || m === 'DELETE';
}

function isCsrfExempt(path: string): boolean {
    return path.endsWith('/api/v1/auth/login') || path.endsWith('/api/v1/health');
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const urlString = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
    console.log(`[apiFetch] Input: ${input}, URL String: ${urlString}, Type: ${typeof input}`);
    
    const headers = new Headers(init.headers || {});
    const requestInit: RequestInit = { ...init, headers, credentials: 'include' };

    if (isProtectedMethod(init.method) && !isCsrfExempt(urlString)) {
        if (!cachedCsrfToken) {
            await refreshCsrfToken();
        }
        if (cachedCsrfToken && !headers.has('X-CSRF-Token')) {
            headers.set('X-CSRF-Token', cachedCsrfToken);
        }
    }

    console.log(`[apiFetch] About to fetch: ${input} with init:`, requestInit);
    
    // Use the input URL directly - Vite proxy will handle /api/* routes automatically
    let response = await fetch(input, requestInit);
    const headerToken = response.headers.get('X-CSRF-Token');
    if (headerToken) {
        cachedCsrfToken = headerToken;
    }
    if (response.status === 403) {
        try {
            const data = await response.clone().json().catch(() => ({} as any));
            if ((data as any)?.code === 'csrf_token_invalid') {
                await refreshCsrfToken();
                if (cachedCsrfToken) {
                    headers.set('X-CSRF-Token', cachedCsrfToken);
                }
                response = await fetch(finalUrl, requestInit);
            }
        } catch {
            // ignore
        }
    }
    return response;
}

/**
 * Format a date for display
 */
export function formatDate(date: string | Date): string {
    const d = new Date(date);
    return d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Format a number with thousands separators
 */
export function formatNumber(num: number): string {
    return new Intl.NumberFormat('en-US').format(num);
}

/**
 * Truncate text to a given length
 */
export function truncateText(text: string, maxLength: number): string {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength - 3) + '...';
}

/**
 * Get the initials from a full name
 */
export function getInitials(name: string): string {
    return name
        .split(' ')
        .map(word => word.charAt(0).toUpperCase())
        .join('')
        .substring(0, 2);
}

/**
 * Check if a string is a valid email address
 */
export function isValidEmail(email: string): boolean {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

/**
 * Generate a random string of given length
 */
export function generateRandomString(length: number): string {
    const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
        result += characters.charAt(Math.floor(Math.random() * characters.length));
    }
    return result;
}

/**
 * Debounce function to limit how often a function can be called
 */
export function debounce<T extends (...args: any[]) => any>(
    func: T,
    wait: number
): (...args: Parameters<T>) => void {
    let timeout: NodeJS.Timeout;
    return (...args: Parameters<T>) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
}

/**
 * Get the status badge color for different statuses
 */
export function getStatusColor(status: string): string {
    const colors: Record<string, string> = {
        active: 'bg-green-100 text-green-800',
        pending: 'bg-yellow-100 text-yellow-800',
        approved: 'bg-green-100 text-green-800',
        denied: 'bg-red-100 text-red-800',
        expired: 'bg-gray-100 text-gray-800',
        completed: 'bg-blue-100 text-blue-800',
        failed: 'bg-red-100 text-red-800',
        running: 'bg-purple-100 text-purple-800',
        queued: 'bg-gray-100 text-gray-800'
    };
    
    return colors[status.toLowerCase()] || 'bg-gray-100 text-gray-800';
}

/**
 * Calculate the percentage for progress bars
 */
export function calculatePercentage(current: number, total: number): number {
    if (total === 0) return 0;
    return Math.round((current / total) * 100);
}

/**
 * Format file size in human readable format
 */
export function formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Alias for formatFileSize for consistency
 */
export function getFileSize(bytes: number): string {
    return formatFileSize(bytes);
}

/**
 * Get relative time string (e.g., "2 hours ago")
 */
export function getRelativeTime(date: string | Date): string {
    const now = new Date();
    const past = new Date(date);
    const diffInSeconds = Math.floor((now.getTime() - past.getTime()) / 1000);
    
    if (diffInSeconds < 60) return 'just now';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)} minutes ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)} hours ago`;
    if (diffInSeconds < 2592000) return `${Math.floor(diffInSeconds / 86400)} days ago`;
    if (diffInSeconds < 31536000) return `${Math.floor(diffInSeconds / 2592000)} months ago`;
    
    return `${Math.floor(diffInSeconds / 31536000)} years ago`;
}

/**
 * Format date and time for display
 */
export function formatDateTime(date: string | Date): string {
    const d = new Date(date);
    return d.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

/**
 * Parse Wayback Machine timestamp format (YYYYMMDDHHMMSS) to Date
 * Example: '20230607112257' or '20240706032712'
 */
export function parseWaybackTimestamp(timestamp: string): Date | null {
    if (!timestamp || timestamp.length !== 14) {
        return null;
    }
    
    const year = parseInt(timestamp.substring(0, 4));
    const month = parseInt(timestamp.substring(4, 6)) - 1; // Month is 0-indexed
    const day = parseInt(timestamp.substring(6, 8));
    const hour = parseInt(timestamp.substring(8, 10));
    const minute = parseInt(timestamp.substring(10, 12));
    const second = parseInt(timestamp.substring(12, 14));
    
    const date = new Date(year, month, day, hour, minute, second);
    
    // Check if the date is valid
    if (isNaN(date.getTime())) {
        return null;
    }
    
    return date;
}

/**
 * Parse unix timestamp or Wayback Machine timestamp format
 */
export function parseTimestamp(timestamp: string | number): Date | null {
    if (!timestamp) {
        return null;
    }
    
    // If it's a number or looks like a unix timestamp (10 or 13 digits)
    if (typeof timestamp === 'number' || /^\d{10,13}$/.test(timestamp.toString())) {
        const ts = typeof timestamp === 'string' ? parseInt(timestamp) : timestamp;
        // If it's 10 digits, it's seconds; if 13 digits, it's milliseconds
        const date = ts.toString().length === 10 
            ? new Date(ts * 1000) 
            : new Date(ts);
        return isNaN(date.getTime()) ? null : date;
    }
    
    // If it's 14 digits, try Wayback Machine format
    if (typeof timestamp === 'string' && /^\d{14}$/.test(timestamp)) {
        return parseWaybackTimestamp(timestamp);
    }
    
    // Try parsing as regular date string
    const date = new Date(timestamp);
    return isNaN(date.getTime()) ? null : date;
}