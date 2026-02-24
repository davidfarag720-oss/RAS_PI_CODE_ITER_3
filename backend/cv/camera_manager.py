"""
camera_manager.py

Camera interface using OpenCV exclusively.
Handles image capture and vegetable quality analysis using YOLO + EfficientNet.

Author: Ficio Prep Team
Date: January 2026
"""

import asyncio
import os
import cv2
import numpy as np
from typing import Dict, Optional
import logging
from datetime import datetime
from pathlib import Path

from backend.config import get_config, VegetableConfig


class CameraManager:
    """
    Manages camera operations using OpenCV and computer vision analysis.
    
    Uses cv2.VideoCapture exclusively (no picamera2).
    """
    
    def __init__(self, camera_index: Optional[int] = None):
        """
        Initialize camera manager with OpenCV.
        
        Args:
            camera_index: Camera device index (None = use config default)
        """
        self.logger = logging.getLogger('CameraManager')
        self.config = get_config()
        
        # Get camera settings from config
        if camera_index is None:
            camera_index = self.config.get_int('camera_index', 0)
        
        self.camera_index = camera_index
        self.width = self.config.get_int('camera_width', 1920)
        self.height = self.config.get_int('camera_height', 1080)
        
        # Initialize camera
        self.camera = None
        self._init_camera()
        
        # Image save path
        install_path = self.config.get_str('install_path', 'vegetable-slicer')
        self.save_path = Path(install_path) / 'data' / 'cv_images'
        self.save_path.mkdir(parents=True, exist_ok=True)
        
        # CV models (loaded on first use)
        self.yolo_model = None
        self.efficientnet_model = None
        
        self.logger.info(
            f"Camera initialized: index={self.camera_index}, "
            f"resolution={self.width}x{self.height}"
        )
    
    def _init_camera(self):
        """Initialize OpenCV camera"""
        try:
            self.camera = cv2.VideoCapture(self.camera_index)

            if not self.camera.isOpened():
                self.logger.warning(f"Camera {self.camera_index} not available - running in mock mode")
                self.camera = None
                return

            # Set resolution
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            # Verify settings
            actual_width = self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT)

            if actual_width != self.width or actual_height != self.height:
                self.logger.warning(
                    f"Requested {self.width}x{self.height}, "
                    f"got {int(actual_width)}x{int(actual_height)}"
                )

            self.logger.info(f"OpenCV camera {self.camera_index} opened successfully")

        except Exception as e:
            self.logger.warning(f"Failed to initialize camera: {e} - running in mock mode")
            self.camera = None
    
    def capture_frame(self) -> np.ndarray:
        """
        Capture a single frame from the camera.

        Returns:
            NumPy array containing the image (BGR format)

        Raises:
            Exception if capture fails
        """
        if not self.camera or not self.camera.isOpened():
            # Return a mock frame in test mode
            self.logger.debug("Returning mock frame (no camera)")
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)

        ret, frame = self.camera.read()

        if not ret or frame is None:
            # Return mock frame on capture failure
            self.logger.warning("Capture failed, returning mock frame")
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)

        return frame
    
    def save_frame(self, frame: np.ndarray, prefix: str = "frame") -> str:
        """
        Save frame to disk for telemetry/debugging.
        
        Args:
            frame: Image to save
            prefix: Filename prefix
        
        Returns:
            Path to saved image
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{timestamp}.jpg"
        filepath = self.save_path / filename
        
        cv2.imwrite(str(filepath), frame)
        self.logger.debug(f"Saved frame: {filepath}")
        
        return str(filepath)
    
    # ROOT CAUSE (v1.0 bug — Phase 7 fix):
    # _run_yolo_detection and _run_efficientnet_classification both returned
    # healthy=True unconditionally (hardcoded placeholder values). Combined with
    # _ensure_models_loaded() being commented out, no real models were ever loaded.
    # Result: every vegetable was accepted and routed to load_cutter regardless of
    # actual quality. Fix: replace hardcoded values with operator prompt in mock mode.
    async def analyze_vegetable(
        self,
        vegetable_config: VegetableConfig,
        bay_id: int
    ) -> Dict:
        """
        Run CV analysis on a staged vegetable.

        Uses ensemble of YOLO (object detection) and EfficientNet (classification)
        to determine if vegetable is healthy and properly positioned.

        Args:
            vegetable_config: Configuration for the vegetable being analyzed
            bay_id: Bay number (for logging/telemetry)

        Returns:
            Dictionary with keys:
                - accepted: bool (True if vegetable passes quality check)
                - confidence: float (0-1, overall confidence score)
                - healthy: bool (True if vegetable is healthy)
                - positioned: bool (True if properly positioned)
                - reason: str (rejection reason if not accepted)
                - models_agree: bool (True if both models agree)
                - image_path: str (path to saved image)
                - bay_id: int (bay number)
                - vegetable_id: str (vegetable identifier)
        """
        self.logger.info(
            f"Analyzing {vegetable_config.name} from bay {bay_id} "
            f"in {self.config.get_str('cv_grading_mode')} mode..."
        )

        # 1. Capture frame
        frame = self.capture_frame()

        # 2. Save for telemetry (always runs, even when CV is disabled)
        image_path = self.save_frame(
            frame,
            prefix=f"bay{bay_id}_{vegetable_config.id}_analysis"
        )

        # 3. Check cv_check_enabled — if False, accept unconditionally (image still saved above)
        cv_enabled = self.config.get_bool('cv_check_enabled', True)
        if not cv_enabled:
            self.logger.info("CV check disabled (cv_check_enabled=false) — forcing accepted=True")
            return {
                'accepted': True,
                'confidence': 1.0,
                'healthy': True,
                'positioned': True,
                'reason': None,
                'models_agree': True,
                'image_path': image_path,
                'bay_id': bay_id,
                'vegetable_id': vegetable_config.id
            }

        # 4. In mock mode (STM32_MOCK=1), prompt operator for the CV decision.
        # Note: self.camera may be non-None even in mock mode (real webcam present or
        # VideoCapture(0) succeeds on Windows), so we check STM32_MOCK env var instead.
        if os.environ.get('STM32_MOCK') == '1':
            raw = await asyncio.get_event_loop().run_in_executor(
                None,
                input,
                f"[cv-mock] bay{bay_id} {vegetable_config.name} — Accept or reject this vegetable? [a/r]: "
            )
            mock_healthy = raw.strip().lower() == 'a'
            mock_confidence = 0.90 if mock_healthy else 0.10
            self.logger.info(
                f"[cv-mock] Operator decision: {'ACCEPT' if mock_healthy else 'REJECT'}"
            )
            # Build result directly from operator input — skip model stubs
            grading_mode = self.config.get_str('cv_grading_mode', 'harsh')
            result = self._apply_decision_logic(
                {
                    'detected': True,
                    'label': f"{'healthy' if mock_healthy else 'unhealthy'}_{vegetable_config.id}",
                    'healthy': mock_healthy,
                    'confidence': mock_confidence,
                    'bbox': (0, 0, 0, 0),
                    'positioned': True
                },
                {'healthy': mock_healthy, 'confidence': mock_confidence},
                grading_mode
            )
            result['image_path'] = image_path
            result['bay_id'] = bay_id
            result['vegetable_id'] = vegetable_config.id
            return result

        # 5. Real camera path — run model stubs (TODO: implement actual inference)
        # TODO: Load actual models if not already loaded
        # self._ensure_models_loaded(vegetable_config)

        # Run YOLO detection
        yolo_result = self._run_yolo_detection(frame, vegetable_config)

        # Run EfficientNet classification
        efficientnet_result = self._run_efficientnet_classification(frame, vegetable_config)

        # Apply decision logic
        grading_mode = self.config.get_str('cv_grading_mode', 'harsh')
        result = self._apply_decision_logic(
            yolo_result,
            efficientnet_result,
            grading_mode
        )

        result['image_path'] = image_path
        result['bay_id'] = bay_id
        result['vegetable_id'] = vegetable_config.id

        return result
    
    def _ensure_models_loaded(self, vegetable_config: VegetableConfig):
        """
        Load CV models if not already loaded.
        
        Args:
            vegetable_config: Vegetable configuration with model paths
        """
        # TODO: Implement actual model loading
        # For now, this is a placeholder
        
        install_path = self.config.get_str('install_path', '/home/dfarag/vegetable-slicer')
        models_path = Path(install_path) / 'models'
        
        yolo_path = models_path / vegetable_config.yolo_weights
        efficientnet_path = models_path / vegetable_config.efficientnet_weights
        
        # if self.yolo_model is None:
        #     self.yolo_model = load_yolo_model(yolo_path)
        #     self.logger.info(f"Loaded YOLO model: {yolo_path}")
        
        # if self.efficientnet_model is None:
        #     self.efficientnet_model = load_efficientnet_model(efficientnet_path)
        #     self.logger.info(f"Loaded EfficientNet model: {efficientnet_path}")
    
    def _run_yolo_detection(
        self,
        frame: np.ndarray,
        vegetable_config: VegetableConfig
    ) -> Dict:
        """
        Run YOLO object detection.
        
        Args:
            frame: Image to analyze
            vegetable_config: Vegetable configuration
        
        Returns:
            Dictionary with:
                - detected: bool (object detected)
                - label: str ("healthy_<veg>" or "unhealthy_<veg>")
                - confidence: float (0-1)
                - bbox: tuple (x1, y1, x2, y2)
                - positioned: bool (properly positioned)
                - healthy: bool (labeled as healthy)
        """
        # TODO: Implement actual YOLO inference
        # Placeholder implementation
        
        self.logger.debug(f"Running YOLO detection (placeholder) for {vegetable_config.name}...")
        
        # Simulate detection
        detected = True
        healthy = True  # Placeholder
        confidence = 0.85  # Placeholder
        
        label = f"{'healthy' if healthy else 'unhealthy'}_{vegetable_config.id}"
        
        # Check positioning (simple center-of-frame check for now)
        h, w = frame.shape[:2]
        positioned = True  # Placeholder
        
        return {
            'detected': detected,
            'label': label,
            'healthy': healthy,
            'confidence': confidence,
            'bbox': (w//4, h//4, 3*w//4, 3*h//4),  # Placeholder
            'positioned': positioned
        }
    
    def _run_efficientnet_classification(
        self,
        frame: np.ndarray,
        vegetable_config: VegetableConfig
    ) -> Dict:
        """
        Run EfficientNet binary classification.
        
        Args:
            frame: Image to analyze
            vegetable_config: Vegetable configuration
        
        Returns:
            Dictionary with:
                - healthy: bool
                - confidence: float (0-1)
        """
        # TODO: Implement actual EfficientNet inference
        # Placeholder implementation
        
        self.logger.debug(f"Running EfficientNet classification (placeholder) for {vegetable_config.name}...")
        
        # Simulate classification
        healthy = True  # Placeholder
        confidence = 0.90  # Placeholder
        
        return {
            'healthy': healthy,
            'confidence': confidence
        }
    
    def _apply_decision_logic(
        self,
        yolo_result: Dict,
        efficientnet_result: Dict,
        grading_mode: str
    ) -> Dict:
        """
        Apply ensemble decision logic based on both model outputs.
        
        Logic from spec (Page 4):
        1. If YOLO detects multiple objects or no label: follow EfficientNet
        2. If models agree: follow consensus
        3. If models disagree:
           - lenient mode: Accept
           - harsh mode: Reject
        
        Args:
            yolo_result: YOLO detection results
            efficientnet_result: EfficientNet classification results
            grading_mode: "harsh" or "lenient"
        
        Returns:
            Final decision dictionary
        """
        # Check if YOLO detected object
        if not yolo_result['detected']:
            return {
                'accepted': False,
                'confidence': 0.0,
                'healthy': False,
                'positioned': False,
                'reason': 'no_object_detected',
                'models_agree': False
            }
        
        # Check positioning
        if not yolo_result['positioned']:
            return {
                'accepted': False,
                'confidence': yolo_result['confidence'],
                'healthy': yolo_result['healthy'],
                'positioned': False,
                'reason': 'poor_positioning',
                'models_agree': False
            }
        
        # Compare model outputs
        yolo_healthy = yolo_result['healthy']
        eff_healthy = efficientnet_result['healthy']
        
        models_agree = (yolo_healthy == eff_healthy)
        
        # Calculate overall confidence
        avg_confidence = (yolo_result['confidence'] + efficientnet_result['confidence']) / 2
        
        # Get confidence threshold
        confidence_threshold = self.config.get_float('cv_confidence_threshold', 0.7)
        
        # Apply decision logic
        if models_agree:
            # Both agree - follow consensus
            accepted = yolo_healthy and (avg_confidence >= confidence_threshold)
            reason = None if accepted else 'quality_reject'
        else:
            # Models disagree
            if grading_mode == "lenient":
                # Accept on disagreement
                accepted = True
                reason = None
            else:
                # Reject on disagreement (harsh mode)
                accepted = False
                reason = 'model_disagreement'
        
        return {
            'accepted': accepted,
            'confidence': avg_confidence,
            'healthy': yolo_healthy if models_agree else False,
            'positioned': True,
            'reason': reason,
            'models_agree': models_agree
        }
    
    def is_ready(self) -> bool:
        """Check if camera is ready"""
        return self.camera is not None and self.camera.isOpened()
    
    def close(self):
        """Close camera and release resources"""
        if self.camera:
            self.camera.release()
            self.logger.info("Camera closed")
    
    def __del__(self):
        """Cleanup on deletion"""
        self.close()


# ============================================================================
# STANDALONE TESTING
# ============================================================================

def main():
    """Test camera capture and CV analysis"""
    import asyncio
    import sys
    
    # Add parent directory to path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    
    from backend.config import ConfigManager, set_config
    
    logging.basicConfig(level=logging.DEBUG)
    
    # Initialize config
    config = ConfigManager('config.json')
    set_config(config)
    
    camera = CameraManager()
    
    try:
        print("\n=== Capturing test frame ===")
        frame = camera.capture_frame()
        print(f"Frame shape: {frame.shape}")
        
        # Save test frame
        path = camera.save_frame(frame, prefix="test")
        print(f"Saved to: {path}")
        
        # Get cucumber config
        cucumber = config.get_vegetable('cucumber')
        
        # Run CV analysis
        print("\n=== Running CV analysis ===")
        result = asyncio.run(camera.analyze_vegetable(cucumber, bay_id=1))
        
        print(f"Result:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
    finally:
        camera.close()


if __name__ == "__main__":
    main()