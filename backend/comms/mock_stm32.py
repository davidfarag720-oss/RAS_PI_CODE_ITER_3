"""
mock_stm32.py

MockSTM32Interface — drop-in replacement for STM32Interface that uses keyboard
input instead of real UART. Set STM32_MOCK=1 to activate via main.py.

Every method logs a timestamped line to the terminal. Methods that need
hardware feedback prompt the operator for input via run_in_executor so the
FastAPI event loop stays unblocked.

Author: Ficio Prep Team
Date: February 2026
"""

import asyncio
import logging
import time
from typing import List, Tuple, Any

logger = logging.getLogger('MockSTM32')


class MockSTM32Interface:
    """
    Mock implementation of STM32Interface for testing without hardware.

    Mirrors the complete async API of STM32Interface. Fire-and-forget methods
    return success immediately. Feedback methods (hopper empty, cutter idle,
    weight) prompt the operator via stdin.
    """

    def __init__(self):
        self._t0 = time.monotonic()
        self._log: List[Tuple[float, str, Any]] = []
        logger.info("MockSTM32Interface ready — all STM32 commands will be simulated")

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _elapsed(self) -> float:
        return time.monotonic() - self._t0

    def _record(self, method: str, result: Any) -> None:
        elapsed = self._elapsed()
        self._log.append((elapsed, method, result))
        print(f"[mock] +{elapsed:6.3f}s  {method} → {result}", flush=True)

    async def _prompt(self, prompt_text: str) -> str:
        """Await user keyboard input without blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt_text)

    # ------------------------------------------------------------------ #
    # Boot handshake
    # ------------------------------------------------------------------ #

    async def validate_config(
        self,
        num_hoppers: int,
        num_actuators: int,
        bottom_gate: bool,
        parallelization: bool,
        num_vib_motors: int,
    ) -> bool:
        result = True
        self._record(
            f"validate_config(hoppers={num_hoppers}, actuators={num_actuators}, "
            f"bottom_gate={bottom_gate}, parallel={parallelization}, "
            f"vib_motors={num_vib_motors})",
            result,
        )
        return result

    # ------------------------------------------------------------------ #
    # High-level sequences (fire-and-forget)
    # ------------------------------------------------------------------ #

    async def dispose(self, gate_id: int = 1) -> None:
        self._record(f"dispose(gate_id={gate_id})", "OK")

    async def load_cutter(self, gate_id: int = 1, wait_for_cutter_idle: bool = True) -> None:
        if wait_for_cutter_idle:
            await self.wait_for_cutter_idle()
        self._record(f"load_cutter(gate_id={gate_id})", "OK")

    async def cut(self, axis_bitmask: int) -> None:
        self._record(f"cut(axis_bitmask=0b{axis_bitmask:03b})", "OK")

    async def emergency_stop(self) -> None:
        self._record("emergency_stop()", "HALT")

    # ------------------------------------------------------------------ #
    # Feedback methods (operator input required)
    # ------------------------------------------------------------------ #

    async def hopper_dispense(self, hopper_id: int) -> bool:
        """
        Simulate hopper dispense. Prompts operator: did an item fall through?
        Returns True (laser trigger) or False (timeout / empty).
        """
        raw = await self._prompt(
            f"[mock] hopper_dispense(hopper_id={hopper_id}) — item detected? (y/n): "
        )
        result = raw.strip().lower() == "y"
        self._record(f"hopper_dispense(hopper_id={hopper_id})", result)
        return result

    async def wait_for_cutter_idle(
        self, timeout: float = 30.0, poll_interval: float = 0.2
    ) -> None:
        """Prompt operator to press Enter when the cut is physically complete."""
        await self._prompt("[mock] wait_for_cutter_idle — press Enter when cut is done: ")
        self._record("wait_for_cutter_idle()", "done")

    async def is_hopper_empty(self, hopper_id: int) -> bool:
        """Prompt operator whether the hopper is empty."""
        raw = await self._prompt(
            f"[mock] is_hopper_empty(hopper_id={hopper_id}) — hopper empty? (y/n): "
        )
        result = raw.strip().lower() == "y"
        self._record(f"is_hopper_empty(hopper_id={hopper_id})", result)
        return result

    # ------------------------------------------------------------------ #
    # Timing report
    # ------------------------------------------------------------------ #

    def print_timing_report(self) -> None:
        """Dump the full call log to stdout."""
        print("\n[mock] ===== TIMING REPORT =====")
        print(f"{'Elapsed':>10}  Method → Result")
        print("-" * 60)
        for elapsed, method, result in self._log:
            print(f"+{elapsed:9.3f}s  {method} → {result}")
        print("[mock] ===========================\n", flush=True)
