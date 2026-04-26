"""
main.py

FastAPI application for the Vegetable Processing System.
Provides REST API and WebSocket endpoints for the frontend UI.

Author: Ficio Prep Team
Date: February 2026
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from contextlib import asynccontextmanager
import logging
import asyncio
import os
import cv2
import json
from typing import Dict, List, Optional, Set
from pathlib import Path

from backend.api.models import (
    VegetableResponse,
    CutTypeResponse,
    TaskCreateRequest,
    TaskResponse,
    SystemStatusResponse,
    ErrorResponse
)
from backend.api.task_manager import TaskManager, Task, TaskStatus
from backend.config.config_manager import ConfigManager, get_config, set_config
from backend.cv.camera_manager import CameraManager
from backend.comms.raspi_comms_manager import RaspiCommsManager
from backend.stm32_interface import STM32Interface
from backend.config.machine_config import get_machine_config


# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================

# Global instances
task_manager: Optional[TaskManager] = None
camera_manager: Optional[CameraManager] = None
config: Optional[ConfigManager] = None
comms_manager: Optional[RaspiCommsManager] = None
stm32_interface: Optional[STM32Interface] = None

# WebSocket connections for live updates
active_websockets: Set[WebSocket] = set()
websocket_tasks: Set[asyncio.Task] = set()  # Track WebSocket handler tasks
shutdown_event: Optional[asyncio.Event] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes and cleans up resources on startup/shutdown.
    Performs config handshake with STM32 before accepting requests.
    """
    global task_manager, camera_manager, config, shutdown_event, comms_manager, stm32_interface

    logger = logging.getLogger('FastAPI')
    logger.info("Starting Vegetable Processing System API...")

    # Create shutdown event
    shutdown_event = asyncio.Event()

    try:
        # Initialize configuration
        config = ConfigManager('config.json')
        config.validate()
        set_config(config)
        logger.info("Configuration loaded and validated")

        # Check for mock mode before attempting any serial connection
        import os
        if os.environ.get("STM32_MOCK") == "1":
            from backend.comms.mock_stm32 import MockSTM32Interface
            stm32_interface = MockSTM32Interface()
            app.state.config_mismatch = False
            logger.info("STM32_MOCK=1: using MockSTM32Interface (skipping serial connection)")
            print("[mock] STM32_MOCK=1 active — MockSTM32Interface loaded", flush=True)
        else:
            # Initialize STM32 communications
            logger.info("Initializing STM32 communications...")
            try:
                serial_port = config.get_str('serial_port', '/dev/ttyAMA0')
                serial_baudrate = config.get_int('serial_baudrate', 115200)

                comms_manager = RaspiCommsManager(port=serial_port, baudrate=serial_baudrate)
                if not comms_manager.connect():
                    logger.error("Failed to connect to STM32 - running in disconnected mode")
                    stm32_interface = None
                    app.state.config_mismatch = True
                else:
                    logger.info("STM32 connected successfully")
                    stm32_interface = STM32Interface(comms_manager)

                    # Perform config handshake
                    machine_config = get_machine_config()
                    logger.info("Performing config handshake...")

                    try:
                        config_match = await stm32_interface.validate_config(
                            num_hoppers=machine_config.num_hoppers,
                            num_actuators=machine_config.num_actuators,
                            bottom_gate=machine_config.bottom_gate_present,
                            parallelization=machine_config.parallelization_enabled,
                            num_vib_motors=machine_config.num_vibration_motors
                        )

                        if not config_match:
                            logger.critical(
                                "CONFIG MISMATCH: RasPi and STM32 configs do not match! "
                                "Update config.json or reflash STM32 firmware. "
                                "System will NOT enter main operation."
                            )
                            app.state.config_mismatch = True
                        else:
                            logger.info("Config validation SUCCESS - waiting for Power On")
                            app.state.config_mismatch = False

                    except Exception as e:
                        logger.error(f"Config handshake failed: {e}")
                        app.state.config_mismatch = True

            except Exception as e:
                logger.error(f"STM32 initialization failed: {e}")
                comms_manager = None
                stm32_interface = None
                app.state.config_mismatch = True

        # System starts in powered-off state; operator must press Power On to home actuators
        app.state.system_initialized = False

        # Initialize camera
        camera_manager = CameraManager()
        logger.info("Camera initialized")

        # Initialize task manager with workflow event callback
        task_manager = TaskManager(
            config,
            camera_manager,
            stm32_interface=stm32_interface,
            workflow_event_callback=broadcast_workflow_event,
            task_status_callback=broadcast_task_update
        )
        logger.info("Task manager initialized")

        logger.info("System startup complete")

        yield

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down system...")

        # 1. Signal all WebSocket endpoints to close
        if shutdown_event:
            shutdown_event.set()

        # 2. Cancel all WebSocket handler tasks
        for task in websocket_tasks:
            if not task.done():
                task.cancel()

        # 3. Wait briefly for handlers to exit
        if websocket_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*websocket_tasks, return_exceptions=True),
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some WebSocket handlers did not exit cleanly")
        websocket_tasks.clear()

        # 4. Close all WebSocket connections
        disconnected = set()
        for ws in active_websockets:
            try:
                await ws.close(code=1001)
            except:
                pass
            disconnected.add(ws)
        active_websockets.difference_update(disconnected)

        # 5. Shutdown task manager (which cancels workflows)
        if task_manager:
            await task_manager.shutdown()

        # 6. Close camera
        if camera_manager:
            camera_manager.close()

        # 7. Close STM32 communications
        if comms_manager:
            comms_manager.disconnect()

        logger.info("Shutdown complete")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Vegetable Processing System API",
    description="Backend API for automated vegetable slicer control and monitoring",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# STATIC FILES
