import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common';
import { CameraFeed, WeightDisplay, TaskQueue, EmergencyStop } from '../components/processing';
import { useApp } from '../store/AppContext';
import { cancelTask, stopTask, powerOff } from '../api';

export function ProcessingScreen() {
  const navigate = useNavigate();
  const { state, dispatch, getVegetableName, getCutTypeName, refreshData } = useApp();
  const [isSystemStopped, setIsSystemStopped] = useState(false);
  const [showPowerOffConfirm, setShowPowerOffConfirm] = useState(false);
  const [isPoweringOff, setIsPoweringOff] = useState(false);

  // Find the active (running) task
  const activeTask = useMemo(() => {
    return state.tasks.find((t) => t.status === 'running');
  }, [state.tasks]);

  // Get tasks for the queue view: active, queued, and completed (so operators can review and dismiss)
  const queuedTasks = useMemo(() => {
    return state.tasks.filter((t) =>
      t.status === 'running' ||
      t.status === 'queued' ||
      t.status === 'paused' ||
      t.status === 'stopped' ||
      t.status === 'completed'
    );
  }, [state.tasks]);

  // Derive stopped state from tasks (survives page refresh)
  const hasStoppedTasks = useMemo(() => {
    return state.tasks.some((t) => t.status === 'stopped');
  }, [state.tasks]);

  // Build lookup maps for names
  const vegetableNames = useMemo(() => {
    return state.vegetables.reduce((acc, v) => {
      acc[v.id] = v.name;
      return acc;
    }, {} as Record<string, string>);
  }, [state.vegetables]);

  const cutTypeNames = useMemo(() => {
    return state.cutTypes.reduce((acc, c) => {
      acc[c.id] = c.display_name;
      return acc;
    }, {} as Record<string, string>);
  }, [state.cutTypes]);

  const allBaysBusy = (state.systemStatus?.available_bays ?? []).length === 0;

  const handleQueueNewTask = () => {
    navigate('/select');
  };

  const handleViewQueue = () => {
    document.getElementById('task-queue')?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleEmergencyStop = () => {
    setIsSystemStopped(true);
    refreshData();
  };

  const handleRestart = () => {
    setIsSystemStopped(false);
    refreshData();
  };

  const handleCancelQueued = async (taskId: string) => {
    try {
      await cancelTask(taskId);
      dispatch({ type: 'REMOVE_TASK', payload: taskId });
    } catch (e) {
      console.error('Failed to cancel task', e);
    }
  };

  const handleStopActive = async (taskId: string) => {
    try {
      await stopTask(taskId);
      // No immediate state change — task will update via WebSocket when it completes
    } catch (e) {
      console.error('Failed to request graceful stop', e);
    }
  };

  const handlePowerOff = async () => {
    setShowPowerOffConfirm(false);
    setIsPoweringOff(true);
    try {
      await powerOff();
      dispatch({ type: 'SET_SYSTEM_INITIALIZED', payload: false });
      navigate('/');
    } catch (e) {
      console.error('Power off failed', e);
      setIsPoweringOff(false);
    }
  };

  const handleDismissCompleted = async (taskId: string) => {
    dispatch({ type: 'DISMISS_TASK', payload: taskId }); // optimistic — hide immediately
    try {
      await cancelTask(taskId); // DELETE /api/tasks/{id} — removes from backend
    } catch {
      // silent — task already hidden locally; backend will clean up on restart if needed
    }
  };

  // Display info
  const displayBay = activeTask?.bay_id || 1;
  const displayVegetable = activeTask
    ? getVegetableName(activeTask.vegetable_id)
    : 'No active task';
  const displayCut = activeTask ? getCutTypeName(activeTask.cut_type) : '';
  const displayWeight = (activeTask?.stats?.weight_processed_grams || 0) / 1000; // Convert to kg
  const displayItemCount = activeTask?.stats?.items_processed || 0;

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header bar */}
      <header className="bg-surface px-4 py-3 flex items-center justify-between shadow-sm">
        <div className="font-medium text-text-primary">
          {activeTask ? (
            <>Bay {displayBay} | {displayVegetable} ({displayCut})</>
          ) : (
            'Processing'
          )}
        </div>
        <div className="flex items-center gap-3">
          {activeTask && (
            <div className="flex items-center gap-1.5 text-danger">
              <span className="w-2 h-2 bg-danger rounded-full animate-pulse" />
              <span className="text-sm font-semibold">LIVE</span>
            </div>
          )}
          <button
            onClick={() => setShowPowerOffConfirm(true)}
            disabled={isPoweringOff}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-100 text-text-secondary text-sm font-medium active:bg-gray-200 disabled:opacity-50"
            aria-label="Power Off"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v5m0 0a7 7 0 110 14 7 7 0 010-14" />
            </svg>
            {isPoweringOff ? 'Shutting down\u2026' : 'Power Off'}
          </button>
        </div>
      </header>

      {/* Power Off confirmation modal */}
      {showPowerOffConfirm && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-6">
          <div className="bg-surface rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <h2 className="text-lg font-semibold text-text-primary mb-2">Power Off?</h2>
            <p className="text-sm text-text-secondary mb-6">
              This will stop all tasks, home the actuators, and return to the power screen.
              All current progress will be discarded.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowPowerOffConfirm(false)}
                className="flex-1 inline-flex items-center justify-center font-semibold text-lg rounded-2xl min-h-[56px] px-8 py-4 bg-transparent text-text-primary active:bg-gray-100 active:scale-95 transition-all duration-150"
              >
                Cancel
              </button>
              <button
                onClick={handlePowerOff}
                className="flex-1 inline-flex items-center justify-center font-semibold text-lg rounded-2xl min-h-[56px] px-8 py-4 bg-gray-600 text-white active:bg-gray-700 active:scale-95 transition-all duration-150"
              >
                Power Off
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 p-4 space-y-4 pb-24">
        {/* Camera feed */}
        <CameraFeed
          bayId={displayBay}
          vegetableName={displayVegetable}
          cutType={displayCut}
        />

        {/* Stats and stop button row */}
        <div className="flex gap-4">
          <WeightDisplay
            weight={displayWeight}
            itemCount={displayItemCount}
            vegetableName={displayVegetable}
          />
          <EmergencyStop
            onStop={handleEmergencyStop}
            onRestart={handleRestart}
            isStopped={isSystemStopped || hasStoppedTasks}
          />
        </div>

        {/* Task queue */}
        {queuedTasks.length > 0 && (
          <div id="task-queue" className="space-y-2">
            <h3 className="text-sm font-medium text-text-secondary uppercase tracking-wide px-1">
              Task Queue
            </h3>
            <TaskQueue
              tasks={queuedTasks}
              vegetables={vegetableNames}
              cutTypes={cutTypeNames}
              onCancelQueued={handleCancelQueued}
              onStopActive={handleStopActive}
              onDismissCompleted={handleDismissCompleted}
            />
          </div>
        )}
      </div>

      {/* Bottom action buttons */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-background border-t border-gray-200">
        <div className="flex gap-3">
          <Button
            onClick={handleQueueNewTask}
            variant="ghost"
            fullWidth
            size="lg"
            disabled={allBaysBusy}
            className="border-2 border-dashed border-gray-300"
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            }
          >
            {allBaysBusy ? 'Queue Full' : 'Queue New Task'}
          </Button>
          <Button
            onClick={handleViewQueue}
            variant="ghost"
            fullWidth
            size="lg"
            className="border-2 border-gray-300"
            icon={
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            }
          >
            View Queue
          </Button>
        </div>
      </div>
    </div>
  );
}
