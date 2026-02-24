"""
base_workflow.py

Abstract base class for all vegetable processing workflows.
Provides common workflow structure, state management, and error handling.

Author: Ficio Prep Team
Date: January 2026
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, Optional, Dict, Any
import asyncio
import logging
from datetime import datetime


class WorkflowState(Enum):
    """Workflow execution states"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    EMERGENCY_STOPPED = "emergency_stopped"


class WorkflowEvent(Enum):
    """Events that can be emitted during workflow execution"""
    STARTED = "started"
    INITIALIZED = "initialized"
    ITEM_DISPENSED = "item_dispensed"
    CV_CHECK_STARTED = "cv_check_started"
    CV_CHECK_COMPLETED = "cv_check_completed"
    CV_REJECTED = "cv_rejected"
    CV_ACCEPTED = "cv_accepted"
    CUTTING_STARTED = "cutting_started"
    CUTTING_COMPLETED = "cutting_completed"
    ITEM_COMPLETED = "item_completed"
    PAUSED = "paused"
    RESUMED = "resumed"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"
    EMERGENCY_STOPPED = "emergency_stopped"
    BAY_EMPTY = "bay_empty"
    HOPPER_EMPTY = "hopper_empty"  # Alias for BAY_EMPTY (frontend compatibility)
    WEIGHT_UPDATE = "weight_update"
    GATE_LOADED = "gate_loaded"
    DISPOSE_COMPLETE = "dispose_complete"
    ITEM_COMPLETE = "item_complete"


