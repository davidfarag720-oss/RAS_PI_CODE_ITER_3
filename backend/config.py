"""
config.py

System configuration for the Vegetable Processing System.
All hardware mappings, cut definitions, and system parameters.

Author: Ficio Prep Team
Date: January 2026
"""

from enum import IntEnum
from typing import Dict, List
from dataclasses import dataclass


# ============================================================================
# HARDWARE MAPPINGS
# ============================================================================

class HardwareMap:
    """Hardware component mappings"""
    
    # Gate mappings
    GATE_CUTTER_TOP = 1      # Top cutter gate (entry to cutting chamber)
    GATE_CUTTER_BOTTOM = 2   # Bottom cutter gate (exit from cutting chamber)
    GATE_HOPPER_1 = 3        # Hopper 1 gate
    GATE_HOPPER_2 = 4        # Hopper 2 gate
    GATE_HOPPER_3 = 5        # Hopper 3 gate
    GATE_HOPPER_4 = 6        # Hopper 4 gate
    
    # Hopper IDs
    HOPPER_1 = 1
    HOPPER_2 = 2
    HOPPER_3 = 3
    HOPPER_4 = 4
    
    # Cutter axis bitmasks (for CMD_CUT_EXECUTE)
    CUTTER_X = 0b001  # Cutter 1 - Vertical X-axis
    CUTTER_Y = 0b010  # Cutter 2 - Vertical Y-axis
    CUTTER_Z = 0b100  # Cutter 3 - Horizontal Z-axis


# ============================================================================
# CUT TYPE DEFINITIONS
# ============================================================================

class CutType(IntEnum):
    """Supported cut types"""
    LONG_FRY = 1    # Cutters X+Y (longitudinal sticks)
    SHORT_FRY = 2   # Cutters X+Z (short sticks)
    SLICED = 3      # Cutter Z only (round/flat slices)
    LONG_SLICE = 4  # Cutter X only (lengthwise slices)
    CUBED = 5       # Cutters X+Y+Z (cubes/dice)


@dataclass
class CutDefinition:
    """Definition of a cut type"""
    name: str
    display_name: str
    axis_bitmask: int  # Bitmask for cutters to activate
    description: str


# Cut type configurations
CUT_DEFINITIONS: Dict[CutType, CutDefinition] = {
    CutType.LONG_FRY: CutDefinition(
        name="long_fry",
        display_name="Long Fry",
        axis_bitmask=HardwareMap.CUTTER_X | HardwareMap.CUTTER_Y,  # 0b011
        description="Longitudinal sticks"
    ),
    CutType.SHORT_FRY: CutDefinition(
        name="short_fry",
        display_name="Short Fry",
        axis_bitmask=HardwareMap.CUTTER_X | HardwareMap.CUTTER_Z,  # 0b101
        description="Short sticks"
    ),
    CutType.SLICED: CutDefinition(
        name="sliced",
        display_name="Sliced",
        axis_bitmask=HardwareMap.CUTTER_Z,  # 0b100
        description="Round/flat slices"
    ),
    CutType.LONG_SLICE: CutDefinition(
        name="long_slice",
        display_name="Long Slice",
        axis_bitmask=HardwareMap.CUTTER_X,  # 0b001
        description="Lengthwise slices"
    ),
    CutType.CUBED: CutDefinition(
        name="cubed",
        display_name="Cubed",
        axis_bitmask=HardwareMap.CUTTER_X | HardwareMap.CUTTER_Y | HardwareMap.CUTTER_Z,  # 0b111
        description="Cubes/dice"
    ),
}


# ============================================================================
# VEGETABLE CONFIGURATIONS
# ============================================================================

@dataclass
class VegetableConfig:
    """Configuration for a vegetable type"""
    id: str
    name: str
    display_name: str
    hopper_id: int
    supported_cuts: List[CutType]
    cv_model_yolo: str
    cv_model_efficientnet: str
    image_path: str  # For UI display


# Vegetable configurations
VEGETABLES: Dict[str, VegetableConfig] = {
    "cucumber": VegetableConfig(
        id="cucumber",
        name="cucumber",
        display_name="Cucumber",
        hopper_id=HardwareMap.HOPPER_1,
        supported_cuts=[CutType.SLICED, CutType.CUBED],
        cv_model_yolo="models/cucumber_yolo.pt",
        cv_model_efficientnet="models/cucumber_efficientnet.pth",
        image_path="assets/ui/cucumber.png"
    ),
    "carrot": VegetableConfig(
        id="carrot",
        name="carrot",
        display_name="Carrot",
        hopper_id=HardwareMap.HOPPER_2,
        supported_cuts=[CutType.LONG_FRY, CutType.SHORT_FRY, CutType.SLICED, CutType.CUBED],
        cv_model_yolo="models/carrot_yolo.pt",
        cv_model_efficientnet="models/carrot_efficientnet.pth",
        image_path="assets/ui/carrot.png"
    ),
    "tomato": VegetableConfig(
        id="tomato",
        name="tomato",
        display_name="Tomato",
        hopper_id=HardwareMap.HOPPER_3,
        supported_cuts=[CutType.SLICED, CutType.CUBED],
        cv_model_yolo="models/tomato_yolo.pt",
        cv_model_efficientnet="models/tomato_efficientnet.pth",
        image_path="assets/ui/tomato.png"
    ),
    "potato": VegetableConfig(
        id="potato",
        name="potato",
        display_name="Potato",
        hopper_id=HardwareMap.HOPPER_4,
        supported_cuts=[CutType.LONG_FRY, CutType.SHORT_FRY, CutType.CUBED],
        cv_model_yolo="models/potato_yolo.pt",
        cv_model_efficientnet="models/potato_efficientnet.pth",
        image_path="assets/ui/potato.png"
    ),
}


