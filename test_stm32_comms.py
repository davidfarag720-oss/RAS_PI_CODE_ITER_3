#!/usr/bin/env python3
"""
test_stm32_comms.py

Simple test script to verify basic communication with STM32.
Tests:
1. Connection establishment
2. Ping command (echo test)
3. Response validation

Author: Ficio Prep Team
Date: January 2026
"""

import serial
import time
import sys

# ============================================================================
# CONFIGURATION
# ============================================================================

# UART configuration - adjust if needed
SERIAL_PORT = '/dev/ttyAMA0'  # or '/dev/serial0'
BAUD_RATE = 115200

# Protocol constants
PACKET_SIZE = 5
START_BYTE_TX = 0x5A  # RasPi sends this
START_BYTE_RX = 0xA5  # STM32 sends this

# Command codes
CMD_PING = 0x53

# Response codes
RESP_OK = 0x00
RESP_BUSY = 0x01
RESP_INVALID_PARAM = 0x02
RESP_HARDWARE_ERROR = 0x03
RESP_TIMEOUT = 0x04
RESP_UNKNOWN_CMD = 0x0F

# Colors for terminal output
class Color:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_checksum(byte1, byte2, byte3):
    """Calculate simple sum checksum"""
    return (byte1 + byte2 + byte3) & 0xFF

def build_packet(cmd, param1=0, param2=0):
    """Build 5-byte TX packet with checksum"""
    checksum = calculate_checksum(cmd, param1, param2)
    return bytes([START_BYTE_TX, cmd, param1, param2, checksum])

def parse_response(packet):
    """Parse 5-byte RX packet"""
    if len(packet) != PACKET_SIZE:
        return None
    
    if packet[0] != START_BYTE_RX:
        return None
    
    status = packet[1]
    data_l = packet[2]
    data_h = packet[3]
    rx_checksum = packet[4]
    
    # Validate checksum
    calc_checksum = calculate_checksum(status, data_l, data_h)
    if rx_checksum != calc_checksum:
        print(f"{Color.RED}Checksum error: expected 0x{calc_checksum:02X}, got 0x{rx_checksum:02X}{Color.RESET}")
        return None
    
    # Combine data bytes
    data = (data_h << 8) | data_l
    
    return {
        'status': status,
        'data': data,
        'raw': packet
    }

def status_to_string(status):
    """Convert status code to human-readable string"""
    status_map = {
        RESP_OK: "OK",
        RESP_BUSY: "BUSY",
        RESP_INVALID_PARAM: "INVALID_PARAM",
        RESP_HARDWARE_ERROR: "HARDWARE_ERROR",
        RESP_TIMEOUT: "TIMEOUT",
        RESP_UNKNOWN_CMD: "UNKNOWN_CMD"
    }
    return status_map.get(status, f"UNKNOWN(0x{status:02X})")

def print_packet(label, packet):
    """Print packet bytes in hex"""
    hex_str = ' '.join([f'{b:02X}' for b in packet])
    print(f"{label}: [{hex_str}]")

# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_connection(ser):
    """Test if serial port is open and responding"""
    print(f"\n{Color.BOLD}=== TEST 1: Connection Test ==={Color.RESET}")
    
    if not ser.is_open:
        print(f"{Color.RED}✗ Serial port not open{Color.RESET}")
        return False
    
    print(f"{Color.GREEN}✓ Serial port opened: {SERIAL_PORT} @ {BAUD_RATE} baud{Color.RESET}")
    
    # Flush buffers
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.1)
    
    return True

