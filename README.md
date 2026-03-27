# Motor Control System for USV
=======================

## 🎯 Project Summary

**Raspberry Pi-based motor control system** for Unmanned Surface Vehicle (USV) tether/launcher reels with **trapezoidal velocity profile** control.

### Key Features
- 🚀 **Trapezoidal velocity profile** (accel/decel ramps)
- 🎛️ **Feedforward + PID** control 
- 📡 **Modbus RTU encoder feedback** (Tether addr 1, Launcher addr 2)
- ⚡ **PCA9685 PWM** (I2C bus 4, 250Hz)
- 🌐 **FastAPI web UI** (`http://localhost:8888`)
- 💾 **Persistent settings** (`app/config.json`)
- 🔄 **systemd service** auto-start

## 🛠️ Hardware Requirements

```
📦 Components:
├── PCA9685 PWM controller (I2C 0x40)
├── 2x HM Modbus encoders (RS485, addr 1+2)
├── 2x Brushless motors w/ ESC (RC PWM)
├── RS485 adapter (USB→/dev/ttyUSB0)
└── Raspberry Pi 4/5

🔌 Wiring:
├── PCA9685 → I2C Bus 4
├── Tether motor → PWM ch14
├── Launcher motor → PWM ch15
└── Encoders → /dev/ttyUSB0 (9600 baud)
```

## 🚀 Installation (New Raspberry Pi)

### 1. Clone & Setup
```bash
cd /home/pi
git clone <your-repo> motor-control
cd motor-control
cd app
pip install -r requirements.txt  # or python setup.py install
```

### 2. Enable Service
```bash
sudo cp app/motor-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable motor-control.service
sudo systemctl start motor-control.service
```

### 3. Verify
```bash
sudo systemctl status motor-control.service
curl http://localhost:8888  # Should show UI
curl http://localhost:8888/v1.0/config  # Should show config
```

### 4. Access UI
```
Web UI: http://raspberrypi.local:8888

```

## ⚙️ Configuration

**All settings saved to `app/config.json` & persist across restarts**:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `serial_port` | Encoder serial | `/dev/ttyUSB0` |
| `baud_rate` | Serial baud | `9600` |
| `encoder_resolution` | Pulses/rev | `4096` |
| `drum_circumference` | Wheel diam (m) | `0.2` |
| `tether_ctrl.ff_gain` | Feedforward gain | `75` |
| `tether_ctrl.kp` | PID Kp | `12` |
| `tether_ctrl.position_gain` | Length → speed gain | `1.0` |
| `tether_ctrl.accel` | Acceleration (m/s²) | `0.03` |
| `launcher_ctrl.*` | Same for launcher | Same |

**Tune via UI**: ⚙️ Settings → Apply → **Persists forever**

## 🔧 Troubleshooting

### Service Won't Start
```bash
sudo systemctl status motor-control.service -l
journalctl -u motor-control.service -f
```

**Common fixes**:
```
# IndentationError → cp app/main_trapezoidal app/main.py
# PCA9685 missing → Install `python3-smbus`
sudo apt install python3-smbus i2c-tools
sudo i2cdetect -y 4  # Should show 40
```

### No Encoder Data
```bash
ls /dev/ttyUSB*
sudo minicom -D /dev/ttyUSB0 -b 9600  # Test encoders
curl http://localhost:8888/v1.0/encoder/status
```

### PWM Not Working
```bash
sudo i2cdetect -y 4  # PCA9685 must show 40
sudo raspi-config → Interfacing → Enable I2C
```




## ⚠️ Important Notes

1. **PWM Range**: 700=Full CW, 1000=Neutral, 1300=Full CCW
2. **Encoder Addresses**: Modbus addr 1=tether, 2=launcher
3. **Trapezoidal**: Smooth accel/decel prevents ESC damage
4. **Auto-save**: All UI settings → `config.json` → survive reboots
5. **Backup**: `main.py.bak2` has last working version

## 📱 Web UI Controls

| Control | Description |
|---------|-------------|
| 🎛️ Speed Slider | 0-2 m/s trapezoidal ramp |
| 📏 Cable Length | Length setpoint (outer PID loop) |
| ⚡ Direct PWM | Raw RC PWM (bypass controller) |
| ⚙️ Settings | Tune FF/Kp/accel (persists!) |
| 🎯 Master | Apply same to both motors |


