"""
config.py

Configuration file for STM32 communication system.
Modify these values to match your hardware setup.

Author: Ficio Prep Team
Date: January 2026
"""

# ============================================================================
# SERIAL PORT CONFIGURATION
# ============================================================================

# Serial port device
# Raspberry Pi 5 options:
#   - '/dev/ttyAMA0' - Primary UART (GPIO 14/15)
#   - '/dev/serial0'  - Symlink to primary UART
#   - '/dev/ttyUSB0'  - USB-to-serial adapter
SERIAL_PORT = '/dev/ttyAMA0'

# Baud rate (must match STM32)
BAUD_RATE = 115200

# Serial timeout in seconds
SERIAL_TIMEOUT = 0.1

# ============================================================================
# COMMUNICATION PARAMETERS
# ============================================================================

# Default command timeout (seconds)
COMMAND_TIMEOUT = 1.0

# Watchdog ping interval (seconds)
WATCHDOG_INTERVAL = 1.0

# Maximum consecutive watchdog failures before declaring connection lost
WATCHDOG_MAX_FAILURES = 3

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

# Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = 'INFO'

# Log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# Log file (None for console only)
LOG_FILE = None  # e.g., '/var/log/stm32_comms.log'

# ============================================================================
# SYSTEM PARAMETERS
# ============================================================================

# Initialization retry attempts
INIT_RETRY_ATTEMPTS = 3

# Initialization retry delay (seconds)
INIT_RETRY_DELAY = 0.5

# System startup delay (seconds) - wait for STM32 to boot
STARTUP_DELAY = 0.5

# ============================================================================
# HARDWARE-SPECIFIC PARAMETERS
# ============================================================================

# Number of gates (1-4)
NUM_GATES = 4

# Number of cutters (1-3)
NUM_CUTTERS = 3

# Scale parameters
SCALE_MAX_WEIGHT_G = 65535  # Maximum weight in grams (uint16_t max)
SCALE_PRECISION = 0.1       # Scale precision in grams

# ============================================================================
# OPERATIONAL PARAMETERS
# ============================================================================

# Default dispensing timeout (seconds)
DISPENSING_TIMEOUT = 10.0

# Scale reading interval during dispensing (seconds)
SCALE_READ_INTERVAL = 0.1

# Gate operation timeout (seconds)
GATE_TIMEOUT = 5.0

# Cutter cycle timeout (seconds)
CUTTER_TIMEOUT = 5.0