def test_ping_simple(ser):
    """Test ping with simple echo value"""
    print(f"\n{Color.BOLD}=== TEST 2: Simple Ping Test ==={Color.RESET}")
    
    echo_value = 0x1234
    p1 = (echo_value >> 8) & 0xFF
    p2 = echo_value & 0xFF
    
    print(f"Sending PING command with echo value: 0x{echo_value:04X}")
    
    # Build and send packet
    packet = build_packet(CMD_PING, p1, p2)
    print_packet("TX", packet)
    
    ser.write(packet)
    
    # Wait for response
    print("Waiting for response...")
    time.sleep(0.1)  # Give STM32 time to respond
    
    if ser.in_waiting < PACKET_SIZE:
        print(f"{Color.RED}✗ No response received (timeout){Color.RESET}")
        return False
    
    # Read response
    response_bytes = ser.read(PACKET_SIZE)
    print_packet("RX", response_bytes)
    
    # Parse response
    response = parse_response(response_bytes)
    if response is None:
        print(f"{Color.RED}✗ Failed to parse response{Color.RESET}")
        return False
    
    # Check status
    print(f"Response status: {status_to_string(response['status'])}")
    print(f"Response data: 0x{response['data']:04X}")
    
    if response['status'] != RESP_OK:
        print(f"{Color.RED}✗ Status not OK{Color.RESET}")
        return False
    
    if response['data'] != echo_value:
        print(f"{Color.RED}✗ Echo mismatch! Sent: 0x{echo_value:04X}, Got: 0x{response['data']:04X}{Color.RESET}")
        return False
    
    print(f"{Color.GREEN}✓ Ping successful - echo matched!{Color.RESET}")
    return True

def test_ping_multiple(ser, count=5):
    """Test multiple pings with different values"""
    print(f"\n{Color.BOLD}=== TEST 3: Multiple Ping Test ({count} pings) ==={Color.RESET}")
    
    success_count = 0
    
    for i in range(count):
        # Use different echo values
        echo_value = 0x1000 + (i * 0x0111)
        p1 = (echo_value >> 8) & 0xFF
        p2 = echo_value & 0xFF
        
        print(f"\nPing {i+1}/{count}: echo=0x{echo_value:04X}")
        
        # Send packet
        packet = build_packet(CMD_PING, p1, p2)
        ser.write(packet)
        
        # Wait for response
        time.sleep(0.05)
        
        if ser.in_waiting < PACKET_SIZE:
            print(f"{Color.RED}  ✗ No response{Color.RESET}")
            continue
        
        # Read and parse response
        response_bytes = ser.read(PACKET_SIZE)
        response = parse_response(response_bytes)
        
        if response is None:
            print(f"{Color.RED}  ✗ Parse failed{Color.RESET}")
            continue
        
        if response['status'] != RESP_OK or response['data'] != echo_value:
            print(f"{Color.RED}  ✗ Failed (status={status_to_string(response['status'])}, data=0x{response['data']:04X}){Color.RESET}")
            continue
        
        print(f"{Color.GREEN}  ✓ Success{Color.RESET}")
        success_count += 1
    
    print(f"\n{Color.BOLD}Results: {success_count}/{count} pings successful{Color.RESET}")
    
    if success_count == count:
        print(f"{Color.GREEN}✓ All pings successful!{Color.RESET}")
        return True
    else:
        print(f"{Color.YELLOW}⚠ Some pings failed{Color.RESET}")
        return False

