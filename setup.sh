#!/bin/bash
set -e

# ─── Motor Control - One-Step Installer ─────────────────────────────────────
# Usage: git clone <repo> /home/pi/motor-control && cd motor-control && bash setup.sh
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$PROJECT_DIR/app"
VENV_DIR="$PROJECT_DIR/venv"
SERVICE_FILE="motor-control.service"

echo -e "${GREEN}Motor Control - Installer${NC}"
echo "=========================================="

# ── 1. System dependencies ──────────────────────────────────────────────────
echo -e "\n${GREEN}[1/4] Installing system packages...${NC}"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv python3-smbus i2c-tools > /dev/null

# ── 2. Python virtual environment & dependencies ─────────────────────────────
echo -e "${GREEN}[2/4] Creating venv & installing Python packages...${NC}"
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install -q -r "$APP_DIR/requirements.txt"

# ── 3. Enable I2C (needed for PCA9685 PWM) ─────────────────────────────────
echo -e "${GREEN}[3/4] Enabling I2C interface...${NC}"
sudo raspi-config nonint do_i2c 0 2>/dev/null || echo -e "${YELLOW}  Could not auto-enable I2C. Enable manually via sudo raspi-config.${NC}"

# ── 4. Install & start systemd service ──────────────────────────────────────
echo -e "${GREEN}[4/4] Installing systemd service...${NC}"
sudo cp "$APP_DIR/$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_FILE
sudo systemctl restart $SERVICE_FILE

# ── Done ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}=========================================="
echo -e "  Installation complete!"
echo -e "==========================================${NC}"
echo ""
echo -e "  Web UI:  ${YELLOW}http://$(hostname -I | awk '{print $1}'):8888${NC}"
echo -e "  Logs:    ${YELLOW}journalctl -u motor-control -f${NC}"
echo -e "  Status:  ${YELLOW}sudo systemctl status motor-control${NC}"
echo ""
echo -e "  The service starts automatically on boot."
echo ""
