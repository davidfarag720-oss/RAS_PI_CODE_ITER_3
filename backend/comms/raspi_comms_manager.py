#!/usr/bin/env python3
"""
raspi_comms_manager.py

UART Communication Manager for Raspberry Pi 5
Communicates with STM32 using fixed 5-byte packets with checksum validation.

Protocol:
    RX (from STM32): [START_TX, STATUS, DATA_L, DATA_H, CHECKSUM]
    TX (to STM32):   [START_RX, CMD, PARAM1, PARAM2, CHECKSUM]

Author: Ficio Prep Team
Date: January 2026
"""

import serial
import threading
import time
import logging
from typing import Optional, Callable, Dict, Tuple
from dataclasses import dataclass
from enum import IntEnum


# ============================================================================
# PROTOCOL CONSTANTS (must match STM32 comms_manager.h)
# ============================================================================

class ProtocolConstants:
    """Protocol constants matching STM32 definitions"""
    PACKET_SIZE = 5
    
    # Start bytes
    START_BYTE_RX = 0xA5  # STM32 sends this
    START_BYTE_TX = 0x5A  # RasPi sends this
    
    # TX Packet indices (RasPi -> STM32)
    TX_START_IDX = 0
    TX_CMD_IDX = 1
    TX_PARAM1_IDX = 2
    TX_PARAM2_IDX = 3
    TX_CHECKSUM_IDX = 4
    
    # RX Packet indices (STM32 -> RasPi)
    RX_START_IDX = 0
    RX_STATUS_IDX = 1
    RX_DATA_L_IDX = 2
    RX_DATA_H_IDX = 3
    RX_CHECKSUM_IDX = 4


class CommandCode(IntEnum):
    """Command codes for STM32 (must match STM32 definitions)"""
    # Gate commands
    CMD_GATE_TRIGGER = 0x10
    CMD_GATE_STATUS = 0x11
    CMD_GATE_ABORT = 0x12
    
    # Cutter commands
    CMD_CUTTER_CYCLE = 0x20
    CMD_CUTTER_RESET = 0x21
    CMD_CUTTER_STATUS = 0x22
    
    # Vibration commands
    CMD_VIB_SET = 0x30
    
    # Scale commands
    CMD_SCALE_READ = 0x40
    CMD_SCALE_TARE = 0x41
    
    # System commands
    CMD_PING = 0x50
    CMD_EMERGENCY_STOP = 0x55


class ResponseStatus(IntEnum):
    """Response status codes from STM32 (must match STM32 definitions)"""
    RESP_OK = 0x00
    RESP_ERR_PARAM = 0x01
    RESP_ERR_BUSY = 0x02
    RESP_ERR_SENSOR = 0x03
    RESP_ERR_UNKNOWN_CMD = 0x0F


@dataclass
class Response:
    """Parsed response from STM32"""
    status: ResponseStatus
    data: int  # 16-bit data (data_h << 8 | data_l)
    raw_packet: bytes
    timestamp: float


# ============================================================================
# COMMUNICATION MANAGER
# ============================================================================

