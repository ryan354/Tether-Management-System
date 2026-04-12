#! /usr/bin/env python3
from pathlib import Path
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi_versioning import VersionedFastAPI, version
from loguru import logger
from typing import Any
import time
import json
import os

from motor import Motor, FoldMotor, MotorData, ControllerConfig, PWM_MIDDLE, PWM_MAX_CW, PWM_MIN_CCW, PWM_FREQ
from encoder import init_encoder, get_encoder_reader

# Config file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Default config
DEFAULT_CONFIG = {
    "serial_port": "/dev/ttyUSB0",
    "baud_rate": 9600,
    "encoder_resolution": 4096,
    "drum_circumference": 0.2,
    "tether_encoder_address": 1,
    "launcher_encoder_address": 2,
    # Trapezoidal + FF+P controller config (replaces PID)
    "tether_ctrl":   {"ff_gain": 150.0, "kp": 15.0, "accel_rate": 0.05, "decel_rate": 0.05, "position_gain": 2.0},
    "launcher_ctrl": {"ff_gain": 150.0, "kp": 15.0, "accel_rate": 0.05, "decel_rate": 0.05, "position_gain": 2.0},
    "pwm_middle": 1000,
    "pwm_max_cw": 700,
    "pwm_min_ccw": 1300,
    "tether_invert": False,
    "launcher_invert": False,
    # Fold motor (Basic ESC T200): 1100-1500-1900, ±25 deadband
    "fold_ctrl": {
        "pwm_middle": 1500,
        "pwm_max_cw": 1100,
        "pwm_min_ccw": 1900,
        "fold_speed_pct": 10,
        "unfold_speed_pct": 10
    }
}

# Load config (merge saved values over defaults so new fields are always present)
def load_config():
    import copy
    config = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                saved = json.load(f)
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(config.get(k), dict):
                    config[k].update(v)
                else:
                    config[k] = v
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load config, using defaults: {e}")
    return config

def save_config(config):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

CONFIG = load_config()

# Initialize encoder
encoder_reader = None


# ─── Hardware: PCA9685 + GPIO ──────────────────────────────────────────────

