#!/usr/bin/env python3
"""
Motor controllers for tether/launcher reels and USBL fold mechanism.

Motor       – Trapezoidal velocity profile + Feedforward-P speed controller
FoldMotor   – Simple CW/CCW with dual limit switches and safety timeout
"""

import time
from loguru import logger
from pydantic import BaseModel


class ControllerConfig(BaseModel):
    ff_gain:        float = 300.0   # PWM output per m/s (tune open-loop first)
    kp:             float = 15.0    # P gain for speed error correction
    accel_rate:     float = 0.05    # m/s added per loop cycle (ramp up)
    decel_rate:     float = 0.05    # m/s removed per loop cycle (ramp down)
    position_gain:  float = 2.0     # how aggressively to slow near target length


class MotorData(BaseModel):
    desired_speed: float
    desired_length: float


# PWM constants (RC ESC protocol via PCA9685)
PWM_FREQ = 250
PWM_MIDDLE = 1000
PWM_MAX_CW = 700    # Full speed clockwise
PWM_MIN_CCW = 1300  # Full speed counter-clockwise


class Motor:
    """Trapezoidal + FF+P motor controller for cable reels."""

    STOP_DEADBAND_M   = 0.02    # stop when within 20mm of target length
    SPEED_DEADBAND_MS = 0.01    # ignore speed error below 1 cm/s

    def __init__(self, name, pwm_channel, set_pwm_fn, enable_pwm_fn, navigator_available):
        self.name        = name
        self.pwm_channel = pwm_channel
        self._set_pwm    = set_pwm_fn
        self._enable_pwm = enable_pwm_fn
        self._navigator  = navigator_available

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

        # Direction inversion (swaps CW/CCW when True)
        self.invert_direction = False

        # Trapezoidal + FF+P controller parameters
        self.ff_gain       = 300.0
        self.kp            = 15.0
        self.accel_rate    = 0.05
        self.decel_rate    = 0.05
        self.position_gain = 2.0

        # Internal trapezoidal state
        self._ramped_speed = 0.0

        # For status/display only
        self.speed_output  = 0.0

        self.last_update = time.time()

    def _write_pwm(self, rc_pwm):
        """Write an RC PWM value to the PCA9685 channel."""
        pca9685_value = int(rc_pwm / 4000 * 4095)
        if self._navigator:
            try:
                self._set_pwm(self.pwm_channel, pca9685_value)
                self._enable_pwm()
            except Exception as e:
                logger.error(f"Failed to set PWM for {self.name}: {e}")

    def _invert_pwm(self, rc_pwm):
        """Invert PWM around neutral (1000). 850->1150, 1150->850, etc."""
        if self.invert_direction:
            return PWM_MIDDLE + (PWM_MIDDLE - rc_pwm)
        return rc_pwm

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

        Stage 1 - Length -> speed target (position loop)
        Stage 2 - Trapezoidal ramp
        Stage 3 - FF + P speed loop
        Stage 4 - Map to RC PWM (700-1300)
        """
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
        self.last_update = now

        self.current_speed  = encoder_speed
        self.current_length = encoder_length

        # Direct PWM override
        if self.direct_pwm is not None:
            rc_pwm = self._invert_pwm(self.direct_pwm)
            self._write_pwm(rc_pwm)
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
        rc_pwm = self._invert_pwm(self._compute_rc_pwm())
        self._write_pwm(rc_pwm)

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

    def stop(self):
        """Stop motor - set PWM to neutral and reset ramp state."""
        pca9685_neutral = int(PWM_MIDDLE / 4000 * 4095)
        if self._navigator:
            try:
                self._set_pwm(self.pwm_channel, pca9685_neutral)
                self._enable_pwm()
            except Exception as e:
                logger.error(f"Failed to stop motor {self.name}: {e}")
        self.direct_pwm    = None
        self._ramped_speed = 0.0
        self.speed_output  = 0.0
        logger.info(f"{self.name}: stopped")


class FoldMotor:
    """Simple motor controller for fold/unfold mechanism with limit switches."""

    SAFETY_TIMEOUT = 30  # seconds max travel time

    def __init__(self, pwm_channel, fold_pin, unfold_pin,
                 set_pwm_fn, navigator_available, gpio_module, config):
        self.pwm_channel = pwm_channel
        self.fold_pin = fold_pin
        self.unfold_pin = unfold_pin
        self._set_pwm = set_pwm_fn
        self._navigator = navigator_available
        self._gpio = gpio_module
        self._config = config
        self.state = "unknown"
        self._motion_start_time = 0.0

        # Load PWM config
        self._load_config()
        self.current_pwm = self.pwm_middle

        # Send neutral PWM to arm the ESC
        if self._navigator:
            pca9685_value = int(self.pwm_middle / 4000 * 4095)
            try:
                self._set_pwm(self.pwm_channel, pca9685_value)
                logger.info(f"FoldMotor: ESC arming signal sent (PWM {self.pwm_middle})")
            except Exception as e:
                logger.error(f"FoldMotor: failed to send arming signal: {e}")

        # Read initial switch states
        if self._navigator:
            if self._gpio.input(self.fold_pin):
                self.state = "folded"
            elif self._gpio.input(self.unfold_pin):
                self.state = "unfolded"

            # Try interrupt-based detection, fall back to polling
            self._use_interrupts = False
            try:
                self._gpio.add_event_detect(self.fold_pin, self._gpio.RISING,
                                            callback=self._on_fold_limit, bouncetime=50)
                self._gpio.add_event_detect(self.unfold_pin, self._gpio.RISING,
                                            callback=self._on_unfold_limit, bouncetime=50)
                self._use_interrupts = True
                logger.info("FoldMotor: using GPIO interrupt detection")
            except RuntimeError:
                logger.warning("FoldMotor: GPIO edge detection failed, using polling mode")

        logger.info(f"FoldMotor initialized: channel={pwm_channel}, state={self.state}, "
                    f"middle={self.pwm_middle}, fold={self.pwm_fold}, unfold={self.pwm_unfold}")

    def _load_config(self):
        """Load fold motor PWM settings from CONFIG."""
        fc = self._config.get("fold_ctrl", {})
        self.pwm_middle = fc.get("pwm_middle", 1500)
        self.pwm_max_cw = fc.get("pwm_max_cw", 1100)
        self.pwm_min_ccw = fc.get("pwm_min_ccw", 1900)
        fold_pct = fc.get("fold_speed_pct", 50) / 100.0
        unfold_pct = fc.get("unfold_speed_pct", 50) / 100.0
        self.pwm_fold = int(self.pwm_middle + (self.pwm_min_ccw - self.pwm_middle) * fold_pct)
        self.pwm_unfold = int(self.pwm_middle + (self.pwm_max_cw - self.pwm_middle) * unfold_pct)

    def _stop_motor(self):
        self.current_pwm = self.pwm_middle
        pca9685_value = int(self.pwm_middle / 4000 * 4095)
        if self._navigator:
            try:
                self._set_pwm(self.pwm_channel, pca9685_value)
            except Exception as e:
                logger.error(f"FoldMotor: failed to stop: {e}")

    def _on_fold_limit(self, channel):
        if self.state == "folding":
            self._stop_motor()
            self.state = "folded"
            logger.info("FoldMotor: fold limit reached - motor stopped")

    def _on_unfold_limit(self, channel):
        if self.state == "unfolding":
            self._stop_motor()
            self.state = "unfolded"
            logger.info("FoldMotor: unfold limit reached - motor stopped")

    def fold(self):
        if self.state == "folded":
            return "already_folded"
        if self.state in ("folding", "unfolding"):
            return "already_in_progress"
        if self._navigator and self._gpio.input(self.fold_pin):
            self.state = "folded"
            return "already_folded"

        self.state = "folding"
        self.current_pwm = self.pwm_fold
        self._motion_start_time = time.time()
        pca9685_value = int(self.pwm_fold / 4000 * 4095)
        if self._navigator:
            try:
                self._set_pwm(self.pwm_channel, pca9685_value)
            except Exception as e:
                logger.error(f"FoldMotor: failed to start fold: {e}")
                return "error"
        logger.info(f"FoldMotor: folding at PWM {self.pwm_fold}")
        return "folding"

    def unfold(self):
        if self.state == "unfolded":
            return "already_unfolded"
        if self.state in ("folding", "unfolding"):
            return "already_in_progress"
        if self._navigator and self._gpio.input(self.unfold_pin):
            self.state = "unfolded"
            return "already_unfolded"

        self.state = "unfolding"
        self.current_pwm = self.pwm_unfold
        self._motion_start_time = time.time()
        pca9685_value = int(self.pwm_unfold / 4000 * 4095)
        if self._navigator:
            try:
                self._set_pwm(self.pwm_channel, pca9685_value)
            except Exception as e:
                logger.error(f"FoldMotor: failed to start unfold: {e}")
                return "error"
        logger.info(f"FoldMotor: unfolding at PWM {self.pwm_unfold}")
        return "unfolding"

    def stop(self):
        self._stop_motor()
        if self.state in ("folding", "unfolding"):
            self.state = "unknown"
        logger.info("FoldMotor: emergency stop")

    def check_safety_timeout(self):
        if self.state in ("folding", "unfolding"):
            if time.time() - self._motion_start_time > self.SAFETY_TIMEOUT:
                self._stop_motor()
                self.state = "unknown"
                logger.warning("FoldMotor: safety timeout - stopped after 30s")

    def get_status(self):
        self.check_safety_timeout()
        fold_sw = self._gpio.input(self.fold_pin) if self._navigator else False
        unfold_sw = self._gpio.input(self.unfold_pin) if self._navigator else False

        # Poll-based limit switch detection
        if self._navigator:
            if self.state == "folding" and fold_sw:
                self._stop_motor()
                self.state = "folded"
                logger.info("FoldMotor: fold limit reached (polled) - motor stopped")
            elif self.state == "unfolding" and unfold_sw:
                self._stop_motor()
                self.state = "unfolded"
                logger.info("FoldMotor: unfold limit reached (polled) - motor stopped")

        return {
            "state": self.state,
            "pwm_value": self.current_pwm,
            "pwm_middle": self.pwm_middle,
            "pwm_max_cw": self.pwm_max_cw,
            "pwm_min_ccw": self.pwm_min_ccw,
            "fold_switch": bool(fold_sw),
            "unfold_switch": bool(unfold_sw),
        }
