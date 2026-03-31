#!/usr/bin/env python3
"""
HM Encoder (Modbus RTU) Reader for Cable Control
Supports multiple encoders with different addresses
"""

import serial
import struct
import threading
import time
import os
import json
from loguru import logger

# ─── DEFAULT CONFIG ────────────────────────────
DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD_RATE = 9600
DEFAULT_ENCODER_RESOLUTION = 4096  # PPR
DEFAULT_DRUM_CIRCUMFERENCE_M = 0.2  # meters
DEADBAND_PULSES = 5
POLL_INTERVAL_S = 0.1


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build_request(addr, fc, reg_addr, reg_len) -> bytes:
    msg = struct.pack(">BBHH", addr, fc, reg_addr, reg_len)
    return msg + struct.pack("<H", crc16(msg))


def parse_response(data: bytes, n_regs: int):
    if len(data) < 3 + 2 * n_regs + 2:
        return None
    if data[1] & 0x80:
        return None
    if data[2] != 2 * n_regs:
        return None
    if struct.unpack("<H", data[-2:])[0] != crc16(data[:-2]):
        return None
    return [struct.unpack(">H", data[3 + i*2: 5 + i*2])[0] for i in range(n_regs)]


class EncoderReader:
    """Thread-safe encoder reader with Modbus RTU"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.serial_port = self.config.get("serial_port", DEFAULT_SERIAL_PORT)
        self.baud_rate = self.config.get("baud_rate", DEFAULT_BAUD_RATE)
        self.encoder_resolution = self.config.get("encoder_resolution", DEFAULT_ENCODER_RESOLUTION)
        self.drum_circumference = self.config.get("drum_circumference", DEFAULT_DRUM_CIRCUMFERENCE_M)
        
        # Encoder states: address -> {raw, total_m, speed, direction, laps}
        self.encoders = {}
        # Per-address direction inversion: address -> bool
        self.invert = {}
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.ser = None
        self.error_count = 0
        self.last_read_ok = {}
        
    def start(self):
        """Start encoder reading thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        logger.info("Encoder reader started")
        
    def stop(self):
        """Stop encoder reading thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.ser and self.ser.is_open:
            self.ser.close()
        logger.info("Encoder reader stopped")
        
    def _init_serial(self):
        """Initialize serial connection"""
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_EVEN,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.5
            )
            logger.info(f"Serial connected: {self.serial_port}")
        except Exception as e:
            logger.error(f"Serial init failed: {e}")
            self.ser = None
            
    def _read_loop(self):
        """Main reading loop"""
        self._init_serial()
        
        while self.running:
            t0 = time.time()
            
            # Reconnect if needed
            if not self.ser or not self.ser.is_open:
                self._init_serial()
                time.sleep(1)
                continue
                
            # Read each configured encoder
            for addr in list(self.encoders.keys()):
                self._read_encoder(addr)
                
            elapsed = time.time() - t0
            time.sleep(max(0, POLL_INTERVAL_S - elapsed))
            
    def _read_encoder(self, address):
        """Read single encoder"""
        if not self.ser or not self.ser.is_open:
            self.last_read_ok[address] = False
            return
            
        req = build_request(address, 0x04, 0x0003, 0x0002)
        try:
            self.ser.reset_input_buffer()
            self.ser.write(req)
            resp = self.ser.read(9)
            regs = parse_response(resp, 2)
            
            if regs:
                raw = (regs[0] << 16) | regs[1]
                laps = int(raw / self.encoder_resolution)  # Calculate laps from raw
                now = time.time()
                
                with self.lock:
                    prev = self.encoders.get(address, {})
                    prev_enc = prev.get("raw")
                    prev_time = prev.get("timestamp")
                    read_ok = self.last_read_ok.get(address, False)
                    
                    if read_ok and prev_enc is not None and prev_time is not None:
                        dt = now - prev_time
                        delta = raw - prev_enc
                        
                        # 32-bit rollover
                        if delta > 2**31: delta -= 2**32
                        elif delta < -2**31: delta += 2**32
                        
                        # Deadband
                        if abs(delta) <= DEADBAND_PULSES:
                            delta = 0
                            
                        # Apply direction inversion if configured
                        if self.invert.get(address, False):
                            delta = -delta

                        cable_delta_m = (delta / self.encoder_resolution) * self.drum_circumference

                        enc = self.encoders[address]
                        enc["total_m"] += cable_delta_m
                        enc["speed_ms"] = abs(cable_delta_m) / dt if dt > 0 else 0
                        enc["raw"] = raw
                        enc["laps"] = laps
                        enc["timestamp"] = now

                        if delta > DEADBAND_PULSES:
                            enc["direction"] = "ROLL OUT"
                        elif delta < -DEADBAND_PULSES:
                            enc["direction"] = "ROLL IN"
                        else:
                            enc["direction"] = "STOPPED"
                            enc["speed_ms"] = 0
                    else:
                        # First read or previous failed
                        if address not in self.encoders:
                            self.encoders[address] = {
                                "raw": raw,
                                "laps": laps,
                                "total_m": 0.0,
                                "speed_ms": 0.0,
                                "direction": "STOPPED",
                                "timestamp": now
                            }
                        else:
                            self.encoders[address]["raw"] = raw
                            self.encoders[address]["timestamp"] = now
                    
                    self.last_read_ok[address] = True
                    self.error_count = 0
                    
            else:
                self.last_read_ok[address] = False
                self.error_count += 1
                
        except Exception as e:
            logger.error(f"Read encoder {address} error: {e}")
            self.last_read_ok[address] = False
            self.error_count += 1
            
    def add_encoder(self, address, name=""):
        """Add encoder to read"""
        with self.lock:
            self.encoders[address] = {
                "raw": 0,
                "laps": 0,
                "total_m": 0.0,
                "speed_ms": 0.0,
                "direction": "STOPPED",
                "timestamp": time.time(),
                "name": name
            }
        logger.info(f"Added encoder address {address}: {name}")
        
    def reset_counter(self, address):
        """Reset counter for specific encoder"""
        with self.lock:
            if address in self.encoders:
                self.encoders[address]["total_m"] = 0.0
                self.encoders[address]["laps"] = 0
                # Do NOT reset raw to 0 — that would cause a massive delta spike
                # on the next read (real_raw - 0 ≈ 783m) which also triggers a
                # motor pulse via the controller.
                # Instead, mark last_read_ok=False so the next read establishes
                # the real hardware raw as the new baseline (no delta calc),
                # while total_m stays at 0.
                self.last_read_ok[address] = False
        logger.info(f"Reset counter for encoder {address}")
        
    def get_status(self):
        """Get all encoder statuses"""
        with self.lock:
            result = {}
            for addr, data in self.encoders.items():
                result[addr] = {
                    "raw": data["raw"],
                    "laps": data["laps"],
                    "total_m": data["total_m"],
                    "speed_ms": data["speed_ms"],
                    "direction": data["direction"],
                    "name": data.get("name", f"Encoder {addr}")
                }
            return result
            
    def get_status_dict(self):
        """Get named status dictionary"""
        status = self.get_status()
        result = {
            "tether": status.get(1, {"total_m": 0, "speed_ms": 0, "direction": "STOPPED"}),
            "launcher": status.get(2, {"total_m": 0, "speed_ms": 0, "direction": "STOPPED"}),
            "error_count": self.error_count
        }
        return result


# Singleton instance
_encoder_reader = None

def get_encoder_reader():
    global _encoder_reader
    return _encoder_reader

def init_encoder(config=None):
    global _encoder_reader
    _encoder_reader = EncoderReader(config)
    # Default: add tether (addr 1) and launcher (addr 2)
    _encoder_reader.add_encoder(1, "Tether")
    _encoder_reader.add_encoder(2, "Launcher")
    return _encoder_reader