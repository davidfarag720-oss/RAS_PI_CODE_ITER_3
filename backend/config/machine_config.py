"""
machine_config.py

Machine variant configuration mirroring STM32 machine_config.h.
Loads from config.json machine_variant section.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class MachineConfig:
    """Machine variant parameters matching STM32 configuration"""
    active_variant: Literal["mini", "vertical"]
    num_hoppers: int
    num_actuators: int
    bottom_gate_present: bool
    parallelization_enabled: bool
    num_vibration_motors: int

    def to_handshake_bytes(self) -> tuple:
        """
        Convert to 4-byte handshake format for CMD_CONFIG_HANDSHAKE.

        Returns:
            (param1, param2, param3, param4) tuple for UART packet

        Format:
            PARAM1: num_hoppers (1-4)
            PARAM2: num_actuators (1-3)
            PARAM3: flags byte (bit0=bottom_gate, bit1=parallelization)
            PARAM4: num_vibration_motors (1-4)
        """
        flags = 0
        if self.bottom_gate_present:
            flags |= 0x01
        if self.parallelization_enabled:
            flags |= 0x02

        return (self.num_hoppers, self.num_actuators, flags, self.num_vibration_motors)

    @classmethod
    def from_dict(cls, data: dict) -> 'MachineConfig':
        """Create from config.json machine_variant section"""
        return cls(
            active_variant=data['active_variant'],
            num_hoppers=data['num_hoppers'],
            num_actuators=data['num_actuators'],
            bottom_gate_present=data['bottom_gate_present'],
            parallelization_enabled=data['parallelization_enabled'],
            num_vibration_motors=data['num_vibration_motors']
        )


def get_machine_config() -> MachineConfig:
    """Load machine config from global ConfigManager"""
    from backend.config import get_config
    config_mgr = get_config()

    # Load raw config to access machine_variant (top-level key)
    import json
    from pathlib import Path
    config_path = Path(config_mgr.config_path)
    with open(config_path, 'r') as f:
        config = json.load(f)

    return MachineConfig.from_dict(config['machine_variant'])
