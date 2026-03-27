#!/bin/bash
set -e

echo "🚀 Motor Control Setup Script"
echo "============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root or pi
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}This script should NOT be run as root. Run as 'pi' user.${NC}"
   exit 1
fi

cd "$(dirname "$0")"

PROJECT_DIR="/home/pi/motor-control"
APP_DIR="$PROJECT_DIR/app"

echo -e "${GREEN}1. Updating system...${NC}"
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-smbus i2c-tools python3-serial raspi-config git

echo -e "${GREEN}2. Enabling I2C interface...${NC}"
sudo raspi-config nonint do_i2c 1

echo -e "${GREEN}3. Generating requirements.txt...${NC}"
cd app
pipreqs --force . || echo "pipreqs failed, creating manually..."

if [ ! -f requirements.txt ]; then
    cat > requirements.txt << 'EOF'
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
fastapi-versioning>=1.0.0
loguru>=0.7.0
pydantic>=2.0.0
pyserial>=3.5
EOF
fi

echo -e "${GREEN}4. Creating Python virtual environment...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}5. Installing service...${NC}"
sudo cp motor-control.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable motor-control.service

echo -e "${GREEN}6. Setting up Git repository...${NC}"
cd "$PROJECT_DIR"
if [ ! -d .git ]; then
    git init
    cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
env.bak/
pip-log.txt
pip-delete-this-directory.txt

# Logs
*.log
motor.log

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/

# Backups
backups/
EOF
    git add .
    git commit -m "Initial commit: Motor control system with FastAPI + trapezoidal control"
    echo -e "${GREEN}✅ Git repository initialized and initial commit created${NC}"
    echo -e "${YELLOW}To push to remote: git remote add origin <url> && git push -u origin main${NC}"
else
    echo -e "${YELLOW}Git repo already exists${NC}"
fi

echo -e "${GREEN}7. Starting service...${NC}"
sudo systemctl restart motor-control.service
sudo systemctl status motor-control.service --no-pager -l

echo -e "\n${GREEN}🎉 Setup complete!${NC}"
echo -e "${YELLOW}Access the web UI:${NC} http://localhost:8888 or http://$(hostname).local:8888"
echo -e "${YELLOW}Service logs:${NC} journalctl -u motor-control.service -f"
echo -e "${YELLOW}Test API:${NC} curl http://localhost:8888/v1.0/motors/status"
echo -e "${GREEN}Run this script anytime to update/refresh setup.${NC}"

