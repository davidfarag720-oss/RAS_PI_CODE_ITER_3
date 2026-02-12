# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated vegetable processing system (Ficio Prep) with computer vision quality control. Target hardware is Raspberry Pi 5 communicating with STM32 microcontroller via UART.

**Tech Stack:** Python 3, FastAPI, OpenCV (no picamera2), YOLO + EfficientNet for CV, SQLAlchemy with async SQLite, pyserial for STM32 UART.

## Build & Run Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows
pip install -r requirements.txt

# Run API server
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload

# Production startup
./start_api.sh

# Testing
pytest test_api_integration.py -v                    # Full API test suite
python3 test_pipelining.py                           # Workflow pipelining test
python3 backend/comms/test_basic_coms.py             # STM32 communications test
python3 validate_integration.py                      # Architecture validation

# Validate config
python3 -c "from backend.config import ConfigManager; c = ConfigManager(); c.validate(); print('Valid')"
```

## Architecture

### Configuration-Driven Design
- `config.json` is the single source of truth for system settings, vegetables, and cut types
- `ConfigManager` (backend/config/config_manager.py) loads/validates JSON and provides global access via `get_config()`
- To add a vegetable: add JSON entry + image to assets/ui/ (no code changes needed)

### Single Parameterized Workflow
- `StandardVegetableWorkflow` handles ALL vegetables (no subclasses)
- Driven by: `VegetableConfig` (from config) + runtime `bay_id` + `cut_type`
- State machine pattern: IDLE → INITIALIZING → RUNNING → PAUSED/COMPLETED/ERROR
- Emits 16+ events via async `update_callback` for real-time UI updates

### Processing Sequence (All Vegetables)
1. DISPENSE: Hopper vibrates + laser detection → item falls to staging
2. CV ANALYZE: Overhead camera captures static image → YOLO + EfficientNet quality check
3. VALIDATE: Rejected items are logged; accepted items proceed
4. ENTER: Top gate opens → item enters cutting chamber
5. GATE CLOSE: Top gate closes → **prefetch starts** (dispense next item while cutting)
6. CUT: Execute cut with axis bitmask (parallel with prefetch)
7. EXIT: Bottom gate opens → product exits
8. REPEAT: Until bay empty

### Pipelining/Prefetching
Critical optimization: next item is dispensed and CV analyzed while current item cuts. Prefetch starts AFTER top gate closes (safety requirement).

### Hardware Communication (STM32)
5-byte UART packets with checksum validation. Command codes in `backend/comms/raspi_comms_manager.py`:
- Gates (0x10-0x1F): OPEN, CLOSE, CYCLE, HOPPER_DISPENSE
- Cutter (0x20-0x2F): CUT_EXECUTE (axis bitmask), CUT_HOME, CUT_ABORT
- Scale (0x40-0x4F): SCALE_READ, SCALE_TARE
- System (0xF0-0xFF): EMERGENCY_STOP, RESET_SYSTEM

## Key Files

| File | Purpose |
|------|---------|
| config.json | System settings, vegetables, cut types |
| backend/config/config_manager.py | Global configuration access |
| backend/workflows/base_workflow.py | State machine + event system |
| backend/workflows/standard_workflow.py | Single parameterized workflow |
| backend/api/main.py | FastAPI endpoints, WebSocket, lifespan |
| backend/api/task_manager.py | Bay reservation, task queue |
| backend/comms/raspi_comms_manager.py | STM32 UART protocol |
| backend/cv/camera_manager.py | OpenCV + YOLO + EfficientNet |

## API Structure

REST endpoints: `/api/vegetables`, `/api/cut-types`, `/api/tasks` (CRUD), `/api/status`, `/api/emergency-stop`

WebSocket: `/ws/camera` (live JPEG frames), `/ws/updates` (system events)

Task model: One task per bay maximum. TaskManager enforces bay reservation.

## Code Patterns

```python
# Configuration access
from backend.config import get_config
config = get_config()
veg = config.get_vegetable('cucumber')
cut = config.get_cut_type('sliced')

# Create workflow
workflow = StandardVegetableWorkflow(
    stm32_interface=stm32,
    cv_manager=camera,
    vegetable_config=veg,
    bay_id=1,            # Runtime parameter
    cut_type="sliced",   # Runtime parameter
    target_count=50,
    update_callback=async_callback
)
await workflow.run()
```

## Conventions

- Async-first: all workflows, CV, and hardware comms are async
- Type hints throughout with Pydantic models for API contracts
- Custom exceptions: WorkflowError, HardwareError, CVError, SafetyError
- Enums for constants: CommandCode, ResponseStatus, WorkflowState, WorkflowEvent
- pytest with pytest-asyncio for testing
