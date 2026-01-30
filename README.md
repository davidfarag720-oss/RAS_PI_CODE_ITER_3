# Raspberry Pi 5 ↔ STM32 UART Communication

Python-based communication manager for full-duplex UART communication between Raspberry Pi 5 and STM32.

## Features

- ✅ **Protocol Matching**: Exactly mirrors STM32 packet structure (5-byte packets with checksum)
- ✅ **Robust Communication**: Automatic resync, checksum validation, timeout handling
- ✅ **Thread-Safe**: Background receiver thread with thread-safe response handling
- ✅ **High-Level Interface**: Convenient wrapper methods for common commands
- ✅ **Watchdog Support**: Automatic connection monitoring with configurable ping interval
- ✅ **Easy Integration**: Clean API for use in larger Python applications
- ✅ **Comprehensive Logging**: Built-in logging for debugging and monitoring

## Protocol Overview

**TX (Raspberry Pi → STM32):**
```
[START_TX, CMD, PARAM1, PARAM2, CHECKSUM]
0x5A      0xXX  0xXX    0xXX     0xXX
```

**RX (STM32 → Raspberry Pi):**
```
[START_RX, STATUS, DATA_L, DATA_H, CHECKSUM]
0xA5      0xXX    0xXX    0xXX    0xXX
```

## Quick Start

### 1. Hardware Setup

#### Enable UART on Raspberry Pi 5

Edit `/boot/firmware/config.txt`:
```bash
sudo nano /boot/firmware/config.txt
```

Add these lines:
```
# Enable UART
enable_uart=1
dtoverlay=uart0
```

Reboot:
```bash
sudo reboot
```

#### Verify UART

Check that UART is available:
```bash
ls -l /dev/ttyAMA0
ls -l /dev/serial0
```

#### Wiring

Connect Raspberry Pi to STM32:
```
RasPi GPIO 14 (TXD) → STM32 RX (e.g., PA10/USART6_RX)
RasPi GPIO 15 (RXD) → STM32 TX (e.g., PA9/USART6_TX)
RasPi GND           → STM32 GND
```

**Important**: Ensure voltage levels are compatible (3.3V for both).

### 2. Software Setup

#### Install Dependencies

```bash
pip3 install pyserial
```

#### Set Permissions

Add your user to the `dialout` group:
```bash
sudo usermod -a -G dialout $USER
```

Log out and back in for changes to take effect.

### 3. Basic Usage

```python
from raspi_comms_manager import RaspiCommsManager, STM32Interface
import time

# Create communication manager
comms = RaspiCommsManager(port='/dev/ttyAMA0', baudrate=115200)
stm32 = STM32Interface(comms)

# Connect
if comms.connect():
    time.sleep(0.5)  # Wait for STM32 to stabilize
    
    # Test communication
    if stm32.ping(0x1234):
        print("Communication successful!")
    
    # Read scale
    weight = stm32.read_scale()
    print(f"Weight: {weight}g")
    
    # Cleanup
    comms.disconnect()
```

## File Structure

```
.
├── raspi_comms_manager.py  # Core communication manager
├── example_integration.py  # Integration examples with watchdog
├── config.py              # Configuration file
└── README.md              # This file
```

## API Reference

### RaspiCommsManager

Low-level communication manager.

```python
# Initialize
comms = RaspiCommsManager(port='/dev/ttyAMA0', baudrate=115200, timeout=0.1)

# Connect/Disconnect
comms.connect()
comms.disconnect()

# Send command (wait for response)
response = comms.send_command(cmd=0x10, param1=1, param2=0, wait_response=True, timeout=1.0)

# Send command (fire-and-forget)
comms.send_command(cmd=0x10, param1=1, param2=0, wait_response=False)

# Register response callback
comms.register_response_callback(callback_id=1, callback=my_callback)

# Get statistics
stats = comms.get_stats()
```

### STM32Interface

High-level convenience interface.

```python
stm32 = STM32Interface(comms)

# System commands
stm32.ping(echo_value=0x1234)              # Returns: bool
stm32.emergency_stop()                      # Returns: bool

# Scale commands
weight = stm32.read_scale()                 # Returns: float (grams) or None
stm32.tare_scale()                         # Returns: bool

# Gate commands
stm32.trigger_gate(gate_id=1)              # Returns: bool
status = stm32.get_gate_status(gate_id=1)  # Returns: int or None

# Vibration control
stm32.set_vibration(enable=True)           # Returns: bool
```

### Command Codes

