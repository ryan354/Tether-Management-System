# Tether Management System

Raspberry Pi motor controller for USV tether/launcher reels and USBL transponder foldable mount.
Trapezoidal velocity profile + Feedforward-P control, with a web UI.

## Quick Install (Raspberry Pi)

```bash
git clone https://github.com/ryan354/Tether-Management-System.git /home/tms/Tether-Management-System
cd /home/tms/Tether-Management-System
bash setup.sh
```

That's it. The service is now running and will auto-start on every boot.

**Web UI:** `http://<pi-ip-address>:8888`

## Hardware

### Navigator Board (Blue Robotics)

| Component | Connection |
|-----------|------------|
| PCA9685 PWM (on Navigator) | I2C bus 4, address 0x40, ext 24.576 MHz clock |
| PCA9685 Output Enable | GPIO 26 (active LOW) |
| Navigator Ch1 | Constant 3.3V output (for limit switch power) |

### Motors & ESCs

| Motor | Navigator Channel | PCA9685 Ch | PWM Range |
|-------|-------------------|------------|-----------|
| Tether Reel | Ch15 | 14 | 700-1000-1300 |
| Launcher Reel | Ch16 | 15 | 700-1000-1300 |
| USBL Fold Mount (Basic ESC T200) | Ch14 | 13 | 1100-1500-1900 |

### Encoders

| Encoder | Connection |
|---------|------------|
| RS485 Modbus RTU | USB `/dev/ttyUSB0`, 9600 baud |
| Tether encoder | Modbus address 1 |
| Launcher encoder | Modbus address 2 |

### USBL Fold Mechanism

| Component | Connection |
|-----------|------------|
| Fold limit switch | GPIO 18, pull-down, active HIGH (wire to 3.3V via Ch1) |
| Unfold limit switch | GPIO 27, pull-down, active HIGH (wire to 3.3V via Ch1) |

## Features

- **Tether & Launcher motors**: Trapezoidal velocity profile + FF+P speed controller with encoder feedback
- **Direct PWM mode**: Manual slider control (bypasses controller)
- **USBL foldable mount**: One-button fold/unfold with limit switch auto-stop and 30s safety timeout
- **Direction inversion**: Per-encoder invert checkbox (swaps CW/CCW, direction label, and cable length accumulation)
- **Persistent config**: All settings saved to `config.json` and survive restarts
- **Web UI**: Real-time status, sliders, settings modal

## Service Management

```bash
sudo systemctl status motor-control    # Check status
sudo systemctl restart motor-control   # Restart
sudo systemctl stop motor-control      # Stop
journalctl -u motor-control -f         # Live logs
```

## Configuration

All settings are editable from the web UI (Settings button) and saved to `app/config.json`.

| Setting | Description | Default |
|---------|-------------|---------|
| `serial_port` | Encoder serial port | `/dev/ttyUSB0` |
| `baud_rate` | Serial baud rate | `9600` |
| `encoder_resolution` | Pulses per revolution | `4096` |
| `drum_circumference` | Drum circumference (m) | `0.2` |
| `tether_invert` | Invert tether direction | `false` |
| `launcher_invert` | Invert launcher direction | `false` |
| `fold_ctrl.pwm_middle` | Fold ESC neutral | `1500` |
| `fold_ctrl.fold_speed_pct` | Fold speed (%) | `10` |
| `fold_ctrl.unfold_speed_pct` | Unfold speed (%) | `10` |

## API

Base URL: `http://<pi-ip>:8888/v1.0`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/motors/status` | GET | All motor + encoder + fold status |
| `/motor/{id}/set` | POST | Set speed + length target |
| `/motor/{id}/stop` | POST | Stop motor |
| `/motor/{id}/pause_resume` | POST | Toggle pause/resume |
| `/motor/{id}/direct_pwm?pwm_value=N` | POST | Direct PWM (-1 to disable) |
| `/motor/{id}/pid` | POST | Update controller gains |
| `/fold/fold` | POST | Start folding |
| `/fold/unfold` | POST | Start unfolding |
| `/fold/stop` | POST | Emergency stop fold motor |
| `/fold/status` | GET | Fold mechanism state + switches |
| `/config` | GET/POST | Read/write config |
| `/encoder/status` | GET | Encoder data |
| `/encoder/reset?which=tether` | POST | Zero encoder counter |

## Troubleshooting

**Service won't start:**
```bash
journalctl -u motor-control -n 50 --no-pager
```

**No I2C (PCA9685 not found):**
```bash
sudo i2cdetect -y 4  # Should show 0x40
```
Ensure `/boot/firmware/config.txt` contains:
```
dtoverlay=i2c4,pins_6_7,baudrate=1000000
```

**No encoder data:**
```bash
ls /dev/ttyUSB*      # Check USB adapter is connected
```

## Project Structure

```
Tether-Management-System/
├── setup.sh                  # One-step installer
├── app/
│   ├── main.py               # FastAPI server + motor controller
│   ├── encoder.py            # Modbus RTU encoder reader
│   ├── config.json           # Persistent settings
│   ├── static/index.html     # Web UI
│   ├── motor-control.service # systemd unit file
│   └── requirements.txt      # Python dependencies
└── README.md
```