# ============================================================================

# Serve vegetable images — mount at /assets/ui specifically so it doesn't shadow frontend JS/CSS
install_path = Path("/home") / os.environ.get("USER", "pi") / "vegetable-slicer"
ui_images_path = install_path / "assets" / "ui"
local_ui_images_path = Path(__file__).parent.parent.parent / "assets" / "ui"
if ui_images_path.exists():
    app.mount("/assets/ui", StaticFiles(directory=str(ui_images_path)), name="ui-images")
elif local_ui_images_path.exists():
    app.mount("/assets/ui", StaticFiles(directory=str(local_ui_images_path)), name="ui-images")

# Serve React frontend build
frontend_dist_path = Path(__file__).parent.parent.parent / "frontend" / "dist"


# ============================================================================
# CONFIGURATION ENDPOINTS
# ============================================================================

@app.get("/api/vegetables", response_model=List[VegetableResponse])
async def list_vegetables():
    """
    Get list of all available vegetables.
    
    Returns:
        List of vegetables with IDs, names, images, and supported cuts
    """
    vegetables = config.get_vegetables_dict()
    return [
        VegetableResponse(
            id=veg['id'],
            name=veg['name'],
            image_url=f"/assets/ui/{Path(veg['image_path']).name}",
            supported_cuts=veg['supported_cuts']
        )
        for veg in vegetables
    ]


@app.get("/api/vegetables/{vegetable_id}/cuts", response_model=List[CutTypeResponse])
async def get_vegetable_cuts(vegetable_id: str):
    """
    Get supported cut types for a specific vegetable.
    
    Args:
        vegetable_id: Vegetable ID (e.g., "cucumber")
    
    Returns:
        List of supported cut types with details
    """
    veg = config.get_vegetable(vegetable_id)
    if not veg:
        raise HTTPException(status_code=404, detail=f"Vegetable '{vegetable_id}' not found")
    
    all_cuts = config.get_cut_types_dict()
    
    return [
        CutTypeResponse(
            name=cut_name,
            display_name=all_cuts[cut_name]['display_name'],
            description=all_cuts[cut_name]['description']
        )
        for cut_name in veg.supported_cuts
        if cut_name in all_cuts
    ]


