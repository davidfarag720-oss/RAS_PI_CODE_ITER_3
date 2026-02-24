#!/usr/bin/env python3
"""
raspi_comms_manager.py

UART Communication Manager for Raspberry Pi 5
Communicates with STM32 using fixed 5-byte packets with checksum validation.

Protocol:
    RX (from STM32): [START_RX, STATUS, DATA_L, DATA_H, CHECKSUM]
    TX (to STM32):   [START_TX, CMD, PARAM1, PARAM2, CHECKSUM]

Author: Ficio Prep Team
Date: January 2026
"""

import serial
import threading
import time
import logging
from typing import Optional, Callable, Dict
from dataclasses import dataclass
from enum import IntEnum


# ============================================================================
# PROTOCOL CONSTANTS
# ============================================================================

class ProtocolConstants:
    """Protocol constants for 5-byte packet structure"""
    PACKET_SIZE = 5

    # Unsolicited event status codes (STM32 -> RasPi, not responses to commands)
    EVENT_GATE_AT_POSITION_C = 0x10  # Gate servo reached Position C; DATA_L = gate_id

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
    """Command codes for STM32"""

    # ==================== GATE COMMANDS (0x10 - 0x1F) ====================
    CMD_GATE_OPEN = 0x10        # PARAM1: gate_id (1-6), PARAM2: unused
    CMD_GATE_CLOSE = 0x11       # PARAM1: gate_id (1-6), PARAM2: unused
    CMD_GATE_CYCLE = 0x12       # PARAM1: gate_id (1-6), PARAM2: unused
    CMD_HOPPER_DISPENSE = 0x13  # PARAM1: hopper_id (1-4), PARAM2: unused
                                # (includes vibration + smart laser detection)
    CMD_DISPOSE = 0x14          # PARAM1: gate_id (1-2), PARAM2: unused
    CMD_LOAD_CUTTER = 0x15      # PARAM1: gate_id (1-2), PARAM2: unused
    CMD_QUERY_GATE = 0x16       # PARAM1: gate_id (1-2), PARAM2: unused
    
    # ==================== CUTTER COMMANDS (0x20 - 0x2F) ====================
    CMD_CUT_EXECUTE = 0x20      # PARAM1: axis bitmask (bit0=X, bit1=Y, bit2=Z)
    CMD_CUT = 0x21              # Execute cutting cycle with completion notification
    CMD_GET_CUTTER_STATUS = 0x22  # Query cutter status (idle/busy/error)
    CMD_CUT_HOME = 0x23         # Home all cutter axes
    CMD_CUT_ABORT = 0x24        # Emergency stop cutters
    
    # ==================== VIBRATION COMMANDS (0x30 - 0x3F) ====================
    CMD_VIB_SET = 0x30          # PARAM1: hopper_id (1-4), PARAM2: state (0=off, 1=on)
    CMD_VIB_ALL_OFF = 0x31      # Turn off all vibration motors
    
    # ==================== SCALE COMMANDS (0x40 - 0x4F) ====================
    CMD_SCALE_READ = 0x40       # Returns weight in grams (0-20000)
    CMD_SCALE_TARE = 0x41       # Zero the scale
    CMD_SCALE_CALIBRATE = 0x42  # PARAM1: cal_mode, PARAM2: unused
    
    # ==================== STATUS/QUERY COMMANDS (0x50 - 0x5F) ====================
    CMD_GET_HOPPER_STATUS = 0x50  # Returns bitmask: bit0-3 = empty for hoppers 1-4
    CMD_GET_GATE_STATUS = 0x51    # PARAM1: gate_id, Returns: 0=closed, 1=open, 2=moving
    CMD_CONFIG_HANDSHAKE = 0x52   # Config validation handshake
    CMD_PING = 0x53               # PARAM1/2: echo values
    
    # ==================== SYSTEM COMMANDS (0xF0 - 0xFF) ====================
    CMD_EMERGENCY_STOP = 0xF0   # Stop all motion immediately
    CMD_RESET_SYSTEM = 0xF1     # Software reset


class ResponseStatus(IntEnum):
    """Response status codes from STM32"""
    RESP_OK = 0x00              # Success
    RESP_BUSY = 0x01            # Device busy
    RESP_INVALID_PARAM = 0x02   # Invalid parameter
    RESP_HARDWARE_ERROR = 0x03  # Hardware fault
    RESP_TIMEOUT = 0x04         # Operation timeout
    RESP_UNKNOWN_CMD = 0x0F     # Unknown command