def test_timing(ser):
    """Test round-trip timing"""
    print(f"\n{Color.BOLD}=== TEST 4: Timing Test ==={Color.RESET}")
    
    iterations = 10
    timings = []
    
    for i in range(iterations):
        echo_value = 0xABCD
        p1 = (echo_value >> 8) & 0xFF
        p2 = echo_value & 0xFF
        
        packet = build_packet(CMD_PING, p1, p2)
        
        # Measure round-trip time
        start_time = time.time()
        ser.write(packet)
        
        # Wait for response (with timeout)
        timeout = time.time() + 0.5
        while ser.in_waiting < PACKET_SIZE and time.time() < timeout:
            time.sleep(0.001)
        
        if ser.in_waiting < PACKET_SIZE:
            print(f"{Color.RED}  Ping {i+1}: Timeout{Color.RESET}")
            continue
        
        response_bytes = ser.read(PACKET_SIZE)
        elapsed = (time.time() - start_time) * 1000  # Convert to ms
        
        response = parse_response(response_bytes)
        if response and response['status'] == RESP_OK and response['data'] == echo_value:
            timings.append(elapsed)
            print(f"  Ping {i+1}: {elapsed:.2f} ms")
    
    if timings:
        avg_time = sum(timings) / len(timings)
        min_time = min(timings)
        max_time = max(timings)
        
        print(f"\n{Color.BOLD}Timing Statistics:{Color.RESET}")
        print(f"  Average: {avg_time:.2f} ms")
        print(f"  Min:     {min_time:.2f} ms")
        print(f"  Max:     {max_time:.2f} ms")
        print(f"{Color.GREEN}✓ Timing test complete{Color.RESET}")
        return True
    else:
        print(f"{Color.RED}✗ No successful pings{Color.RESET}")
        return False

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def main():
    print(f"{Color.BOLD}{Color.BLUE}")
    print("=" * 70)
    print("  STM32 Communication Test Script")
    print("  Testing UART communication with ping commands")
    print("=" * 70)
    print(f"{Color.RESET}")
    
    # Open serial port
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUD_RATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        print(f"{Color.GREEN}Serial port opened successfully{Color.RESET}\n")
    except serial.SerialException as e:
        print(f"{Color.RED}Failed to open serial port: {e}{Color.RESET}")
        print(f"\nTroubleshooting:")
        print(f"  1. Check if port exists: ls -l /dev/ttyAMA*")
        print(f"  2. Check permissions: sudo usermod -a -G dialout $USER")
        print(f"  3. Try alternate port: /dev/serial0")
        sys.exit(1)
    
    try:
        # Give STM32 time to initialize
        print("Waiting for STM32 to initialize...")
        time.sleep(1.0)
        
        # Run tests
        results = []
        
        results.append(("Connection", test_connection(ser)))
        
        if results[-1][1]:  # Only continue if connection test passed
            results.append(("Simple Ping", test_ping_simple(ser)))
            results.append(("Multiple Pings", test_ping_multiple(ser, 5)))
            results.append(("Timing", test_timing(ser)))
        
        # Print summary
        print(f"\n{Color.BOLD}{Color.BLUE}")
        print("=" * 70)
        print("  TEST SUMMARY")
        print("=" * 70)
        print(f"{Color.RESET}")
        
        for test_name, result in results:
            status = f"{Color.GREEN}PASS{Color.RESET}" if result else f"{Color.RED}FAIL{Color.RESET}"
            print(f"  {test_name:.<50} {status}")
        
        total = len(results)
        passed = sum(1 for _, r in results if r)
        
        print(f"\n{Color.BOLD}Total: {passed}/{total} tests passed{Color.RESET}\n")
        
        if passed == total:
            print(f"{Color.GREEN}{Color.BOLD}✓ ALL TESTS PASSED - Communication working!{Color.RESET}\n")
            print("Next steps:")
            print("  - Check SWO output on STM32 to see DEBUG_LOG messages")
            print("  - Ensure DEBUG is defined in STM32 project settings")
            print("  - Start integrating machine control functions")
            return 0
        else:
            print(f"{Color.YELLOW}{Color.BOLD}⚠ SOME TESTS FAILED{Color.RESET}\n")
            print("Troubleshooting:")
            print("  1. Verify STM32 is running and programmed with latest firmware")
            print("  2. Check UART6 TX/RX connections (are they swapped?)")
            print("  3. Verify baud rate matches (115200)")
            print("  4. Check SWO output for error messages")
            print("  5. Verify DMA is started: HAL_UART_Receive_DMA(&huart6, raspi_rx_buffer, 256)")
            return 1
    
    except KeyboardInterrupt:
        print(f"\n\n{Color.YELLOW}Test interrupted by user{Color.RESET}")
        return 1
    
    finally:
        # Clean up
        if ser.is_open:
            ser.close()
            print(f"\n{Color.BLUE}Serial port closed{Color.RESET}")

if __name__ == '__main__':
    sys.exit(main())