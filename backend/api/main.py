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


# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================

# Global instances
task_manager: Optional[TaskManager] = None
camera_manager: Optional[CameraManager] = None
config: Optional[ConfigManager] = None

# WebSocket connections for live updates
active_websockets: Set[WebSocket] = set()
shutdown_event: Optional[asyncio.Event] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Initializes and cleans up resources on startup/shutdown.
    """
    global task_manager, camera_manager, config, shutdown_event

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

        # Initialize camera
        camera_manager = CameraManager()
        logger.info("Camera initialized")

        # Initialize task manager
        task_manager = TaskManager(config, camera_manager)
        logger.info("Task manager initialized")

        logger.info("✓ System startup complete")

        yield

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down system...")

        # Signal all WebSocket endpoints to close
        if shutdown_event:
            shutdown_event.set()

        # Close all active WebSocket connections
        disconnected = set()
        for ws in active_websockets:
            try:
                await ws.close(code=1001)
            except:
                pass
            disconnected.add(ws)
        active_websockets.difference_update(disconnected)

        # Give WebSocket handlers time to clean up
        await asyncio.sleep(0.5)

        if task_manager:
            await task_manager.shutdown()

        if camera_manager:
            camera_manager.close()

        logger.info("✓ Shutdown complete")


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

# Serve vegetable images and other assets
install_path = Path("/home/pi/vegetable-slicer")
assets_path = install_path / "assets"

# Also check for local development paths
local_assets_path = Path(__file__).parent.parent.parent / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
elif local_assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(local_assets_path)), name="assets")

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
    
    Args:
        request: Task creation request with vegetable, bay, and cut type
    
    Returns:
        Created task details
        
    Raises:
        HTTPException 409: If bay already has a task
    """
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
    
    # Validate bay is valid (1-4)
    num_bays = config.get_int('num_bays', 4)
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
    await task_manager.emergency_stop()
    
    # Broadcast to all WebSocket clients
    await broadcast_system_event({
        'event': 'emergency_stop',
        'timestamp': asyncio.get_event_loop().time()
    })


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

    try:
        while not shutdown_event.is_set():
            if not camera_manager or not camera_manager.is_ready():
                await asyncio.sleep(0.1)
                continue

            try:
                # Capture frame
                frame = camera_manager.capture_frame()

                # Encode as JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

                # Send to client
                await websocket.send_bytes(buffer.tobytes())

                # Limit frame rate to ~30 FPS
                await asyncio.sleep(1/30)

            except Exception as e:
                logging.error(f"Error streaming frame: {e}")
                break

    except WebSocketDisconnect:
        pass
    finally:
        active_websockets.discard(websocket)


@app.websocket("/ws/updates")
async def websocket_system_updates(websocket: WebSocket):
    """
    WebSocket endpoint for system updates.
    Sends task updates, status changes, and system events.
    """
    await websocket.accept()
    active_websockets.add(websocket)

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
    finally:
        active_websockets.discard(websocket)


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
        app.mount("/static", StaticFiles(directory=str(frontend_assets)), name="frontend-static")


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