# Axis bitmasks for cutter commands
class CutterAxis(IntEnum):
    """Bitmask values for cutter axes"""
    AXIS_X = 0b001  # Cutter 1 (Vertical X)
    AXIS_Y = 0b010  # Cutter 2 (Vertical Y)
    AXIS_Z = 0b100  # Cutter 3 (Horizontal Z)


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

        # Event signaled when STM32 sends EVENT_GATE_AT_POSITION_C notification
        self._gate_at_c_event = threading.Event()
        self._gate_at_c_gate_id: int = 0  # Which gate triggered the event
        
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
        
        # Detect unsolicited events BEFORE constructing Response (prevents enum ValueError)
        if status == ProtocolConstants.EVENT_GATE_AT_POSITION_C:
            self._gate_at_c_gate_id = data_l  # DATA_L contains gate_id
            self._gate_at_c_event.set()
            self.logger.info(f"EVENT: Gate at Position C (gate_id={data_l})")
            # Do NOT store as last_response — this is an unsolicited event,
            # not a response to any pending command. Still call registered callbacks.
            self.stats['rx_count'] += 1
            return

        # Combine data bytes into 16-bit value
        data = (data_h << 8) | data_l

        # Create response object (only for command responses, not unsolicited events)
        response = Response(
            status=ResponseStatus(status),
            data=data,
            raw_packet=packet,
            timestamp=time.time()
        )

        self.stats['rx_count'] += 1
        self.logger.debug(f"RX: STATUS=0x{status:02X} DATA={data}")

        # Only store as last_response if it's a command response (not an unsolicited event)
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

    def wait_for_gate_at_position_c(self, gate_id: int = 1, timeout: float = 5.0) -> bool:
        """
        Block until STM32 sends EVENT_GATE_AT_POSITION_C for the given gate,
        or timeout elapses.

        Must be called AFTER sending CMD_LOAD_CUTTER (the STM32 fires the event
        when its FSM enters GATE_AT_POSITION_C during the load-cutter sequence).

        The event latch should be cleared BEFORE sending CMD_LOAD_CUTTER to avoid
        a race where the STM32 fires the event before this wait starts. See
        STM32Interface.load_cutter() for the correct ordering.

        Args:
            gate_id: Expected gate ID in the event (default 1 = CUTTER_TOP_ID)
            timeout: Maximum wait in seconds (default 5.0)

        Returns:
            True if event received for the expected gate within timeout
            False if timeout elapsed (caller should warn and proceed with caution)
        """
        # Wait for the event to be set by _process_packet()
        received = self._gate_at_c_event.wait(timeout=timeout)

        if received:
            if self._gate_at_c_gate_id == gate_id:
                self.logger.info(f"Gate {gate_id} confirmed at Position C")
                return True
            else:
                # Different gate fired — unexpected, treat as timeout
                self.logger.warning(
                    f"Gate-at-C event for gate {self._gate_at_c_gate_id}, "
                    f"expected gate {gate_id}"
                )
                return False
        else:
            self.logger.warning(
                f"Timeout waiting for gate {gate_id} at Position C "
                f"({timeout}s elapsed)"
            )
            return False

    # ========================================================================
    # HIGH-LEVEL COMMAND METHODS
    # ========================================================================

    def config_handshake(self, num_hoppers: int, num_actuators: int,
                         bottom_gate: bool, parallelization: bool,
                         num_vib_motors: int, timeout: float = 1.0) -> Response:
        """
        Perform config handshake with STM32.

        Returns:
            Response with RESP_OK if match, RESP_INVALID_PARAM if mismatch
        """
        flags = 0
        if bottom_gate:
            flags |= 0x01
        if parallelization:
            flags |= 0x02

        return self.send_command(0x52, num_hoppers, num_actuators, timeout=timeout)

    def dispose(self, gate_id: int = 1, timeout: float = 3.0) -> Response:
        """
        Execute dispose sequence (Base -> Dispose -> hold -> Base).

        Args:
            gate_id: Gate ID (1=top, 2=bottom)
            timeout: Command timeout in seconds

        Returns:
            Response with RESP_OK on success
        """
        return self.send_command(CommandCode.CMD_DISPOSE, gate_id, 0, timeout=timeout)

    def load_cutter(self, gate_id: int = 1, timeout: float = 3.0) -> Response:
        """
        Execute load-cutter sequence (Base -> Position C).

        Args:
            gate_id: Gate ID (1=top, 2=bottom)
            timeout: Command timeout in seconds

        Returns:
            Response with RESP_OK on success, RESP_BUSY if cutter busy (parallel mode)
        """
        return self.send_command(CommandCode.CMD_LOAD_CUTTER, gate_id, 0, timeout=timeout)

    def cut(self, axis_bitmask: int, timeout: float = 10.0) -> Response:
        """
        Execute cutting cycle with completion notification.

        Args:
            axis_bitmask: Axis bitmask (bit0=X, bit1=Y, bit2=Z)
            timeout: Command timeout in seconds

        Returns:
            Response with RESP_OK on success
        """
        return self.send_command(CommandCode.CMD_CUT, axis_bitmask, 0, timeout=timeout)

    def hopper_dispense(self, hopper_id: int, timeout: float = 3.0) -> Response:
        """
        Dispense from hopper (includes vibration, laser detection, auto-close).

        Args:
            hopper_id: Hopper ID (1-4)
            timeout: Command timeout in seconds

        Returns:
            Response with RESP_OK on success, RESP_TIMEOUT if no laser trigger
        """
        return self.send_command(CommandCode.CMD_HOPPER_DISPENSE, hopper_id, 0, timeout=timeout)

    def query_gate(self, gate_id: int = 1, timeout: float = 0.5) -> Response:
        """
        Query gate status and position.

        Args:
            gate_id: Gate ID (1=top, 2=bottom)
            timeout: Command timeout in seconds

        Returns:
            Response with:
                data_l: Gate status (0=IDLE, 1=DISPOSING, 2=LOADING, 3=COMPLETE, 255=ERROR)
                data_h: Position (0-255 scaled from 0-4095)
        """
        return self.send_command(CommandCode.CMD_QUERY_GATE, gate_id, 0, timeout=timeout)

    def query_hopper(self, hopper_id: int, timeout: float = 0.5) -> Response:
        """
        Query single hopper status (detailed mode).

        Args:
            hopper_id: Hopper ID (1-4)
            timeout: Command timeout in seconds

        Returns:
            Response with:
                data_l bits: [0]=empty, [1]=last_success, [2-4]=state
                data_h bits: [0-3]=consecutive_timeouts, [4-7]=consecutive_successes
        """
        return self.send_command(CommandCode.CMD_GET_HOPPER_STATUS, hopper_id, 0, timeout=timeout)

    def query_cutter_status(self, timeout: float = 0.5) -> Response:
        """
        Query cutter status.

        Returns:
            Response with:
                data_l: Cutter state (0=IDLE, 1=BUSY, 255=ERROR)
                data_h: Active axis bitmask or error code
        """
        return self.send_command(CommandCode.CMD_GET_CUTTER_STATUS, 0, 0, timeout=timeout)

    def emergency_stop(self, timeout: float = 1.0) -> Response:
        """Emergency stop all motion."""
        return self.send_command(CommandCode.CMD_EMERGENCY_STOP, 0, 0, timeout=timeout)


