import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { cubicOut } from 'svelte/easing';
import type { TransitionConfig } from 'svelte/transition';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

type FlyAndScaleParams = {
	y?: number;
	x?: number;
	start?: number;
	duration?: number;
};

export const flyAndScale = (
	node: Element,
	params: FlyAndScaleParams = { y: -8, x: 0, start: 0.95, duration: 150 }
): TransitionConfig => {
	const style = getComputedStyle(node);
	const transform = style.transform === 'none' ? '' : style.transform;

	const scaleConversion = (valueA: number, scaleA: [number, number], scaleB: [number, number]) => {
		const [minA, maxA] = scaleA;
		const [minB, maxB] = scaleB;

		const percentage = (valueA - minA) / (maxA - minA);
		const valueB = percentage * (maxB - minB) + minB;

		return valueB;
	};

	const styleToString = (style: Record<string, number | string | undefined>): string => {
		return Object.keys(style).reduce((str, key) => {
			if (style[key] === undefined) return str;
			return str + `${key}:${style[key]};`;
		}, '');
	};

	return {
		duration: params.duration ?? 200,
		delay: 0,
		css: (t) => {
			const y = scaleConversion(t, [0, 1], [params.y ?? 5, 0]);
			const x = scaleConversion(t, [0, 1], [params.x ?? 0, 0]);
			const scale = scaleConversion(t, [0, 1], [params.start ?? 0.95, 1]);

			return styleToString({
				transform: `${transform} translate3d(${x}px, ${y}px, 0) scale(${scale})`,
				opacity: t
			});
		},
		easing: cubicOut
	};
};

// Date formatting utilities
export function formatDate(date: Date | string, options?: Intl.DateTimeFormatOptions) {
	const d = typeof date === 'string' ? new Date(date) : date;
	return d.toLocaleDateString('en-US', {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		...options
	});
}

export function formatDateTime(date: Date | string) {
	const d = typeof date === 'string' ? new Date(date) : date;
	return d.toLocaleString('en-US', {
		year: 'numeric',
		month: 'short',
		day: 'numeric',
		hour: '2-digit',
		minute: '2-digit'
	});
}

export function formatRelativeTime(date: Date | string) {
	const d = typeof date === 'string' ? new Date(date) : date;
	const now = new Date();
	const diffInMs = now.getTime() - d.getTime();
	const diffInMinutes = Math.floor(diffInMs / (1000 * 60));
	const diffInHours = Math.floor(diffInMinutes / 60);
	const diffInDays = Math.floor(diffInHours / 24);

	if (diffInMinutes < 1) return 'Just now';
	if (diffInMinutes < 60) return `${diffInMinutes}m ago`;
	if (diffInHours < 24) return `${diffInHours}h ago`;
	if (diffInDays < 7) return `${diffInDays}d ago`;
	
	return formatDate(d);
}

// Number formatting utilities
export function formatNumber(num: number, options?: Intl.NumberFormatOptions) {
	return new Intl.NumberFormat('en-US', options).format(num);
}

export function formatBytes(bytes: number, decimals = 2) {
	if (!+bytes) return '0 Bytes';

	const k = 1024;
	const dm = decimals < 0 ? 0 : decimals;
	const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

	const i = Math.floor(Math.log(bytes) / Math.log(k));

	return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function formatPercentage(value: number, total: number, decimals = 1) {
	if (total === 0) return '0%';
	const percentage = (value / total) * 100;
	return `${percentage.toFixed(decimals)}%`;
}

// URL utilities
export function getApiUrl(path: string) {
	const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
	return `${baseUrl}${path}`;
}

// CSRF/session-aware fetch utilities
let cachedCsrfToken: string | null = null;

async function refreshCsrfToken(): Promise<string | null> {
    try {
        const res = await fetch(getApiUrl('/api/v1/csrf-token'), {
            method: 'GET',
            credentials: 'include'
        });
        // Prefer header set by middleware (session-linked HMAC token)
        const tokenFromHeader = res.headers.get('X-CSRF-Token');
        if (tokenFromHeader) {
            cachedCsrfToken = tokenFromHeader;
            return cachedCsrfToken;
        }
        // Fallback: keep existing cache if any
        return cachedCsrfToken;
    } catch (e) {
        return cachedCsrfToken;
    }
}

function isProtectedMethod(method?: string): boolean {
    const m = (method || 'GET').toUpperCase();
    return m === 'POST' || m === 'PUT' || m === 'PATCH' || m === 'DELETE';
}

function isCsrfExempt(path: string): boolean {
    // Keep in sync with backend exemptions
    return path.endsWith('/api/v1/auth/login') || path.endsWith('/api/v1/health');
}

export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const urlString = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
    const headers = new Headers(init.headers || {});

    // Always send cookies for session auth
    const requestInit: RequestInit = { ...init, headers, credentials: 'include' };

    // Attach CSRF token for state-changing requests
    if (isProtectedMethod(init.method) && !isCsrfExempt(urlString)) {
        if (!cachedCsrfToken) {
            await refreshCsrfToken();
        }
        if (cachedCsrfToken && !headers.has('X-CSRF-Token')) {
            headers.set('X-CSRF-Token', cachedCsrfToken);
        }
    }

    let response = await fetch(input, requestInit);

    // Update cached token from any response header
    const headerToken = response.headers.get('X-CSRF-Token');
    if (headerToken) {
        cachedCsrfToken = headerToken;
    }

    // If CSRF failed once, refresh token and retry once
    if (response.status === 403) {
        try {
            const data = await response.clone().json().catch(() => ({} as any));
            if ((data as any)?.code === 'csrf_token_invalid') {
                await refreshCsrfToken();
                if (cachedCsrfToken) {
                    headers.set('X-CSRF-Token', cachedCsrfToken);
                }
                response = await fetch(input, requestInit);
            }
        } catch {
            // ignore
        }
    }

    return response;
}

// Validation utilities
export function isValidUrl(url: string) {
	try {
		new URL(url);
		return true;
	} catch {
		return false;
	}
}

export function isValidDomain(domain: string) {
	const domainRegex = /^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/;
	return domainRegex.test(domain);
}

// Debounce utility
export function debounce<T extends (...args: any[]) => any>(
	func: T,
	wait: number
): (...args: Parameters<T>) => void {
	let timeout: NodeJS.Timeout;
	return function executedFunction(...args: Parameters<T>) {
		const later = () => {
			clearTimeout(timeout);
			func(...args);
		};
		clearTimeout(timeout);
		timeout = setTimeout(later, wait);
	};
}

// Generate random ID
export function generateId(length = 8) {
	return Math.random().toString(36).substring(2, length + 2);
}