# ============================================================================
# SYSTEM SETTINGS
# ============================================================================

class SystemConfig:
    """System-wide configuration"""
    
    # Installation path
    INSTALL_PATH = "/home/dfarag/vegetable-slicer"
    
    # Hardware
    NUM_HOPPERS = 4
    NUM_CAMERAS = 1
    
    # Serial communication
    SERIAL_PORT = "/dev/ttyAMA0"
    SERIAL_BAUDRATE = 115200
    SERIAL_TIMEOUT = 0.1
    
    # Computer Vision
    CV_GRADING_MODE = "harsh"  # "harsh" or "lenient"
    CV_IMAGE_SAVE_PATH = f"{INSTALL_PATH}/data/cv_images"
    CV_CONFIDENCE_THRESHOLD = 0.7  # Minimum confidence for CV acceptance
    
    # Camera settings
    CAMERA_INDEX = 0  # USB camera index
    CAMERA_WIDTH = 1920
    CAMERA_HEIGHT = 1080
    
    # Workflow settings
    STAGING_DELAY = 0.3  # Seconds to wait after dispense before CV check
    GATE_DELAY = 0.2     # Seconds to wait after gate operations
    CUT_DELAY = 0.5      # Seconds to wait after cut execution
    
    # Scale settings
    SCALE_MAX_WEIGHT = 20000  # grams (20 kg)
    SCALE_TARE_ON_STARTUP = True
    
    # Database
    DATABASE_PATH = f"{INSTALL_PATH}/data/telemetry.db"
    UPLOAD_TELEMETRY_HOUR = 23  # Hour to upload telemetry (0-23)
    
    # UI settings
    UI_REFRESH_RATE = 60  # FPS for UI updates
    UI_THEME = "light"
    UI_COLORS = {
        "primary": "#4CAF50",    # Green
        "secondary": "#9E9E9E",  # Grey
        "background": "#FFFFFF", # White
        "text": "#212121",
        "error": "#F44336",
        "warning": "#FF9800"
    }
    
    # Safety
    EMERGENCY_STOP_ENABLED = True
    MAX_CONSECUTIVE_CV_FAILURES = 5  # Stop workflow after this many failures
    
    # Logging
    LOG_LEVEL = "INFO"  # "DEBUG", "INFO", "WARNING", "ERROR"
    LOG_FILE = f"{INSTALL_PATH}/logs/system.log"
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_vegetable_by_hopper(hopper_id: int) -> VegetableConfig:
    """
    Get vegetable configuration by hopper ID.
    
    Args:
        hopper_id: Hopper number (1-4)
    
    Returns:
        VegetableConfig or None if not found
    """
    for veg in VEGETABLES.values():
        if veg.hopper_id == hopper_id:
            return veg
    return None


def get_cut_definition(cut_type: CutType) -> CutDefinition:
    """
    Get cut definition by cut type.
    
    Args:
        cut_type: CutType enum value
    
    Returns:
        CutDefinition
    """
    return CUT_DEFINITIONS.get(cut_type)


def is_cut_supported(vegetable_id: str, cut_type: CutType) -> bool:
    """
    Check if a cut type is supported for a vegetable.
    
    Args:
        vegetable_id: Vegetable ID string
        cut_type: CutType enum value
    
    Returns:
        True if supported, False otherwise
    """
    veg = VEGETABLES.get(vegetable_id)
    if veg:
        return cut_type in veg.supported_cuts
    return False


def get_gate_for_hopper(hopper_id: int) -> int:
    """
    Get gate ID for a hopper.
    
    Args:
        hopper_id: Hopper number (1-4)
    
    Returns:
        Gate ID (3-6)
    """
    # Gates 3-6 map to hoppers 1-4
    return hopper_id + 2


# ============================================================================
# VALIDATION
# ============================================================================

def validate_config():
    """
    Validate configuration consistency.
    Raises ValueError if configuration is invalid.
    """
    # Check hopper IDs are unique
    hopper_ids = [veg.hopper_id for veg in VEGETABLES.values()]
    if len(hopper_ids) != len(set(hopper_ids)):
        raise ValueError("Duplicate hopper IDs in vegetable configuration")
    
    # Check hopper IDs are in valid range
    for hopper_id in hopper_ids:
        if hopper_id < 1 or hopper_id > SystemConfig.NUM_HOPPERS:
            raise ValueError(f"Invalid hopper ID: {hopper_id}")
    
    # Check all vegetables have valid cut types
    for veg in VEGETABLES.values():
        for cut_type in veg.supported_cuts:
            if cut_type not in CUT_DEFINITIONS:
                raise ValueError(f"Invalid cut type {cut_type} for {veg.name}")
    
    print("✓ Configuration validated successfully")


# Run validation on import
if __name__ == "__main__":
    validate_config()