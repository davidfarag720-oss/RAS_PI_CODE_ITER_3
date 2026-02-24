import { Task } from '../../api/types';
import { Card } from '../common';

interface TaskQueueProps {
  tasks: Task[];
  vegetables: Record<string, string>; // id -> display_name
  cutTypes: Record<string, string>; // id -> display_name
  onCancelQueued: (taskId: string) => void;     // X on queued → DELETE API
  onStopActive: (taskId: string) => void;       // X on running → POST /stop API
  onDismissCompleted: (taskId: string) => void; // X on completed/failed/cancelled/stopped → client-side
}

export function TaskQueue({ tasks, vegetables, cutTypes, onCancelQueued, onStopActive, onDismissCompleted }: TaskQueueProps) {
  const getStatusColor = (status: Task['status']) => {
    switch (status) {
      case 'running':
        return 'bg-green-500';
      case 'queued':
        return 'bg-yellow-500';
      case 'paused':
        return 'bg-blue-500';
      case 'completed':
        return 'bg-gray-400';
      case 'stopped':
        return 'bg-orange-400';
      case 'failed':
      case 'cancelled':
        return 'bg-red-500';
      default:
        return 'bg-gray-400';
    }
  };

  const getStatusLabel = (status: Task['status']) => {
    switch (status) {
      case 'running':
        return 'Running';
      case 'queued':
        return 'Queued';
      case 'paused':
        return 'Paused';
      case 'completed':
        return 'Done';
      case 'stopped':
        return 'Stopped';
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return status;
    }
  };

  const handleXButton = (task: Task) => {
    if (task.status === 'queued') {
      onCancelQueued(task.id);
    } else if (task.status === 'running') {
      onStopActive(task.id);
    } else {
      // completed, failed, cancelled, stopped, paused
      onDismissCompleted(task.id);
    }
  };

  const isCompleted = (status: Task['status']) =>
    status === 'completed' || status === 'failed' || status === 'cancelled' || status === 'stopped';

  if (tasks.length === 0) {
    return (
      <Card padding="lg" className="text-center">
        <p className="text-text-secondary">No tasks in queue</p>
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <Card key={task.id} padding="md" className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${getStatusColor(task.status)}`} />
            <div>
              <div className="font-medium text-text-primary">
                Bay {task.bay_id}: {vegetables[task.vegetable_id] || task.vegetable_id}
              </div>
              <div className="text-sm text-text-secondary">
                {cutTypes[task.cut_type] || task.cut_type}
              </div>
              {isCompleted(task.status) && (
                <div className="text-xs text-text-secondary mt-0.5">
                  {(task.stats.weight_processed_grams / 1000).toFixed(2)} kg &middot; {task.stats.items_processed} items
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="text-right">
              <div className="text-sm font-medium text-text-primary">
                {getStatusLabel(task.status)}
              </div>
            </div>
            <button
              onClick={() => handleXButton(task)}
              className="p-2 rounded-full hover:bg-gray-100 active:bg-gray-200 text-text-secondary hover:text-text-primary transition-colors"
              aria-label={`Remove task for Bay ${task.bay_id}`}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </Card>
      ))}
    </div>
  );
}