@app.get("/api/cut-types", response_model=Dict[str, CutTypeResponse])
async def list_cut_types():
    """
    Get all available cut types.

    Returns:
        Dictionary of cut type configurations
    """
    cuts = config.get_cut_types_dict()
    return {
        name: CutTypeResponse(
            name=cut['name'],
            display_name=cut['display_name'],
            description=cut['description']
        )
        for name, cut in cuts.items()
    }


@app.get("/api/config/machine")
async def machine_config_endpoint():
    """
    Get machine variant configuration.

    Returns machine hardware configuration for UI adaptation.
    Frontend can use this to show/hide features based on variant.

    Returns:
        Dictionary with machine variant and hardware capabilities

    API Contract (non-breaking addition):
        Response: {
            "variant": str,           # "mini" or "vertical"
            "num_hoppers": int,       # Number of hoppers (1-4)
            "num_actuators": int,     # Number of cutter actuators (1-3)
            "bottom_gate_present": bool,  # Bottom gate installed
            "parallelization_enabled": bool  # Parallel processing enabled
        }
    """
    from backend.config.machine_config import get_machine_config
    machine_config = get_machine_config()
    return {
        "variant": machine_config.active_variant,
        "num_hoppers": machine_config.num_hoppers,
        "num_actuators": machine_config.num_actuators,
        "bottom_gate_present": machine_config.bottom_gate_present,
        "parallelization_enabled": machine_config.parallelization_enabled
    }


# ============================================================================
# TASK MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/api/tasks", response_model=TaskResponse, status_code=201)
async def create_task(request: TaskCreateRequest, background_tasks: BackgroundTasks):
    """
    Create a new processing task.

    CRITICAL RULES:
    - Only ONE task per bay (queued OR running)
    - Task runs until STM32 reports hopper EMPTY
    - NO target count - processes entire hopper
    - Bay becomes available only after hopper is empty

    API Contract (MUST remain stable):
        Request body: {
            "vegetable_id": str,  # e.g., "cucumber"
            "cut_type": str,      # e.g., "sliced"
            "bay_id": int,        # 1-4
            "workflow_class": Optional[str]  # Optional workflow override
        }
        Response: TaskResponse (see models.py)

    Args:
        request: Task creation request with vegetable, bay, and cut type

    Returns:
        Created task details

    Raises:
        HTTPException 409: If bay already has a task
        HTTPException 503: If config mismatch detected
    """
    # Check for config mismatch (prevents operation if STM32/RasPi configs don't match)
    if getattr(app.state, 'config_mismatch', False):
        raise HTTPException(
            status_code=503,
            detail="Config mismatch detected - cannot create tasks until resolved. Check logs for details."
        )

    # Check system is initialized (Power On must be pressed first)
    if not getattr(app.state, 'system_initialized', False):
        raise HTTPException(
            status_code=503,
            detail="System not initialized. Press Power On to home actuators before starting tasks."
        )

    # Validate vegetable exists
    veg = config.get_vegetable(request.vegetable_id)
    if not veg:
        raise HTTPException(status_code=404, detail=f"Vegetable '{request.vegetable_id}' not found")
    
    # Validate cut type is supported
    if not config.is_cut_supported(request.vegetable_id, request.cut_type):
        raise HTTPException(
            status_code=400,
            detail=f"Cut type '{request.cut_type}' not supported for {veg.name}"
        )
    
    # Validate bay is valid (1 to num_hoppers)
    from backend.config.machine_config import get_machine_config
    num_bays = get_machine_config().num_hoppers
    if request.bay_id < 1 or request.bay_id > num_bays:
        raise HTTPException(status_code=400, detail=f"Invalid bay ID: {request.bay_id}")
    
    # Check if bay already has a task (queued OR running)
    if task_manager.is_bay_in_use(request.bay_id):
        raise HTTPException(
            status_code=409,
            detail=f"Bay {request.bay_id} already has a task. Wait until it's empty."
        )
    
    # Create task (will reserve the bay)
    try:
        task = await task_manager.create_task(
            vegetable_id=request.vegetable_id,
            bay_id=request.bay_id,
            cut_type=request.cut_type,
            workflow_class=request.workflow_class
        )
    except ValueError as e:
        # Bay already reserved (race condition)
        raise HTTPException(status_code=409, detail=str(e))
    
    # Notify WebSocket clients
    await broadcast_task_update(task)
    
    return TaskResponse.from_task(task)


