# Motor Control System

Raspberry Pi motor controller for USV tether/launcher reels.
Trapezoidal velocity profile + Feedforward-P control, with a web UI.

## Quick Install (new Raspberry Pi)

```bash
git clone https://github.com/ryan354/Tether-Management-System.git /home/pi/motor-control
cd /Tether-Management-System
bash setup.sh
```

That's it. The service is now running and will auto-start on every boot.

**Web UI:** `http://<pi-ip-address>:8888`

## Hardware Wiring

| Component | Connection |
|-----------|------------|
| PCA9685 PWM board | I2C bus 4, address 0x40 |
| Tether motor ESC | PCA9685 channel 14 |
| Launcher motor ESC | PCA9685 channel 15 |
| RS485 encoders | USB `/dev/ttyUSB0`, 9600 baud |
| Tether encoder | Modbus address 1 |
| Launcher encoder | Modbus address 2 |

**PWM range:** 700 (full CW) — 1000 (neutral) — 1300 (full CCW)

## Service Management

```bash
sudo systemctl status motor-control    # Check status
sudo systemctl restart motor-control   # Restart
sudo systemctl stop motor-control      # Stop
journalctl -u motor-control -f         # Live logs
```

## Configuration

All settings are editable from the web UI (Settings button) and saved to `app/config.json`.
Changes persist across restarts.

| Setting | Description | Default |
|---------|-------------|---------|
| `serial_port` | Encoder serial port | `/dev/ttyUSB0` |
| `baud_rate` | Serial baud rate | `9600` |
| `encoder_resolution` | Pulses per revolution | `4096` |
| `drum_circumference` | Drum circumference (m) | `0.2` |
| `ff_gain` | Feedforward gain | `75` |
| `kp` | Proportional gain | `9` |
| `position_gain` | Length-to-speed gain | `1.0` |
| `accel` / `decel` | Ramp rate (m/s per cycle) | `0.03` |

## API

Base URL: `http://<pi-ip>:8888/v1.0`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/motors/status` | GET | All motor + encoder status |
| `/motor/{id}/set` | POST | Set speed + length target |
| `/motor/{id}/stop` | POST | Stop motor |
| `/motor/{id}/pause_resume` | POST | Toggle pause/resume |
| `/motor/{id}/direct_pwm?pwm_value=N` | POST | Direct PWM (700-1300, -1 to disable) |
| `/motor/{id}/pid` | POST | Update controller gains |
| `/config` | GET/POST | Read/write config |
| `/encoder/status` | GET | Encoder data |
| `/encoder/reset?which=tether` | POST | Zero encoder counter |

## Troubleshooting

**Service won't start:**
```bash
journalctl -u motor-control -n 50 --no-pager
```
**Raspi Wifi no Internet:**
```
route wifi adapter as default gateway
nmcli connection show
```

**No I2C (PCA9685 not found):**
```bash
sudo raspi-config    # Interface Options > I2C > Enable
sudo i2cdetect -y 4  # Should show 0x40
sudo apt install python3-smbus
```

**No encoder data:**
```bash
ls /dev/ttyUSB*      # Check USB adapter is connected
```

## Project Structure

```
motor-control/
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
