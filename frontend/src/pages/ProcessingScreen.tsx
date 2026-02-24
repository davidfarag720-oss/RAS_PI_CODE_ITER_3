import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../components/common';
import { CameraFeed, WeightDisplay, TaskQueue, EmergencyStop } from '../components/processing';
import { useApp } from '../store/AppContext';
import { cancelTask, stopTask } from '../api';

export function ProcessingScreen() {
  const navigate = useNavigate();
  const { state, dispatch, getVegetableName, getCutTypeName, refreshData } = useApp();
  const [isSystemStopped, setIsSystemStopped] = useState(false);

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

  const handleDismissCompleted = (taskId: string) => {
    dispatch({ type: 'DISMISS_TASK', payload: taskId });
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
        {activeTask && (
          <div className="flex items-center gap-1.5 text-danger">
            <span className="w-2 h-2 bg-danger rounded-full animate-pulse" />
            <span className="text-sm font-semibold">LIVE</span>
          </div>
        )}
      </header>

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
