import { get, post, del } from './client';
import { Task, TaskCreateRequest } from './types';

export async function getTasks(): Promise<Task[]> {
  return get<Task[]>('/tasks');
}

export async function getTask(id: string): Promise<Task> {
  return get<Task>(`/tasks/${id}`);
}

export async function createTask(request: TaskCreateRequest): Promise<Task> {
  return post<Task>('/tasks', request);
}

export async function cancelTask(id: string): Promise<{ message: string }> {
  return del<{ message: string }>(`/tasks/${id}`);
}

export async function pauseTask(id: string): Promise<Task> {
  return post<Task>(`/tasks/${id}/pause`);
}

export async function resumeTask(id: string): Promise<Task> {
  return post<Task>(`/tasks/${id}/resume`);
}

export async function stopTask(id: string): Promise<void> {
  await post<void>(`/tasks/${id}/stop`);
}
