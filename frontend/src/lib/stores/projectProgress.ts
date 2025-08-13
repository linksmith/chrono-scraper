/**
 * Project progress store for handling real-time task updates
 */
import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import { websocketStore, MessageType } from './websocket';

export interface TaskProgress {
  id: string;
  project_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number; // 0-100
  message: string;
  details?: any;
  started_at?: string;
  updated_at: string;
  completed_at?: string;
  error?: string;
}

export interface ProjectStatus {
  id: string;
  name: string;
  status: string;
  total_pages?: number;
  completed_pages?: number;
  failed_pages?: number;
  progress_percentage?: number;
  last_updated?: string;
}

export interface Notification {
  id: string;
  type: 'task_completed' | 'task_failed' | 'project_update' | 'system';
  title: string;
  message: string;
  project_id?: string;
  task_id?: string;
  timestamp: string;
  read: boolean;
  actions?: Array<{
    label: string;
    action: string;
    primary?: boolean;
  }>;
}

interface ProjectProgressState {
  activeTasks: Map<string, TaskProgress>;
  completedTasks: Map<string, TaskProgress>;
  projects: Map<string, ProjectStatus>;
  notifications: Notification[];
  subscribedProjects: Set<string>;
}

function createProjectProgressStore() {
  const { subscribe, set, update } = writable<ProjectProgressState>({
    activeTasks: new Map(),
    completedTasks: new Map(),
    projects: new Map(),
    notifications: [],
    subscribedProjects: new Set()
  });

  // Listen for WebSocket messages
  if (browser) {
    window.addEventListener('websocket-message', (event) => {
      const message = (event as CustomEvent).detail;
      handleProgressMessage(message);
    });

    window.addEventListener('websocket-connected', () => {
      // Re-subscribe to projects when reconnected
      const state = getCurrentState();
      state.subscribedProjects.forEach(projectId => {
        subscribeToProject(projectId);
      });
    });

    // Load persisted state from localStorage
    loadFromStorage();
  }

  function getCurrentState(): ProjectProgressState {
    let currentState: ProjectProgressState;
    const unsubscribe = subscribe(state => {
      currentState = state;
    });
    unsubscribe();
    return currentState!;
  }

  function saveToStorage() {
    if (!browser) return;

    try {
      const state = getCurrentState();
      const persistedState = {
        activeTasks: Array.from(state.activeTasks.entries()),
        completedTasks: Array.from(state.completedTasks.entries()).slice(-20), // Keep last 20
        projects: Array.from(state.projects.entries()),
        notifications: state.notifications.slice(-50), // Keep last 50
        subscribedProjects: Array.from(state.subscribedProjects),
        lastUpdated: new Date().toISOString()
      };

      localStorage.setItem('projectProgress', JSON.stringify(persistedState));
    } catch (error) {
      console.warn('Failed to save project progress to storage:', error);
    }
  }

  function loadFromStorage() {
    if (!browser) return;

    try {
      const stored = localStorage.getItem('projectProgress');
      if (stored) {
        const data = JSON.parse(stored);
        
        update(state => ({
          ...state,
          activeTasks: new Map(data.activeTasks || []),
          completedTasks: new Map(data.completedTasks || []),
          projects: new Map(data.projects || []),
          notifications: (data.notifications || []).map((n: any) => ({
            ...n,
            read: false // Mark as unread on reload
          })),
          subscribedProjects: new Set(data.subscribedProjects || [])
        }));
      }
    } catch (error) {
      console.warn('Failed to load project progress from storage:', error);
    }
  }

  function handleProgressMessage(message: any) {
    switch (message.type) {
      case MessageType.TASK_PROGRESS:
      case 'task_progress':
        updateTaskProgress(message.payload || message);
        break;
      case 'task_completed':
        completeTask(message.payload || message);
        break;
      case 'task_failed':
        failTask(message.payload || message);
        break;
      case MessageType.PROJECT_UPDATE:
      case 'project_update':
      case 'project_status':
        updateProjectStatus(message.payload || message);
        break;
      case 'scrape_progress':
        updateScrapeProgress(message.payload || message);
        break;
      case 'url_completed':
        handleUrlCompleted(message.payload || message);
        break;
    }
  }

  function updateTaskProgress(data: any) {
    update(state => {
      const taskProgress: TaskProgress = {
        id: data.task_id,
        project_id: data.project_id,
        status: data.status || 'running',
        progress: Math.min(Math.max(data.progress || 0, 0), 100),
        message: data.message || '',
        details: data.details,
        updated_at: data.timestamp || new Date().toISOString(),
        error: data.error
      };

      const newActiveTasks = new Map(state.activeTasks);
      
      if (data.status === 'completed' || data.status === 'failed') {
        // Move to completed tasks
        const newCompletedTasks = new Map(state.completedTasks);
        newCompletedTasks.set(taskProgress.id, {
          ...taskProgress,
          completed_at: taskProgress.updated_at
        });
        newActiveTasks.delete(taskProgress.id);

        // Create notification
        const notification = createTaskNotification(taskProgress);
        if (notification) {
          state.notifications.push(notification);
        }

        const newState = {
          ...state,
          activeTasks: newActiveTasks,
          completedTasks: newCompletedTasks,
          notifications: state.notifications.slice(-50) // Keep last 50
        };
        
        saveToStorage();
        return newState;
      } else {
        // Update active task
        newActiveTasks.set(taskProgress.id, taskProgress);
        
        const newState = {
          ...state,
          activeTasks: newActiveTasks
        };
        
        // Save to storage less frequently for active tasks
        if (Math.random() < 0.1) { // 10% chance to save
          setTimeout(saveToStorage, 100);
        }
        
        return newState;
      }
    });
  }

  function updateScrapeProgress(data: any) {
    update(state => {
      const taskId = `scrape_${data.domain_id}_${data.project_id}`;
      const taskProgress: TaskProgress = {
        id: taskId,
        project_id: data.project_id,
        status: 'running',
        progress: ((data.current || 0) / (data.total || 1)) * 100,
        message: data.status || 'Processing...',
        details: {
          current: data.current,
          total: data.total,
          domain_name: data.domain_name,
          snapshots_found: data.snapshots_found
        },
        updated_at: new Date().toISOString()
      };

      const newActiveTasks = new Map(state.activeTasks);
      newActiveTasks.set(taskId, taskProgress);

      return {
        ...state,
        activeTasks: newActiveTasks
      };
    });
  }

  function updateProjectStatus(data: any) {
    update(state => {
      const projectStatus: ProjectStatus = {
        id: data.id || data.project_id,
        name: data.name || 'Unknown Project',
        status: data.status || 'unknown',
        total_pages: data.total_pages,
        completed_pages: data.completed_pages,
        failed_pages: data.failed_pages,
        progress_percentage: data.progress_percentage,
        last_updated: data.last_updated || new Date().toISOString()
      };

      const newProjects = new Map(state.projects);
      newProjects.set(projectStatus.id, projectStatus);

      const newState = {
        ...state,
        projects: newProjects
      };
      
      saveToStorage();
      return newState;
    });
  }

  function handleUrlCompleted(data: any) {
    // Create a small notification for URL completion (optional)
    if (data.project_id && Math.random() < 0.05) { // Only 5% of URLs create notifications
      update(state => {
        const notification: Notification = {
          id: `url_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          type: 'project_update',
          title: 'Page Scraped',
          message: `Successfully processed: ${data.url_data?.url || 'page'}`,
          project_id: data.project_id,
          timestamp: new Date().toISOString(),
          read: false
        };

        return {
          ...state,
          notifications: [...state.notifications.slice(-49), notification] // Keep last 50
        };
      });
    }
  }

  function completeTask(data: any) {
    updateTaskProgress({
      ...data,
      status: 'completed'
    });
  }

  function failTask(data: any) {
    updateTaskProgress({
      ...data,
      status: 'failed'
    });
  }

  function createTaskNotification(task: TaskProgress): Notification | null {
    if (task.status === 'completed') {
      return {
        id: `task_complete_${task.id}`,
        type: 'task_completed',
        title: 'Task Completed',
        message: task.message || `Task "${task.id}" completed successfully`,
        project_id: task.project_id,
        task_id: task.id,
        timestamp: task.updated_at,
        read: false,
        actions: [
          {
            label: 'View Project',
            action: `navigate:/projects/${task.project_id}`,
            primary: true
          }
        ]
      };
    } else if (task.status === 'failed') {
      return {
        id: `task_failed_${task.id}`,
        type: 'task_failed',
        title: 'Task Failed',
        message: task.error || task.message || `Task "${task.id}" failed`,
        project_id: task.project_id,
        task_id: task.id,
        timestamp: task.updated_at,
        read: false,
        actions: [
          {
            label: 'View Details',
            action: `navigate:/projects/${task.project_id}`,
            primary: true
          },
          {
            label: 'Retry',
            action: `retry:${task.id}`
          }
        ]
      };
    }
    return null;
  }

  function subscribeToProject(projectId: string) {
    update(state => {
      const newSubscribed = new Set(state.subscribedProjects);
      newSubscribed.add(projectId);
      
      // Subscribe via WebSocket
      websocketStore.subscribeToChannel(`project:${projectId}`);
      
      return {
        ...state,
        subscribedProjects: newSubscribed
      };
    });
    
    saveToStorage();
  }

  function unsubscribeFromProject(projectId: string) {
    update(state => {
      const newSubscribed = new Set(state.subscribedProjects);
      newSubscribed.delete(projectId);
      
      // Unsubscribe via WebSocket
      websocketStore.unsubscribeFromChannel(`project:${projectId}`);
      
      return {
        ...state,
        subscribedProjects: newSubscribed
      };
    });
    
    saveToStorage();
  }

  function markNotificationRead(notificationId: string) {
    update(state => {
      const newNotifications = state.notifications.map(n =>
        n.id === notificationId ? { ...n, read: true } : n
      );
      
      const newState = {
        ...state,
        notifications: newNotifications
      };
      
      saveToStorage();
      return newState;
    });
  }

  function markAllNotificationsRead() {
    update(state => {
      const newNotifications = state.notifications.map(n => ({ ...n, read: true }));
      
      const newState = {
        ...state,
        notifications: newNotifications
      };
      
      saveToStorage();
      return newState;
    });
  }

  function clearCompletedTasks() {
    update(state => {
      const newState = {
        ...state,
        completedTasks: new Map()
      };
      
      saveToStorage();
      return newState;
    });
  }

  function removeNotification(notificationId: string) {
    update(state => {
      const newNotifications = state.notifications.filter(n => n.id !== notificationId);
      
      const newState = {
        ...state,
        notifications: newNotifications
      };
      
      saveToStorage();
      return newState;
    });
  }

  return {
    subscribe,
    subscribeToProject,
    unsubscribeFromProject,
    markNotificationRead,
    markAllNotificationsRead,
    clearCompletedTasks,
    removeNotification,
    // Get current state (for debugging)
    getCurrentState
  };
}

export const projectProgress = createProjectProgressStore();

// Derived stores for components
export const activeTasks = derived(
  projectProgress,
  $progress => Array.from($progress.activeTasks.values())
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
);

export const completedTasks = derived(
  projectProgress,
  $progress => Array.from($progress.completedTasks.values())
    .sort((a, b) => new Date(b.completed_at || b.updated_at).getTime() - new Date(a.completed_at || a.updated_at).getTime())
);

export const projects = derived(
  projectProgress,
  $progress => Array.from($progress.projects.values())
);

export const unreadNotifications = derived(
  projectProgress,
  $progress => $progress.notifications.filter(n => !n.read)
);

export const allNotifications = derived(
  projectProgress,
  $progress => $progress.notifications
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
);

export const activeTasksCount = derived(activeTasks, $tasks => $tasks.length);
export const unreadNotificationsCount = derived(unreadNotifications, $notifications => $notifications.length);

// Helper function to get task progress for a specific project
export const getProjectTasks = derived(
  projectProgress,
  $progress => (projectId: string) => {
    const active = Array.from($progress.activeTasks.values())
      .filter(task => task.project_id === projectId);
    const completed = Array.from($progress.completedTasks.values())
      .filter(task => task.project_id === projectId);
    
    return { active, completed };
  }
);