```python
from raspi_comms_manager import CommandCode

# Gate commands
CommandCode.CMD_GATE_TRIGGER    # 0x10
CommandCode.CMD_GATE_STATUS     # 0x11
CommandCode.CMD_GATE_ABORT      # 0x12

# Cutter commands
CommandCode.CMD_CUTTER_CYCLE    # 0x20
CommandCode.CMD_CUTTER_RESET    # 0x21
CommandCode.CMD_CUTTER_STATUS   # 0x22

# Vibration commands
CommandCode.CMD_VIB_SET         # 0x30

# Scale commands
CommandCode.CMD_SCALE_READ      # 0x40
CommandCode.CMD_SCALE_TARE      # 0x41

# System commands
CommandCode.CMD_PING            # 0x50
CommandCode.CMD_EMERGENCY_STOP  # 0x55
```

### Response Status Codes

```python
from raspi_comms_manager import ResponseStatus

ResponseStatus.RESP_OK              # 0x00 - Success
ResponseStatus.RESP_ERR_PARAM       # 0x01 - Invalid parameter
ResponseStatus.RESP_ERR_BUSY        # 0x02 - Device busy
ResponseStatus.RESP_ERR_SENSOR      # 0x03 - Sensor error
ResponseStatus.RESP_ERR_UNKNOWN_CMD # 0x0F - Unknown command
```

## Advanced Usage

### Watchdog Implementation

```python
from example_integration import SystemController

# Create system with automatic watchdog
system = SystemController(serial_port='/dev/ttyAMA0', baudrate=115200)

# Initialize (also starts watchdog)
if system.initialize():
    # Watchdog automatically pings STM32 every second
    # Will detect connection loss after 3 consecutive failures
    
    # Your application logic here
    time.sleep(60)
    
    # Clean shutdown (stops watchdog)
    system.shutdown()
```

### Custom Response Callbacks

```python
def my_response_handler(response):
    """Called for every response from STM32"""
    print(f"Status: {response.status.name}")
    print(f"Data: {response.data}")
    print(f"Timestamp: {response.timestamp}")

comms.register_response_callback(callback_id=1, callback=my_response_handler)
```

### Integration with Other Modules

```python
# In your main application
from raspi_comms_manager import RaspiCommsManager, STM32Interface
import my_vision_module
import my_control_module

comms = RaspiCommsManager(port='/dev/ttyAMA0', baudrate=115200)
stm32 = STM32Interface(comms)

if comms.connect():
    # Use STM32 interface alongside other modules
    image = my_vision_module.capture()
    command = my_control_module.process(image)
    
    # Control hardware based on vision/control output
    stm32.trigger_gate(command.gate_id)
    weight = stm32.read_scale()
    
    # Continue your application logic...
```

## Configuration

Edit `config.py` to customize:

- Serial port settings
- Communication timeouts
- Watchdog parameters
- Logging configuration
- Hardware-specific parameters

## Troubleshooting

### "Permission denied" error

Add user to dialout group:
```bash
sudo usermod -a -G dialout $USER
# Log out and log back in
```

### "No such file or directory: /dev/ttyAMA0"

1. Check if UART is enabled in `/boot/firmware/config.txt`
2. Try `/dev/serial0` instead
3. Verify with: `ls -l /dev/tty*`

### Communication not working

1. **Check wiring**: Verify TX→RX, RX→TX, GND→GND
2. **Check baud rate**: Must match STM32 (default: 115200)
3. **Test with loopback**: Connect RX to TX on RasPi, should echo
4. **Enable debug logging**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

### Checksum errors

- Electromagnetic interference on wires
- Ground loop issues
- Loose connections
- Voltage level mismatch

### Watchdog keeps failing

- STM32 not responding (check if running)
- Baud rate mismatch
- Wiring issue
- STM32 in reset or error state

## Testing

### Basic Communication Test

```bash
python3 raspi_comms_manager.py
```

This will:
- Connect to STM32
- Send ping command
- Read scale
- Print statistics

### Integration Test

```bash
python3 example_integration.py
```

This will:
- Initialize system with watchdog
- Run for 10 seconds
- Attempt a dispensing cycle
- Clean shutdown

## Performance

- **Latency**: ~10-20ms per command (blocking mode)
- **Throughput**: ~100-200 commands/sec (non-blocking)
- **CPU Usage**: <1% (receiver thread)
- **Memory**: ~5MB (Python + libraries)

## Future Enhancements

- [ ] Non-blocking transmit with DMA
- [ ] Command queue for high-rate operations
- [ ] Protocol versioning/negotiation
- [ ] CRC instead of simple checksum
- [ ] Unsolicited message support (STM32→RasPi notifications)
- [ ] Automatic reconnection on connection loss
- [ ] Message timestamping and latency tracking

## License

Proprietary - Ficio Prep Team

## Support

For issues or questions, contact the Ficio Prep Team.