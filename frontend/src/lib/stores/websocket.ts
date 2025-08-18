/**
 * WebSocket store with automatic reconnection and message queuing
 * Following best practices for production-ready WebSocket client
 */
import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import { page } from '$app/stores';
import { authStore } from './auth';

export enum ConnectionState {
  DISCONNECTED = 'disconnected',
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  RECONNECTING = 'reconnecting',
  ERROR = 'error'
}

export enum MessageType {
  HEARTBEAT = 'heartbeat',
  TASK_PROGRESS = 'task_progress',
  PROJECT_UPDATE = 'project_update',
  USER_MESSAGE = 'user_message',
  ERROR = 'error',
  RECONNECT = 'reconnect',
  BATCH = 'batch'
}

interface WebSocketMessage {
  id?: string;
  type: MessageType | string;
  payload?: any;
  timestamp: string;
}

interface QueuedMessage {
  id: string;
  message: any;
  timestamp: number;
  retryCount: number;
}

interface WebSocketState {
  socket: WebSocket | null;
  connectionState: ConnectionState;
  lastError: string | null;
  reconnectAttempts: number;
  messages: WebSocketMessage[];
  subscriptions: Set<string>;
  messageQueue: QueuedMessage[];
  lastSyncTime: string | null;
}

const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds
const HEARTBEAT_INTERVAL = 30000; // 30 seconds
const MESSAGE_HISTORY_LIMIT = 100;

function getReconnectDelay(attempts: number): number {
  // Exponential backoff with jitter
  const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, attempts), MAX_RECONNECT_DELAY);
  const jitter = Math.random() * 0.3 * delay;
  return delay + jitter;
}

function generateId(): string {
  return crypto.randomUUID();
}

