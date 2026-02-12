import { useState, useCallback, useRef, useEffect } from 'react';
import { useWebSocket } from './useWebSocket';

interface UseCameraFeedReturn {
  imageUrl: string | null;
  isConnected: boolean;
  fps: number;
  reconnect: () => void;
}

export function useCameraFeed(): UseCameraFeedReturn {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [fps, setFps] = useState(0);
  const frameCountRef = useRef(0);
  const lastFpsUpdateRef = useRef(Date.now());
  const previousUrlRef = useRef<string | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    // Handle binary JPEG data
    if (event.data instanceof Blob) {
      // Revoke previous URL to prevent memory leak
      if (previousUrlRef.current) {
        URL.revokeObjectURL(previousUrlRef.current);
      }

      const url = URL.createObjectURL(event.data);
      previousUrlRef.current = url;
      setImageUrl(url);

      // Calculate FPS
      frameCountRef.current += 1;
      const now = Date.now();
      const elapsed = now - lastFpsUpdateRef.current;

      if (elapsed >= 1000) {
        setFps(Math.round((frameCountRef.current * 1000) / elapsed));
        frameCountRef.current = 0;
        lastFpsUpdateRef.current = now;
      }
    }
  }, []);

  const { isConnected, reconnect } = useWebSocket({
    url: '/ws/camera',
    onMessage: handleMessage,
  });

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (previousUrlRef.current) {
        URL.revokeObjectURL(previousUrlRef.current);
      }
    };
  }, []);

  return { imageUrl, isConnected, fps, reconnect };
}
