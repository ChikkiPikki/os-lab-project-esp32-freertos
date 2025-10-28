# ESP32 Dynamic Task Manager

A complete system for creating and managing sensor tasks dynamically on ESP32 via UART configuration from a Python GUI.

## Features

- **Dynamic Task Creation**: Create up to 32 tasks dynamically from Python UI
- **Multi-Sensor Support**: Each task can use up to 3 sensors simultaneously
- **Sensor Averaging**: All readings are averaged over 10 samples for accuracy
- **Mutex Protection**: All sensor access is mutex-protected for safe concurrent access
- **UART Logging**: Each task logs data back to Python UI with mutex-protected UART
- **GUI Configuration**: Easy-to-use Tkinter interface for building configs

## Supported Sensors

1. **DHT11** - Temperature and Humidity (1-2 second intervals recommended)
2. **Ultrasonic (HC-SR04)** - Distance measurement (100ms+ intervals)
3. **MPU6050** - 6-axis IMU (accelerometer + gyroscope) (100ms+ intervals)

## Hardware Connections

Defined in `main/include/board.h`:

```c
#define ULTRASONIC_TRIG_PIN 32
#define ULTRASONIC_ECHO_PIN 35
#define MPU_SDA_PIN 22
#define MPU_SCL_PIN 23
#define DHT_DATA_PIN 13
```

## System Architecture

### ESP32 Firmware

1. **main.c**: UART initialization, config reception, task manager invocation
2. **task_manager.c**: JSON parsing, dynamic task creation, task execution
3. **sensors.c**: Sensor read functions with averaging support
4. **Mutexes**: Separate mutexes for DHT11, Ultrasonic, MPU6050, and UART

### Task Configuration Format

```json
{
  "tasks": [
    {
      "name": "TaskName",
      "priority": 5,
      "period_ms": 1000,
      "sensors": ["dht11", "ultrasonic", "mpu6050"]
    }
  ]
}
```

### Python GUI (`python_gui/config_manager.py`)

- **Serial Connection**: Select port, baud rate, connect/disconnect
- **Task Builder**: Add tasks with name, priority, period, and sensors
- **Task List**: View, edit, remove configured tasks
- **Config Management**: Load/save JSON configs
- **Send to ESP32**: Transfer config via UART
- **Live Logging**: View real-time sensor data from ESP32

## Installation & Usage

### 1. Build and Flash ESP32

```bash
cd /run/media/tanay/T7/freertos_projects/os_lab_project
idf.py build
idf.py flash monitor
```

### 2. Run Python GUI

```bash
cd python_gui
python3 config_manager.py
```

**Requirements**:
```bash
pip install pyserial
```

### 3. Using the System

1. **Connect**: Select COM port, click "Connect"
2. **Build Config**:
   - Enter task name
   - Set priority (1-10)
   - Set period in milliseconds
   - Select sensors (max 3 per task)
   - Click "Add Task"
3. **Optional**: Save config for later use
4. **Send**: Click "Send to ESP32"
5. **Monitor**: Watch live sensor data in log window

## Communication Protocol

### Python → ESP32

```
START
<JSON_CONFIG>
END
```

### ESP32 → Python

```
READY          # Acknowledges START
TASKS_CREATED  # Config parsed successfully
ERROR          # Config parse/creation failed
[TaskName] H:45.2% T:23.5C Dist:50cm AccX:0.102g ...  # Sensor data logs
```

## Sensor Reading Details

### Averaging (10 samples per task cycle)

Each task reads configured sensors 10 times and averages:
- **DHT11**: Humidity (%), Temperature (°C)
- **Ultrasonic**: Distance (cm)
- **MPU6050**: Acceleration X, Y, Z (g)

### Timing Constraints

- **DHT11**: Minimum 1-2 second interval between reads
- **Ultrasonic**: 50-100ms recommended for stable readings
- **MPU6050**: 10-100ms for motion tracking

### Mutex Protection

All sensors use dedicated mutexes to prevent race conditions:
- Tasks can safely share sensors
- UART logging uses a separate mutex to prevent garbled output

## Example Configurations

### Environmental Monitor (DHT11 only)
```json
{
  "tasks": [
    {
      "name": "EnvMonitor",
      "priority": 5,
      "period_ms": 2000,
      "sensors": ["dht11"]
    }
  ]
}
```

### Proximity Alert (Ultrasonic only)
```json
{
  "tasks": [
    {
      "name": "ProximityCheck",
      "priority": 6,
      "period_ms": 500,
      "sensors": ["ultrasonic"]
    }
  ]
}
```

### Multi-Sensor Fusion
```json
{
  "tasks": [
    {
      "name": "AllSensors",
      "priority": 7,
      "period_ms": 1000,
      "sensors": ["dht11", "ultrasonic", "mpu6050"]
    }
  ]
}
```

### Multiple Tasks Sharing Sensors
```json
{
  "tasks": [
    {
      "name": "FastMotion",
      "priority": 8,
      "period_ms": 100,
      "sensors": ["mpu6050"]
    },
    {
      "name": "SlowEnv",
      "priority": 4,
      "period_ms": 5000,
      "sensors": ["dht11", "ultrasonic"]
    },
    {
      "name": "MixedData",
      "priority": 5,
      "period_ms": 1000,
      "sensors": ["ultrasonic", "mpu6050"]
    }
  ]
}
```

## Troubleshooting

### ESP32 Not Receiving Config
- Check UART connection and port selection
- Ensure baud rate is 115200
- Check ESP32 monitor output for errors

### Sensor Read Failures
- **DHT11**: Needs 4.7k-10k pull-up resistor, 2s stabilization on boot
- **Ultrasonic**: Check 5V power, ensure ECHO returns to GPIO that tolerates 5V
- **MPU6050**: Verify I2C connections (SDA/SCL), check address (0x68 or 0x69)

### Task Creation Fails
- Verify JSON format is valid
- Check task count ≤ 32
- Check sensor count per task ≤ 3
- Ensure enough heap memory (each task uses 4KB stack)

### Garbled UART Output
- UART mutex ensures atomic writes
- If issues persist, reduce task count or logging frequency

## File Structure

```
os_lab_project/
├── main/
│   ├── main.c                  # UART config reception, app_main
│   ├── task_manager.c          # Dynamic task creation & execution
│   ├── sensors.c               # Sensor read functions
│   ├── include/
│   │   ├── board.h             # Pin definitions
│   │   ├── sensors.h           # Sensor API
│   │   └── task_manager.h      # Task manager API
│   └── CMakeLists.txt
├── python_gui/
│   └── config_manager.py       # Tkinter UI
├── config_example.json         # Example configuration
└── README_DYNAMIC_TASKS.md     # This file
```

## Technical Details

### Memory Usage
- Each task: ~4KB stack
- JSON config buffer: 4KB
- Maximum 32 tasks = ~128KB task memory

### FreeRTOS Configuration
- Tasks use `vTaskDelayUntil` for precise timing
- Priority range: 1-10 (higher = more priority)
- All tasks are persistent once created

### Safety Features
- Mutex protection on all shared resources
- Averaged readings reduce noise
- Timeout handling for sensor failures
- JSON validation before task creation

## Future Enhancements

- Task deletion/modification without reboot
- Real-time task statistics (CPU usage, timing)
- Data logging to SD card
- Web-based UI alternative
- Additional sensor support (BME280, DS18B20, etc.)

## License

Educational project for OS Lab.