function createWebSocketStore() {
  const { subscribe, set, update } = writable<WebSocketState>({
    socket: null,
    connectionState: ConnectionState.DISCONNECTED,
    lastError: null,
    reconnectAttempts: 0,
    messages: [],
    subscriptions: new Set(),
    messageQueue: [],
    lastSyncTime: null
  });

  let reconnectTimeout: NodeJS.Timeout | null = null;
  let heartbeatInterval: NodeJS.Timeout | null = null;
  let currentUrl: string | null = null;
  let currentToken: string | null = null;

  function getReconnectDelay(attempts: number): number {
    const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, attempts), MAX_RECONNECT_DELAY);
    const jitter = Math.random() * 0.3 * delay;
    return delay + jitter;
  }

  function startHeartbeat(socket: WebSocket) {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
    }
    
    heartbeatInterval = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        const heartbeat = {
          type: MessageType.HEARTBEAT,
          timestamp: new Date().toISOString()
        };
        socket.send(JSON.stringify(heartbeat));
      }
    }, HEARTBEAT_INTERVAL);
  }

  function stopHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
      heartbeatInterval = null;
    }
  }

  function handleMessage(event: MessageEvent) {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      
      update(state => {
        const newMessages = [...state.messages, message].slice(-MESSAGE_HISTORY_LIMIT);
        const newState = { ...state, messages: newMessages, lastSyncTime: message.timestamp };
        
        // Handle different message types
        switch (message.type) {
          case MessageType.HEARTBEAT:
            // Respond to server heartbeat
            if (state.socket && state.socket.readyState === WebSocket.OPEN) {
              state.socket.send(JSON.stringify({
                type: 'heartbeat_response',
                timestamp: new Date().toISOString()
              }));
            }
            break;
            
          case MessageType.BATCH:
            // Handle batch messages
            if (message.payload?.messages) {
              message.payload.messages.forEach((batchedMessage: WebSocketMessage) => {
                dispatchCustomEvent('websocket-message', batchedMessage);
              });
            }
            break;
            
          default:
            // Dispatch custom event for components to handle
            dispatchCustomEvent('websocket-message', message);
        }
        
        return newState;
      });
    } catch (error) {
      console.error('Error parsing WebSocket message:', error, event.data);
    }
  }

  function dispatchCustomEvent(eventName: string, detail: any) {
    if (browser && window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent(eventName, { detail }));
    }
  }

  function sendQueuedMessages(socket: WebSocket) {
    update(state => {
      const failedMessages: QueuedMessage[] = [];
      
      for (const queuedMessage of state.messageQueue) {
        try {
          socket.send(JSON.stringify(queuedMessage.message));
        } catch (error) {
          console.error('Failed to send queued message:', error);
          if (queuedMessage.retryCount < 3) {
            failedMessages.push({
              ...queuedMessage,
              retryCount: queuedMessage.retryCount + 1
            });
          }
        }
      }
      
      return { ...state, messageQueue: failedMessages };
    });
  }

  function attemptReconnection() {
    if (!currentUrl || !currentToken) return;
    
    update(state => {
      if (state.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        return {
          ...state,
          connectionState: ConnectionState.ERROR,
          lastError: 'Maximum reconnection attempts reached'
        };
      }

      const attempts = state.reconnectAttempts + 1;
      const delay = getReconnectDelay(attempts);

      console.log(`Attempting reconnection ${attempts}/${MAX_RECONNECT_ATTEMPTS} in ${delay}ms`);

      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }

      reconnectTimeout = setTimeout(() => {
        connect(currentUrl!, currentToken!);
      }, delay);

      return {
        ...state,
        reconnectAttempts: attempts,
        connectionState: ConnectionState.RECONNECTING
      };
    });
  }

  function connect(url: string, token: string) {
    if (!browser) return;

    currentUrl = url;
    currentToken = token;

    update(state => ({
      ...state,
      connectionState: state.reconnectAttempts > 0 ? 
        ConnectionState.RECONNECTING : ConnectionState.CONNECTING
    }));

    try {
      const wsUrl = `${url}?token=${encodeURIComponent(token)}`;
      const socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        console.log('WebSocket connected');
        
        update(state => ({
          ...state,
          socket,
          connectionState: ConnectionState.CONNECTED,
          reconnectAttempts: 0,
          lastError: null
        }));

        // Send queued messages
        sendQueuedMessages(socket);
        
        // Start heartbeat
        startHeartbeat(socket);
        
        // Request sync of missed updates if reconnecting
        const state = get(websocketStore);
        if (state.lastSyncTime) {
          socket.send(JSON.stringify({
            type: MessageType.RECONNECT,
            last_message_time: state.lastSyncTime
          }));
        }

        // Dispatch connected event
        dispatchCustomEvent('websocket-connected', { url, token });
      };

      socket.onmessage = handleMessage;

      socket.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        stopHeartbeat();

        update(state => ({
          ...state,
          socket: null,
          connectionState: ConnectionState.DISCONNECTED
        }));

        // Attempt reconnection if not intentionally closed
        if (event.code !== 1000 && event.code !== 1001) {
          attemptReconnection();
        }

        // Dispatch disconnected event
        dispatchCustomEvent('websocket-disconnected', { code: event.code, reason: event.reason });
      };

      socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        update(state => ({
          ...state,
          connectionState: ConnectionState.ERROR,
          lastError: 'WebSocket connection error'
        }));
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      update(state => ({
        ...state,
        connectionState: ConnectionState.ERROR,
        lastError: error instanceof Error ? error.message : 'Connection failed'
      }));
    }
  }

  function sendMessage(message: any) {
    update(state => {
      const messageWithId = {
        ...message,
        id: generateId(),
        timestamp: new Date().toISOString()
      };

      if (state.connectionState === ConnectionState.CONNECTED && state.socket) {
        try {
          state.socket.send(JSON.stringify(messageWithId));
        } catch (error) {
          console.error('Failed to send message:', error);
          // Queue message for retry
          const queuedMessage: QueuedMessage = {
            id: messageWithId.id,
            message: messageWithId,
            timestamp: Date.now(),
            retryCount: 0
          };
          return { ...state, messageQueue: [...state.messageQueue, queuedMessage] };
        }
      } else {
        // Queue message for when connected
        const queuedMessage: QueuedMessage = {
          id: messageWithId.id,
          message: messageWithId,
          timestamp: Date.now(),
          retryCount: 0
        };
        return { ...state, messageQueue: [...state.messageQueue, queuedMessage] };
      }

      return state;
    });
  }

  function subscribeToChannel(channel: string) {
    update(state => {
      const newSubscriptions = new Set(state.subscriptions);
      newSubscriptions.add(channel);

      if (state.connectionState === ConnectionState.CONNECTED && state.socket) {
        state.socket.send(JSON.stringify({
          type: 'subscribe',
          channel
        }));
      }

      return { ...state, subscriptions: newSubscriptions };
    });
  }

  function unsubscribeFromChannel(channel: string) {
    update(state => {
      const newSubscriptions = new Set(state.subscriptions);
      newSubscriptions.delete(channel);

      if (state.connectionState === ConnectionState.CONNECTED && state.socket) {
        state.socket.send(JSON.stringify({
          type: 'unsubscribe',
          channel
        }));
      }

      return { ...state, subscriptions: newSubscriptions };
    });
  }

  function disconnect() {
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
    
    stopHeartbeat();

    update(state => {
      if (state.socket) {
        state.socket.close(1000, 'Client disconnect');
      }
      
      return {
        ...state,
        socket: null,
        connectionState: ConnectionState.DISCONNECTED,
        reconnectAttempts: 0
      };
    });

    currentUrl = null;
    currentToken = null;
  }

  function get(store: any) {
    let value: WebSocketState;
    store.subscribe((v: WebSocketState) => { value = v; })();
    return value!;
  }

  return {
    subscribe,
    connect,
    disconnect,
    sendMessage,
    subscribeToChannel,
    unsubscribeFromChannel,
    // Expose state for debugging
    getState: () => get({ subscribe })
  };
}

export const websocketStore = createWebSocketStore();

// Derived stores for easy access
export const connectionState = derived(websocketStore, $ws => $ws.connectionState);
export const isConnected = derived(connectionState, $state => $state === ConnectionState.CONNECTED);
export const messages = derived(websocketStore, $ws => $ws.messages);
export const hasError = derived(websocketStore, $ws => $ws.connectionState === ConnectionState.ERROR);
export const errorMessage = derived(websocketStore, $ws => $ws.lastError);

// Auto-connect when auth token is available - TEMPORARILY DISABLED for debugging
if (false && browser) {
  // Subscribe to auth changes to auto-connect/disconnect
  authStore.subscribe(auth => {
    if (auth.isAuthenticated && auth.token) {
      // Get WebSocket URL from current page or environment
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.hostname + ':8000';
      const wsUrl = `${protocol}//${host}/api/v1/ws/dashboard/${auth.user?.id}`;
      websocketStore.connect(wsUrl, auth.token);
    } else {
      websocketStore.disconnect();
    }
  });
}