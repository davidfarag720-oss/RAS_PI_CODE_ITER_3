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
import importlib
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
        self.stream_width = self.config.get_int('stream_width', 1280)
        self.stream_height = self.config.get_int('stream_height', 720)
        self.stream_fps = self.config.get_int('stream_fps', 30)

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
        self.models_ready = False
        self.model_status = {"yolo": False, "efficientnet": False}
        self._loaded_model_keys = {"yolo": None, "efficientnet": None}
        self._active_vegetable_id = None
        self._model_cache = {}

        # Preload configured CV models at startup so failures are visible early.
        self._preload_models_on_startup()
        
        self.logger.info(
            f"Camera initialized: index={self.camera_index}, "
            f"resolution={self.width}x{self.height}, "
            f"stream={self.stream_width}x{self.stream_height}@{self.stream_fps}fps, "
            f"cv_grading_mode={self.config.get_str('cv_grading_mode', 'harsh')}, "
            f"cv_check_enabled={self.config.get_bool('cv_check_enabled', True)}"
        )

    def _preload_models_on_startup(self):
        """Preload CV models for all configured vegetables during service startup."""
        try:
            vegetables = self.config.list_vegetables()
            if not vegetables:
                self.logger.warning("No vegetables configured; skipping CV model preload")
                return

            self.logger.info("Preloading CV models on startup...")
            for veg in vegetables:
                self.logger.info(f"Preloading models for vegetable={veg.id}")
                self._ensure_models_loaded(veg)
            self.logger.info("CV model preload complete")
        except Exception as e:
            self.logger.error(f"Startup CV preload failed: {e}", exc_info=True)

    def _init_camera(self):
        """Initialize OpenCV camera"""
        try:
            self.camera = cv2.VideoCapture(self.camera_index)

            if not self.camera.isOpened():
                self.logger.warning(f"Camera {self.camera_index} not available - running in mock mode")
                self.camera = None
                return

            # Set resolution and FPS
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.camera.set(cv2.CAP_PROP_FPS, self.stream_fps)

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

    def capture_stream_frame(self) -> np.ndarray:
        """
        Capture a frame for live streaming at the configured stream resolution.

        Captures from the main camera and resizes to stream_width x stream_height.
        MSMF/V4L2 only allow one VideoCapture per device, so a separate handle
        is not used.

        Returns:
            NumPy array (BGR) at stream_width x stream_height
        """
        frame = self.capture_frame()
        if frame.shape[1] != self.stream_width or frame.shape[0] != self.stream_height:
            frame = cv2.resize(frame, (self.stream_width, self.stream_height))
        return frame

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
            self.logger.warning("Capture source unavailable; returning mock frame (all zeros)")
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)

        ret, frame = self.camera.read()

        if not ret or frame is None:
            # Return mock frame on capture failure
            self.logger.error("Capture failed from camera.read(); returning mock frame")
            return np.zeros((self.height, self.width, 3), dtype=np.uint8)
        self.logger.debug(f"Captured frame successfully: shape={frame.shape}, dtype={frame.dtype}")

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

        # 5. Real camera path — validate model files / load status before inference
        self._ensure_models_loaded(vegetable_config)

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
        install_path = self.config.get_str('install_path', '/home/dfarag/vegetable-slicer')
        models_path = Path(install_path) / 'models'
        
        yolo_path = models_path / vegetable_config.yolo_weights
        efficientnet_path = models_path / vegetable_config.efficientnet_weights
        self._active_vegetable_id = vegetable_config.id
        cache_key = vegetable_config.id
        if cache_key in self._model_cache:
            cached = self._model_cache[cache_key]
            self.yolo_model = cached.get("yolo_model")
            self.efficientnet_model = cached.get("efficientnet_model")
            self.model_status = dict(cached.get("model_status", self.model_status))
            self._loaded_model_keys = dict(cached.get("loaded_keys", self._loaded_model_keys))
            self.models_ready = all(self.model_status.values())
            return
        
        self.model_status["yolo"] = yolo_path.exists()
        self.model_status["efficientnet"] = efficientnet_path.exists()

        if self.model_status["yolo"]:
            self.logger.info(f"YOLO weights found: {yolo_path}")
        else:
            self.logger.error(f"YOLO weights missing: {yolo_path}")

        if self.model_status["efficientnet"]:
            self.logger.info(f"EfficientNet weights found: {efficientnet_path}")
        else:
            self.logger.error(f"EfficientNet weights missing: {efficientnet_path}")

        # Load YOLO model object if needed
        yolo_key = str(yolo_path)
        if self.model_status["yolo"] and self._loaded_model_keys["yolo"] != yolo_key:
            try:
                ultralytics = importlib.import_module("ultralytics")
                self.yolo_model = ultralytics.YOLO(str(yolo_path))
                self._loaded_model_keys["yolo"] = yolo_key
                self.logger.info(f"YOLO model loaded successfully: {yolo_path}")
            except Exception as e:
                self.yolo_model = None
                self.logger.error(f"Failed to load YOLO model from {yolo_path}: {e}", exc_info=True)

        # Load EfficientNet classifier object if needed
        efficientnet_key = str(efficientnet_path)
        if self.model_status["efficientnet"] and self._loaded_model_keys["efficientnet"] != efficientnet_key:
            try:
                torch = importlib.import_module("torch")
                self.efficientnet_model = torch.load(str(efficientnet_path), map_location="cpu")
                # Torch checkpoints may contain wrapper dicts; keep raw object and
                # handle structure in inference path.
                if hasattr(self.efficientnet_model, "eval"):
                    self.efficientnet_model.eval()
                self._loaded_model_keys["efficientnet"] = efficientnet_key
                self.logger.info(f"EfficientNet model loaded successfully: {efficientnet_path}")
            except Exception as e:
                self.efficientnet_model = None
                self.logger.error(
                    f"Failed to load EfficientNet model from {efficientnet_path}: {e}",
                    exc_info=True
                )

        self.model_status["yolo"] = self.model_status["yolo"] and (self.yolo_model is not None)
        self.model_status["efficientnet"] = self.model_status["efficientnet"] and (self.efficientnet_model is not None)
        self.models_ready = all(self.model_status.values())
        self._model_cache[cache_key] = {
            "yolo_model": self.yolo_model,
            "efficientnet_model": self.efficientnet_model,
            "model_status": dict(self.model_status),
            "loaded_keys": dict(self._loaded_model_keys),
        }

        if not self.models_ready:
            self.logger.error("CV models are not ready; inference will fail-closed (reject)")
    
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
        
        if not self.model_status["yolo"] or self.yolo_model is None:
            return {
                'detected': False,
                'label': None,
                'healthy': False,
                'confidence': 0.0,
                'bbox': None,
                'positioned': False,
                'object_count': 0,
                'reason': 'yolo_weights_missing'
            }

        h, w = frame.shape[:2]
        try:
            results = self.yolo_model.predict(source=frame, verbose=False)
            if not results:
                return {
                    'detected': False, 'label': None, 'healthy': False, 'confidence': 0.0,
                    'bbox': None, 'positioned': False, 'object_count': 0, 'reason': 'no_yolo_results'
                }
            result = results[0]
            boxes = getattr(result, "boxes", None)
            object_count = len(boxes) if boxes is not None else 0
            if object_count == 0:
                return {
                    'detected': False, 'label': None, 'healthy': False, 'confidence': 0.0,
                    'bbox': None, 'positioned': False, 'object_count': 0, 'reason': 'no_object_detected'
                }
            detected = True
            top_box = boxes[0]
            conf = float(top_box.conf.item()) if hasattr(top_box, "conf") else 0.0
            cls_id = int(top_box.cls.item()) if hasattr(top_box, "cls") else -1
            names = getattr(result, "names", {}) or {}
            class_name = names.get(cls_id) if isinstance(names, dict) else None
            label = class_name if class_name else f"class_{cls_id}"
            # Label convention: healthy_* vs unhealthy_*
            healthy = label.startswith("healthy")
            xyxy = top_box.xyxy[0].tolist() if hasattr(top_box, "xyxy") else [0, 0, w, h]
            x1, y1, x2, y2 = [int(v) for v in xyxy]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            positioned = (0.2 * w) <= cx <= (0.8 * w) and (0.2 * h) <= cy <= (0.8 * h)
            confidence = max(0.0, min(1.0, conf))
        except Exception as e:
            self.logger.error(f"YOLO inference failed: {e}", exc_info=True)
            return {
                'detected': False, 'label': None, 'healthy': False, 'confidence': 0.0,
                'bbox': None, 'positioned': False, 'object_count': 0, 'reason': 'yolo_inference_error'
            }
        
        return {
            'detected': detected,
            'label': label,
            'healthy': healthy,
            'confidence': confidence,
            'bbox': (x1, y1, x2, y2),
            'positioned': positioned,
            'object_count': object_count,
            'reason': None
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
        
        if not self.model_status["efficientnet"] or self.efficientnet_model is None:
            return {
                'healthy': False,
                'confidence': 0.0,
                'reason': 'efficientnet_weights_missing'
            }
        try:
            torch = importlib.import_module("torch")
            # Minimal preprocessing (BGR->RGB, resize, normalize to [0,1])
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, (224, 224))
            tensor = torch.from_numpy(resized).float().permute(2, 0, 1).unsqueeze(0) / 255.0

            model_obj = self.efficientnet_model
            if isinstance(model_obj, dict):
                # Common checkpoint patterns
                for key in ("model", "net", "classifier"):
                    if key in model_obj:
                        model_obj = model_obj[key]
                        break
            if not hasattr(model_obj, "__call__"):
                raise RuntimeError("EfficientNet checkpoint did not contain callable model")

            with torch.no_grad():
                logits = model_obj(tensor)
            if hasattr(logits, "squeeze"):
                logits = logits.squeeze()
            probs = torch.sigmoid(logits) if logits.ndim == 0 else torch.softmax(logits, dim=-1)

            if probs.ndim == 0:
                p_healthy = float(probs.item())
            else:
                if probs.shape[-1] < 2:
                    p_healthy = float(probs.flatten()[0].item())
                else:
                    p_healthy = float(probs.flatten()[-1].item())
            healthy = p_healthy >= 0.5
            confidence = p_healthy if healthy else (1.0 - p_healthy)
        except Exception as e:
            self.logger.error(f"EfficientNet inference failed: {e}", exc_info=True)
            return {'healthy': False, 'confidence': 0.0, 'reason': 'efficientnet_inference_error'}
        
        return {
            'healthy': healthy,
            'confidence': confidence,
            'reason': None
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
        self.logger.info(
            "CV decision inputs: yolo=%s eff=%s grading_mode=%s",
            yolo_result,
            efficientnet_result,
            grading_mode
        )
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
        
        # Check multi-object/no-label fallback to EfficientNet
        if yolo_result.get('object_count', 1) != 1 or not yolo_result.get('label'):
            eff_healthy = efficientnet_result['healthy']
            self.logger.info(
                "YOLO ambiguous (object_count=%s, label=%s) -> following EfficientNet=%s",
                yolo_result.get('object_count'),
                yolo_result.get('label'),
                eff_healthy
            )
            return {
                'accepted': eff_healthy,
                'confidence': efficientnet_result['confidence'],
                'healthy': eff_healthy,
                'positioned': yolo_result.get('positioned', False),
                'reason': None if eff_healthy else 'efficientnet_reject',
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
        
        final = {
            'accepted': accepted,
            'confidence': avg_confidence,
            'healthy': yolo_healthy if models_agree else False,
            'positioned': True,
            'reason': reason,
            'models_agree': models_agree
        }
        self.logger.info("CV final decision: %s", final)
        return final
    
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