class BaseWorkflow(ABC):
    """
    Abstract base class for all processing workflows.
    
    Subclasses must implement:
    - setup(): Pre-workflow initialization
    - process_single_item(): Process one item
    - should_continue(): Check if workflow should continue
    - cleanup(): Post-workflow cleanup (optional)
    """
    
    def __init__(self, stm32_interface, cv_manager, update_callback: Optional[Callable] = None):
        """
        Initialize workflow.
        
        Args:
            stm32_interface: STM32Interface for hardware control
            cv_manager: CameraManager for computer vision
            update_callback: Async callback for status updates (receives event dict)
        """
        self.stm32 = stm32_interface
        self.cv = cv_manager
        self.update_callback = update_callback
        
        # State management
        self.state = WorkflowState.IDLE
        self._stop_requested = False
        self._pause_requested = False
        self._stop_after_current = False
        
        # Metrics
        self.total_items = 0
        self.successful_items = 0
        self.cv_rejected_items = 0
        self.errors = 0
        self.start_time = None
        self.end_time = None
        
        # Logging
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Workflow metadata (set by subclass)
        self.workflow_name = "BaseWorkflow"
        self.vegetable_type = "unknown"
        self.cut_type = "unknown"
        self.bay_id = 0
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    async def run(self):
        """
        Main workflow execution loop.
        Handles initialization, item processing, and cleanup.
        """
        try:
            # Initialize
            self.state = WorkflowState.INITIALIZING
            self.start_time = datetime.now()
            await self._emit_event(WorkflowEvent.STARTED)
            
            self.logger.info(f"Starting workflow: {self.workflow_name}")
            
            # Run setup
            await self.setup()
            
            self.state = WorkflowState.RUNNING
            await self._emit_event(WorkflowEvent.INITIALIZED)
            
            # Main processing loop
            while self.state == WorkflowState.RUNNING:
                # Check for stop/pause requests
                if self._stop_requested:
                    self.logger.info("Stop requested")
                    break

                if self._stop_after_current:
                    self.logger.info("Graceful stop: stopping after current item completed")
                    break

                if self._pause_requested:
                    await self._handle_pause()
                    continue

                # Process single item
                try:
                    success = await self.process_single_item()
                    
                    self.total_items += 1
                    
                    if success:
                        self.successful_items += 1
                        await self._emit_event(
                            WorkflowEvent.ITEM_COMPLETED,
                            {"success": True}
                        )
                    else:
                        self.errors += 1
                        await self._emit_event(
                            WorkflowEvent.ITEM_COMPLETED,
                            {"success": False}
                        )
                    
                except Exception as e:
                    self.logger.error(f"Error processing item: {e}", exc_info=True)
                    self.errors += 1
                    await self._emit_event(
                        WorkflowEvent.ERROR,
                        {"message": str(e)}
                    )
                
                # Check if should continue
                if not await self.should_continue():
                    self.logger.info("Workflow completion condition met")
                    break
            
            # Cleanup
            await self.cleanup()
            
            self.end_time = datetime.now()
            self.state = WorkflowState.COMPLETED
            await self._emit_event(WorkflowEvent.COMPLETED)
            
            self.logger.info(
                f"Workflow completed: {self.successful_items}/{self.total_items} successful, "
                f"{self.cv_rejected_items} rejected, {self.errors} errors"
            )
            
        except Exception as e:
            self.logger.error(f"Workflow fatal error: {e}", exc_info=True)
            self.state = WorkflowState.ERROR
            await self._emit_event(
                WorkflowEvent.ERROR,
                {"message": f"Fatal error: {str(e)}"}
            )
            raise
    
    async def pause(self):
        """Request workflow pause."""
        if self.state == WorkflowState.RUNNING:
            self._pause_requested = True
            self.logger.info("Pause requested")
    
    async def resume(self):
        """Resume paused workflow."""
        if self.state == WorkflowState.PAUSED:
            self._pause_requested = False
            self.state = WorkflowState.RUNNING
            await self._emit_event(WorkflowEvent.RESUMED)
            self.logger.info("Workflow resumed")
    
    async def stop(self):
        """Request workflow stop."""
        self._stop_requested = True
        self.logger.info("Stop requested")
        await self._emit_event(WorkflowEvent.STOPPED)

    async def stop_after_current(self):
        """Request workflow stop after current item completes (graceful stop).

        Unlike stop(), this does NOT interrupt the current item.
        The workflow finishes process_single_item() and then checks the flag
        at the top of the main loop before starting the next item.
        """
        self._stop_after_current = True
        self.logger.info("Graceful stop requested — will stop after current item")

    async def emergency_stop(self):
        """Emergency stop all operations."""
        self.logger.warning("Emergency stop activated")
        self.stm32.emergency_stop()
        self.state = WorkflowState.EMERGENCY_STOPPED
        await self._emit_event(WorkflowEvent.EMERGENCY_STOPPED)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current workflow metrics.
        
        Returns:
            Dictionary of metrics
        """
        duration = None
        if self.start_time:
            end = self.end_time or datetime.now()
            duration = (end - self.start_time).total_seconds()
        
        return {
            "workflow_name": self.workflow_name,
            "vegetable_type": self.vegetable_type,
            "cut_type": self.cut_type,
            "bay_id": self.bay_id,
            "state": self.state.value,
            "total_items": self.total_items,
            "successful_items": self.successful_items,
            "cv_rejected_items": self.cv_rejected_items,
            "errors": self.errors,
            "success_rate": self._calculate_success_rate(),
            "duration_seconds": duration,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }
    
    # ========================================================================
    # ABSTRACT METHODS (must be implemented by subclasses)
    # ========================================================================
    
    @abstractmethod
    async def setup(self):
        """Pre-workflow setup. Called once before processing begins."""
        pass
    
    @abstractmethod
    async def process_single_item(self) -> bool:
        """
        Process one item through the workflow.
        
        Returns:
            True if item was successfully processed, False otherwise
        """
        pass
    
    @abstractmethod
    async def should_continue(self) -> bool:
        """
        Check if workflow should continue processing.
        
        Returns:
            True to continue, False to stop
        """
        pass
    
    async def cleanup(self):
        """
        Post-workflow cleanup.
        Called once after processing completes.
        
        Override if needed. Default implementation does nothing.
        """
        pass
    
    # ========================================================================
    # HELPER METHODS (available to subclasses)
    # ========================================================================
    
    async def _emit_event(self, event: WorkflowEvent, data: Optional[Dict[str, Any]] = None):
        """Emit a workflow event via the update callback."""
        if self.update_callback:
            event_data = {
                "event": event.value,
                "workflow_name": self.workflow_name,
                "state": self.state.value,
                "bay_id": self.bay_id,
                "metrics": {
                    "total": self.total_items,
                    "successful": self.successful_items,
                    "cv_rejected": self.cv_rejected_items,
                    "errors": self.errors,
                    "success_rate": self._calculate_success_rate()
                }
            }
            
            if data:
                event_data.update(data)
            
            try:
                await self.update_callback(event_data)
            except Exception as e:
                self.logger.error(f"Error in update callback: {e}")
    
    async def _handle_pause(self):
        """Handle pause state."""
        if self.state != WorkflowState.PAUSED:
            self.state = WorkflowState.PAUSED
            await self._emit_event(WorkflowEvent.PAUSED)
            self.logger.info("Workflow paused")
        
        # Wait until resumed or stopped
        while self._pause_requested and not self._stop_requested:
            await asyncio.sleep(0.1)
    
    def _calculate_success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_items == 0:
            return 100.0
        return round((self.successful_items / self.total_items) * 100, 1)
    
    async def _wait_async(self, seconds: float):
        """Async sleep with pause/stop checking."""
        elapsed = 0.0
        interval = 0.05  # Check every 50ms
        
        while elapsed < seconds:
            if self._stop_requested or self._pause_requested:
                break
            
            await asyncio.sleep(min(interval, seconds - elapsed))
            elapsed += interval


# ============================================================================
# WORKFLOW EXCEPTIONS
# ============================================================================

class WorkflowError(Exception):
    """Base exception for workflow errors."""
    pass


class HardwareError(WorkflowError):
    """Hardware communication or operation error."""
    pass


class CVError(WorkflowError):
    """Computer vision processing error."""
    pass


class SafetyError(WorkflowError):
    """Safety-related error (e.g., bay empty, sensor failure)."""
    pass