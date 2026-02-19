"""
task_manager.py

Task manager for coordinating workflow execution.
Handles task queueing, execution, and status tracking.

Author: Ficio Prep Team
Date: February 2026
"""

import asyncio
import logging
import random
from typing import Dict, List, Optional, Set
from datetime import datetime
from enum import Enum
import uuid
from dataclasses import dataclass, field


class MockSTM32Interface:
    """
    Mock STM32 interface for testing without hardware.
    Simulates hardware responses with random behavior.
    """

    def __init__(self):
        self.logger = logging.getLogger('MockSTM32')
        self._hopper_items = {1: random.randint(30, 80), 2: random.randint(30, 80),
                             3: random.randint(30, 80), 4: random.randint(30, 80)}

    async def scale_tare(self) -> bool:
        self.logger.debug("Mock: Scale tared")
        return True

    async def scale_read(self) -> float:
        return random.uniform(20.0, 100.0)

    async def is_hopper_empty(self, bay_id: int) -> bool:
        return self._hopper_items.get(bay_id, 0) <= 0

    async def hopper_dispense(self, bay_id: int) -> bool:
        if self._hopper_items.get(bay_id, 0) > 0:
            self._hopper_items[bay_id] -= 1
            self.logger.debug(f"Mock: Dispensed from bay {bay_id}, {self._hopper_items[bay_id]} remaining")
            return True
        return False

    async def gate_open(self, gate_id: int) -> bool:
        self.logger.debug(f"Mock: Gate {gate_id} opened")
        return True

    async def gate_close(self, gate_id: int) -> bool:
        self.logger.debug(f"Mock: Gate {gate_id} closed")
        return True

    async def dispose(self, gate_id: int = 1) -> None:
        self.logger.debug(f"Mock: Dispose via gate {gate_id}")

    async def load_cutter(self, gate_id: int = 1, wait_for_cutter_idle: bool = True) -> None:
        self.logger.debug(f"Mock: Load cutter via gate {gate_id}")
        await asyncio.sleep(0.1)

    async def cut(self, axis_bitmask: int) -> None:
        self.logger.debug(f"Mock: Cut with bitmask {axis_bitmask:03b}")
        await asyncio.sleep(0.2)

    async def wait_for_cutter_idle(self, timeout: float = 30.0, poll_interval: float = 0.2) -> None:
        self.logger.debug("Mock: Cutter idle")

    async def cut_execute(self, axis_bitmask: int) -> bool:
        self.logger.debug(f"Mock: Cut executed with bitmask {axis_bitmask:03b}")
        return True

    async def vibration_all_off(self) -> bool:
        return True

    async def emergency_stop(self) -> bool:
        self.logger.warning("Mock: Emergency stop")
        return True


class TaskStatus(str, Enum):
    """Task status enumeration"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """
    Represents a processing task.
    
    CRITICAL: Task runs until STM32 reports hopper is EMPTY.
    There is NO target count - the hopper determines when the task stops.
    """
    id: str
    vegetable_id: str
    vegetable_name: str
    bay_id: int
    cut_type: str
    cut_display_name: str
    workflow_class: Optional[str] = None
    
    # Status
    status: TaskStatus = TaskStatus.QUEUED
    
    # Statistics
    items_processed: int = 0
    items_rejected: int = 0
    weight_processed_grams: float = 0.0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Error tracking
    error_message: Optional[str] = None
    
    # Internal
    _workflow_instance: Optional[object] = None
    _task_future: Optional[asyncio.Task] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.items_processed + self.items_rejected
        if total == 0:
            return 0.0
        return self.items_processed / total


class TaskManager:
    """
    Manages task queue and workflow execution.
    
    CRITICAL RULES:
    1. Only ONE task runs at a time (shared cutting chamber)
    2. Only ONE task per bay (queued OR running)
    3. Task runs until STM32 reports hopper EMPTY
    4. Bay becomes available only after hopper is empty
    
    Responsibilities:
    - Queue management (FIFO)
    - Bay reservation (prevent duplicate bay tasks)
    - Workflow instantiation and execution
    - Statistics tracking
    - Error handling
    """
    
    def __init__(self, config, camera_manager, stm32_interface=None, workflow_event_callback=None):
        """
        Initialize task manager.

        Args:
            config: ConfigManager instance
            camera_manager: CameraManager instance
            stm32_interface: Optional STM32Interface instance (uses MockSTM32 if None)
            workflow_event_callback: Optional async callback for workflow events (event_name, event_data)
        """
        self.logger = logging.getLogger('TaskManager')
        self.config = config
        self.camera_manager = camera_manager
        self.stm32_interface = stm32_interface or MockSTM32Interface()
        self.workflow_event_callback = workflow_event_callback

        # Task storage
        self.tasks: Dict[str, Task] = {}  # task_id -> Task
        self.task_queue: List[str] = []  # FIFO queue of task IDs

        # Bay tracking
        self.reserved_bays: Set[int] = set()  # Bays with tasks (queued OR running)
        self.active_bays: Set[int] = set()    # Bays currently running

        # Execution control
        self.running = False
        self.executor_task: Optional[asyncio.Task] = None

        # Start task executor
        self.start_executor()
    
    def start_executor(self):
        """Start background task executor"""
        if not self.running:
            self.running = True
            self.executor_task = asyncio.create_task(self._task_executor_loop())
            self.logger.info("Task executor started")
    
    async def shutdown(self):
        """Shutdown task manager and cancel all tasks"""
        self.logger.info("Shutting down task manager...")
        self.running = False
        
        # Cancel all active tasks
        for task_id in list(self.tasks.keys()):
            task = self.tasks[task_id]
            if task.status in [TaskStatus.QUEUED, TaskStatus.RUNNING]:
                await self._cancel_task_internal(task)
        
        # Wait for executor to finish
        if self.executor_task:
            self.executor_task.cancel()
            try:
                await self.executor_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Task manager shutdown complete")
    
    # ========================================================================
    # TASK CREATION
    # ========================================================================
    
    async def create_task(
        self,
        vegetable_id: str,
        bay_id: int,
        cut_type: str,
        workflow_class: Optional[str] = None
    ) -> Task:
        """
        Create a new processing task.
        
        IMPORTANT: Only ONE task per bay allowed (queued OR running).
        Bay is reserved when task is created, released when hopper is empty.
        Task runs until STM32 reports hopper EMPTY - no target count.
        
        Args:
            vegetable_id: Vegetable ID
            bay_id: Bay number (1-4)
            cut_type: Cut type name
            workflow_class: Optional custom workflow class name
        
        Returns:
            Created Task instance
            
        Raises:
            ValueError: If bay already has a task
        """
        # Check if bay is already reserved
        if bay_id in self.reserved_bays:
            raise ValueError(f"Bay {bay_id} already has a task. Wait until it's empty.")
        
        # Get vegetable and cut configs
        veg_config = self.config.get_vegetable(vegetable_id)
        cut_config = self.config.get_cut_type(cut_type)
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Create task
        task = Task(
            id=task_id,
            vegetable_id=vegetable_id,
            vegetable_name=veg_config.name,
            bay_id=bay_id,
            cut_type=cut_type,
            cut_display_name=cut_config.display_name if cut_config else cut_type,
            workflow_class=workflow_class
        )
        
        # Store task and reserve bay
        self.tasks[task_id] = task
        self.task_queue.append(task_id)
        self.reserved_bays.add(bay_id)  # Reserve bay immediately
        
        self.logger.info(
            f"Task created: {task_id} - {veg_config.name} ({cut_type}) "
            f"on bay {bay_id}, will run until hopper empty"
        )
        
        return task
    
    # ========================================================================
    # TASK EXECUTION
    # ========================================================================
    
    async def _task_executor_loop(self):
        """
        Background loop that processes queued tasks.
        
        CRITICAL: Only ONE task can run at a time because there is only
        ONE cutting chamber (shared resource). Tasks run sequentially
        until hopper is empty, then next task starts.
        """
        self.logger.info("Task executor loop started (SEQUENTIAL mode)")
        
        while self.running:
            try:
                # Check if ANY task is currently running
                if len(self.active_bays) > 0:
                    # Wait for current task to finish
                    await asyncio.sleep(0.5)
                    continue
                
                # No active tasks - get next queued task
                task_to_execute = None
                
                if self.task_queue:
                    task_id = self.task_queue[0]  # FIFO - first in queue
                    task = self.tasks.get(task_id)
                    
                    if task and task.status == TaskStatus.QUEUED:
                        task_to_execute = task
                        self.task_queue.remove(task_id)
                
                if task_to_execute:
                    # Execute task (will block until complete)
                    # Store the task future for potential cancellation
                    task_to_execute._task_future = asyncio.current_task()
                    await self._execute_task(task_to_execute)
                else:
                    # No tasks - wait before checking again
                    await asyncio.sleep(0.5)
                
            except Exception as e:
                self.logger.error(f"Error in task executor loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _execute_task(self, task: Task):
        """
        Execute a single task.
        
        CRITICAL: Task runs until STM32 reports hopper EMPTY,
        not until target_count is reached.
        
        Args:
            task: Task to execute
        """
        try:
            # Mark bay as active
            self.active_bays.add(task.bay_id)
            
            # Update task status
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            
            self.logger.info(f"Starting task {task.id} on bay {task.bay_id}")
            
            # Import workflow class
            workflow_class = self._get_workflow_class(task.workflow_class)
            
            # Get vegetable config
            veg_config = self.config.get_vegetable(task.vegetable_id)
            
            # Create workflow event callback wrapper
            async def workflow_update_callback(event_data: dict):
                """Wrapper to broadcast workflow events and update task stats"""
                event_name = event_data.get("event", "unknown")

                # Update task statistics based on event
                if event_name == "item_completed":
                    task.items_processed += 1
                elif event_name == "cv_rejected":
                    task.items_rejected += 1
                elif event_name == "weight_update":
                    task.weight_processed_grams = event_data.get("total_weight", 0.0)

                # Broadcast to WebSocket clients
                if self.workflow_event_callback:
                    try:
                        await self.workflow_event_callback(event_name, event_data)
                    except Exception as e:
                        self.logger.error(f"Error in workflow event callback: {e}")

            # Instantiate workflow
            workflow = workflow_class(
                stm32_interface=self.stm32_interface,
                cv_manager=self.camera_manager,
                vegetable_config=veg_config,
                bay_id=task.bay_id,
                cut_type=task.cut_type,
                target_count=1000,  # Process until hopper empty
                update_callback=workflow_update_callback
            )

            task._workflow_instance = workflow

            # Execute workflow (runs until hopper empty)
            await self._run_workflow(task, workflow)
            
            # Mark as completed
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            
            self.logger.info(
                f"Task {task.id} completed: {task.items_processed} processed, "
                f"{task.items_rejected} rejected"
            )
            
        except asyncio.CancelledError:
            # Task was cancelled
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            self.logger.info(f"Task {task.id} cancelled")
            
        except Exception as e:
            # Task failed
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error_message = str(e)
            self.logger.error(f"Task {task.id} failed: {e}", exc_info=True)
            
        finally:
            # Release bay (IMPORTANT: only released when hopper is empty)
            self.active_bays.discard(task.bay_id)
            self.reserved_bays.discard(task.bay_id)  # Bay now available
            task._workflow_instance = None
            task._task_future = None

            self.logger.info(f"Bay {task.bay_id} released (hopper empty)")
    
    async def _run_workflow(self, task: Task, workflow):
        """
        Run workflow and update task statistics.

        Args:
            task: Task being executed
            workflow: Workflow instance
        """
        # Execute workflow
        await workflow.run()

        # Update task statistics from workflow metrics
        metrics = workflow.get_metrics()
        task.items_processed = metrics.get('successful_items', 0)
        task.items_rejected = metrics.get('cv_rejected_items', 0)
        task.weight_processed_grams = getattr(workflow, 'total_weight_processed', 0.0)
    
    def _get_workflow_class(self, workflow_class_name: Optional[str]):
        """
        Get workflow class by name.
        
        Args:
            workflow_class_name: Workflow class name or None for default
        
        Returns:
            Workflow class
        """
        if workflow_class_name:
            # TODO: Implement dynamic workflow loading
            # For now, just use default
            self.logger.warning(
                f"Custom workflow '{workflow_class_name}' requested but not implemented. "
                "Using default StandardVegetableWorkflow."
            )
        
        # Import default workflow
        from backend.workflows.standard_workflow import StandardVegetableWorkflow
        return StandardVegetableWorkflow
    
    # ========================================================================
    # TASK CANCELLATION
    # ========================================================================
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: Task UUID
        
        Returns:
            True if cancelled, False if not found or cannot be cancelled
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        
        if task.status not in [TaskStatus.QUEUED, TaskStatus.RUNNING]:
            return False
        
        await self._cancel_task_internal(task)
        return True
    
    async def _cancel_task_internal(self, task: Task):
        """
        Internal cancellation logic.

        Args:
            task: Task to cancel
        """
        if task.status == TaskStatus.QUEUED:
            # Remove from queue
            if task.id in self.task_queue:
                self.task_queue.remove(task.id)
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()

            # Release bay reservation
            self.reserved_bays.discard(task.bay_id)
            self.logger.info(f"Bay {task.bay_id} released (task cancelled)")

        elif task.status == TaskStatus.RUNNING:
            # Stop workflow gracefully first
            if task._workflow_instance:
                if hasattr(task._workflow_instance, 'stop'):
                    try:
                        await task._workflow_instance.stop()
                    except Exception as e:
                        self.logger.warning(f"Error stopping workflow: {e}")

            # Force-cancel the actual asyncio task if it exists
            if task._task_future and not task._task_future.done():
                task._task_future.cancel()
                try:
                    await asyncio.wait_for(task._task_future, timeout=2.0)
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    self.logger.warning(f"Task {task.id} did not cancel within timeout")

            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()

            # Release bay immediately on forced cancellation
            self.active_bays.discard(task.bay_id)
            self.reserved_bays.discard(task.bay_id)
            self.logger.info(f"Bay {task.bay_id} released (task force-cancelled)")
    
    async def emergency_stop(self):
        """Emergency stop - cancel all tasks"""
        self.logger.warning("EMERGENCY STOP initiated")
        
        # Cancel all tasks
        for task_id in list(self.tasks.keys()):
            task = self.tasks[task_id]
            if task.status in [TaskStatus.QUEUED, TaskStatus.RUNNING]:
                await self._cancel_task_internal(task)
        
        self.logger.warning("All tasks stopped")
    
    # ========================================================================
    # TASK QUERIES
    # ========================================================================
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> List[Task]:
        """Get all tasks"""
        return list(self.tasks.values())
    
    def get_active_tasks(self) -> List[Task]:
        """Get active (running) tasks"""
        return [t for t in self.tasks.values() if t.status == TaskStatus.RUNNING]
    
    def get_queued_tasks(self) -> List[Task]:
        """Get queued tasks"""
        return [t for t in self.tasks.values() if t.status == TaskStatus.QUEUED]
    
    def get_active_bays(self) -> Set[int]:
        """Get set of currently active bay IDs"""
        return self.active_bays.copy()
    
    def is_bay_in_use(self, bay_id: int) -> bool:
        """
        Check if a bay has a task (queued OR running).
        
        Args:
            bay_id: Bay number
            
        Returns:
            True if bay is reserved (has a task)
        """
        return bay_id in self.reserved_bays
    
    def get_available_bays(self) -> Set[int]:
        """
        Get bays that are available (no queued or running tasks).
        Uses num_hoppers from machine config as the source of truth
        for how many physical bays exist.

        Returns:
            Set of available bay numbers
        """
        from backend.config.machine_config import get_machine_config
        num_bays = get_machine_config().num_hoppers
        all_bays = set(range(1, num_bays + 1))
        return all_bays - self.reserved_bays
