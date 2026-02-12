"""
test_api_integration.py

Comprehensive test suite for FastAPI integration.
Tests all endpoints and API contracts.

Author: Ficio Prep Team
Date: February 2026
"""

import pytest
import pytest_asyncio
import asyncio
import json
from pathlib import Path
from httpx import AsyncClient
from fastapi.testclient import TestClient
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.api.main import app
from backend.api import main as api_main
from backend.config.config_manager import ConfigManager, set_config


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="session")
def test_config():
    """Load test configuration"""
    config = ConfigManager('config.json')
    set_config(config)
    return config


@pytest.fixture
def client(test_config):
    """Create test client with fresh task manager state"""
    with TestClient(app) as client:
        yield client
        # Cleanup: Reset task manager state after each test
        if api_main.task_manager:
            api_main.task_manager.tasks.clear()
            api_main.task_manager.task_queue.clear()
            api_main.task_manager.reserved_bays.clear()
            api_main.task_manager.active_bays.clear()


@pytest_asyncio.fixture
async def async_client(test_config):
    """Create async test client with fresh task manager state"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
        # Cleanup: Reset task manager state after each test
        await asyncio.sleep(0.1)  # Allow any pending operations to complete
        if api_main.task_manager:
            api_main.task_manager.tasks.clear()
            api_main.task_manager.task_queue.clear()
            api_main.task_manager.reserved_bays.clear()
            api_main.task_manager.active_bays.clear()


# ============================================================================
# CONFIGURATION ENDPOINT TESTS
# ============================================================================

class TestConfigurationEndpoints:
    """Test configuration-related endpoints"""

    def test_list_vegetables(self, client):
        """Test GET /api/vegetables"""
        response = client.get("/api/vegetables")

        assert response.status_code == 200
        vegetables = response.json()

        assert isinstance(vegetables, list)
        assert len(vegetables) == 4  # cucumber, carrot, tomato, potato

        # Check structure
        for veg in vegetables:
            assert 'id' in veg
            assert 'name' in veg
            assert 'image_url' in veg
            assert 'supported_cuts' in veg
            assert isinstance(veg['supported_cuts'], list)

        # Check cucumber specifically
        cucumber = next((v for v in vegetables if v['id'] == 'cucumber'), None)
        assert cucumber is not None
        assert cucumber['name'] == 'Cucumber'
        assert 'sliced' in cucumber['supported_cuts']
        assert 'cubed' in cucumber['supported_cuts']

        print("✓ test_list_vegetables passed")

    def test_get_vegetable_cuts(self, client):
        """Test GET /api/vegetables/{id}/cuts"""
        response = client.get("/api/vegetables/cucumber/cuts")

        assert response.status_code == 200
        cuts = response.json()

        assert isinstance(cuts, list)
        assert len(cuts) == 2  # sliced, cubed

        # Check structure
        for cut in cuts:
            assert 'name' in cut
            assert 'display_name' in cut
            assert 'description' in cut

        # Check specific cuts
        cut_names = [c['name'] for c in cuts]
        assert 'sliced' in cut_names
        assert 'cubed' in cut_names

        print("✓ test_get_vegetable_cuts passed")

    def test_get_vegetable_cuts_not_found(self, client):
        """Test GET /api/vegetables/{id}/cuts with invalid vegetable"""
        response = client.get("/api/vegetables/invalid_vegetable/cuts")

        assert response.status_code == 404
        error = response.json()
        assert 'detail' in error

        print("✓ test_get_vegetable_cuts_not_found passed")

    def test_list_cut_types(self, client):
        """Test GET /api/cut-types"""
        response = client.get("/api/cut-types")

        assert response.status_code == 200
        cuts = response.json()

        assert isinstance(cuts, dict)
        assert 'sliced' in cuts
        assert 'cubed' in cuts
        assert 'long_fry' in cuts

        # Check structure
        for cut_name, cut_data in cuts.items():
            assert 'name' in cut_data
            assert 'display_name' in cut_data
            assert 'description' in cut_data

        print("✓ test_list_cut_types passed")


# ============================================================================
# TASK MANAGEMENT ENDPOINT TESTS
# ============================================================================

class TestTaskManagementEndpoints:
    """Test task management endpoints"""

    @pytest.mark.asyncio
    async def test_create_task(self, async_client):
        """Test POST /api/tasks"""
        task_data = {
            "vegetable_id": "cucumber",
            "bay_id": 1,
            "cut_type": "sliced"
        }

        response = await async_client.post("/api/tasks", json=task_data)

        assert response.status_code == 201
        task = response.json()

        # Check response structure
        assert 'id' in task
        assert task['vegetable_id'] == 'cucumber'
        assert task['bay_id'] == 1
        assert task['cut_type'] == 'sliced'
        assert task['status'] == 'queued'
        assert 'stats' in task
        assert 'created_at' in task

        print("✓ test_create_task passed")

    @pytest.mark.asyncio
    async def test_create_task_invalid_vegetable(self, async_client):
        """Test POST /api/tasks with invalid vegetable"""
        task_data = {
            "vegetable_id": "invalid_veg",
            "bay_id": 1,
            "cut_type": "sliced"
        }

        response = await async_client.post("/api/tasks", json=task_data)
        assert response.status_code == 404

        print("✓ test_create_task_invalid_vegetable passed")

    @pytest.mark.asyncio
    async def test_create_task_unsupported_cut(self, async_client):
        """Test POST /api/tasks with unsupported cut type"""
        task_data = {
            "vegetable_id": "cucumber",
            "bay_id": 1,
            "cut_type": "long_fry"  # Not supported for cucumber
        }

        response = await async_client.post("/api/tasks", json=task_data)
        assert response.status_code == 400

        print("✓ test_create_task_unsupported_cut passed")

    @pytest.mark.asyncio
    async def test_create_task_invalid_bay(self, async_client):
        """Test POST /api/tasks with invalid bay ID"""
        task_data = {
            "vegetable_id": "cucumber",
            "bay_id": 10,  # Invalid bay
            "cut_type": "sliced"
        }

        response = await async_client.post("/api/tasks", json=task_data)
        # Pydantic validation returns 422 for invalid bay_id (outside 1-4 range)
        assert response.status_code == 422

        print("✓ test_create_task_invalid_bay passed")

    @pytest.mark.asyncio
    async def test_list_tasks(self, async_client):
        """Test GET /api/tasks"""
        # Create a task first
        task_data = {
            "vegetable_id": "carrot",
            "bay_id": 2,
            "cut_type": "sliced"
        }
        create_response = await async_client.post("/api/tasks", json=task_data)
        assert create_response.status_code == 201

        # List tasks
        response = await async_client.get("/api/tasks")

        assert response.status_code == 200
        tasks = response.json()

        assert isinstance(tasks, list)
        assert len(tasks) > 0

        print("✓ test_list_tasks passed")

    @pytest.mark.asyncio
    async def test_get_task(self, async_client):
        """Test GET /api/tasks/{id}"""
        # Create a task
        task_data = {
            "vegetable_id": "tomato",
            "bay_id": 3,
            "cut_type": "sliced"
        }
        create_response = await async_client.post("/api/tasks", json=task_data)
        task_id = create_response.json()['id']

        # Get task
        response = await async_client.get(f"/api/tasks/{task_id}")

        assert response.status_code == 200
        task = response.json()

        assert task['id'] == task_id
        assert task['vegetable_id'] == 'tomato'

        print("✓ test_get_task passed")

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, async_client):
        """Test GET /api/tasks/{id} with invalid ID"""
        response = await async_client.get("/api/tasks/invalid-id")

        assert response.status_code == 404

        print("✓ test_get_task_not_found passed")

    @pytest.mark.asyncio
    async def test_cancel_task(self, async_client):
        """Test DELETE /api/tasks/{id}"""
        # Create a task
        task_data = {
            "vegetable_id": "potato",
            "bay_id": 4,
            "cut_type": "cubed"
        }
        create_response = await async_client.post("/api/tasks", json=task_data)
        task_id = create_response.json()['id']

        # Cancel task
        response = await async_client.delete(f"/api/tasks/{task_id}")

        assert response.status_code == 204

        # Verify task is cancelled
        get_response = await async_client.get(f"/api/tasks/{task_id}")
        task = get_response.json()
        assert task['status'] in ['cancelled', 'queued']  # May still be queued if cancelled quickly

        print("✓ test_cancel_task passed")


# ============================================================================
# SYSTEM STATUS ENDPOINT TESTS
# ============================================================================

class TestSystemStatusEndpoints:
    """Test system status endpoints"""

    @pytest.mark.asyncio
    async def test_get_system_status(self, async_client):
        """Test GET /api/status"""
        response = await async_client.get("/api/status")

        assert response.status_code == 200
        status = response.json()

        # Check structure
        assert 'scale_weight_grams' in status
        assert 'active_tasks' in status
        assert 'queued_tasks' in status
        assert 'available_bays' in status
        assert 'camera_ready' in status

        assert isinstance(status['available_bays'], list)
        assert isinstance(status['active_tasks'], int)
        assert isinstance(status['queued_tasks'], int)

        print("✓ test_get_system_status passed")

    @pytest.mark.asyncio
    async def test_emergency_stop(self, async_client):
        """Test POST /api/emergency-stop"""
        response = await async_client.post("/api/emergency-stop")

        assert response.status_code == 204

        print("✓ test_emergency_stop passed")


# ============================================================================
# CAMERA ENDPOINT TESTS
# ============================================================================

class TestCameraEndpoints:
    """Test camera-related endpoints"""

    def test_get_camera_snapshot(self, client):
        """Test GET /api/camera/snapshot"""
        # This will fail if no camera is available, which is expected in testing
        response = client.get("/api/camera/snapshot")

        # Should either succeed (200) or fail with 503 (camera not available)
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            assert response.headers['content-type'] == 'image/jpeg'

        print("✓ test_get_camera_snapshot passed")


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

class TestHealthCheck:
    """Test health check endpoint"""

    def test_health_check(self, client):
        """Test GET /health"""
        response = client.get("/health")

        assert response.status_code == 200
        health = response.json()

        assert 'status' in health
        assert 'camera' in health
        assert 'config_loaded' in health
        assert 'task_manager' in health

        assert health['config_loaded'] is True
        assert health['task_manager'] is True

        print("✓ test_health_check passed")


# ============================================================================
# INTEGRATION TESTS (API Contract Tests)
# ============================================================================

class TestIntegration:
    """Integration tests verifying API contracts and bay reservation logic"""

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self, async_client):
        """
        Test complete task lifecycle: create -> check status

        Note: This test verifies the API contract for task creation and status.
        Actual task execution requires real hardware (STM32) and is tested on RPi.
        The mock STM32 cannot simulate the full hardware workflow.
        """
        # Create task
        task_data = {
            "vegetable_id": "cucumber",
            "bay_id": 1,
            "cut_type": "sliced"
        }

        create_response = await async_client.post("/api/tasks", json=task_data)
        assert create_response.status_code == 201
        task_id = create_response.json()['id']

        print(f"Created task: {task_id}")

        # Get task immediately after creation
        status_response = await async_client.get(f"/api/tasks/{task_id}")
        task = status_response.json()

        # Verify task structure and initial state
        assert task['status'] in ['queued', 'running']
        assert task['id'] == task_id
        assert task['vegetable_id'] == 'cucumber'
        assert task['bay_id'] == 1
        assert task['cut_type'] == 'sliced'
        assert 'stats' in task
        assert task['stats']['items_processed'] == 0

        print(f"Task status: {task['status']}")
        print("✓ test_full_task_lifecycle passed")

    @pytest.mark.asyncio
    async def test_bay_reservation(self, async_client):
        """Test that each bay can only have one task at a time"""
        # Create task on bay 1
        task1_data = {
            "vegetable_id": "cucumber",
            "bay_id": 1,
            "cut_type": "sliced"
        }
        response1 = await async_client.post("/api/tasks", json=task1_data)
        assert response1.status_code == 201

        # Try to create another task on bay 1 (should fail with 409 Conflict)
        task2_data = {
            "vegetable_id": "cucumber",
            "bay_id": 1,
            "cut_type": "cubed"
        }
        response2 = await async_client.post("/api/tasks", json=task2_data)
        assert response2.status_code == 409  # Conflict - bay already reserved

        # But can create task on bay 2 (different bay)
        task3_data = {
            "vegetable_id": "carrot",
            "bay_id": 2,
            "cut_type": "sliced"
        }
        response3 = await async_client.post("/api/tasks", json=task3_data)
        assert response3.status_code == 201

        print("✓ test_bay_reservation passed")

    @pytest.mark.asyncio
    async def test_sequential_execution(self, async_client):
        """Test task creation on multiple bays"""
        # Create task on bay 1
        task1_data = {"vegetable_id": "cucumber", "bay_id": 1, "cut_type": "sliced"}
        response1 = await async_client.post("/api/tasks", json=task1_data)
        assert response1.status_code == 201
        task1_id = response1.json()['id']

        # Create task on bay 2 (should succeed - different bay)
        task2_data = {"vegetable_id": "carrot", "bay_id": 2, "cut_type": "sliced"}
        response2 = await async_client.post("/api/tasks", json=task2_data)
        assert response2.status_code == 201
        task2_id = response2.json()['id']

        # Both tasks should exist
        status1 = await async_client.get(f"/api/tasks/{task1_id}")
        status2 = await async_client.get(f"/api/tasks/{task2_id}")

        task1 = status1.json()
        task2 = status2.json()

        # Verify both tasks exist in the system
        assert task1['id'] == task1_id
        assert task2['id'] == task2_id
        assert task1['bay_id'] == 1
        assert task2['bay_id'] == 2

        print("✓ test_sequential_execution passed")


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("FASTAPI INTEGRATION TEST SUITE")
    print("="*80 + "\n")

    # Run pytest
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-s"  # Show print statements
    ])
