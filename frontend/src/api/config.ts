import { get } from './client';
import { MachineConfig } from './types';

export async function getMachineConfig(): Promise<MachineConfig> {
    return get<MachineConfig>('/config/machine');
}
