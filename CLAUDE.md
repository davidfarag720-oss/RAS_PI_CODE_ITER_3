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

### Hardware Configuration

**Gates (6 total):**
- Gate 1 (Top Cutter): Controls entry into cutting chamber
- Gate 2 (Bottom Cutter): Controls exit from cutting chamber
- Gates 3-6: Map to Hoppers 1-4 respectively
- Smart Dispensing: STM32 "Cycle" command opens gate slowly until laser sensor trips (detects falling vegetable), then closes immediately to prevent double-feeding

**Cutters (3 axes):**
- Cutter 1: Vertical slice (X-axis)
- Cutter 2: Vertical slice (Y-axis)
- Cutter 3: Horizontal slice (Z-axis)
- Control: Raspberry Pi sends 3-bit bitmask; STM32 synchronizes physical movement

**Vibration System:**
- 4 motors corresponding to Hoppers 1-4
- Triggered concurrently with hopper dispense to prevent jams

**Scale:**
- Real-time weight monitoring polled from STM32
- Calibration/precision handled at firmware level

### Cut Type to Actuator Mapping

| Cut Type | Actuators | Axis Bitmask | Result |
|----------|-----------|--------------|--------|
| Long Fry | Cutters 1+2 | 0b011 (3) | Longitudinal sticks |
| Short Fry | Cutters 1+3 | 0b101 (5) | Short sticks |
| Sliced | Cutter 3 | 0b100 (4) | Round/flat slices |
| Long Slice | Cutter 1 | 0b001 (1) | Lengthwise slices |
| Cubed | Cutters 1+2+3 | 0b111 (7) | Cubes/dice |

### Computer Vision Decision Logic

**Model Ensemble:**
- Model A (YOLO): Detects object, labels as "healthy" or "unhealthy"
- Model B (EfficientNetV2): Binary classification (healthy vs unhealthy)

**Decision Flow:**
1. If YOLO detects multiple objects OR no label → follow EfficientNet
2. If models agree → follow consensus
3. If models disagree:
   - `cv_grading_mode: "lenient"` → Accept
   - `cv_grading_mode: "harsh"` → Reject

Captured images saved to `data/cv_images/` for telemetry and model retraining.

### Hardware Communication (STM32)

**Protocol:** 5-byte UART packets with checksum validation. The protocol is fully extensible for arbitrary functions (calibration routines, diagnostics, parameter updates, etc.).

**Baseline Command Set** (see `backend/comms/raspi_comms_manager.py`):
- 0x10 (CMD_GATE_CTRL): gate_id, action_code (0=Close, 1=Open, 2=Cycle)
- 0x20 (CMD_CUT_EXECUTE): 3-bit bitmask for axes
- 0x30 (CMD_VIB_SET): hopper_id, state (0=Off, 1=On)
- 0x40 (CMD_SCALE_READ): Returns weight as float
- 0x50 (CMD_GET_STATUS): Returns hopper empty/full status bits
- 0xF0+ (System): EMERGENCY_STOP, RESET_SYSTEM

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

## UI Screen Flow (Phase 3)

Touch-optimized interface with White/Grey/Green palette:

1. **Splash/Home:** "Ficio Prep" header, "Tap anywhere to begin" overlay
2. **Vegetable Selection:** 2xN grid of square tiles (rounded corners), vegetable image + name
3. **Configuration:**
   - Dropdown for cut type (filtered by vegetable's supported_cuts)
   - Bay selection (disables bays with active tasks)
   - Large green "Begin" button (bottom right)
4. **Processing (Active):**
   - Live camera feed of staging area
   - Large "Weight Processed: X kg" display
   - "Queue New Task" button (returns to Screen 2)
   - Queue list view
   - Large red "STOP" button

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

## Deployment Environment

- **Hardware:** Raspberry Pi 5
- **OS:** Linux (Debian-based)
- **Display:** Capacitive touch screen
- **Install Path:** `/home/pi/vegetable-slicer`
- **Camera:** USB camera (expandable to multi-camera via config)
- **Serial:** `/dev/ttyAMA0` @ 115200 baud (STM32 UART)
