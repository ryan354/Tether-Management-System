#! /usr/bin/env python3
from pathlib import Path
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi_versioning import VersionedFastAPI, version
from loguru import logger
from typing import Any
from pydantic import BaseModel
import time
import json
import os

# Config file path
CONFIG_FILE = "/home/pi/motor-control/app/config.json"

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
    "pwm_min_ccw": 1300
}

# Load config
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load config, using defaults: {e}")
    return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

CONFIG = load_config()

# Initialize encoder
from encoder import init_encoder, get_encoder_reader
encoder_reader = None



# PWM Configuration (from Ryan's spec)
# Frequency: 250 Hz
# Middle (neutral): 1000
# Max CW: 700
# Min CCW: 1300
PWM_FREQ = 250
PWM_MIDDLE = 1000
PWM_MAX_CW = 700    # Full speed clockwise
PWM_MIN_CCW = 1300  # Full speed counter-clockwise

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
    logger.warning(f"I2C PWM not available: {e} - running in simulation mode")
    def set_pwm(channel, value):
        pass
    def enable_pwm():
        pass

PWM_CHANNELS = {
    "motor1": 14,  # Navigator Ch15 → PCA9685 channel 14
    "motor2": 15,  # Navigator Ch16 → PCA9685 channel 15
}


class MotorData(BaseModel):
    desired_speed: float
    desired_length: float


class ControllerConfig(BaseModel):
    ff_gain:        float = 300.0   # PWM output per m/s (tune open-loop first)
    kp:             float = 15.0    # P gain for speed error correction
    accel_rate:     float = 0.05    # m/s added per loop cycle (ramp up)
    decel_rate:     float = 0.05    # m/s removed per loop cycle (ramp down)
    position_gain:  float = 2.0     # how aggressively to slow near target length


# Cable length conversion (will be calibrated)
# Example: encoder pulses to meters
CABLE_PULSES_PER_METER = 1000


