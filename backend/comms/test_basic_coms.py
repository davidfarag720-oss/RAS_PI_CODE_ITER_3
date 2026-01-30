#!/usr/bin/env python3
"""
test_basic_comms.py

Simple test script to verify STM32 communication is working properly.
Tests: Connection, Initialization, Ping, and Watchdog functionality.

Usage:
    python3 test_basic_comms.py

Author: Ficio Prep Team
Date: January 2026
"""

import time
import logging
import sys
from backend.comms.raspi_comms_manager import RaspiCommsManager, STM32Interface, ResponseStatus

# Test configuration
SERIAL_PORT = '/dev/ttyAMA0'  # Change if using different port
BAUD_RATE = 115200
WATCHDOG_DURATION = 10  # How long to run watchdog test (seconds)


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_result(test_name, passed, details=""):
    """Print test result."""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"{test_name:.<45} {status}")
    if details:
        print(f"    └─ {details}")


def test_connection(comms):
    """Test 1: Verify serial connection can be established."""
    print_header("TEST 1: Connection")
    
    try:
        success = comms.connect()
        
        if success and comms.is_connected():
            print_result("Serial port connection", True, f"Connected to {SERIAL_PORT}")
            return True
        else:
            print_result("Serial port connection", False, "Failed to open port")
            return False
            
    except Exception as e:
        print_result("Serial port connection", False, f"Exception: {e}")
        return False


def test_initialization(stm32):
    """Test 2: Verify STM32 responds to ping (initialization)."""
    print_header("TEST 2: Initialization")
    
    print("Waiting for STM32 to stabilize...")
    time.sleep(0.5)
    
    # Try multiple pings to ensure stable communication
    print("\nAttempting 3 ping tests...")
    
    successes = 0
    for i in range(3):
        test_value = 0x1234 + i
        result = stm32.ping(test_value)
        
        print(f"  Ping {i+1}/3 (value=0x{test_value:04X})...", end=" ")
        if result:
            print("✓")
            successes += 1
        else:
            print("✗")
        
        time.sleep(0.2)
    
    passed = successes == 3
    print_result("Initialization pings", passed, f"{successes}/3 successful")
    
    return passed


def test_ping_reliability(stm32):
    """Test 3: Test ping reliability over multiple attempts."""
    print_header("TEST 3: Ping Reliability")
    
    num_pings = 10
    successes = 0
    failures = 0
    
    print(f"Sending {num_pings} rapid pings...")
    
    for i in range(num_pings):
        test_value = 0xAB00 + i
        
        if stm32.ping(test_value):
            successes += 1
            print(".", end="", flush=True)
        else:
            failures += 1
            print("x", end="", flush=True)
        
        time.sleep(0.05)  # Small delay between pings
    
    print()  # New line after dots
    
    success_rate = (successes / num_pings) * 100
    passed = success_rate >= 90  # Pass if 90% or better
    
    print_result("Ping reliability", passed, 
                f"{successes}/{num_pings} successful ({success_rate:.1f}%)")
    
    return passed


def test_watchdog(comms, stm32):
    """Test 4: Verify watchdog functionality."""
    print_header("TEST 4: Watchdog")
    
    print(f"Starting watchdog (will run for {WATCHDOG_DURATION} seconds)...")
    print("Watchdog will ping STM32 every second.")
    print("Press Ctrl+C to stop early.\n")
    
    # Manual watchdog implementation for testing
    ping_interval = 1.0
    max_failures = 3
    consecutive_failures = 0
    ping_count = 0
    failed_pings = 0
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < WATCHDOG_DURATION:
            # Send ping
            ping_count += 1
            test_value = 0xDEAD
            
            if stm32.ping(test_value):
                consecutive_failures = 0
                print(f"[{ping_count:2d}] Watchdog ping OK", end="")
            else:
                consecutive_failures += 1
                failed_pings += 1
                print(f"[{ping_count:2d}] Watchdog ping FAILED (consecutive: {consecutive_failures})", end="")
                
                if consecutive_failures >= max_failures:
                    print("\n⚠ WATCHDOG: Connection lost!")
                    print_result("Watchdog functionality", False, 
                               f"Lost connection after {consecutive_failures} failures")
                    return False
            
            # Show stats
            stats = comms.get_stats()
            print(f" | TX:{stats['tx_count']} RX:{stats['rx_count']} ERR:{stats['checksum_errors']}")
            
            # Wait for next ping interval
            time.sleep(ping_interval)
    
    except KeyboardInterrupt:
        print("\n\nWatchdog test interrupted by user")
    
    elapsed = time.time() - start_time
    success_rate = ((ping_count - failed_pings) / ping_count) * 100 if ping_count > 0 else 0
    
    passed = failed_pings == 0
    print_result("Watchdog functionality", passed, 
                f"{ping_count - failed_pings}/{ping_count} pings successful ({success_rate:.1f}%)")
    
    return passed


