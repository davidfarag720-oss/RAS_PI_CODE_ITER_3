import { Task } from '../../api/types';
import { Card } from '../common';

interface TaskQueueProps {
  tasks: Task[];
  vegetables: Record<string, string>; // id -> display_name
  cutTypes: Record<string, string>; // id -> display_name
}

export function TaskQueue({ tasks, vegetables, cutTypes }: TaskQueueProps) {
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
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return status;
    }
  };

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
        <Card key={task.id} padding="md" className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-2 h-2 rounded-full ${getStatusColor(task.status)}`} />
            <div>
              <div className="font-medium text-text-primary">
                Bay {task.bay_id}: {vegetables[task.vegetable_id] || task.vegetable_id}
              </div>
              <div className="text-sm text-text-secondary">
                {cutTypes[task.cut_type] || task.cut_type}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-sm font-medium text-text-primary">
              {getStatusLabel(task.status)}
            </div>
            <div className="text-xs text-text-secondary">
              {(task.stats.weight_processed_grams / 1000).toFixed(2)} kg
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}
