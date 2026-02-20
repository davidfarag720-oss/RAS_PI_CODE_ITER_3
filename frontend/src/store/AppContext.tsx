import React, { createContext, useContext, useReducer, useEffect, useCallback, ReactNode } from 'react';
import {
  VegetableConfig,
  CutType,
  Task,
  SystemStatus,
  getVegetables,
  getCutTypes,
  getTasks,
  getSystemStatus,
  getMachineConfig,
  MachineConfig,
} from '../api';
import { useSystemUpdates } from '../hooks';

interface AppState {
  vegetables: VegetableConfig[];
  cutTypes: CutType[];
  tasks: Task[];
  systemStatus: SystemStatus | null;
  machineConfig: MachineConfig | null;
  isLoading: boolean;
  error: string | null;
}

type AppAction =
  | { type: 'SET_VEGETABLES'; payload: VegetableConfig[] }
  | { type: 'SET_CUT_TYPES'; payload: CutType[] }
  | { type: 'SET_TASKS'; payload: Task[] }
  | { type: 'ADD_TASK'; payload: Task }
  | { type: 'UPDATE_TASK'; payload: Task }
  | { type: 'REMOVE_TASK'; payload: string }
  | { type: 'SET_SYSTEM_STATUS'; payload: SystemStatus }
  | { type: 'SET_MACHINE_CONFIG'; payload: MachineConfig }
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: string | null };

const initialState: AppState = {
  vegetables: [],
  cutTypes: [],
  tasks: [],
  systemStatus: null,
  machineConfig: null,
  isLoading: true,
  error: null,
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_VEGETABLES':
      return { ...state, vegetables: action.payload };
    case 'SET_CUT_TYPES':
      return { ...state, cutTypes: action.payload };
    case 'SET_TASKS':
      return { ...state, tasks: action.payload };
    case 'ADD_TASK':
      return { ...state, tasks: [...state.tasks, action.payload] };
    case 'UPDATE_TASK': {
      const exists = state.tasks.some((t) => t.id === action.payload.id);
      return {
        ...state,
        tasks: exists
          ? state.tasks.map((t) => (t.id === action.payload.id ? action.payload : t))
          : [...state.tasks, action.payload],
      };
    }
    case 'REMOVE_TASK':
      return {
        ...state,
        tasks: state.tasks.filter((t) => t.id !== action.payload),
      };
    case 'SET_SYSTEM_STATUS':
      return { ...state, systemStatus: action.payload };
    case 'SET_MACHINE_CONFIG':
      return { ...state, machineConfig: action.payload };
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload };
    case 'SET_ERROR':
      return { ...state, error: action.payload };
    default:
      return state;
  }
}

interface AppContextValue {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
  refreshData: () => Promise<void>;
  getVegetableName: (id: string) => string;
  getCutTypeName: (id: string) => string;
  getAvailableBays: () => number[];
  hasActiveTasks: () => boolean;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  const refreshData = useCallback(async () => {
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'SET_ERROR', payload: null });

    try {
      const [vegetables, cutTypes, tasks, status, machineConfig] = await Promise.all([
        getVegetables(),
        getCutTypes(),
        getTasks(),
        getSystemStatus(),
        getMachineConfig(),
      ]);

      dispatch({ type: 'SET_VEGETABLES', payload: vegetables });
      dispatch({ type: 'SET_CUT_TYPES', payload: cutTypes });
      dispatch({ type: 'SET_TASKS', payload: tasks });
      dispatch({ type: 'SET_SYSTEM_STATUS', payload: status });
      dispatch({ type: 'SET_MACHINE_CONFIG', payload: machineConfig });
    } catch (error) {
      console.error('Failed to load data:', error);
      dispatch({
        type: 'SET_ERROR',
        payload: error instanceof Error ? error.message : 'Failed to load data',
      });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  }, []);

  // Handle real-time updates from WebSocket
  const handleSystemUpdate = useCallback((update: { type?: string; event?: string; task_id?: string; data?: Record<string, unknown> }) => {
    // task_update messages from broadcast_task_update
    if (update.type === 'task_update' && update.data) {
      dispatch({ type: 'UPDATE_TASK', payload: update.data as unknown as Task });
    }
    // system_event messages (emergency_stop, system_restarted)
    else if (update.type === 'system_event' && update.data) {
      // Refresh all data to pick up STOPPED task statuses
      refreshData();
      return; // refreshData already fetches system status
    }

    // Refresh status on any update
    getSystemStatus().then((status) => {
      dispatch({ type: 'SET_SYSTEM_STATUS', payload: status });
    });
  }, [refreshData]);

  const { isConnected } = useSystemUpdates(handleSystemUpdate);

  // Initial data load
  useEffect(() => {
    refreshData();
  }, [refreshData]);

  // Background poll: keeps task list and status fresh even when WS events are missed
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const [tasks, status] = await Promise.all([getTasks(), getSystemStatus()]);
        dispatch({ type: 'SET_TASKS', payload: tasks });
        dispatch({ type: 'SET_SYSTEM_STATUS', payload: status });
      } catch {
        // silent — don't surface background poll failures to the user
      }
    }, 3000);
    return () => clearInterval(id);
  }, []); // empty deps: runs once for the lifetime of the provider

  // Re-sync on every WebSocket connect/reconnect to catch events missed during downtime
  useEffect(() => {
    if (isConnected) {
      refreshData();
    }
  }, [isConnected, refreshData]);

  const getVegetableName = useCallback(
    (id: string) => {
      const veg = state.vegetables.find((v) => v.id === id);
      return veg?.name || id;
    },
    [state.vegetables]
  );

  const getCutTypeName = useCallback(
    (id: string) => {
      const cut = state.cutTypes.find((c) => c.id === id);
      return cut?.display_name || id;
    },
    [state.cutTypes]
  );

  const getAvailableBays = useCallback(() => {
    return state.systemStatus?.available_bays || [];
  }, [state.systemStatus]);

  const hasActiveTasks = useCallback(() => {
    return state.tasks.some((t) => t.status === 'running' || t.status === 'queued');
  }, [state.tasks]);

  const value: AppContextValue = {
    state,
    dispatch,
    refreshData,
    getVegetableName,
    getCutTypeName,
    getAvailableBays,
    hasActiveTasks,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}
