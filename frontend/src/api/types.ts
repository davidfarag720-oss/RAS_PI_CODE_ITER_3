// Matches backend Pydantic models

export interface VegetableConfig {
  id: string;
  name: string;           // Display name from backend
  image_url: string;      // Full path like "/assets/ui/cucumber.jpg"
  supported_cuts: string[];
}

export interface CutType {
  id: string;             // Set from dict key when converting response
  name: string;
  display_name: string;
  description: string;
}

export interface TaskStats {
  items_processed: number;
  items_rejected: number;
  weight_processed_grams: number;
  success_rate: number;
}

export interface Task {
  id: string;
  vegetable_id: string;
  vegetable_name: string;
  cut_type: string;
  cut_display_name: string;
  bay_id: number;
  status: TaskStatus;
  stats: TaskStats;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

export type TaskStatus =
  | 'queued'     // Backend uses 'queued' not 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'stopped';   // Stopped by emergency stop, can be restarted

export interface TaskCreateRequest {
  vegetable_id: string;
  cut_type: string;
  bay_id: number;
  target_count?: number;
}

export interface SystemStatus {
  scale_weight_grams: number;
  active_tasks: number;
  queued_tasks: number;
  available_bays: number[];  // Just bay IDs
  camera_ready: boolean;
}

export interface SystemUpdate {
  type: string;              // "task_update" | "system_event" | "workflow_event" | "status"
  event?: string;            // For workflow_event type
  task_id?: string;
  bay_id?: number;
  data?: Record<string, unknown>;
  timestamp?: string | number;
}

export interface ApiError {
  detail: string;
}

export interface MachineConfig {
  variant: string;
  num_hoppers: number;
  num_actuators: number;
  bottom_gate_present: boolean;
  parallelization_enabled: boolean;
}
