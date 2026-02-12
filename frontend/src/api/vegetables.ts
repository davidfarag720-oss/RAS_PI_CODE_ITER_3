import { get } from './client';
import { VegetableConfig, CutType } from './types';

export async function getVegetables(): Promise<VegetableConfig[]> {
  return get<VegetableConfig[]>('/vegetables');
}

export async function getVegetable(id: string): Promise<VegetableConfig> {
  return get<VegetableConfig>(`/vegetables/${id}`);
}

export async function getCutTypes(): Promise<CutType[]> {
  // Backend returns dict keyed by cut name, convert to array with id field
  const dict = await get<Record<string, Omit<CutType, 'id'>>>('/cut-types');
  return Object.entries(dict).map(([id, cut]) => ({ id, ...cut }));
}

export async function getCutType(id: string): Promise<CutType> {
  return get<CutType>(`/cut-types/${id}`);
}
