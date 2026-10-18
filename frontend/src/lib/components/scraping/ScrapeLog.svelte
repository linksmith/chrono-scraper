<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { browser } from '$app/environment';
	import { Card, CardContent } from '$lib/components/ui/card';
	import { Badge } from '$lib/components/ui/badge';

	// The scrape-progress socket is keyed by session id. `active` tells us whether
	// a scrape is currently running so we can show the right idle/live state.
	export let sessionId: number | null = null;
	export let active = false;

	interface LogLine {
		t: string;
		level: 'info' | 'success' | 'warn' | 'error';
		text: string;
	}

	let lines: LogLine[] = [];
	let connState: 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed' = 'idle';
	let socket: WebSocket | null = null;
	let connectedSessionId: number | null = null;
	let logEl: HTMLDivElement | null = null;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
	let reconnectAttempts = 0;
	let lastProgressText = '';
	let destroyed = false;
	const MAX_LINES = 300;
	const HEARTBEAT_MS = 20_000; // server reaps connections idle >60s

	function stamp(): string {
		// Client-side timestamp — server events don't all carry one.
		const d = new Date();
		return d.toLocaleTimeString('en-US', { hour12: false });
	}

	async function push(level: LogLine['level'], text: string) {
		lines = [...lines, { t: stamp(), level, text }].slice(-MAX_LINES);
		await tick();
		if (logEl) logEl.scrollTop = logEl.scrollHeight;
	}

	// Turn an arbitrary server event into a readable line. Resilient to schema
	// differences across CDX-discovery / page-progress / session-stats events.
	function describe(msg: any): { level: LogLine['level']; text: string } | null {
		if (!msg || typeof msg !== 'object') return null;
		const type = String(msg.type || msg.event_type || msg.message_type || '').toLowerCase();
		const p = msg.payload && typeof msg.payload === 'object' ? msg.payload : msg.data && typeof msg.data === 'object' ? msg.data : msg;

		if (
			type === 'heartbeat' ||
			type === 'heartbeat_response' ||
			type === 'ping' ||
			type === 'pong' ||
			type === 'connection_established'
		) {
			return null;
		}

		// A frame whose payload is just an error string (e.g. progress query failed)
		if (p.error && typeof p.error === 'string' && !p.page_url && !p.url) {
			return { level: 'warn', text: p.error };
		}

		const url = p.original_url || p.page_url || p.url || p.wayback_url || '';
		const status = String(p.status || p.page_status || '').toLowerCase();
		const stage = p.processing_stage || p.stage || '';

		if (type.includes('cdx') || p.records_found != null || p.total_found != null) {
			const n = p.records_found ?? p.total_found ?? p.results_found ?? p.total_urls ?? 0;
			return { level: 'info', text: `Discovered ${Number(n).toLocaleString()} archived URLs` };
		}
		// Session-level progress: periodic progress_update / initial_progress
		// frames and worker session_stats events. Checked before page events so
		// 'page_progress' (which contains "progress") isn't swallowed — it has a
		// URL and falls through to the page branch below.
		if (
			!url &&
			(type === 'progress_update' ||
				type === 'initial_progress' ||
				type.includes('session') ||
				type.includes('stats')) &&
			p.completed_urls != null
		) {
			const c = p.completed_urls ?? 0;
			const f = p.failed_urls ?? 0;
			const t = p.total_urls ?? 0;
			const rate = p.pages_per_minute ? `, ${Number(p.pages_per_minute).toFixed(1)}/min` : '';
			const text = `Progress: ${c}/${t} scraped${f ? `, ${f} failed` : ''}${rate}`;
			if (text === lastProgressText) return null; // don't spam identical lines
			lastProgressText = text;
			return { level: 'info', text };
		}
		if (type.includes('stage') && stage) {
			return { level: 'info', text: `${stage}${url ? `: ${url}` : ''}` };
		}
		if (type.includes('page') || url) {
			if (status.includes('fail') || status.includes('error')) {
				const err = p.error_message || p.error || '';
				return { level: 'error', text: `Failed: ${url}${err ? ` — ${err}` : ''}` };
			}
			if (status.includes('skip')) {
				const err = p.error_message || '';
				return { level: 'warn', text: `Skipped: ${url}${err ? ` — ${err}` : ''}` };
			}
			if (status.includes('complet')) return { level: 'success', text: `Scraped: ${url}` };
			if (status) return { level: 'info', text: `${status}: ${url}` };
			return { level: 'info', text: url };
		}
		if (p.message) return { level: 'info', text: String(p.message) };
		return null;
	}

	function clearTimers() {
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		if (heartbeatTimer) {
			clearInterval(heartbeatTimer);
			heartbeatTimer = null;
		}
	}

	function scheduleReconnect(id: number) {
		if (destroyed || reconnectTimer || id !== connectedSessionId) return;
		connState = 'reconnecting';
		// Exponential backoff with jitter, capped at 15s.
		const delay = Math.min(15_000, 1000 * 2 ** reconnectAttempts) + Math.random() * 500;
		reconnectAttempts += 1;
		reconnectTimer = setTimeout(() => {
			reconnectTimer = null;
			if (!destroyed && id === connectedSessionId) openSocket(id);
		}, delay);
	}

	function openSocket(id: number) {
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		// Same-origin: the dev server proxies /api/v1/ws to the backend (see
		// vite.config.ts), so this works regardless of whether port 8000 is
		// reachable from the browser's network, and cookies flow naturally.
		const url = `${protocol}//${window.location.host}/api/v1/ws/scrape/${id}`;
		connState = reconnectAttempts > 0 ? 'reconnecting' : 'connecting';
		let ws: WebSocket;
		try {
			ws = new WebSocket(url);
		} catch {
			scheduleReconnect(id);
			return;
		}
		socket = ws;

		ws.onopen = () => {
			if (socket !== ws) return;
			connState = 'connected';
			reconnectAttempts = 0;
			// The server reaps connections without client liveness within 60s.
			if (heartbeatTimer) clearInterval(heartbeatTimer);
			heartbeatTimer = setInterval(() => {
				if (ws.readyState === WebSocket.OPEN) {
					ws.send(JSON.stringify({ type: 'ping' }));
				}
			}, HEARTBEAT_MS);
		};
		ws.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data);
				const described = describe(data);
				if (described) push(described.level, described.text);
			} catch {
				// ignore malformed frames
			}
		};
		ws.onclose = () => {
			// A stale socket (superseded by a newer connect) must not touch state.
			if (socket !== ws) return;
			if (heartbeatTimer) {
				clearInterval(heartbeatTimer);
				heartbeatTimer = null;
			}
			socket = null;
			if (!destroyed && connectedSessionId === id) scheduleReconnect(id);
			else connState = 'closed';
		};
		// onerror is always followed by onclose; reconnect is handled there.
	}

	function connect(id: number) {
		if (!browser) return;
		disconnect();
		connectedSessionId = id;
		reconnectAttempts = 0;
		lastProgressText = '';
		openSocket(id);
	}

	function disconnect() {
		clearTimers();
		connectedSessionId = null;
		if (socket) {
			try {
				socket.close(1000, 'component cleanup');
			} catch {
				/* noop */
			}
			socket = null;
		}
	}

	// (Re)connect whenever the target session changes.
	$: if (browser && sessionId && sessionId !== connectedSessionId) {
		connect(sessionId);
	}

	onDestroy(() => {
		destroyed = true;
		disconnect();
	});

	const levelClass: Record<LogLine['level'], string> = {
		info: 'text-muted-foreground',
		success: 'text-emerald-600',
		warn: 'text-amber-600',
		error: 'text-destructive'
	};
</script>

<div class="space-y-2">
	<div class="flex items-center justify-between">
		<h2 class="text-sm font-semibold text-muted-foreground">Live log</h2>
		<Badge variant={connState === 'connected' ? 'secondary' : 'outline'} class="text-xs">
			{#if connState === 'connected'}
				connected
			{:else if connState === 'connecting'}
				connecting…
			{:else if connState === 'reconnecting'}
				reconnecting…
			{:else if active}
				waiting…
			{:else}
				idle
			{/if}
		</Badge>
	</div>
	<Card>
		<CardContent class="p-0">
			<div
				bind:this={logEl}
				class="h-56 overflow-y-auto p-3 font-mono text-xs leading-relaxed"
			>
				{#if lines.length === 0}
					<p class="text-muted-foreground">
						{#if !sessionId}
							No scrape session yet.
						{:else if active}
							Waiting for activity…
						{:else}
							No live activity. Progress and results are shown above.
						{/if}
					</p>
				{:else}
					{#each lines as line}
						<div class="flex gap-2">
							<span class="shrink-0 text-muted-foreground/60">{line.t}</span>
							<span class={levelClass[line.level]}>{line.text}</span>
						</div>
					{/each}
				{/if}
			</div>
		</CardContent>
	</Card>
</div>
