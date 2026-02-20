import { useState } from 'react';
import { emergencyStop, restartSystem } from '../../api';

interface EmergencyStopProps {
  onStop?: () => void;
  onRestart?: () => void;
  isStopped?: boolean;
}

export function EmergencyStop({ onStop, onRestart, isStopped = false }: EmergencyStopProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleStop = async () => {
    if (isLoading) return;  // Guard against double-fire
    setIsLoading(true);
    try {
      await emergencyStop();
      onStop?.();
    } catch (error) {
      console.error('Emergency stop failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRestart = async () => {
    if (isLoading) return;  // Guard against double-fire
    setIsLoading(true);
    try {
      await restartSystem();
      onRestart?.();
    } catch (error) {
      console.error('Restart failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (isStopped) {
    return (
      <button
        onClick={handleRestart}
        disabled={isLoading}
        className="bg-green-600 text-white rounded-2xl p-6 flex flex-col items-center justify-center gap-2 active:bg-green-700 active:scale-95 transition-all min-w-[120px] shadow-lg"
      >
        {/* Restart icon */}
        <svg
          className="w-12 h-12"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        <span className="text-lg font-bold uppercase">
          {isLoading ? 'Restarting...' : 'RESTART'}
        </span>
      </button>
    );
  }

  return (
    <button
      onClick={handleStop}
      disabled={isLoading}
      className="bg-danger text-white rounded-2xl p-6 flex flex-col items-center justify-center gap-2 active:bg-red-600 active:scale-95 transition-all min-w-[120px] shadow-lg"
    >
      {/* Stop icon */}
      <svg
        className="w-12 h-12"
        fill="currentColor"
        viewBox="0 0 24 24"
      >
        <rect x="4" y="4" width="16" height="16" rx="2" />
      </svg>
      <span className="text-lg font-bold uppercase">
        {isLoading ? 'Stopping...' : 'STOP'}
      </span>
    </button>
  );
}