class Motor:
    # Deadband constants
    STOP_DEADBAND_M   = 0.02    # stop when within 20mm of target length
    SPEED_DEADBAND_MS = 0.01    # ignore speed error below 1 cm/s

    def __init__(self, name):
        self.name        = name
        self.pwm_channel = PWM_CHANNELS.get(name, 15)

        # Setpoints
        self.desired_speed  = 0.0
        self.desired_length = 0.0
        
        # Pause/Resume feature
        self.paused         = False
        self.paused_speed   = 0.0
        self.paused_length  = 0.0

        # Feedback (from encoder)
        self.current_speed  = 0.0
        self.current_length = 0.0

        # Direct PWM override (None = use controller)
        self.direct_pwm = None

        # ── Trapezoidal + FF+P controller parameters ──────────────────────
        # ff_gain      : open-loop PWM per m/s. Tune first (run open-loop,
        #                measure speed). e.g. output=100 → 0.5 m/s → gain=200.
        self.ff_gain       = 300.0
        # kp           : closes the loop on speed error after FF is tuned.
        #                Start at 5, raise until drift corrects without oscillation.
        self.kp            = 15.0
        # accel/decel  : m/s per loop cycle (100ms). 0.05 = 0.5 m/s per second.
        self.accel_rate    = 0.05
        self.decel_rate    = 0.05
        # position_gain: remaining_length × gain = speed_target.
        #                2.0 → 0.5 m away gives 1.0 m/s target. Controls decel curve.
        self.position_gain = 2.0

        # Internal trapezoidal state
        self._ramped_speed = 0.0

        # For status/display only
        self.speed_output  = 0.0

        self.last_update = time.time()
    
    def _ramp(self, current: float, target: float) -> float:
        """Step current toward target by at most accel/decel_rate per cycle."""
        if current < target:
            return min(current + self.accel_rate, target)
        elif current > target:
            return max(current - self.decel_rate, target)
        return target

    def _compute_rc_pwm(self) -> int:
        """
        Trapezoidal + FF+P controller -> RC PWM (700-1300).

        Stage 1 - Length -> speed target (position loop):
          speed_target = min(desired_speed, remaining_distance * position_gain)
          Naturally decelerates as cable approaches desired_length.

        Stage 2 - Trapezoidal ramp:
          Smoothly ramps _ramped_speed toward signed speed_target.
          Prevents sudden PWM jumps on new setpoint or direction change.

        Stage 3 - FF + P speed loop:
          pwm_ff = ramped_speed * ff_gain      (open-loop feedforward)
          pwm_p  = speed_error  * kp            (P correction)
          pwm_out = pwm_ff + pwm_p

        Stage 4 - Map to RC PWM (700-1300):
          pwm_out > 0  -> pay out  (CCW, toward 1300)
          pwm_out < 0  -> reel in  (CW,  toward  700)
        """
        # PAUSE CHECK - immediate stop if paused
        if self.paused:
            self._ramped_speed = 0.0
            return PWM_MIDDLE
        
        # Stage 1: length error -> signed speed target
        length_error = self.desired_length - self.current_length

        if abs(length_error) <= self.STOP_DEADBAND_M:
            self._ramped_speed = 0.0
            return PWM_MIDDLE

        direction    = 1.0 if length_error > 0 else -1.0
        speed_target = min(abs(self.desired_speed),
                           abs(length_error) * self.position_gain)
        speed_target  = max(speed_target, 0.0)
        signed_target = direction * speed_target

        # Stage 2: trapezoidal ramp
        self._ramped_speed = self._ramp(self._ramped_speed, signed_target)

        # Stage 3: FF + P
        pwm_ff = self._ramped_speed * self.ff_gain

        signed_actual = self.current_speed if length_error > 0 else -self.current_speed
        speed_error   = self._ramped_speed - signed_actual
        if abs(speed_error) < self.SPEED_DEADBAND_MS:
            speed_error = 0.0
        pwm_p = speed_error * self.kp

        pwm_out = pwm_ff + pwm_p

        # Stage 4: map to RC PWM (700-1300)
        if pwm_out >= 0:
            rc_pwm = PWM_MIDDLE + (pwm_out / 300.0) * (PWM_MIN_CCW - PWM_MIDDLE)
        else:
            rc_pwm = PWM_MIDDLE + (pwm_out / 300.0) * (PWM_MIDDLE - PWM_MAX_CW)

        rc_pwm = max(PWM_MAX_CW, min(PWM_MIN_CCW, rc_pwm))
        self.speed_output = (rc_pwm - PWM_MIDDLE) / 300.0 * 100.0
        return int(rc_pwm)

    def update(self, encoder_length: float, encoder_speed: float = 0.0) -> dict:
        """Update motor state with encoder feedback and compute PWM."""
        now = time.time()
        dt  = max(now - self.last_update, 0.001)
        self.last_update = now

        self.current_speed  = encoder_speed
        self.current_length = encoder_length

        # Direct PWM override
        if self.direct_pwm is not None:
            rc_pwm        = self.direct_pwm
            pca9685_value = int(rc_pwm / 4000 * 4095)
            if NAVIGATOR_AVAILABLE:
                try:
                    set_pwm(self.pwm_channel, pca9685_value)
                    enable_pwm()
                except Exception as e:
                    logger.error(f"Failed to set PWM for {self.name}: {e}")
            self.speed_output = (rc_pwm - PWM_MIDDLE) / 300.0 * 100.0
            return {
                "desired_speed": self.desired_speed,
                "desired_length": self.desired_length,
                "current_speed": self.current_speed,
                "current_length": self.current_length,
                "pwm_value": rc_pwm,
                "mode": "direct"
            }

        # Trapezoidal + FF+P
        rc_pwm        = self._compute_rc_pwm()
        pca9685_value = int(rc_pwm / 4000 * 4095)

        if NAVIGATOR_AVAILABLE:
            try:
                set_pwm(self.pwm_channel, pca9685_value)
                enable_pwm()
            except Exception as e:
                logger.error(f"Failed to set PWM for {self.name}: {e}")

        return {
            "desired_speed":  self.desired_speed,
            "desired_length": self.desired_length,
            "current_speed":  self.current_speed,
            "current_length": self.current_length,
            "pwm_value":      rc_pwm,
            "ramped_speed":   round(self._ramped_speed, 4),
            "controller": {
                "ff_gain":       self.ff_gain,
                "kp":            self.kp,
                "accel_rate":    self.accel_rate,
                "decel_rate":    self.decel_rate,
                "position_gain": self.position_gain,
            }
        }

    def set_desired(self, desired_speed: float, desired_length: float):
        self.desired_speed  = max(0.0, min(2.0, desired_speed))
        self.desired_length = max(0.0, min(100.0, desired_length))

    def set_controller_config(self, cfg: ControllerConfig):
        self.ff_gain       = cfg.ff_gain
        self.kp            = cfg.kp
        self.accel_rate    = cfg.accel_rate
        self.decel_rate    = cfg.decel_rate
        self.position_gain = cfg.position_gain
        logger.info(f"{self.name}: controller updated -> {cfg}")

    def set_pid_config(self, speed_pid=None, length_pid=None):
        """Legacy alias - use set_controller_config instead."""
        pass

    def stop(self):
        """Stop motor - set PWM to neutral and reset ramp state."""
        pca9685_neutral = int(PWM_MIDDLE / 4000 * 4095)
        if NAVIGATOR_AVAILABLE:
            try:
                set_pwm(self.pwm_channel, pca9685_neutral)
                enable_pwm()
            except Exception as e:
                logger.error(f"Failed to stop motor {self.name}: {e}")
        self.direct_pwm    = None
        self._ramped_speed = 0.0
        self.speed_output  = 0.0
        logger.info(f"{self.name}: stopped")


SERVICE_NAME = "MotorControlExtension"

app = FastAPI(
    title="Motor Control API",
    description="API for controlling 2 motors with PID control and cable encoder feedback",
)

# Initialize motors with Navigator PWM channels
# Ch15 = motor1, Ch16 = motor2
motors = {
    "motor1": Motor("motor1"),
    "motor2": Motor("motor2"),
}

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
        # Disable direct mode - set to neutral (1000)
        motor.direct_pwm = None
        pca9685_value = int(1000 / 4000 * 4095)  # 1000 -> 1023
        if NAVIGATOR_AVAILABLE:
            set_pwm(motor.pwm_channel, pca9685_value)
            enable_pwm()
        logger.info(f"{motor_id}: Direct PWM disabled - set to neutral (1000)")
    else:
        # Clamp to 700-1300 (Ryan's spec)
        pwm_value = max(700, min(1300, pwm_value))
        motor.direct_pwm = pwm_value
        # Convert RC PWM (700-1300) to PCA9685 (0-4095)
        # 250Hz = 4000us period: pca9685 = (rc_us / 4000) * 4095
        pca9685_value = int(pwm_value / 4000 * 4095)
        # Apply immediately
        if NAVIGATOR_AVAILABLE:
            set_pwm(motor.pwm_channel, pca9685_value)
            enable_pwm()
        logger.info(f"{motor_id}: Direct PWM set to {pwm_value} (RC) -> {pca9685_value} (PCA9685)")
    
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
            "paused": motor.paused,  # Add paused status for UI
        }
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
    logger.info("Encoder reader initialized on startup")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888, log_config=None)