import { get, post } from './client';
import { SystemStatus } from './types';

export async function getSystemStatus(): Promise<SystemStatus> {
  return get<SystemStatus>('/status');
}

export async function emergencyStop(): Promise<{ message: string }> {
  return post<{ message: string }>('/emergency-stop');
}

export async function resetSystem(): Promise<{ message: string }> {
  return post<{ message: string }>('/reset');
}

export async function restartSystem(): Promise<{ tasks_requeued: number }> {
  return post<{ tasks_requeued: number }>('/restart');
}
