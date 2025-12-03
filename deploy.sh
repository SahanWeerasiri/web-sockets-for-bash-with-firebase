#!/bin/bash

# Firebase RTDB Server Deployment Script for Oracle Cloud VM
# Author: Server Deployment Script
# Usage: ./deploy.sh

set -e  # Exit on error

echo "================================================"
echo "Firebase RTDB Server Deployment"
echo "================================================"

# Configuration
APP_NAME="firebase-rtdb"
APP_USER="ubuntu"
APP_DIR="/home/${APP_USER}/web-sockets-for-bash-with-firebase"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="/var/log/${APP_NAME}"
SERVICE_NAME="${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[+]${NC} $1"
}

print_error() {
    echo -e "${RED}[!]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    print_error "Please run as normal user (ubuntu), not as root!"
    exit 1
fi

# Step 1: System Update
print_status "Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Step 2: Install System Dependencies
print_status "Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    libssl-dev \
    libffi-dev \
    net-tools \
    telnet \
    curl \
    ufw

# Step 3: Create Application Directory
print_status "Setting up application directory..."
if [ ! -d "$APP_DIR" ]; then
    print_error "Application directory not found: $APP_DIR"
    print_error "Please place the application in $APP_DIR first"
    exit 1
fi

cd "$APP_DIR"
sudo chown -R $APP_USER:$APP_USER "$APP_DIR"

# Step 4: Setup Python Virtual Environment
print_status "Setting up Python virtual environment..."
if [ -d "$VENV_DIR" ]; then
    print_warning "Virtual environment already exists. Recreating..."
    rm -rf "$VENV_DIR"
fi

python3 -m venv "$VENV_DIR"

# Step 5: Activate Virtual Environment and Install Packages
print_status "Installing Python dependencies..."
source "${VENV_DIR}/bin/activate"
pip install --upgrade pip
pip install wheel

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    print_error "requirements.txt not found!"
    print_status "Creating basic requirements.txt..."
    cat > requirements.txt << EOF
firebase-admin
Flask
Flask-SocketIO
python-socketio
eventlet
python-dotenv
pyopenssl
cryptography
EOF
    pip install -r requirements.txt
fi

# Step 6: Create Log Directory
print_status "Setting up logging..."
sudo mkdir -p "$LOG_DIR"
sudo chown -R $APP_USER:$APP_USER "$LOG_DIR"
sudo chmod 755 "$LOG_DIR"

# Step 7: Create Systemd Service File
print_status "Creating systemd service..."
sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=Firebase RTDB Command Server
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$VENV_DIR/bin/python server_v3.py
Restart=always
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=$SERVICE_NAME

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$LOG_DIR $APP_DIR
PrivateTmp=true
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

# Step 8: Setup Log Rotation
print_status "Configuring log rotation..."
sudo tee /etc/logrotate.d/${SERVICE_NAME} > /dev/null << EOF
${LOG_DIR}/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 640 ${APP_USER} ${APP_USER}
    sharedscripts
    postrotate
        systemctl reload ${SERVICE_NAME} > /dev/null 2>&1 || true
    endscript
}
EOF

# Step 9: Configure Firewall (UFW)
print_status "Configuring firewall..."
sudo ufw --force disable  # Disable temporarily during setup

# Allow SSH first
sudo ufw allow 22/tcp
sudo ufw allow 5005/tcp  # HTTP Server
sudo ufw allow 8081/tcp  # TCP Server
sudo ufw --force enable

# Step 10: Enable and Start Service
print_status "Starting service..."
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

# Wait a moment for service to start
sleep 3

# Step 11: Verify Service Status
print_status "Verifying service status..."
if sudo systemctl is-active --quiet ${SERVICE_NAME}; then
    print_success "Service is running!"
else
    print_error "Service failed to start!"
    sudo systemctl status ${SERVICE_NAME} --no-pager -l
    exit 1
fi

# Step 12: Display Information
echo ""
echo "================================================"
echo "DEPLOYMENT COMPLETE"
echo "================================================"
echo "Application Dir: $APP_DIR"
echo "Virtual Env:     $VENV_DIR"
echo "Log Directory:   $LOG_DIR"
echo "Service Name:    $SERVICE_NAME"
echo "HTTP Port:       5005"
echo "TCP Port:        8081"
echo ""
echo "================================================"
echo "MANAGEMENT COMMANDS"
echo "================================================"
echo "Check status:    sudo systemctl status ${SERVICE_NAME}"
echo "Start service:   sudo systemctl start ${SERVICE_NAME}"
echo "Stop service:    sudo systemctl stop ${SERVICE_NAME}"
echo "Restart service: sudo systemctl restart ${SERVICE_NAME}"
echo "View logs:       sudo journalctl -u ${SERVICE_NAME} -f"
echo "View app logs:   tail -f ${LOG_DIR}/server.log"
echo ""
echo "================================================"
echo "TESTING COMMANDS"
echo "================================================"
echo "Test HTTP:       curl http://localhost:5005/status"
echo "Test TCP:        telnet localhost 8081"
echo "Check ports:     sudo netstat -tulpn | grep -E '5005|8081'"
echo ""
echo "================================================"
echo "NEXT STEPS"
echo "================================================"
echo "1. Check Oracle Cloud Security Rules for ports 5005 & 8081"
echo "2. Test from remote machine:"
echo "   - HTTP: curl http://YOUR_VM_IP:5005/status"
echo "   - TCP: telnet YOUR_VM_IP 8081"
echo "3. Update .env file with your Firebase credentials"
echo "================================================"

# Final verification
print_status "Running final checks..."
curl -s http://localhost:5005/status > /dev/null && \
    print_success "HTTP server is responding" || \
    print_error "HTTP server not responding"

sudo netstat -tulpn | grep -q ":5005 " && \
    print_success "Port 5005 is listening" || \
    print_error "Port 5005 not listening"

sudo netstat -tulpn | grep -q ":8081 " && \
    print_success "Port 8081 is listening" || \
    print_error "Port 8081 not listening"

print_success "Deployment completed successfully!"