# ============================================================================
# HIGH-LEVEL INTERFACE
# ============================================================================

class STM32Interface:
    """
    High-level interface for common STM32 operations.
    Provides simple methods for typical commands.
    """
    
    def __init__(self, comms: RaspiCommsManager):
        self.comms = comms
        self.logger = logging.getLogger('STM32Interface')
    
    # ==================== SYSTEM COMMANDS ====================
    
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
    
    def reset_system(self) -> bool:
        """Reset STM32 system."""
        resp = self.comms.send_command(CommandCode.CMD_RESET_SYSTEM)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    # ==================== GATE COMMANDS ====================
    
    def gate_open(self, gate_id: int) -> bool:
        """
        Open a gate.
        
        Args:
            gate_id: Gate number (1-6)
                1-2: Cutter gates (top/bottom)
                3-6: Hopper gates (hoppers 1-4)
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_GATE_OPEN, gate_id)
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.debug(f"Gate {gate_id} opened")
            return True
        return False
    
    def gate_close(self, gate_id: int) -> bool:
        """Close a gate."""
        resp = self.comms.send_command(CommandCode.CMD_GATE_CLOSE, gate_id)
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.debug(f"Gate {gate_id} closed")
            return True
        return False
    
    def gate_cycle(self, gate_id: int) -> bool:
        """Cycle a gate (open then close)."""
        resp = self.comms.send_command(CommandCode.CMD_GATE_CYCLE, gate_id)
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.debug(f"Gate {gate_id} cycled")
            return True
        return False
    
    def get_gate_status(self, gate_id: int) -> Optional[int]:
        """
        Get gate status.
        
        Returns:
            0 = closed, 1 = open, 2 = moving, None = error
        """
        resp = self.comms.send_command(CommandCode.CMD_GET_GATE_STATUS, gate_id)
        if resp and resp.status == ResponseStatus.RESP_OK:
            return resp.data
        return None
    
    # ==================== HOPPER COMMANDS ====================
    
    def hopper_dispense(self, hopper_id: int) -> bool:
        """
        Dispense one item from hopper (smart dispense with laser detection).
        
        Args:
            hopper_id: Hopper number (1-4)
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_HOPPER_DISPENSE, hopper_id)
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.info(f"Hopper {hopper_id} dispensed item")
            return True
        elif resp and resp.status == ResponseStatus.RESP_TIMEOUT:
            self.logger.warning(f"Hopper {hopper_id} dispense timeout (possibly empty)")
        return False
    
    def get_hopper_status(self) -> Optional[int]:
        """
        Get hopper empty status.
        
        Returns:
            Bitmask where bit0-3 represent empty status for hoppers 1-4
            1 = empty, 0 = has items
            None if error
        """
        resp = self.comms.send_command(CommandCode.CMD_GET_HOPPER_STATUS)
        if resp and resp.status == ResponseStatus.RESP_OK:
            return resp.data
        return None
    
    def is_hopper_empty(self, hopper_id: int) -> bool:
        """
        Check if specific hopper is empty.
        
        Args:
            hopper_id: Hopper number (1-4)
        
        Returns:
            True if empty, False if has items or error
        """
        status = self.get_hopper_status()
        if status is not None:
            bit_position = hopper_id - 1
            return (status & (1 << bit_position)) != 0
        return False
    
    # ==================== CUTTER COMMANDS ====================
    
    def cut_execute(self, axis_bitmask: int) -> bool:
        """
        Execute cut on specified axes.
        
        Args:
            axis_bitmask: Bitmask for axes
                bit0 (0x01): X-axis (Cutter 1 - Vertical X)
                bit1 (0x02): Y-axis (Cutter 2 - Vertical Y)
                bit2 (0x04): Z-axis (Cutter 3 - Horizontal Z)
                
                Examples:
                    0x04 (0b100): Z-axis only (horizontal slice)
                    0x03 (0b011): X+Y axes (for cubed)
                    0x07 (0b111): All axes
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_CUT_EXECUTE, axis_bitmask)
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.info(f"Cut executed on axes: 0b{axis_bitmask:03b}")
            return True
        return False
    
    def cut_home(self, timeout: float = 45.0) -> bool:
        """Home all cutter axes and clear bay. Blocks ~30s."""
        resp = self.comms.send_command(CommandCode.CMD_CUT_HOME, timeout=timeout)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    def cut_abort(self) -> bool:
        """Emergency abort all cutter motion."""
        resp = self.comms.send_command(CommandCode.CMD_CUT_ABORT)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    # ==================== VIBRATION COMMANDS ====================
    
    def vibration_set(self, hopper_id: int, state: bool) -> bool:
        """
        Set vibration motor state for a hopper.
        
        Args:
            hopper_id: Hopper number (1-4)
            state: True = on, False = off
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_VIB_SET, hopper_id, 1 if state else 0)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    def vibration_all_off(self) -> bool:
        """Turn off all vibration motors."""
        resp = self.comms.send_command(CommandCode.CMD_VIB_ALL_OFF)
        return resp is not None and resp.status == ResponseStatus.RESP_OK
    
    # ==================== SCALE COMMANDS ====================
    
    def scale_read(self) -> Optional[float]:
        """
        Read weight from scale.
        
        Returns:
            Weight in grams (0-20000), or None if error
        """
        resp = self.comms.send_command(CommandCode.CMD_SCALE_READ)
        
        if resp:
            if resp.status == ResponseStatus.RESP_OK:
                return float(resp.data)  # Data is in grams
            elif resp.status == ResponseStatus.RESP_BUSY:
                self.logger.warning("Scale busy")
            elif resp.status == ResponseStatus.RESP_HARDWARE_ERROR:
                self.logger.error("Scale hardware error")
        
        return None
    
    def scale_tare(self) -> bool:
        """
        Tare (zero) the scale.
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_SCALE_TARE)
        if resp and resp.status == ResponseStatus.RESP_OK:
            self.logger.info("Scale tared")
            return True
        return False
    
    def scale_calibrate(self, cal_mode: int = 0) -> bool:
        """
        Calibrate scale.
        
        Args:
            cal_mode: Calibration mode (0 = default)
        
        Returns:
            True if successful
        """
        resp = self.comms.send_command(CommandCode.CMD_SCALE_CALIBRATE, cal_mode)
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
        
        # Test hopper status
        print("\n=== Testing Hopper Status ===")
        status = stm32.get_hopper_status()
        if status is not None:
            print(f"✓ Hopper status: 0b{status:04b}")
            for i in range(1, 5):
                empty = stm32.is_hopper_empty(i)
                print(f"  Hopper {i}: {'EMPTY' if empty else 'HAS ITEMS'}")
        
        # Test scale reading
        print("\n=== Testing Scale ===")
        weight = stm32.scale_read()
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