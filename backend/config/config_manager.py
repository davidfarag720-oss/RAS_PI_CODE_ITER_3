"""
config_manager.py

Configuration manager that loads system settings from config.json.
Provides runtime access to vegetables, cut types, and system settings.

Author: Ficio Prep Team
Date: January 2026
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class VegetableConfig:
    """Configuration for a vegetable type"""
    name: str
    id: str
    image_path: str
    yolo_weights: str
    efficientnet_weights: str
    supported_cuts: List[str]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VegetableConfig':
        """Create VegetableConfig from dictionary"""
        return cls(
            name=data['name'],
            id=data['id'],
            image_path=data['image_path'],
            yolo_weights=data['cv_models']['yolo_weights'],
            efficientnet_weights=data['cv_models']['efficientnet_weights'],
            supported_cuts=data['supported_cuts']
        )


@dataclass
class CutTypeConfig:
    """Configuration for a cut type"""
    name: str
    display_name: str
    axis_bitmask: int
    description: str
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CutTypeConfig':
        """Create CutTypeConfig from dictionary"""
        return cls(
            name=data['name'],
            display_name=data['display_name'],
            axis_bitmask=data['axis_bitmask'],
            description=data['description']
        )


class ConfigManager:
    """
    Manages system configuration loaded from config.json.
    Provides access to vegetables, cut types, and system settings.
    """
    
    def __init__(self, config_path: str = "config.json"):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to config.json file
        """
        self.logger = logging.getLogger('ConfigManager')
        self.config_path = Path(config_path)
        
        # Configuration data
        self.system_settings: Dict[str, Any] = {}
        self.vegetables: Dict[str, VegetableConfig] = {}
        self.cut_types: Dict[str, CutTypeConfig] = {}
        
        # Load configuration
        self.reload()
    
    def reload(self):
        """Load or reload configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Load system settings
            self.system_settings = config.get('system_settings', {})
            
            # Load vegetables
            self.vegetables = {}
            for veg_data in config.get('vegetables', []):
                veg = VegetableConfig.from_dict(veg_data)
                self.vegetables[veg.id] = veg
            
            # Load cut types
            self.cut_types = {}
            for cut_name, cut_data in config.get('cut_types', {}).items():
                cut = CutTypeConfig.from_dict(cut_data)
                self.cut_types[cut.name] = cut
            
            self.logger.info(
                f"Configuration loaded: {len(self.vegetables)} vegetables, "
                f"{len(self.cut_types)} cut types, "
                f"cv_grading_mode={self.system_settings.get('cv_grading_mode', 'harsh')}, "
                f"cv_check_enabled={self.system_settings.get('cv_check_enabled', True)}"
            )
            
        except FileNotFoundError:
            self.logger.error(f"Config file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            raise
    
    # ========================================================================
    # VEGETABLE ACCESS
    # ========================================================================
    
    def get_vegetable(self, vegetable_id: str) -> Optional[VegetableConfig]:
        """
        Get vegetable configuration by ID.
        
        Args:
            vegetable_id: Vegetable ID (e.g., "cucumber")
        
        Returns:
            VegetableConfig or None if not found
        """
        return self.vegetables.get(vegetable_id)
    
    def list_vegetables(self) -> List[VegetableConfig]:
        """Get list of all vegetables"""
        return list(self.vegetables.values())
    
    def get_vegetables_dict(self) -> List[Dict[str, Any]]:
        """
        Get vegetables as list of dictionaries for API response.
        
        Returns:
            List of vegetable dictionaries
        """
        return [
            {
                'id': veg.id,
                'name': veg.name,
                'image_path': veg.image_path,
                'supported_cuts': veg.supported_cuts
            }
            for veg in self.vegetables.values()
        ]
    
    # ========================================================================
    # CUT TYPE ACCESS
    # ========================================================================
    
    def get_cut_type(self, cut_name: str) -> Optional[CutTypeConfig]:
        """
        Get cut type configuration by name.
        
        Args:
            cut_name: Cut type name (e.g., "sliced")
        
        Returns:
            CutTypeConfig or None if not found
        """
        return self.cut_types.get(cut_name)
    
    def list_cut_types(self) -> List[CutTypeConfig]:
        """Get list of all cut types"""
        return list(self.cut_types.values())
    
    def get_cut_types_dict(self) -> Dict[str, Dict[str, Any]]:
        """
        Get cut types as dictionary for API response.
        
        Returns:
            Dictionary of cut type configurations
        """
        return {
            name: {
                'name': cut.name,
                'display_name': cut.display_name,
                'axis_bitmask': cut.axis_bitmask,
                'description': cut.description
            }
            for name, cut in self.cut_types.items()
        }
    
    def is_cut_supported(self, vegetable_id: str, cut_name: str) -> bool:
        """
        Check if a cut type is supported for a vegetable.
        
        Args:
            vegetable_id: Vegetable ID
            cut_name: Cut type name
        
        Returns:
            True if supported, False otherwise
        """
        veg = self.get_vegetable(vegetable_id)
        if not veg:
            return False
        return cut_name in veg.supported_cuts
    
    # ========================================================================
    # SYSTEM SETTINGS ACCESS
    # ========================================================================
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get system setting by key.
        
        Args:
            key: Setting key
            default: Default value if key not found
        
        Returns:
            Setting value or default
        """
        return self.system_settings.get(key, default)
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get system setting as integer"""
        value = self.get(key, default)
        return int(value) if value is not None else default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get system setting as float"""
        value = self.get(key, default)
        return float(value) if value is not None else default
    
    def get_str(self, key: str, default: str = "") -> str:
        """Get system setting as string"""
        value = self.get(key, default)
        return str(value) if value is not None else default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get system setting as boolean"""
        value = self.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value) if value is not None else default

    # ========================================================================
    # HARDWARE MAPPINGS
    # ========================================================================
    
    @staticmethod
    def get_gate_for_bay(bay_id: int) -> int:
        """
        Get gate ID for a bay/hopper.
        
        Args:
            bay_id: Bay number (1-4)
        
        Returns:
            Gate ID (3-6) for hopper gates
        """
        # Gates 1-2: Cutter gates
        # Gates 3-6: Hopper gates for bays 1-4
        return bay_id + 2
    
    @staticmethod
    def get_bay_from_gate(gate_id: int) -> Optional[int]:
        """
        Get bay ID from gate ID.
        
        Args:
            gate_id: Gate ID
        
        Returns:
            Bay number (1-4) or None if not a hopper gate
        """
        if 3 <= gate_id <= 6:
            return gate_id - 2
        return None
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    def validate(self) -> bool:
        """
        Validate configuration consistency.
        
        Returns:
            True if valid, raises ValueError if invalid
        """
        # Check required system settings
        required_settings = [
            'num_cameras', 'cv_grading_mode',
            'serial_port', 'serial_baudrate'
        ]
        for setting in required_settings:
            if setting not in self.system_settings:
                raise ValueError(f"Missing required system setting: {setting}")

        # Check vegetables have valid cut types
        for veg in self.vegetables.values():
            for cut_name in veg.supported_cuts:
                if cut_name not in self.cut_types:
                    raise ValueError(
                        f"Vegetable '{veg.id}' references unknown cut type: {cut_name}"
                    )
        
        self.logger.info("✓ Configuration validated successfully")
        return True


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

# Global config manager instance (initialized by main app)
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def set_config(config_manager: ConfigManager):
    """Set global config manager instance"""
    global _config_manager
    _config_manager = config_manager
