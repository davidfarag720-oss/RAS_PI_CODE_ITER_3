import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { powerOn } from '../api';
import { useApp } from '../store/AppContext';

type PowerState = 'off' | 'booting' | 'error';

export function SplashScreen() {
  const navigate = useNavigate();
  const { dispatch } = useApp();
  const [powerState, setPowerState] = useState<PowerState>('off');
  const [errorMessage, setErrorMessage] = useState<string>('');

  const handlePowerOn = async () => {
    if (powerState === 'booting') return;

    setPowerState('booting');
    setErrorMessage('');

    try {
      await powerOn();
      dispatch({ type: 'SET_SYSTEM_INITIALIZED', payload: true });
      navigate('/select');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Power on failed. Check STM32 connection.';
      setErrorMessage(msg);
      setPowerState('error');
    }
  };

  const isBooting = powerState === 'booting';

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center select-none">
      <h1 className="text-5xl font-bold text-text-primary mb-16">Ficio Prep</h1>

      {/* Power button */}
      <button
        onClick={handlePowerOn}
        disabled={isBooting}
        className={[
          'w-32 h-32 rounded-full flex items-center justify-center transition-all duration-200',
          'focus:outline-none',
          isBooting
            ? 'bg-surface border-4 border-gray-300 cursor-not-allowed'
            : powerState === 'error'
            ? 'bg-surface border-4 border-danger active:scale-95 cursor-pointer'
            : 'bg-surface border-4 border-primary active:scale-95 cursor-pointer shadow-lg',
        ].join(' ')}
        aria-label="Power On"
      >
        {isBooting ? (
          /* Spinner during homing sequence */
          <svg
            className="w-12 h-12 text-gray-400 animate-spin"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="3"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
            />
          </svg>
        ) : (
          /* Power icon */
          <svg
            className={[
              'w-14 h-14',
              powerState === 'error' ? 'text-danger' : 'text-primary',
            ].join(' ')}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 3v5m0 0a7 7 0 110 14 7 7 0 010-14"
            />
          </svg>
        )}
      </button>

      {/* Status text below button */}
      <p className="mt-6 text-sm uppercase tracking-[0.25em] text-text-secondary">
        {isBooting ? 'Initializing system\u2026' : powerState === 'error' ? 'Tap to retry' : 'Tap to power on'}
      </p>

      {/* Error detail */}
      {powerState === 'error' && errorMessage && (
        <p className="mt-3 text-sm text-danger max-w-xs text-center px-4">{errorMessage}</p>
      )}

      {/* Subtle hint during boot */}
      {isBooting && (
        <p className="mt-2 text-xs text-text-secondary opacity-60">
          Homing actuators — this takes up to 45 seconds
        </p>
      )}
    </div>
  );
}
