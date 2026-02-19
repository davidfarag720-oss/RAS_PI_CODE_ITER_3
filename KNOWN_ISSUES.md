# Known Issues and Limitations

## 1. Top Gate Control Protocol Mismatch (Feb 2026)

**Status:** Waiting for STM32 Phase 4 implementation

### Issue
The `standard_workflow.py` workflow currently calls:
```python
self.stm32.gate_open(self.gate_cutter_top)   # gate_id 1
self.stm32.gate_close(self.gate_cutter_top)  # gate_id 1
```

However, the STM32 firmware **does not support** `CMD_GATE_OPEN` or `CMD_GATE_CLOSE` for gate_id 1 (top cutter gate). These commands return `RESP_INVALID_PARAM`.

### Root Cause
- Original architecture (ARCHITECTURE.md) designed direct gate control via RasPi
- Recent STM32 redesign (commit 78d92bf) moved to "high-level sequence" philosophy
- Top gate now uses `CMD_LOAD_CUTTER` (opens and holds) and `CMD_DISPOSE` (full cycle)
- **Missing:** No way to close top gate after `CMD_LOAD_CUTTER` - deferred to "Phase 4"

### Impact
**The standard workflow cannot run repeated items** until Phase 4 is implemented.

First call to `gate_open(1)` will fail and workflow will error out.

### Workaround
None recommended. Wait for Phase 4.

### When Phase 4 is Complete

The STM32 will implement `Gate_ReturnToBase()` function and wire it to `CMD_GATE_CLOSE`.

**Workflow changes needed:**

Option A: Use `CMD_LOAD_CUTTER` + `CMD_GATE_CLOSE`
```python
# In _execute_cut() method:
if not self.stm32.load_cutter(self.gate_cutter_top):  # New method
    raise HardwareError("Failed to open top gate")
await self._wait_async(self.gate_delay)

if not self.stm32.gate_close(self.gate_cutter_top):  # Existing method
    raise HardwareError("Failed to close top gate")
```

Option B: If STM32 implements full direct control
```python
# No changes needed - gate_open/gate_close will work
```

**New method to add** (if using Option A):
```python
# In backend/comms/raspi_comms_manager.py, STM32Interface class:
def load_cutter(self, gate_id: int) -> bool:
    """Execute load-cutter sequence (opens gate to Position C, arms bottom gate)"""
    resp = self.comms.send_command(CommandCode.CMD_LOAD_CUTTER, gate_id)
    return resp and resp.status == ResponseStatus.OK
```

### Related Documentation
See `C:\Ficio\STM32\Core\.planning\PHASE4_GATE_CLOSE_NOTES.md` for full details and implementation plan.

---

**Last Updated:** 2026-02-14