# Try direct PCA9685 I2C control (Navigator board: external 24.576 MHz clock, OE on GPIO 26)
try:
    try:
        import smbus
    except ImportError:
        import smbus2 as smbus
    import RPi.GPIO as GPIO

    I2C_BUS = 4  # Navigator PCA9685 on bus 4
    PCA9685_ADDR = 0x40
    bus = smbus.SMBus(I2C_BUS)

    # PCA9685 registers
    PCA9685_MODE1 = 0x00
    PCA9685_MODE2 = 0x01
    PCA9685_PRESCALE = 0xFE
    PCA9685_LED0_ON_L = 0x06

    # --- Enable Output Enable pin (GPIO 26, active LOW) ---
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(26, GPIO.OUT)
    GPIO.output(26, GPIO.LOW)  # LOW = outputs enabled
    logger.info("PCA9685 OE pin (GPIO 26) driven LOW - outputs enabled")

    # --- Limit switch GPIO pins for fold mechanism ---
    FOLD_LIMIT_PIN = 18    # GPIO 18 (Navigator PWM0 header) - fold limit switch
    UNFOLD_LIMIT_PIN = 27  # GPIO 27 (Navigator leak header) - unfold limit switch
    GPIO.setup(FOLD_LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(UNFOLD_LIMIT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    logger.info(f"Limit switch GPIOs configured: fold={FOLD_LIMIT_PIN}, unfold={UNFOLD_LIMIT_PIN}")

    # --- Init PCA9685 with external 24.576 MHz clock ---
    # Step 1: Sleep mode
    bus.write_byte_data(PCA9685_ADDR, PCA9685_MODE1, 0x10)
    time.sleep(0.005)
    # Step 2: Enable external clock (bit 6) + sleep (bit 4)
    bus.write_byte_data(PCA9685_ADDR, PCA9685_MODE1, 0x50)
    time.sleep(0.005)
    # Step 3: Set prescale for 250 Hz using 24.576 MHz external clock
    # Prescale = round(24576000 / (4096 * 250)) - 1 = 23
    prescale = int(round(24576000 / (4096 * PWM_FREQ)) - 1)
    bus.write_byte_data(PCA9685_ADDR, PCA9685_PRESCALE, prescale)
    time.sleep(0.005)
    # Step 4: Wake up with external clock + auto-increment
    bus.write_byte_data(PCA9685_ADDR, PCA9685_MODE1, 0x60)  # EXTCLK(0x40) + AI(0x20)
    time.sleep(0.005)

    # Set Navigator Ch1 (PCA9685 channel 0) to constant 3.3V output
    ch1_reg = PCA9685_LED0_ON_L + (0 * 4)
    bus.write_byte_data(PCA9685_ADDR, ch1_reg, 0)       # ON_L
    bus.write_byte_data(PCA9685_ADDR, ch1_reg + 1, 0x10) # ON_H bit4 = full ON
    bus.write_byte_data(PCA9685_ADDR, ch1_reg + 2, 0)    # OFF_L
    bus.write_byte_data(PCA9685_ADDR, ch1_reg + 3, 0)    # OFF_H
    logger.info("Navigator Ch1 set to constant 3.3V output")

    NAVIGATOR_AVAILABLE = True
    logger.info(f"PCA9685 PWM initialized at {PWM_FREQ} Hz (ext 24.576 MHz clock, prescale={prescale})")

    def set_pwm(channel, value):
        """Set PWM value for channel (0-4095)"""
        if value < 0:
            value = 0
        elif value > 4095:
            value = 4095
        reg = PCA9685_LED0_ON_L + (channel * 4)
        try:
            bus.write_byte_data(PCA9685_ADDR, reg, 0)       # ON_L
            bus.write_byte_data(PCA9685_ADDR, reg + 1, 0)   # ON_H
            bus.write_byte_data(PCA9685_ADDR, reg + 2, value & 0xFF)       # OFF_L
            bus.write_byte_data(PCA9685_ADDR, reg + 3, (value >> 8) & 0xFF)  # OFF_H
        except OSError as e:
            time.sleep(0.05)
            try:
                bus.write_byte_data(PCA9685_ADDR, reg, 0)
                bus.write_byte_data(PCA9685_ADDR, reg + 1, 0)
                bus.write_byte_data(PCA9685_ADDR, reg + 2, value & 0xFF)
                bus.write_byte_data(PCA9685_ADDR, reg + 3, (value >> 8) & 0xFF)
            except OSError as e2:
                logger.error(f"Failed to set PWM channel {channel} to {value}: {e2}")

    def enable_pwm():
        GPIO.output(26, GPIO.LOW)

except Exception as e:
    NAVIGATOR_AVAILABLE = False
    FOLD_LIMIT_PIN = 18
    UNFOLD_LIMIT_PIN = 27
    logger.warning(f"I2C PWM not available: {e} - running in simulation mode")
    def set_pwm(channel, value):
        pass
    def enable_pwm():
        pass

    # Provide a stub GPIO module for FoldMotor in simulation mode
    class _StubGPIO:
        RISING = 31
        PUD_DOWN = 21
        BCM = 11
        OUT = 0
        IN = 1
        @staticmethod
        def input(pin):
            return False
        @staticmethod
        def add_event_detect(*args, **kwargs):
            raise RuntimeError("No GPIO")
        @staticmethod
        def setup(*args, **kwargs):
            pass
        @staticmethod
        def output(*args, **kwargs):
            pass
        @staticmethod
        def setmode(*args, **kwargs):
            pass
        @staticmethod
        def setwarnings(*args, **kwargs):
            pass
    GPIO = _StubGPIO()

PWM_CHANNELS = {
    "motor1": 14,  # Navigator Ch15 → PCA9685 channel 14
    "motor2": 15,  # Navigator Ch16 → PCA9685 channel 15
    "motor3": 13,  # Navigator Ch14 → PCA9685 channel 13 (fold mechanism)
}


# ─── Initialize motors ────────────────────────────────────────────────────

motors = {
    "motor1": Motor("motor1", PWM_CHANNELS["motor1"], set_pwm, enable_pwm, NAVIGATOR_AVAILABLE),
    "motor2": Motor("motor2", PWM_CHANNELS["motor2"], set_pwm, enable_pwm, NAVIGATOR_AVAILABLE),
}

# Apply direction inversion from config
motors["motor1"].invert_direction = CONFIG.get("tether_invert", False)
motors["motor2"].invert_direction = CONFIG.get("launcher_invert", False)

def _apply_encoder_invert():
    """Sync encoder invert flags from config."""
    if encoder_reader:
        tether_addr = CONFIG.get("tether_encoder_address", 1)
        launcher_addr = CONFIG.get("launcher_encoder_address", 2)
        encoder_reader.invert[tether_addr] = CONFIG.get("tether_invert", False)
        encoder_reader.invert[launcher_addr] = CONFIG.get("launcher_invert", False)

# Fold mechanism motor
fold_motor = FoldMotor(
    pwm_channel=PWM_CHANNELS["motor3"],
    fold_pin=FOLD_LIMIT_PIN,
    unfold_pin=UNFOLD_LIMIT_PIN,
    set_pwm_fn=set_pwm,
    navigator_available=NAVIGATOR_AVAILABLE,
    gpio_module=GPIO,
    config=CONFIG,
)


# ─── FastAPI app ──────────────────────────────────────────────────────────

SERVICE_NAME = "MotorControlExtension"

app = FastAPI(
    title="Motor Control API",
    description="API for controlling motors with PID control and cable encoder feedback",
)

logger.info(f"Starting {SERVICE_NAME}!")
if NAVIGATOR_AVAILABLE:
    logger.info(f"Navigator active - PWM freq: {PWM_FREQ} Hz")
else:
    logger.warning("Running in SIMULATION MODE (no Navigator)")

@app.post("/motor/{motor_id}/set", status_code=status.HTTP_200_OK)
@version(1, 0)
async def set_motor(motor_id: str, data: MotorData) -> Any:
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")

    motors[motor_id].set_desired(data.desired_speed, data.desired_length)
    logger.info(f"{motor_id}: desired_speed={data.desired_speed}, desired_length={data.desired_length}")
    return {"status": "ok", "desired_speed": data.desired_speed, "desired_length": data.desired_length}

@app.post("/motor/{motor_id}/pid", status_code=status.HTTP_200_OK)
@version(1, 0)
async def set_controller(motor_id: str, cfg: ControllerConfig) -> Any:
    """Update Trapezoidal + FF+P controller parameters."""
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")
    motors[motor_id].set_controller_config(cfg)
    return {"status": "ok", "controller": cfg.dict()}

@app.post("/motor/{motor_id}/encoder", status_code=status.HTTP_200_OK)
@version(1, 0)
async def update_encoder(motor_id: str, encoder_length: float, encoder_speed: float = 0.0) -> Any:
    """Update motor with encoder feedback (cable length in meters, speed in m/s)"""
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")

    state = motors[motor_id].update(encoder_length, encoder_speed)
    return state

@app.post("/motor/{motor_id}/direct_pwm", status_code=status.HTTP_200_OK)
@version(1, 0)
async def set_direct_pwm(motor_id: str, pwm_value: int) -> Any:
    """Set direct PWM value (700-1300). Set to -1 to disable direct mode."""
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")

    motor = motors[motor_id]
    if pwm_value < 0:
        # Disable direct mode
        motor.direct_pwm = None
        motor.stop()
        logger.info(f"{motor_id}: Direct PWM disabled")
    else:
        # Clamp to 700-1300 and store; motor.update() applies inversion + writes PCA9685
        pwm_value = max(700, min(1300, pwm_value))
        motor.direct_pwm = pwm_value
        logger.info(f"{motor_id}: Direct PWM set to {pwm_value} (RC)")

    return {"status": "ok", "direct_pwm": motor.direct_pwm, "pwm_value": pwm_value if motor.direct_pwm else "PID mode"}

@app.post("/motor/{motor_id}/pause_resume", status_code=status.HTTP_200_OK)
@version(1, 0)
async def pause_resume_motor(motor_id: str) -> Any:
    """Toggle pause/resume - STOP immediately (PWM=1000), resume from saved targets"""
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")

    motor = motors[motor_id]

    if motor.paused:
        # RESUME: restore saved targets
        motor.desired_speed  = motor.paused_speed
        motor.desired_length = motor.paused_length
        motor.paused = False
        logger.info(f"{motor_id}: RESUMED (speed={motor.paused_speed:.2f}, length={motor.paused_length:.2f})")
        return {"status": "resumed", "speed": motor.paused_speed, "length": motor.paused_length}
    else:
        # PAUSE: save targets, stop immediately
        motor.paused_speed   = motor.desired_speed
        motor.paused_length  = motor.desired_length
        motor.paused = True
        logger.info(f"{motor_id}: PAUSED (saved speed={motor.paused_speed:.2f}, length={motor.paused_length:.2f})")
        return {"status": "paused", "saved_speed": motor.paused_speed, "saved_length": motor.paused_length}

@app.post("/motor/{motor_id}/stop", status_code=status.HTTP_200_OK)
@version(1, 0)
async def stop_motor(motor_id: str) -> Any:
    """Stop the motor"""
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")

    motors[motor_id].stop()
    motors[motor_id].desired_speed = 0.0
    motors[motor_id].desired_length = 0.0
    return {"status": "ok", "message": "Motor stopped"}

@app.get("/motor/{motor_id}/status", status_code=status.HTTP_200_OK)
@version(1, 0)
async def get_motor_status(motor_id: str) -> Any:
    if motor_id not in motors:
        raise HTTPException(status_code=404, detail="Motor not found")

    motor = motors[motor_id]
    return {
        "desired_speed":  motor.desired_speed,
        "desired_length": motor.desired_length,
        "current_speed":  motor.current_speed,
        "current_length": motor.current_length,
        "pwm_value":      int(PWM_MIDDLE + motor.speed_output / 100.0 * 300),
        "ramped_speed":   round(motor._ramped_speed, 4),
        "paused":         motor.paused,
        "controller": {
            "ff_gain":       motor.ff_gain,
            "kp":            motor.kp,
            "accel_rate":    motor.accel_rate,
            "decel_rate":    motor.decel_rate,
            "position_gain": motor.position_gain,
        }
    }

@app.get("/motors/status", status_code=status.HTTP_200_OK)
@version(1, 0)
async def get_all_motors_status() -> Any:
    result = {}

    # Get encoder data
    enc_data = {}
    if encoder_reader:
        enc_data = encoder_reader.get_status_dict()

    for motor_id, motor in motors.items():
        # Get encoder data for this motor
        if motor_id == "motor1":
            enc = enc_data.get("tether", {})
        else:
            enc = enc_data.get("launcher", {})

        enc_length = enc.get("total_m", 0)
        enc_speed = enc.get("speed_ms", 0)
        enc_direction = enc.get("direction", "STOPPED")

        # Feed encoder data into controller ONLY if NOT paused
        if not motor.paused:
            # Feed encoder data into PID and run control loop
            motor.update(enc_length, enc_speed)

            # Compute RC PWM value for display
            pwm_val = int(PWM_MIDDLE + motor.speed_output / 100.0 * 300)
            pwm_val = max(PWM_MAX_CW, min(PWM_MIN_CCW, pwm_val))
        else:
            pwm_val = PWM_MIDDLE  # Paused = neutral PWM

        result[motor_id] = {
            "desired_speed": motor.desired_speed,
            "desired_length": motor.desired_length,
            "current_speed": motor.current_speed,
            "current_length": motor.current_length,
            "pwm_value": pwm_val,
            # Encoder data
            "encoder_length": enc_length,
            "encoder_speed": enc_speed,
            "encoder_direction": enc_direction,
            "paused": motor.paused,
        }
    # Add fold mechanism status
    result["fold"] = fold_motor.get_status()
    return result

@app.get("/info")
async def get_info() -> Any:
    """Get system info"""
    return {
        "navigator_available": NAVIGATOR_AVAILABLE,
        "pwm_freq_hz": PWM_FREQ,
        "pwm_middle": PWM_MIDDLE,
        "pwm_max_cw": PWM_MAX_CW,
        "pwm_min_ccw": PWM_MIN_CCW,
    }

# ─── Config API ─────────────────────────────────────────────────────────────
@app.get("/config", status_code=status.HTTP_200_OK)
@version(1, 0)
async def get_config() -> Any:
    """Get current configuration"""
    return CONFIG

@app.post("/config", status_code=status.HTTP_200_OK)
@version(1, 0)
async def set_config(config: dict) -> Any:
    """Save configuration"""
    global CONFIG, encoder_reader
    # Track invert changes to reset encoders
    old_tether_inv = CONFIG.get("tether_invert", False)
    old_launcher_inv = CONFIG.get("launcher_invert", False)
    CONFIG.update(config)
    save_config(CONFIG)

    # Restart encoder with new config
    if encoder_reader:
        encoder_reader.stop()
    encoder_reader = init_encoder({
        "serial_port": CONFIG.get("serial_port", "/dev/ttyUSB0"),
        "baud_rate": CONFIG.get("baud_rate", 9600),
        "encoder_resolution": CONFIG.get("encoder_resolution", 4096),
        "drum_circumference": CONFIG.get("drum_circumference", 0.2)
    })
    encoder_reader.start()

    # Update motor controller config
    for motor in motors.values():
        if motor.name == "motor1":
            cfg = CONFIG.get("tether_ctrl", {})
        elif motor.name == "motor2":
            cfg = CONFIG.get("launcher_ctrl", {})
        else:
            continue
        # Normalize config keys: config.json uses "accel"/"decel",
        # ControllerConfig expects "accel_rate"/"decel_rate"
        normalized = {
            "ff_gain": cfg.get("ff_gain", 150.0),
            "kp": cfg.get("kp", 15.0),
            "position_gain": cfg.get("position_gain", 2.0),
            "accel_rate": cfg.get("accel_rate", cfg.get("accel", 0.05)),
            "decel_rate": cfg.get("decel_rate", cfg.get("decel", 0.05)),
        }
        motor.set_controller_config(ControllerConfig(**normalized))

    # Apply direction inversion
    motors["motor1"].invert_direction = CONFIG.get("tether_invert", False)
    motors["motor2"].invert_direction = CONFIG.get("launcher_invert", False)
    _apply_encoder_invert()
    # Reset encoder counters if invert changed
    if encoder_reader:
        if CONFIG.get("tether_invert", False) != old_tether_inv:
            encoder_reader.reset_counter(CONFIG.get("tether_encoder_address", 1))
            logger.info("Tether encoder reset due to invert change")
        if CONFIG.get("launcher_invert", False) != old_launcher_inv:
            encoder_reader.reset_counter(CONFIG.get("launcher_encoder_address", 2))
            logger.info("Launcher encoder reset due to invert change")

    # Reload fold motor config
    fold_motor._load_config()
    fold_motor.current_pwm = fold_motor.pwm_middle
    logger.info(f"Fold motor config reloaded: middle={fold_motor.pwm_middle}, fold={fold_motor.pwm_fold}, unfold={fold_motor.pwm_unfold}")

    logger.info("Config updated and encoder restarted")
    return {"status": "ok", "config": CONFIG}

# ─── Encoder API ───────────────────────────────────────────────────────────
@app.get("/encoder/status", status_code=status.HTTP_200_OK)
@version(1, 0)
async def get_encoder_status() -> Any:
    """Get encoder status"""
    if not encoder_reader:
        return {"tether": {}, "launcher": {}, "error": "Encoder not initialized"}
    return encoder_reader.get_status_dict()

@app.post("/encoder/reset", status_code=status.HTTP_200_OK)
@version(1, 0)
async def reset_encoder(which: str) -> Any:
    """Reset encoder counter (tether or launcher)"""
    if not encoder_reader:
        raise HTTPException(status_code=500, detail="Encoder not initialized")

    if which == "tether":
        encoder_reader.reset_counter(CONFIG.get("tether_encoder_address", 1))
    elif which == "launcher":
        encoder_reader.reset_counter(CONFIG.get("launcher_encoder_address", 2))
    else:
        raise HTTPException(status_code=400, detail="Invalid encoder (use 'tether' or 'launcher')")

    return {"status": "ok", "reset": which}

# ─── Serial Ports API ──────────────────────────────────────────────────────
@app.get("/serial/ports", status_code=status.HTTP_200_OK)
@version(1, 0)
async def list_serial_ports() -> Any:
    """List available serial ports"""
    import glob
    ports = []
    for pattern in ["/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyS*"]:
        ports.extend(glob.glob(pattern))
    return {"ports": sorted(ports)}

# ---- Fold Mechanism API ------------------------------------------------

@app.post("/fold/fold", status_code=status.HTTP_200_OK)
@version(1, 0)
async def fold_mount() -> Any:
    """Fold the USBL mount."""
    result = fold_motor.fold()
    return {"status": result, "state": fold_motor.state}

@app.post("/fold/unfold", status_code=status.HTTP_200_OK)
@version(1, 0)
async def unfold_mount() -> Any:
    """Unfold the USBL mount."""
    result = fold_motor.unfold()
    return {"status": result, "state": fold_motor.state}

@app.post("/fold/stop", status_code=status.HTTP_200_OK)
@version(1, 0)
async def stop_fold() -> Any:
    """Emergency stop the fold motor."""
    fold_motor.stop()
    return {"status": "stopped", "state": fold_motor.state}

@app.get("/fold/status", status_code=status.HTTP_200_OK)
@version(1, 0)
async def get_fold_status() -> Any:
    """Get fold mechanism status."""
    return fold_motor.get_status()

app = VersionedFastAPI(app, version="1.0.0", prefix_format="/v{major}.{minor}", enable_latest=True)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

@app.get("/", response_class=FileResponse)
async def root() -> Any:
    return "index.html"

# Initialize encoder on startup
@app.on_event("startup")
async def startup_event():
    global encoder_reader
    encoder_reader = init_encoder({
        "serial_port": CONFIG.get("serial_port", "/dev/ttyUSB0"),
        "baud_rate": CONFIG.get("baud_rate", 9600),
        "encoder_resolution": CONFIG.get("encoder_resolution", 4096),
        "drum_circumference": CONFIG.get("drum_circumference", 0.2)
    })
    encoder_reader.start()
    _apply_encoder_invert()
    logger.info("Encoder reader initialized on startup")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888, log_config=None)
