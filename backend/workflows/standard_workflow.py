"""
standard_workflow.py

Single parameterized workflow for all vegetable types.
Driven by VegetableConfig and runtime bay selection.

Implements the standard processing sequence from Technical Specifications Page 2:
1. Dispense from bay
2. CV analysis in staging area
3. If accepted: enter cutting chamber, cut, exit
4. Repeat until target reached or bay empty

Author: Ficio Prep Team
Date: January 2026
"""

import asyncio
from typing import Optional, Dict

from .base_workflow import BaseWorkflow, WorkflowEvent, HardwareError, CVError
from backend.config import get_config, VegetableConfig, CutTypeConfig
from backend.stm32_interface import STM32Interface


class StandardVegetableWorkflow(BaseWorkflow):
    """
    Single parameterized workflow for all vegetable processing.
    
    This workflow is driven by:
    - VegetableConfig: Defines the vegetable type, CV models, supported cuts
    - bay_id: Runtime-selected bay (1-4) where the vegetable is loaded
    - cut_type: Selected cut type (must be in vegetable's supported_cuts)
    
    No subclassing needed - all vegetables follow the same processing sequence.
    """
    
    def __init__(
        self,
        stm32_interface,
        cv_manager,
        vegetable_config: VegetableConfig,
        bay_id: int,
        cut_type: str,
        target_count: int = 50,
        update_callback: Optional[callable] = None
    ):
        """
        Initialize standard vegetable workflow.
        
        Args:
            stm32_interface: STM32Interface for hardware control
            cv_manager: CameraManager for CV processing
            vegetable_config: Configuration for the vegetable type
            bay_id: Bay number (1-4) where vegetable is loaded
            cut_type: Cut type name (e.g., "sliced", "cubed")
            target_count: Number of items to process
            update_callback: Callback for status updates
        
        Raises:
            ValueError: If bay_id is invalid or cut_type not supported
        """
        super().__init__(stm32_interface, cv_manager, update_callback)
        
        # Get configuration
        self.config = get_config()
        
        # Validate bay_id against actual hopper count
        from backend.config.machine_config import get_machine_config
        num_bays = get_machine_config().num_hoppers
        if bay_id < 1 or bay_id > num_bays:
            raise ValueError(f"Invalid bay_id: {bay_id} (must be 1-{num_bays})")
        
        # Validate cut_type is supported
        if cut_type not in vegetable_config.supported_cuts:
            raise ValueError(
                f"Cut type '{cut_type}' not supported for {vegetable_config.name}. "
                f"Supported: {vegetable_config.supported_cuts}"
            )
        
        # Get cut type configuration
        cut_config = self.config.get_cut_type(cut_type)
        if not cut_config:
            raise ValueError(f"Unknown cut type: {cut_type}")
        
        # Workflow configuration
        self.vegetable_config = vegetable_config
        self.bay_id = bay_id
        self.cut_config = cut_config
        self.target_count = target_count
        
        # Workflow metadata
        self.workflow_name = f"{vegetable_config.name} {cut_config.display_name}"
        self.vegetable_type = vegetable_config.id
        self.cut_type = cut_type
        
        # Hardware mappings
        self.gate_cutter_top = 1    # Top cutter gate (entry)
        self.gate_cutter_bottom = 2  # Bottom cutter gate (exit)
        self.gate_bay = self.config.get_gate_for_bay(bay_id)  # Bay gate (3-6)
        
        # State tracking
        self.current_item = 0
        self.consecutive_cv_failures = 0
        self.bay_empty = False
        self.total_weight_processed = 0.0
        
        # Prefetch state for pipeline optimization
        self._prefetch_task: Optional[asyncio.Task] = None
        self._prefetch_result: Optional[Dict] = None
        self._prefetch_item_number: Optional[int] = None
        
        # Timing configuration from config
        self.staging_delay = self.config.get_float('staging_delay', 0.3)
        self.gate_delay = self.config.get_float('gate_delay', 0.2)
        self.cut_delay = self.config.get_float('cut_delay', 0.5)
        self.max_cv_failures = self.config.get_int('max_consecutive_cv_failures', 5)
        
        self.logger.info(
            f"StandardWorkflow initialized: {self.workflow_name}, "
            f"bay={bay_id}, target={target_count}, "
            f"cut_mask=0b{cut_config.axis_bitmask:03b}"
        )
    
    # ========================================================================
    # WORKFLOW IMPLEMENTATION (Standard Processing Sequence)
    # ========================================================================
    
    async def setup(self):
        """
        Initialize workflow - tare scale, verify bay, close gates.

        Implements pre-workflow setup as per spec.
        """
        self.logger.info(f"Setting up {self.workflow_name} workflow...")

        # Tare the scale
        self.logger.info("Taring scale...")
        try:
            # Scale operations are not in STM32Interface, call directly on comms
            if not self.stm32.comms.scale_tare():
                raise HardwareError("Failed to tare scale")
        except Exception as e:
            self.logger.warning(f"Scale tare failed: {e}")

        await self._wait_async(0.5)

        # Verify bay is not empty
        try:
            is_empty = await self.stm32.is_hopper_empty(self.bay_id)
            if is_empty:
                self.bay_empty = True
                raise HardwareError(f"Bay {self.bay_id} is empty")
        except Exception as e:
            raise HardwareError(f"Failed to check hopper status: {e}")

        self.logger.info("Setup complete")
    
    async def process_single_item(self) -> bool:
        """
        Process one item through the standard workflow sequence.

        Uses pipelined processing: while current item is cutting, the next item
        is dispensed and CV-checked in parallel. Prefetch starts AFTER the gate
        closes to prevent items from falling into an open gate.

        Standard Processing Sequence (from spec Page 2):
        1. Dispense: Vegetable falls from bay into staging area
        2. CV Analysis: Overhead camera captures static image
        3. Route based on CV:
           - If rejected: dispose (to waste)
           - If accepted: load_cutter -> cut -> bottom gate auto-opens
        4. Repeat until target reached or bay empty

        Returns:
            True if successfully processed, False if error or rejected
        """
        item_num = self.current_item + 1
        self.logger.info(f"=== Processing item {item_num}/{self.target_count} ===")

        try:
            # Check if we have a prefetched result from previous iteration
            if self._prefetch_result and self._prefetch_item_number == item_num:
                self.logger.debug(f"Using prefetched CV result for item {item_num}")
                cv_result = self._prefetch_result
                # Clear prefetch state
                self._prefetch_result = None
                self._prefetch_item_number = None
            else:
                # No prefetch available, do it now (first item or prefetch failed)
                # Step 1: Dispense from bay into staging area
                success = await self._dispense_from_bay()
                if not success:
                    # Timeout - possibly empty, let caller check
                    return False

                # Step 2: Wait for settling in staging area
                await self._wait_async(self.staging_delay)

                # Step 3: Run CV analysis
                cv_result = await self._run_cv_check()

            # Validate CV result and route accordingly
            if not cv_result['accepted']:
                # REJECTION PATH: Dispose to waste
                self.cv_rejected_items += 1
                self.consecutive_cv_failures += 1

                await self._emit_event(
                    WorkflowEvent.CV_REJECTED,
                    {
                        "item": item_num,
                        "reason": cv_result.get('reason', 'quality'),
                        "confidence": cv_result.get('confidence', 0.0),
                        "bay_id": self.bay_id
                    }
                )

                self.logger.warning(
                    f"Item {item_num} rejected by CV: {cv_result.get('reason', 'unknown')}"
                )

                # Execute dispose sequence via STM32Interface
                try:
                    await self.stm32.dispose(gate_id=1)
                    await self._emit_event(WorkflowEvent.DISPOSE_COMPLETE)
                except Exception as e:
                    self.logger.error(f"Dispose sequence failed: {e}")

                # Start prefetching next item before returning
                await self._start_prefetch_next_item(item_num + 1)

                return False

            # ACCEPTANCE PATH: Load and cut
            self.consecutive_cv_failures = 0

            await self._emit_event(
                WorkflowEvent.ITEM_ACCEPTED,
                {
                    "item": item_num,
                    "confidence": cv_result.get('confidence', 0.0),
                    "quality": cv_result.get('quality', 'good')
                }
            )

            # Execute cutting sequence
            if not await self._execute_cut():
                return False

            # Step 5: Read scale for telemetry
            try:
                weight = self.stm32.comms.scale_read()
                if weight is not None:
                    self.total_weight_processed += weight
                    await self._emit_event(
                        WorkflowEvent.WEIGHT_UPDATE,
                        {"total_weight": self.total_weight_processed}
                    )
            except Exception as e:
                self.logger.warning(f"Failed to read scale: {e}")

            self.current_item += 1
            await self._emit_event(
                WorkflowEvent.ITEM_COMPLETE,
                {"count": self.current_item}
            )
            self.logger.info(f"Item {item_num} completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error processing item {item_num}: {e}", exc_info=True)
            return False
    
    async def should_continue(self) -> bool:
        """
        Check if workflow should continue.

        Stop conditions:
        - Target count reached
        - Bay empty
        - Too many consecutive CV failures

        Returns:
            False if any stop condition is met
        """
        # Check target reached
        if self.current_item >= self.target_count:
            self.logger.info(f"Target of {self.target_count} items reached")
            return False

        # Check bay empty
        try:
            is_empty = await self.stm32.is_hopper_empty(self.bay_id)
            if is_empty:
                self.bay_empty = True
                await self._emit_event(WorkflowEvent.HOPPER_EMPTY, {"bay_id": self.bay_id})
                self.logger.warning(f"Bay {self.bay_id} is empty")
                return False
        except Exception as e:
            self.logger.error(f"Failed to check hopper status: {e}")
            return False

        # Check consecutive CV failures (safety)
        if self.consecutive_cv_failures >= self.max_cv_failures:
            self.logger.error(
                f"Too many consecutive CV failures ({self.consecutive_cv_failures}). "
                "Stopping workflow."
            )
            await self._emit_event(
                WorkflowEvent.ERROR,
                {"message": "Too many consecutive CV failures"}
            )
            return False

        return True
    
    async def cleanup(self):
        """Clean up after workflow completion."""
        self.logger.info("Cleaning up...")

        # Cancel any pending prefetch task
        if self._prefetch_task and not self._prefetch_task.done():
            self._prefetch_task.cancel()
            try:
                await self._prefetch_task
            except asyncio.CancelledError:
                pass

        # Turn off all vibration (if it was enabled)
        try:
            self.stm32.comms.vibration_all_off()
        except Exception as e:
            self.logger.warning(f"Failed to turn off vibration: {e}")

        # Read final weight
        try:
            final_weight = self.stm32.comms.scale_read()
            if final_weight is not None:
                self.logger.info(f"Total weight processed: {self.total_weight_processed:.1f}g")
        except Exception as e:
            self.logger.warning(f"Failed to read final weight: {e}")

        self.logger.info("Cleanup complete")
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    async def _dispense_from_bay(self) -> bool:
        """
        Dispense one item from the bay.

        Uses CMD_HOPPER_DISPENSE which includes vibration and smart laser detection.
        Returns False on timeout (possibly empty) to trigger empty check.

        Returns:
            True if laser triggered (success), False if timeout
        """
        self.logger.info(f"Dispensing from bay {self.bay_id}...")

        await self._emit_event(
            WorkflowEvent.ITEM_DISPENSED,
            {"bay_id": self.bay_id}
        )

        try:
            # Hopper dispense includes vibration and smart laser detection
            # Returns True if laser triggered, False if timeout
            success = await self.stm32.hopper_dispense(self.bay_id)

            if not success:
                # Timeout - possibly empty
                self.logger.warning(f"Hopper {self.bay_id} dispense timeout (possibly empty)")
                return False

            self.logger.debug("Dispense successful")
            return True

        except Exception as e:
            self.logger.error(f"Dispense error: {e}")
            return False
    
    async def _run_cv_check(self) -> dict:
        """
        Run computer vision analysis on staged item.
        
        Uses the vegetable-specific CV models defined in config.
        
        Returns:
            Dictionary with keys:
                - accepted: bool
                - confidence: float (0-1)
                - reason: str (if rejected)
        """
        self.logger.info("Running CV analysis...")
        
        await self._emit_event(WorkflowEvent.CV_CHECK_STARTED)
        
        try:
            # Run CV analysis with vegetable config
            cv_result = await self.cv.analyze_vegetable(
                vegetable_config=self.vegetable_config,
                bay_id=self.bay_id
            )
            
            await self._emit_event(
                WorkflowEvent.CV_CHECK_COMPLETED,
                {
                    "accepted": cv_result['accepted'],
                    "confidence": cv_result['confidence'],
                    "healthy": cv_result.get('healthy', True),
                    "bay_id": self.bay_id
                }
            )
            
            if cv_result['accepted']:
                self.logger.info(
                    f"CV ACCEPT: confidence={cv_result['confidence']:.2f}, "
                    f"healthy={cv_result.get('healthy', True)}"
                )
            else:
                self.logger.warning(
                    f"CV REJECT: reason={cv_result.get('reason', 'unknown')}, "
                    f"confidence={cv_result['confidence']:.2f}"
                )
            
            return cv_result
            
        except Exception as e:
            self.logger.error(f"CV analysis error: {e}", exc_info=True)
            raise CVError(f"CV analysis failed: {e}")
    
    async def _execute_cut(self) -> bool:
        """
        Execute the cutting sequence.

        Standard cutting sequence (from spec Page 2):
        1. Load cutter (waits for cutter idle if parallel mode)
        2. Execute cut (while prefetch runs in parallel)
        3. Wait for cutter idle (includes bottom gate cycle)

        Note: Bottom gate is controlled autonomously by STM32 firmware.
        The gate opens automatically when cutter completes, holds briefly,
        then closes. RasPi does not send explicit open/close commands.

        Returns:
            True if successful, False if error
        """
        self.logger.info("Executing cutting sequence...")

        await self._emit_event(WorkflowEvent.CUTTING_STARTED)

        try:
            # Load cutter (waits for cutter idle if parallel mode interlock)
            self.logger.debug("Loading cutter...")
            await self.stm32.load_cutter(gate_id=1, wait_for_cutter_idle=True)

            await self._emit_event(WorkflowEvent.GATE_LOADED)
            self.logger.debug("Item loaded into cutting chamber")

            # Gate is now CLOSED - safe to start prefetch for next item
            # This runs in parallel while cutting happens
            item_num = self.current_item + 1
            await self._start_prefetch_next_item(item_num + 1)

            # Execute cut using configured axis bitmask
            self.logger.debug(
                f"Executing cut (bitmask: 0b{self.cut_config.axis_bitmask:03b})..."
            )
            await self.stm32.cut(self.cut_config.axis_bitmask)

            # Wait for cutter to become idle (ensures bottom gate sequence completes)
            self.logger.debug("Waiting for cutter to return to idle...")
            await self.stm32.wait_for_cutter_idle(timeout=30.0)

            await self._emit_event(WorkflowEvent.CUTTING_COMPLETED)

            self.logger.info("Cutting sequence complete")
            return True

        except Exception as e:
            self.logger.error(f"Cutting sequence error: {e}", exc_info=True)
            return False
    
    async def _start_prefetch_next_item(self, next_item_num: int):
        """
        Start prefetching the next item in parallel (dispense + CV).

        This runs while the current item is being cut, so the next item
        is ready as soon as cutting finishes.

        Args:
            next_item_num: Item number to prefetch
        """
        # Don't prefetch if we're at or past target
        if next_item_num > self.target_count:
            self.logger.debug("Skipping prefetch - at target")
            return

        # Don't prefetch if bay is empty
        try:
            is_empty = await self.stm32.is_hopper_empty(self.bay_id)
            if is_empty:
                self.logger.debug("Skipping prefetch - bay empty")
                return
        except Exception as e:
            self.logger.warning(f"Failed to check hopper status in prefetch: {e}")
            return

        # Cancel any existing prefetch task
        if self._prefetch_task and not self._prefetch_task.done():
            self._prefetch_task.cancel()
            try:
                await self._prefetch_task
            except asyncio.CancelledError:
                pass

        # Start new prefetch task
        self.logger.debug(f"Starting prefetch for item {next_item_num}")
        self._prefetch_task = asyncio.create_task(
            self._prefetch_next_item(next_item_num)
        )
    
    async def _prefetch_next_item(self, item_num: int):
        """
        Prefetch task: dispense next item and run CV analysis.
        
        This runs in parallel with cutting, so the next item is ready
        immediately when cutting finishes.
        
        Args:
            item_num: Item number being prefetched
        """
        try:
            self.logger.info(f"[PREFETCH] Starting prefetch for item {item_num}")
            
            # Dispense from bay
            if not await self._dispense_from_bay():
                self.logger.warning(f"[PREFETCH] Failed to dispense item {item_num}")
                return
            
            # Wait for settling
            await self._wait_async(self.staging_delay)
            
            # Run CV analysis
            cv_result = await self._run_cv_check()
            
            # Store result for next iteration
            self._prefetch_result = cv_result
            self._prefetch_item_number = item_num
            
            self.logger.info(
                f"[PREFETCH] Item {item_num} ready - "
                f"{'ACCEPTED' if cv_result['accepted'] else 'REJECTED'} "
                f"(confidence: {cv_result['confidence']:.2f})"
            )
            
        except asyncio.CancelledError:
            self.logger.debug(f"[PREFETCH] Prefetch cancelled for item {item_num}")
            raise
        except Exception as e:
            self.logger.error(f"[PREFETCH] Error prefetching item {item_num}: {e}")
            # Clear prefetch state on error
            self._prefetch_result = None
            self._prefetch_item_number = None
    
    def get_progress_percent(self) -> float:
        """Get workflow progress as percentage."""
        if self.target_count == 0:
            return 100.0
        return round((self.current_item / self.target_count) * 100, 1)