def test_statistics(comms):
    """Test 5: Verify statistics tracking."""
    print_header("TEST 5: Communication Statistics")
    
    stats = comms.get_stats()
    
    print(f"  TX packets:        {stats['tx_count']}")
    print(f"  RX packets:        {stats['rx_count']}")
    print(f"  Checksum errors:   {stats['checksum_errors']}")
    print(f"  Sync errors:       {stats['sync_errors']}")
    
    # Basic sanity checks
    has_tx = stats['tx_count'] > 0
    has_rx = stats['rx_count'] > 0
    low_errors = stats['checksum_errors'] < stats['rx_count'] * 0.1  # Less than 10% errors
    
    passed = has_tx and has_rx and low_errors
    
    if not has_tx:
        print_result("Statistics tracking", False, "No TX packets recorded")
    elif not has_rx:
        print_result("Statistics tracking", False, "No RX packets recorded")
    elif not low_errors:
        print_result("Statistics tracking", False, "Too many checksum errors")
    else:
        print_result("Statistics tracking", True, "All statistics look good")
    
    return passed


def main():
    """Main test runner."""
    print("\n" + "█" * 60)
    print("█" + " " * 58 + "█")
    print("█" + "  STM32 ↔ Raspberry Pi Communication Test Suite".center(58) + "█")
    print("█" + " " * 58 + "█")
    print("█" * 60)
    
    # Setup logging
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings and errors
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create communication manager
    print(f"\nInitializing communication manager...")
    print(f"  Port: {SERIAL_PORT}")
    print(f"  Baud: {BAUD_RATE}")
    
    comms = RaspiCommsManager(port=SERIAL_PORT, baudrate=BAUD_RATE)
    stm32 = STM32Interface(comms)
    
    # Track test results
    test_results = {}
    
    try:
        # Run tests in sequence
        test_results['connection'] = test_connection(comms)
        
        if not test_results['connection']:
            print("\n⚠ Cannot proceed without connection. Aborting tests.")
            return False
        
        test_results['initialization'] = test_initialization(stm32)
        
        if not test_results['initialization']:
            print("\n⚠ Cannot proceed without initialization. Aborting tests.")
            return False
        
        test_results['ping_reliability'] = test_ping_reliability(stm32)
        test_results['watchdog'] = test_watchdog(comms, stm32)
        test_results['statistics'] = test_statistics(comms)
        
    except KeyboardInterrupt:
        print("\n\n⚠ Tests interrupted by user")
        
    finally:
        # Cleanup
        print_header("Cleanup")
        comms.disconnect()
        print("Disconnected from STM32")
    
    # Print summary
    print_header("Test Summary")
    
    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results.values() if result)
    
    for test_name, result in test_results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {test_name.replace('_', ' ').title():.<50} {status}")
    
    print("\n" + "-" * 60)
    print(f"  Overall: {passed_tests}/{total_tests} tests passed")
    print("-" * 60)
    
    # Final verdict
    if passed_tests == total_tests:
        print("\n🎉 SUCCESS! All communication tests passed.")
        print("   Your STM32 ↔ Raspberry Pi link is working properly.")
        return True
    else:
        print("\n⚠ FAILURE: Some tests failed.")
        print("   Check wiring, baud rate, and STM32 firmware.")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)