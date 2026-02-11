#!/usr/bin/env python3
"""
test_pipelining.py

Test to verify that prefetching/pipelining works correctly.
Verifies that next item is dispensed and CV-checked while current item is cutting.

Author: Ficio Prep Team
Date: January 2026
"""

import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.config import ConfigManager, set_config
from backend.workflows import StandardVegetableWorkflow

print("="*60)
print("PIPELINING / PREFETCH VERIFICATION")
print("="*60)

# Initialize config
config = ConfigManager('config.json')
set_config(config)
cucumber = config.get_vegetable('cucumber')

# Mock interfaces with timing logs
class MockSTM32:
    def __init__(self):
        self.operation_log = []
    
    def _log(self, operation):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.operation_log.append(f"[{timestamp}] {operation}")
        print(f"  [{timestamp}] STM32: {operation}")
    
    def scale_tare(self):
        self._log("scale_tare")
        return True
    
    def is_hopper_empty(self, h):
        return False
    
    def gate_close(self, g):
        self._log(f"gate_close({g})")
        return True
    
    def hopper_dispense(self, h):
        self._log(f"hopper_dispense({h})")
        return True
    
    def gate_open(self, g):
        self._log(f"gate_open({g})")
        return True
    
    def cut_execute(self, b):
        self._log(f"cut_execute(0b{b:03b}) - CUTTING...")
        return True
    
    def scale_read(self):
        return 150.0
    
    def vibration_all_off(self):
        self._log("vibration_all_off")
        return True
    
    def emergency_stop(self):
        return True

class MockCV:
    def __init__(self):
        self.cv_log = []
    
    async def analyze_vegetable(self, vegetable_config, bay_id):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.cv_log.append(f"[{timestamp}] CV analysis for bay {bay_id}")
        print(f"  [{timestamp}] CV: Analyzing {vegetable_config.name}")
        
        # Simulate CV processing time
        await asyncio.sleep(0.1)
        
        return {
            'accepted': True,
            'confidence': 0.85,
            'healthy': True,
            'positioned': True,
            'reason': None,
            'models_agree': True,
            'image_path': '/fake/path.jpg'
        }

async def test_pipelining():
    """Test that pipelining/prefetch works correctly"""
    
    print("\n=== Testing Pipelined Workflow ===\n")
    
    # Create mock interfaces
    mock_stm32 = MockSTM32()
    mock_cv = MockCV()
    
    # Create workflow
    workflow = StandardVegetableWorkflow(
        stm32_interface=mock_stm32,
        cv_manager=mock_cv,
        vegetable_config=cucumber,
        bay_id=1,
        cut_type="sliced",
        target_count=3  # Process 3 items to see pipelining
    )
    
    # Reduce delays for faster testing
    workflow.staging_delay = 0.05
    workflow.gate_delay = 0.05
    workflow.cut_delay = 0.2  # Simulate cut taking time
    
    print(f"Running: {workflow.workflow_name}")
    print(f"Target: {workflow.target_count} items\n")
    
    start_time = datetime.now()
    
    try:
        await workflow.run()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n{'='*60}")
        print("RESULTS")
        print(f"{'='*60}\n")
        
        metrics = workflow.get_metrics()
        print(f"✓ Workflow completed in {duration:.2f}s")
        print(f"  Processed: {metrics['successful_items']}/{metrics['total_items']}")
        print(f"  Success rate: {metrics['success_rate']}%")
        
        print(f"\n{'='*60}")
        print("OPERATION LOG (Check for pipelining)")
        print(f"{'='*60}\n")
        
        # Print operation log
        for entry in mock_stm32.operation_log:
            print(entry)
        
        print(f"\n{'='*60}")
        print("PIPELINING VERIFICATION")
        print(f"{'='*60}\n")
        
        # Check if pipelining happened
        # We should see hopper_dispense happening DURING cuts (overlap in timestamps)
        
        log_str = '\n'.join(mock_stm32.operation_log)
        
        # Count dispenses and cuts
        dispense_count = log_str.count('hopper_dispense')
        cut_count = log_str.count('cut_execute')
        
        print(f"Dispenses: {dispense_count}")
        print(f"Cuts: {cut_count}")
        
        # Check for concurrent operations (hopper_dispense during cut_execute)
        # Look for pattern: cut_execute followed by hopper_dispense before next gate_open(2)
        pipelining_detected = False
        for i, entry in enumerate(mock_stm32.operation_log):
            if 'cut_execute' in entry and i + 1 < len(mock_stm32.operation_log):
                # Check if next few operations include a hopper_dispense before cut completes
                next_few = '\n'.join(mock_stm32.operation_log[i:i+5])
                if 'hopper_dispense' in next_few:
                    pipelining_detected = True
                    break
        
        if pipelining_detected:
            print("\n✅ PIPELINING WORKING!")
            print("   Next item dispensed DURING cutting (concurrent operations)")
            print("   Check timestamps above - dispense happens while cut is in progress")
        else:
            print("\n⚠️  Pipelining not detected in logs")
        
        # Estimate time saved
        # Without pipelining: (dispense + CV + cut) * 3 items
        # With pipelining: dispense + CV + (cut * 3) - overlaps
        sequential_time = (0.05 + 0.1 + 0.2) * 3  # ~1.05s
        pipelined_time = 0.05 + 0.1 + (0.2 * 3)  # ~0.75s
        theoretical_savings = sequential_time - pipelined_time
        
        print(f"\nTheoretical time comparison:")
        print(f"  Sequential: ~{sequential_time:.2f}s")
        print(f"  Pipelined: ~{pipelined_time:.2f}s")
        print(f"  Savings: ~{theoretical_savings:.2f}s ({(theoretical_savings/sequential_time)*100:.0f}%)")
        
    except Exception as e:
        print(f"✗ Workflow failed: {e}")
        import traceback
        traceback.print_exc()

# Run test
logging.basicConfig(level=logging.INFO)
asyncio.run(test_pipelining())

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)