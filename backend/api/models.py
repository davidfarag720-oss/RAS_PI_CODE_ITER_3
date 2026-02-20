"""
models.py

Pydantic models for API request/response validation.
Defines the contract between frontend and backend.

Author: Ficio Prep Team
Date: February 2026
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================================================
# VEGETABLE MODELS
# ============================================================================

class VegetableResponse(BaseModel):
    """Response model for vegetable information"""
    id: str = Field(..., description="Vegetable ID (e.g., 'cucumber')")
    name: str = Field(..., description="Display name")
    image_url: str = Field(..., description="URL to vegetable image")
    supported_cuts: List[str] = Field(..., description="List of supported cut types")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "cucumber",
                "name": "Cucumber",
                "image_url": "/assets/ui/cucumber.png",
                "supported_cuts": ["sliced", "cubed"]
            }
        }


# ============================================================================
# CUT TYPE MODELS
# ============================================================================

class CutTypeResponse(BaseModel):
    """Response model for cut type information"""
    name: str = Field(..., description="Cut type identifier")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Cut type description")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "sliced",
                "display_name": "Sliced",
                "description": "Round/flat slices"
            }
        }


# ============================================================================
# TASK MODELS
# ============================================================================

class TaskStatus(str, Enum):
    """Task status enumeration"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"  # stopped by emergency, can be re-queued via restart()


class TaskCreateRequest(BaseModel):
    """Request model for creating a new task"""
    vegetable_id: str = Field(..., description="Vegetable to process")
    bay_id: int = Field(..., ge=1, le=4, description="Bay/hopper number (1-4)")
    cut_type: str = Field(..., description="Cut type to apply")
    workflow_class: Optional[str] = Field(
        None,
        description="Optional custom workflow class name (for extensibility)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "vegetable_id": "cucumber",
                "bay_id": 1,
                "cut_type": "sliced",
                "workflow_class": None
            }
        }


class TaskStats(BaseModel):
    """Statistics for a task"""
    items_processed: int = Field(0, description="Items successfully processed")
    items_rejected: int = Field(0, description="Items rejected by CV")
    weight_processed_grams: float = Field(0.0, description="Total weight processed")
    success_rate: float = Field(0.0, ge=0.0, le=1.0, description="Success rate (0-1)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "items_processed": 45,
                "items_rejected": 5,
                "weight_processed_grams": 2350.5,
                "success_rate": 0.90
            }
        }


class TaskResponse(BaseModel):
    """Response model for task information"""
    id: str = Field(..., description="Task UUID")
    vegetable_id: str = Field(..., description="Vegetable being processed")
    vegetable_name: str = Field(..., description="Vegetable display name")
    bay_id: int = Field(..., description="Bay number")
    cut_type: str = Field(..., description="Cut type")
    cut_display_name: str = Field(..., description="Cut type display name")
    status: TaskStatus = Field(..., description="Current task status")
    stats: TaskStats = Field(..., description="Task statistics")
    created_at: datetime = Field(..., description="Task creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Task start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Task completion timestamp")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    @classmethod
    def from_task(cls, task: 'Task') -> 'TaskResponse':
        """
        Create TaskResponse from Task object.
        
        Args:
            task: Task instance from TaskManager
        
        Returns:
            TaskResponse
        """
        return cls(
            id=task.id,
            vegetable_id=task.vegetable_id,
            vegetable_name=task.vegetable_name,
            bay_id=task.bay_id,
            cut_type=task.cut_type,
            cut_display_name=task.cut_display_name,
            status=task.status,
            stats=TaskStats(
                items_processed=task.items_processed,
                items_rejected=task.items_rejected,
                weight_processed_grams=task.weight_processed_grams,
                success_rate=task.success_rate
            ),
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error_message=task.error_message
        )
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "vegetable_id": "cucumber",
                "vegetable_name": "Cucumber",
                "bay_id": 1,
                "cut_type": "sliced",
                "cut_display_name": "Sliced",
                "status": "running",
                "stats": {
                    "items_processed": 23,
                    "items_rejected": 2,
                    "weight_processed_grams": 1150.0,
                    "success_rate": 0.92
                },
                "created_at": "2026-02-10T10:30:00Z",
                "started_at": "2026-02-10T10:30:15Z",
                "completed_at": None,
                "error_message": None
            }
        }


# ============================================================================
# SYSTEM STATUS MODELS
# ============================================================================

class SystemStatusResponse(BaseModel):
    """Response model for system status"""
    scale_weight_grams: float = Field(..., description="Current scale reading")
    active_tasks: int = Field(..., description="Number of active tasks")
    queued_tasks: int = Field(..., description="Number of queued tasks")
    available_bays: List[int] = Field(..., description="Available bay numbers")
    camera_ready: bool = Field(..., description="Camera status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "scale_weight_grams": 2458.5,
                "active_tasks": 2,
                "queued_tasks": 1,
                "available_bays": [2, 4],
                "camera_ready": True
            }
        }


# ============================================================================
# ERROR MODELS
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str = Field(..., description="Error message")
    status_code: int = Field(..., description="HTTP status code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Vegetable 'unknown' not found",
                "status_code": 404,
                "details": None
            }
        }


# ============================================================================
# WEBSOCKET MESSAGE MODELS
# ============================================================================

class WebSocketMessage(BaseModel):
    """Base WebSocket message"""
    type: str = Field(..., description="Message type")
    data: Dict[str, Any] = Field(..., description="Message payload")


class TaskUpdateMessage(WebSocketMessage):
    """Task update WebSocket message"""
    type: str = "task_update"
    data: TaskResponse


class SystemEventMessage(WebSocketMessage):
    """System event WebSocket message"""
    type: str = "system_event"
    data: Dict[str, Any]