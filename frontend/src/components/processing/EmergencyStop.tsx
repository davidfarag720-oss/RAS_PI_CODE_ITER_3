import { useState } from 'react';
import { emergencyStop } from '../../api';

interface EmergencyStopProps {
  onStop?: () => void;
}

export function EmergencyStop({ onStop }: EmergencyStopProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleStop = async () => {
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