@app.get("/api/tasks", response_model=List[TaskResponse])
async def list_tasks():
    """
    Get all tasks (queued, active, completed, failed).
    
    Returns:
        List of all tasks
    """
    tasks = task_manager.get_all_tasks()
    return [TaskResponse.from_task(task) for task in tasks]


@app.get("/api/tasks/active", response_model=List[TaskResponse])
async def list_active_tasks():
    """
    Get currently active tasks.
    
    Returns:
        List of running tasks
    """
    tasks = task_manager.get_active_tasks()
    return [TaskResponse.from_task(task) for task in tasks]


@app.get("/api/tasks/queue", response_model=List[TaskResponse])
async def list_queued_tasks():
    """
    Get queued tasks waiting to start.
    
    Returns:
        List of queued tasks
    """
    tasks = task_manager.get_queued_tasks()
    return [TaskResponse.from_task(task) for task in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    Get details of a specific task.
    
    Args:
        task_id: Task UUID
    
    Returns:
        Task details
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    
    return TaskResponse.from_task(task)


@app.delete("/api/tasks/{task_id}", status_code=204)
async def cancel_task(task_id: str):
    """
    Cancel a task (if queued or active).

    Args:
        task_id: Task UUID
    """
    success = await task_manager.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found or cannot be cancelled")

    # Notify WebSocket clients
    task = task_manager.get_task(task_id)
    if task:
        await broadcast_task_update(task)


@app.post("/api/tasks/{task_id}/stop", status_code=204)
async def stop_task_gracefully(task_id: str):
    """
    Gracefully stop an active task after the current veggie cycle completes.

    The workflow finishes the current item (dispense + CV + cut + gate return)
    and then stops processing. Task transitions to COMPLETED status.

    Use DELETE /api/tasks/{task_id} to cancel a QUEUED task immediately.

    Args:
        task_id: Task UUID

    Raises:
        HTTPException 404: Task not found or not in RUNNING state
    """
    success = await task_manager.graceful_stop_task(task_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found or not currently running (use DELETE for queued tasks)"
        )


# ============================================================================
# SYSTEM STATUS ENDPOINTS
# ============================================================================

@app.get("/api/status", response_model=SystemStatusResponse)
async def get_system_status():
    """
    Get current system status.
    
    Returns:
        System status including scale weight, active tasks, available bays
        
    Note: 
    - Only one task runs at a time (shared cutting chamber)
    - available_bays = bays with NO tasks (not queued, not running)
    """
    # Get scale weight (would query STM32 in production)
    scale_weight = 0.0  # Placeholder
    
    # Get truly available bays (no tasks at all)
    available_bays = list(task_manager.get_available_bays())
    
    # Get task counts
    all_tasks = task_manager.get_all_tasks()
    active_count = len([t for t in all_tasks if t.status == TaskStatus.RUNNING])
    queued_count = len([t for t in all_tasks if t.status == TaskStatus.QUEUED])
    
    return SystemStatusResponse(
        scale_weight_grams=scale_weight,
        active_tasks=active_count,
        queued_tasks=queued_count,
        available_bays=available_bays,
        camera_ready=camera_manager.is_ready() if camera_manager else False
    )


@app.post("/api/emergency-stop", status_code=204)
async def emergency_stop():
    """
    Emergency stop - cancel all tasks and halt system.
    """
    # Send hardware e-stop first
    if stm32_interface:
        await stm32_interface.emergency_stop()

    await task_manager.emergency_stop()

    # Broadcast to all WebSocket clients
    await broadcast_system_event({
        'event': 'emergency_stop',
        'timestamp': asyncio.get_event_loop().time()
    })


@app.post("/api/restart", status_code=200)
async def restart_system():
    """
    Recalibrate STM32 actuators and re-queue all STOPPED tasks.

    Sequence: reset_system -> home_actuators (~30s) -> re-queue stopped tasks.
    """
    if not stm32_interface:
        raise HTTPException(status_code=503, detail="STM32 not connected")

    count = await task_manager.restart(stm32_interface)

    await broadcast_system_event({
        'event': 'system_restarted',
        'tasks_requeued': count
    })

    return {"tasks_requeued": count}


@app.post("/api/power-on", status_code=200)
async def power_on():
    """
    Initialize the system: home all actuators then mark system as ready.

    Must be called before tasks can be created. Sends CMD_CUT_HOME to the STM32
    which runs the full boot sequence (~30-45s), then marks system_initialized=True.

    Sequence: emergency_stop (reset all FSMs) -> reset_system -> home_actuators (~30-45s) -> ready.
    """
    if not stm32_interface:
        raise HTTPException(status_code=503, detail="STM32 not connected")

    if getattr(app.state, 'config_mismatch', False):
        raise HTTPException(status_code=503, detail="Config mismatch - resolve before powering on")

    if getattr(app.state, 'system_initialized', False):
        raise HTTPException(status_code=409, detail="System is already initialized")

    try:
        # Reset all hardware FSMs (gate, cutter, hopper) in case they're stuck from a prior session.
        # Cutter_Boot_Up (inside home_actuators) resets cutter FSM explicitly, but Gate_EmergencyStop
        # is only triggered by CMD_EMERGENCY_STOP — so we must call it here to guarantee GATE_IDLE.
        await stm32_interface.emergency_stop()
        await asyncio.sleep(0.5)  # Let emergency-stop servo close commands execute
        await stm32_interface.reset_system()
        await stm32_interface.home_actuators()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Power on failed: {str(e)}")

    app.state.system_initialized = True

    await broadcast_system_event({'event': 'system_powered_on'})

    return {"status": "ready"}


@app.post("/api/power-off", status_code=200)
async def power_off():
    """
    Graceful shutdown: stop all tasks, home actuators, discard tasks, mark system as off.

    Sequence: block new tasks -> emergency stop -> clear all tasks ->
              reset_system -> home_actuators (~30-45s) -> system_initialized=False.
    """
    # Block new tasks immediately
    app.state.system_initialized = False

    # Halt all in-flight motion
    if stm32_interface:
        await stm32_interface.emergency_stop()

    # Mark all tasks as STOPPED and discard them (no re-queue on power off)
    await task_manager.emergency_stop()
    await task_manager.discard_all_tasks()

    # Home actuators to leave machine in safe state
    if stm32_interface:
        try:
            await stm32_interface.reset_system()
            await stm32_interface.home_actuators()
        except Exception as e:
            logging.getLogger('FastAPI').warning(f"Homing during power-off failed: {e}")

    await broadcast_system_event({'event': 'system_powered_off'})

    return {"status": "off"}


# ============================================================================
# CAMERA ENDPOINTS
# ============================================================================

@app.get("/api/camera/snapshot")
async def get_camera_snapshot():
    """
    Get a single frame from the camera as JPEG.
    
    Returns:
        JPEG image
    """
    if not camera_manager or not camera_manager.is_ready():
        raise HTTPException(status_code=503, detail="Camera not available")
    
    try:
        frame = camera_manager.capture_frame()
        
        # Encode as JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        return StreamingResponse(
            iter([buffer.tobytes()]),
            media_type="image/jpeg"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture frame: {str(e)}")


# ============================================================================
# WEBSOCKET ENDPOINTS
# ============================================================================

@app.websocket("/ws/camera")
async def websocket_camera_feed(websocket: WebSocket):
    """
    WebSocket endpoint for live camera feed.
    Streams JPEG frames continuously.
    """
    await websocket.accept()
    active_websockets.add(websocket)

    # Track this handler task
    current_task = asyncio.current_task()
    if current_task:
        websocket_tasks.add(current_task)

    try:
        while not shutdown_event.is_set():
            if not camera_manager or not camera_manager.is_ready():
                await asyncio.sleep(0.1)
                continue

            try:
                # Capture stream frame (lower resolution, FPS-capped)
                frame = camera_manager.capture_stream_frame()

                # Encode as JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

                # Send to client
                await websocket.send_bytes(buffer.tobytes())

                # Limit frame rate to ~30 FPS
                await asyncio.sleep(1/30)

            except asyncio.CancelledError:
                # Gracefully exit on cancellation
                break
            except Exception as e:
                logging.error(f"Error streaming frame: {e}")
                break

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        active_websockets.discard(websocket)
        if current_task:
            websocket_tasks.discard(current_task)


@app.websocket("/ws/updates")
async def websocket_system_updates(websocket: WebSocket):
    """
    WebSocket endpoint for system updates.
    Sends task updates, status changes, and system events.
    """
    await websocket.accept()
    active_websockets.add(websocket)

    # Track this handler task
    current_task = asyncio.current_task()
    if current_task:
        websocket_tasks.add(current_task)

    try:
        # Send initial status
        status = await get_system_status()
        await websocket.send_json({
            'type': 'status',
            'data': status.model_dump()
        })

        # Keep connection alive until shutdown
        while not shutdown_event.is_set():
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        pass
    finally:
        active_websockets.discard(websocket)
        if current_task:
            websocket_tasks.discard(current_task)


# ============================================================================
# WEBSOCKET BROADCAST HELPERS
# ============================================================================

async def broadcast_task_update(task: Task):
    """Broadcast task update to all connected WebSocket clients"""
    message = {
        'type': 'task_update',
        'data': TaskResponse.from_task(task).model_dump()
    }
    
    disconnected = set()
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except:
            disconnected.add(ws)
    
    # Clean up disconnected clients
    active_websockets.difference_update(disconnected)


async def broadcast_system_event(event: dict):
    """Broadcast system event to all connected WebSocket clients"""
    message = {
        'type': 'system_event',
        'data': event
    }

    disconnected = set()
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except:
            disconnected.add(ws)

    active_websockets.difference_update(disconnected)


async def broadcast_workflow_event(event_name: str, event_data: dict):
    """
    Broadcast workflow event to all connected WebSocket clients.

    Args:
        event_name: WorkflowEvent enum value (e.g., "item_dispensed")
        event_data: Event data dictionary

    WebSocket Message Format (API contract):
        {
            "type": "workflow_event",
            "event": str,              # Event name (e.g., "item_dispensed", "hopper_empty")
            "data": dict,              # Event-specific data
            "timestamp": float         # Unix timestamp
        }
    """
    import time
    message = {
        'type': 'workflow_event',
        'event': event_name,
        'data': event_data,
        'timestamp': time.time()
    }

    disconnected = set()
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except:
            disconnected.add(ws)

    active_websockets.difference_update(disconnected)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        System health status
    """
    return {
        "status": "healthy",
        "camera": camera_manager.is_ready() if camera_manager else False,
        "config_loaded": config is not None,
        "task_manager": task_manager is not None
    }


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error response"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# ============================================================================
# SPA FRONTEND SERVING
# ============================================================================

# Mount frontend static assets if the build exists
if frontend_dist_path.exists():
    frontend_assets = frontend_dist_path / "assets"
    if frontend_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_assets)), name="frontend-static")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    Serve React SPA for all non-API routes.
    This catch-all route must be defined LAST.
    """
    # Don't interfere with API, WebSocket, assets, or health routes
    if (
        full_path.startswith("api/") or
        full_path.startswith("ws/") or
        full_path.startswith("assets/") or
        full_path.startswith("static/") or
        full_path == "health"
    ):
        raise HTTPException(status_code=404, detail="Not found")

    # Serve index.html for SPA routing
    index_path = frontend_dist_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    # Fallback: if no frontend build, return 404
    raise HTTPException(status_code=404, detail="Frontend not built. Run 'npm run build' in frontend/")


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )