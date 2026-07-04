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
	let connState: 'idle' | 'connecting' | 'connected' | 'closed' | 'error' = 'idle';
	let socket: WebSocket | null = null;
	let connectedSessionId: number | null = null;
	let logEl: HTMLDivElement | null = null;
	const MAX_LINES = 300;

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
		const p = msg.payload && typeof msg.payload === 'object' ? msg.payload : msg;

		if (type === 'heartbeat' || type === 'heartbeat_response') return null;

		const url = p.original_url || p.url || p.wayback_url || '';
		const status = String(p.status || p.page_status || '').toLowerCase();
		const stage = p.processing_stage || p.stage || '';

		if (type.includes('cdx') || p.records_found != null || p.total_found != null) {
			const n = p.records_found ?? p.total_found ?? p.total_urls ?? 0;
			return { level: 'info', text: `Discovered ${Number(n).toLocaleString()} archived URLs` };
		}
		if (type.includes('session') || type.includes('stats')) {
			const c = p.completed_urls ?? 0;
			const f = p.failed_urls ?? 0;
			const t = p.total_urls ?? 0;
			return { level: 'info', text: `Progress: ${c}/${t} scraped${f ? `, ${f} failed` : ''}` };
		}
		if (type.includes('stage') && stage) {
			return { level: 'info', text: `${stage}${url ? `: ${url}` : ''}` };
		}
		if (type.includes('page') || url) {
			if (status.includes('fail') || status.includes('error')) {
				const err = p.error_message || p.error || '';
				return { level: 'error', text: `Failed: ${url}${err ? ` — ${err}` : ''}` };
			}
			if (status.includes('complet')) return { level: 'success', text: `Scraped: ${url}` };
			if (status) return { level: 'info', text: `${status}: ${url}` };
			return { level: 'info', text: url };
		}
		if (p.message) return { level: 'info', text: String(p.message) };
		return null;
	}

	function connect(id: number) {
		if (!browser) return;
		disconnect();
		connectedSessionId = id;
		connState = 'connecting';
		try {
			const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			// The API runs on :8000; cookies (host-scoped for localhost) authenticate.
			const url = `${protocol}//${window.location.hostname}:8000/api/v1/ws/scrape/${id}`;
			socket = new WebSocket(url);

			socket.onopen = () => {
				connState = 'connected';
			};
			socket.onmessage = (event) => {
				try {
					const data = JSON.parse(event.data);
					const described = describe(data);
					if (described) push(described.level, described.text);
				} catch {
					// ignore malformed frames
				}
			};
			socket.onerror = () => {
				connState = 'error';
			};
			socket.onclose = () => {
				connState = 'closed';
			};
		} catch (e) {
			connState = 'error';
		}
	}

	function disconnect() {
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

	onDestroy(disconnect);

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
			{:else if active}
				reconnecting…
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
