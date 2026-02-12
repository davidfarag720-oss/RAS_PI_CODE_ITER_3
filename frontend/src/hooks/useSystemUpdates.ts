import { useState, useCallback } from 'react';
import { useWebSocket } from './useWebSocket';
import { SystemUpdate } from '../api/types';

interface UseSystemUpdatesReturn {
  lastUpdate: SystemUpdate | null;
  isConnected: boolean;
  reconnect: () => void;
}

export function useSystemUpdates(
  onUpdate?: (update: SystemUpdate) => void
): UseSystemUpdatesReturn {
  const [lastUpdate, setLastUpdate] = useState<SystemUpdate | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const update: SystemUpdate = JSON.parse(event.data);
      setLastUpdate(update);
      onUpdate?.(update);
    } catch (e) {
      console.error('Failed to parse system update:', e);
    }
  }, [onUpdate]);

  const { isConnected, reconnect } = useWebSocket({
    url: '/ws/updates',
    onMessage: handleMessage,
  });

  return { lastUpdate, isConnected, reconnect };
}