class RaspiCommsManager:
    """
    Manages UART communication with STM32.
    Handles packet assembly, checksum validation, and command/response flow.
    """
    
    def __init__(self, port: str = '/dev/ttyAMA0', baudrate: int = 115200, 
                 timeout: float = 0.1):
        """
        Initialize communication manager.
        
        Args:
            port: Serial port device (e.g., '/dev/ttyAMA0' or '/dev/serial0')
            baudrate: Baud rate (must match STM32)
            timeout: Serial read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        self.serial: Optional[serial.Serial] = None
        self.running = False
        self.rx_thread: Optional[threading.Thread] = None
        
        # Response handling
        self.response_lock = threading.Lock()
        self.last_response: Optional[Response] = None
        self.response_callbacks: Dict[int, Callable[[Response], None]] = {}
        
        # Statistics
        self.stats = {
            'tx_count': 0,
            'rx_count': 0,
            'checksum_errors': 0,
            'sync_errors': 0
        }
        
        # Setup logging
        self.logger = logging.getLogger('RaspiComms')
        
    def connect(self) -> bool:
        """
        Open serial connection and start receiver thread.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )
            
            # Flush any stale data
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            # Start receiver thread
            self.running = True
            self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.rx_thread.start()
            
            self.logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            return True
            
        except serial.SerialException as e:
            self.logger.error(f"Failed to open serial port: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection and stop receiver thread."""
        self.running = False
        
        if self.rx_thread:
            self.rx_thread.join(timeout=2.0)
        
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.logger.info("Disconnected from STM32")
    
    def send_command(self, cmd: CommandCode, param1: int = 0, param2: int = 0,
                     wait_response: bool = True, timeout: float = 1.0) -> Optional[Response]:
        """
        Send command to STM32 and optionally wait for response.
        
        Args:
            cmd: Command code
            param1: First parameter byte (0-255)
            param2: Second parameter byte (0-255)
            wait_response: Whether to wait for response
            timeout: Response timeout in seconds
            
        Returns:
            Response object if wait_response=True, None otherwise
        """
        if not self.serial or not self.serial.is_open:
            self.logger.error("Serial port not open")
            return None
        
        # Build packet
        packet = self._build_packet(cmd, param1, param2)
        
        # Clear last response if waiting for new one
        if wait_response:
            with self.response_lock:
                self.last_response = None
        
        # Send packet
        try:
            self.serial.write(packet)
            self.stats['tx_count'] += 1
            self.logger.debug(f"TX: CMD=0x{cmd:02X} P1={param1} P2={param2}")
            
        except serial.SerialException as e:
            self.logger.error(f"Failed to send command: {e}")
            return None
        
        # Wait for response if requested
        if wait_response:
            return self._wait_for_response(timeout)
        
        return None
    
    def _build_packet(self, cmd: int, param1: int, param2: int) -> bytes:
        """
        Build TX packet with checksum.
        
        Returns:
            5-byte packet ready for transmission
        """
        # Ensure parameters are in valid range
        cmd = cmd & 0xFF
        param1 = param1 & 0xFF
        param2 = param2 & 0xFF
        
        # Calculate checksum (sum of cmd + p1 + p2)
        checksum = (cmd + param1 + param2) & 0xFF
        
        # Build packet
        packet = bytes([
            ProtocolConstants.START_BYTE_TX,
            cmd,
            param1,
            param2,
            checksum
        ])
        
        return packet
    
    def _wait_for_response(self, timeout: float) -> Optional[Response]:
        """
        Wait for response from STM32.
        
        Args:
            timeout: Maximum wait time in seconds
            
        Returns:
            Response object or None if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self.response_lock:
                if self.last_response:
                    return self.last_response
            time.sleep(0.001)  # 1ms polling interval
        
        self.logger.warning("Response timeout")
        return None
    
    def _receive_loop(self):
        """
        Background thread that continuously reads and parses incoming packets.
        """
        packet_buffer = bytearray()
        
        while self.running:
            try:
                # Read available bytes
                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    packet_buffer.extend(data)
                
                # Try to parse packets from buffer
                while len(packet_buffer) >= ProtocolConstants.PACKET_SIZE:
                    # Look for start byte
                    try:
                        start_idx = packet_buffer.index(ProtocolConstants.START_BYTE_RX)
                    except ValueError:
                        # No start byte found, clear buffer
                        packet_buffer.clear()
                        self.stats['sync_errors'] += 1
                        break
                    
                    # Remove any junk before start byte
                    if start_idx > 0:
                        packet_buffer = packet_buffer[start_idx:]
                        self.stats['sync_errors'] += 1
                    
                    # Check if we have a complete packet
                    if len(packet_buffer) >= ProtocolConstants.PACKET_SIZE:
                        # Extract packet
                        packet = bytes(packet_buffer[:ProtocolConstants.PACKET_SIZE])
                        packet_buffer = packet_buffer[ProtocolConstants.PACKET_SIZE:]
                        
                        # Parse and validate
                        self._process_packet(packet)
                    else:
                        # Wait for more data
                        break
                
                time.sleep(0.001)  # Small delay to prevent CPU spinning
                
            except serial.SerialException as e:
                self.logger.error(f"Serial read error: {e}")
                time.sleep(0.1)
    
    def _process_packet(self, packet: bytes):
        """
        Parse and validate received packet.
        
        Args:
            packet: 5-byte packet from STM32
        """
        # Extract fields
        status = packet[ProtocolConstants.RX_STATUS_IDX]
        data_l = packet[ProtocolConstants.RX_DATA_L_IDX]
        data_h = packet[ProtocolConstants.RX_DATA_H_IDX]
        rx_checksum = packet[ProtocolConstants.RX_CHECKSUM_IDX]
        
        # Calculate expected checksum
        calc_checksum = (status + data_l + data_h) & 0xFF
        
        # Validate checksum
        if rx_checksum != calc_checksum:
            self.logger.warning(f"Checksum error: expected 0x{calc_checksum:02X}, got 0x{rx_checksum:02X}")
            self.stats['checksum_errors'] += 1
            return
        
        # Combine data bytes into 16-bit value
        data = (data_h << 8) | data_l
        
        # Create response object
        response = Response(
            status=ResponseStatus(status),
            data=data,
            raw_packet=packet,
            timestamp=time.time()
        )
        
        self.stats['rx_count'] += 1
        self.logger.debug(f"RX: STATUS=0x{status:02X} DATA={data}")
        
        # Store response
        with self.response_lock:
            self.last_response = response
        
        # Call registered callbacks
        for callback in self.response_callbacks.values():
            try:
                callback(response)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
    
    def register_response_callback(self, callback_id: int, 
                                   callback: Callable[[Response], None]):
        """Register a callback for all received responses."""
        self.response_callbacks[callback_id] = callback
    
    def unregister_response_callback(self, callback_id: int):
        """Unregister a response callback."""
        self.response_callbacks.pop(callback_id, None)
    
    def get_stats(self) -> Dict:
        """Get communication statistics."""
        return self.stats.copy()
    
    def is_connected(self) -> bool:
        """Check if serial connection is active."""
        return self.serial is not None and self.serial.is_open and self.running


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

class STM32Interface:
    """
    High-level interface for common STM32 operations.
    Provides simple methods for typical commands.
    """
    
    def __init__(self, comms: RaspiCommsManager):
        self.comms = comms
        self.logger = logging.getLogger('STM32Interface')
    
    def ping(self, echo_value: int = 0x1234) -> bool:
        """
        Send ping command to verify communication.
        
        Args:
            echo_value: 16-bit value that should be echoed back
            
        Returns:
            True if ping successful and echo matches
        """
        p1 = (echo_value >> 8) & 0xFF
        p2 = echo_value & 0xFF
        
        resp = self.comms.send_command(CommandCode.CMD_PING, p1, p2)
        
        if resp and resp.status == ResponseStatus.RESP_OK:
            if resp.data == echo_value:
                self.logger.info(f"Ping successful (echo=0x{echo_value:04X})")
                return True
            else:
                self.logger.warning(f"Ping echo mismatch: sent 0x{echo_value:04X}, got 0x{resp.data:04X}")
        else:
            self.logger.error("Ping failed")
        
        return False
    
    def emergency_stop(self) -> bool:
        """
        Send emergency stop command.
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_EMERGENCY_STOP)
        
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.warning("Emergency stop activated")
            return True
        
        self.logger.error("Emergency stop failed")
        return False
    
    def read_scale(self) -> Optional[float]:
        """
        Read weight from scale.
        
        Returns:
            Weight in grams, or None if error
        """
        resp = self.comms.send_command(CommandCode.CMD_SCALE_READ)
        
        if resp:
            if resp.status == ResponseStatus.RESP_OK:
                return float(resp.data)  # Data is in grams
            elif resp.status == ResponseStatus.RESP_ERR_BUSY:
                self.logger.warning("Scale busy")
            elif resp.status == ResponseStatus.RESP_ERR_SENSOR:
                self.logger.error("Scale sensor error")
        
        return None
    
    def tare_scale(self) -> bool:
        """
        Tare the scale.
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_SCALE_TARE)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    def trigger_gate(self, gate_id: int) -> bool:
        """
        Trigger a gate (1-4).
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_GATE_TRIGGER, gate_id)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    def get_gate_status(self, gate_id: int) -> Optional[int]:
        """
        Get gate status.
        
        Returns:
            Status byte, or None if error
        """
        resp = self.comms.send_command(CommandCode.CMD_GATE_STATUS, gate_id)
        
        if resp and resp.status == ResponseStatus.RESP_OK:
            return resp.data
        
        return None
    
    def set_vibration(self, enable: bool) -> bool:
        """
        Enable/disable vibration.
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_VIB_SET, 1 if enable else 0)
        return resp is not None and resp.status == ResponseStatus.RESP_OK


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

def main():
    """Example usage and basic testing."""
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create communication manager
    comms = RaspiCommsManager(port='/dev/ttyAMA0', baudrate=115200)
    
    # Connect
    if not comms.connect():
        print("Failed to connect to STM32")
        return
    
    # Create high-level interface
    stm32 = STM32Interface(comms)
    
    try:
        # Wait for STM32 to be ready
        time.sleep(0.5)
        
        # Test ping
        print("\n=== Testing Ping ===")
        if stm32.ping(0xABCD):
            print("✓ Ping successful")
        else:
            print("✗ Ping failed")
        
        # Test scale reading
        print("\n=== Testing Scale ===")
        weight = stm32.read_scale()
        if weight is not None:
            print(f"✓ Scale reading: {weight:.1f}g")
        else:
            print("✗ Scale read failed")
        
        # Print statistics
        print("\n=== Communication Statistics ===")
        stats = comms.get_stats()
        for key, value in stats.items():
            print(f"{key}: {value}")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    
    finally:
        # Cleanup
        comms.disconnect()
        print("Disconnected")


if __name__ == '__main__':
    main()