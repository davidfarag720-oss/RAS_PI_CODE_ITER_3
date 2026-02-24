"""
stm32_interface.py

Async wrapper for STM32 communication with state polling and readiness checks.

Author: Ficio Prep Team
Date: February 2026
"""

import asyncio
import logging
from typing import Optional
from backend.comms.raspi_comms_manager import RaspiCommsManager, ResponseStatus, Response


class STM32Interface:
    """
    Async interface to STM32 with high-level commands and state polling.

    Provides workflow-friendly async methods that handle state polling
    for readiness before sending commands.
    """

    def __init__(self, comms: RaspiCommsManager):
        """
        Initialize STM32 interface.

        Args:
            comms: Initialized RaspiCommsManager instance
        """
        self.comms = comms
        self.logger = logging.getLogger('STM32Interface')

    async def _run_sync(self, func, *args, **kwargs):
        """Run synchronous comms method in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    # ========================================================================
    # BOOT HANDSHAKE
    # ========================================================================

    async def validate_config(self, num_hoppers: int, num_actuators: int,
                              bottom_gate: bool, parallelization: bool,
                              num_vib_motors: int) -> bool:
        """
        Validate RasPi config matches STM32 config.

        Returns:
            True if configs match, False if mismatch

        Raises:
            RuntimeError: If handshake fails or timeout
        """
        response = await self._run_sync(
            self.comms.config_handshake,
            num_hoppers, num_actuators, bottom_gate, parallelization, num_vib_motors
        )

        if response.status == ResponseStatus.RESP_OK:
            self.logger.info("Config handshake SUCCESS - RasPi and STM32 configs match")
            return True
        elif response.status == ResponseStatus.RESP_INVALID_PARAM:
            # Decode STM32 config from response
            stm32_hoppers = response.data & 0x0F
            stm32_actuators = (response.data >> 4) & 0x0F
            stm32_flags = (response.data >> 8) & 0x0F
            stm32_vib = (response.data >> 12) & 0x0F

            self.logger.error(
                f"Config MISMATCH - STM32 has: hoppers={stm32_hoppers}, "
                f"actuators={stm32_actuators}, bottom_gate={bool(stm32_flags & 0x01)}, "
                f"parallel={bool(stm32_flags & 0x02)}, vib_motors={stm32_vib}"
            )
            return False
        else:
            raise RuntimeError(f"Config handshake failed: {response.status}")

    # ========================================================================
    # HIGH-LEVEL SEQUENCES
    # ========================================================================

    async def dispose(self, gate_id: int = 1) -> None:
        """Execute dispose sequence and wait for completion."""
        response = await self._run_sync(self.comms.dispose, gate_id)

        if response.status != ResponseStatus.RESP_OK:
            raise RuntimeError(f"Dispose failed: {response.status}")

        self.logger.info(f"Dispose sequence complete (gate {gate_id})")

    async def load_cutter(self, gate_id: int = 1, wait_for_cutter_idle: bool = True) -> None:
        """
        Execute load-cutter sequence and wait for hardware confirmation that the gate
        has reached Position C before returning.

        Sequence:
          1. (optional) Poll cutter until idle — prevents parallel-mode overlap
          2. Clear the gate-at-C event latch (prevent stale event race)
          3. Send CMD_LOAD_CUTTER
          4. Wait up to 5s for EVENT_GATE_AT_POSITION_C notification from STM32
             - If received: return normally (gate confirmed loaded)
             - If timeout: log warning and return (proceed with caution; STM32 may still be moving)

        Args:
            gate_id: Gate ID (1=top, 2=bottom)
            wait_for_cutter_idle: If True, polls cutter status until idle before sending

        Raises:
            RuntimeError: If CMD_LOAD_CUTTER itself fails (RESP_BUSY or unexpected status)
        """
        if wait_for_cutter_idle:
            await self.wait_for_cutter_idle(timeout=30.0)

        # Step 1: Clear event latch BEFORE sending command to avoid race condition
        # (STM32 could theoretically fire the event very quickly after CMD_LOAD_CUTTER)
        self.comms._gate_at_c_event.clear()
        self.comms._gate_at_c_gate_id = 0

        # Step 2: Send CMD_LOAD_CUTTER
        response = await self._run_sync(self.comms.load_cutter, gate_id)

        if response.status == ResponseStatus.RESP_BUSY:
            raise RuntimeError("Load-cutter blocked: cutter still busy (parallel mode)")
        elif response.status != ResponseStatus.RESP_OK:
            raise RuntimeError(f"Load-cutter failed: {response.status}")

        # Step 3: Wait for STM32 to confirm gate reached Position C
        # Timeout: 5s (servo travel takes ~0.5-1.5s in practice; 5s allows margin for jam detection)
        gate_confirmed = await self._run_sync(
            self.comms.wait_for_gate_at_position_c, gate_id, 5.0
        )

        if gate_confirmed:
            self.logger.info(f"Load-cutter confirmed: gate {gate_id} at Position C")
        else:
            # Timeout or wrong gate — log warning but do NOT raise.
            # The gate may still be in transit (servo slower than expected) or
            # notification was lost. Proceeding allows the cut to attempt;
            # the STM32's own interlocks remain active.
            self.logger.warning(
                f"load_cutter: No gate-at-Position-C confirmation for gate {gate_id} "
                f"within 5s — proceeding with caution (gate may still be moving)"
            )

    async def cut(self, axis_bitmask: int) -> None:
        """Execute cutting cycle and wait for completion."""
        response = await self._run_sync(self.comms.cut, axis_bitmask)

        if response.status != ResponseStatus.RESP_OK:
            raise RuntimeError(f"Cut failed: {response.status}")

        self.logger.info(f"Cut cycle complete (axes: 0x{axis_bitmask:02X})")

    async def hopper_dispense(self, hopper_id: int) -> bool:
        """
        Dispense from hopper.

        Returns:
            True if laser triggered (success), False if timeout (possibly empty)
        """
        response = await self._run_sync(self.comms.hopper_dispense, hopper_id)

        if response.status == ResponseStatus.RESP_OK:
            self.logger.info(f"Hopper {hopper_id} dispensed (laser trigger)")
            return True
        elif response.status == ResponseStatus.RESP_TIMEOUT:
            self.logger.warning(f"Hopper {hopper_id} dispense timeout (possibly empty)")
            return False
        else:
            raise RuntimeError(f"Hopper dispense failed: {response.status}")

    # ========================================================================
    # STATE POLLING
    # ========================================================================

    async def wait_for_cutter_idle(self, timeout: float = 30.0, poll_interval: float = 0.2) -> None:
        """
        Poll cutter status until idle.

        Args:
            timeout: Max time to wait in seconds
            poll_interval: Time between polls in seconds

        Raises:
            TimeoutError: If cutter doesn't become idle within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            response = await self._run_sync(self.comms.query_cutter_status)

            if response.status != ResponseStatus.RESP_OK:
                raise RuntimeError(f"Cutter status query failed: {response.status}")

            cutter_state = response.data & 0xFF  # DATA_L

            if cutter_state == 0:  # IDLE
                return
            elif cutter_state == 255:  # ERROR
                raise RuntimeError("Cutter in error state")

            # Still busy
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Cutter did not become idle within {timeout}s")

            await asyncio.sleep(poll_interval)

    async def is_hopper_empty(self, hopper_id: int) -> bool:
        """
        Check if hopper is empty.

        Returns:
            True if empty flag set, False otherwise
        """
        response = await self._run_sync(self.comms.query_hopper, hopper_id)

        if response.status != ResponseStatus.RESP_OK:
            raise RuntimeError(f"Hopper status query failed: {response.status}")

        data_l = response.data & 0xFF
        empty_flag = bool(data_l & 0x01)

        return empty_flag

    async def emergency_stop(self) -> None:
        """Send emergency stop command."""
        response = await self._run_sync(self.comms.emergency_stop)
        self.logger.critical("EMERGENCY STOP sent")

    # ========================================================================
    # SCALE & VIBRATION
    # ========================================================================

    async def scale_tare(self) -> bool:
        """Tare the scale. Returns True on success."""
        return await self._run_sync(self.comms.scale_tare)

    async def scale_read(self) -> Optional[float]:
        """Read current scale weight in grams. Returns None on failure."""
        return await self._run_sync(self.comms.scale_read)

    async def vibration_all_off(self) -> None:
        """Turn off all vibration motors."""
        await self._run_sync(self.comms.vibration_all_off)

    # ========================================================================
    # SYSTEM RECOVERY
    # ========================================================================

    async def reset_system(self) -> None:
        """Clear emergency stop flag (must call before home_actuators after e-stop)."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.comms.reset_system)

    async def home_actuators(self) -> None:
        """Run full boot sequence + clear cutter bay. Waits up to 45s."""
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, self.comms.cut_home)
        if not success:
            raise RuntimeError("Actuator home sequence failed")
