"""
Ficio Prep Backend Package.

This package unifies the core subsystems:
- Comms: Communication with the STM32 firmware.
- Config: System configuration and vegetable database.
- CV: Computer vision and camera management.
- Workflows: State machines for vegetable processing.
"""

# ============================================================================
# 1. Communications (STM32 Interface)
# ============================================================================
from .comms import (
    RaspiCommsManager,
    STM32Interface,
    CommandCode,
    ResponseStatus,
    CutterAxis,
    Response
)

# ============================================================================
# 2. Configuration
# ============================================================================
from .config import (
    ConfigManager,
    VegetableConfig,
    CutTypeConfig,
    get_config,
    set_config
)

# ============================================================================
# 3. Computer Vision
# ============================================================================
from .cv import CameraManager

# ============================================================================
# 4. Workflows (Logic & State)
# ============================================================================
from .workflows import (
    BaseWorkflow,
    WorkflowState,
    WorkflowEvent,
    WorkflowError,
    HardwareError,
    CVError,
    SafetyError,
    StandardVegetableWorkflow
)

# ============================================================================
# EXPORT LIST
# ============================================================================
__all__ = [
    # Comms
    'RaspiCommsManager',
    'STM32Interface',
    'CommandCode',
    'ResponseStatus',
    'CutterAxis',
    'Response',

    # Config
    'ConfigManager',
    'VegetableConfig',
    'CutTypeConfig',
    'get_config',
    'set_config',

    # CV
    'CameraManager',

    # Workflows
    'BaseWorkflow',
    'WorkflowState',
    'WorkflowEvent',
    'WorkflowError',
    'HardwareError',
    'CVError',
    'SafetyError',
    'StandardVegetableWorkflow'
]