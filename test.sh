#!/bin/bash

# Firebase RTDB Server Monitoring Script
# Usage: ./monitor.sh [command]
# Commands: status, logs, ports, network, clients, test, all

set -e

# Configuration
SERVICE_NAME="firebase-rtdb"
LOG_DIR="/var/log/firebase-rtdb"
APP_DIR="/home/ubuntu/web-sockets-for-bash-with-firebase"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_header() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}$1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

check_service_status() {
    print_header "SERVICE STATUS"
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_success "Service is RUNNING"
        echo ""
        sudo systemctl status $SERVICE_NAME --no-pager -l | head -20
    else
        print_error "Service is NOT RUNNING"
        echo ""
        sudo systemctl status $SERVICE_NAME --no-pager -l | head -20
    fi
    
    # Check if enabled on boot
    if systemctl is-enabled --quiet $SERVICE_NAME; then
        print_success "Service is ENABLED on boot"
    else
        print_warning "Service is NOT ENABLED on boot"
    fi
}

check_logs() {
    print_header "RECENT LOGS (last 50 lines)"
    
    if [ -f "${LOG_DIR}/server.log" ]; then
        echo "Application logs:"
        tail -50 "${LOG_DIR}/server.log"
        echo ""
    else
        print_warning "Application log file not found"
    fi
    
    echo "Systemd journal (last 20 entries):"
    sudo journalctl -u $SERVICE_NAME -n 20 --no-pager
}

check_ports() {
    print_header "PORT STATUS"
    
    echo "Checking listening ports:"
    echo "-------------------------"
    
    # Check HTTP port 5005
    if sudo netstat -tulpn | grep -q ":5005 "; then
        print_success "Port 5005 (HTTP) is LISTENING"
        sudo netstat -tulpn | grep ":5005 "
    else
        print_error "Port 5005 (HTTP) is NOT LISTENING"
    fi
    echo ""
    
    # Check TCP port 8081
    if sudo netstat -tulpn | grep -q ":8081 "; then
        print_success "Port 8081 (TCP) is LISTENING"
        sudo netstat -tulpn | grep ":8081 "
    else
        print_error "Port 8081 (TCP) is NOT LISTENING"
    fi
    echo ""
    
    # Check connections
    echo "Active connections:"
    echo "-------------------"
    sudo netstat -tupn | grep -E "(5005|8081)" | head -10
}

check_network() {
    print_header "NETWORK CONFIGURATION"
    
    echo "Public IP address:"
    curl -s ifconfig.me
    echo -e "\n"
    
    echo "Private IP addresses:"
    ip addr show | grep "inet " | grep -v "127.0.0.1"
    echo ""
    
    echo "Firewall status (UFW):"
    sudo ufw status verbose
    echo ""
    
    echo "Routing table:"
    ip route | head -10
}

check_clients() {
    print_header "CLIENT CONNECTIONS"
    
    echo "Checking via HTTP API:"
    echo "----------------------"
    curl -s http://localhost:5005/clients || echo "HTTP API not responding"
    echo ""
    
    echo "Checking via HTTP status:"
    echo "-------------------------"
    curl -s http://localhost:5005/status || echo "HTTP status not responding"
    echo ""
    
    # Check active TCP connections
    echo "Active TCP connections to ports:"
    echo "--------------------------------"
    sudo ss -tupn state established | grep -E "(5005|8081)" | head -10
}

test_connections() {
    print_header "CONNECTION TESTS"
    
    echo "Testing HTTP server (localhost:5005):"
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:5005/status | grep -q "200"; then
        print_success "HTTP server is RESPONDING"
        curl -s http://localhost:5005/status | python3 -m json.tool
    else
        print_error "HTTP server is NOT RESPONDING"
    fi
    echo ""
    
    echo "Testing TCP server (localhost:8081):"
    if timeout 2 telnet localhost 8081 2>&1 | grep -q "Connected"; then
        print_success "TCP server is ACCEPTING connections"
    else
        print_error "TCP server is NOT ACCEPTING connections"
    fi
    echo ""
    
    echo "Testing external connectivity:"
    echo "-----------------------------"
    if ping -c 2 8.8.8.8 > /dev/null 2>&1; then
        print_success "Internet connectivity: OK"
    else
        print_error "Internet connectivity: FAILED"
    fi
}

check_resources() {
    print_header "SYSTEM RESOURCES"
    
    echo "CPU Usage:"
    top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print "CPU Idle: " 100-$1 "%"}'
    echo ""
    
    echo "Memory Usage:"
    free -h
    echo ""
    
    echo "Disk Usage:"
    df -h /
    echo ""
    
    echo "Process Info:"
    ps aux --sort=-%mem | grep -E "(python|firebase)" | head -5
}

check_firebase() {
    print_header "FIREBASE CONFIGURATION"
    
    echo "Checking Firebase files:"
    echo "------------------------"
    
    if [ -f "${APP_DIR}/firebase-key.json" ]; then
        print_success "Firebase key file exists"
        echo "Key file size: $(wc -c < "${APP_DIR}/firebase-key.json") bytes"
    else
        print_error "Firebase key file NOT FOUND"
    fi
    echo ""
    
    if [ -f "${APP_DIR}/.env" ]; then
        print_success ".env file exists"
        echo "Contents (sanitized):"
        grep -v "KEY\|SECRET\|PASSWORD\|TOKEN" "${APP_DIR}/.env"
    else
        print_error ".env file NOT FOUND"
    fi
}

check_all() {
    print_header "COMPREHENSIVE SYSTEM CHECK"
    echo "Timestamp: $(date)"
    echo ""
    
    check_service_status
    echo ""
    
    check_resources
    echo ""
    
    check_ports
    echo ""
    
    test_connections
    echo ""
    
    check_network
    echo ""
    
    check_clients
    echo ""
    
    check_firebase
    echo ""
    
    print_header "QUICK DIAGNOSTIC"
    echo "Running quick diagnostic tests..."
    
    # Quick tests
    tests_passed=0
    tests_total=6
    
    # Test 1: Service running
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_success "[1/6] Service is running"
        ((tests_passed++))
    else
        print_error "[1/6] Service is NOT running"
    fi
    
    # Test 2: HTTP port listening
    if sudo netstat -tulpn | grep -q ":5005 "; then
        print_success "[2/6] HTTP port 5005 listening"
        ((tests_passed++))
    else
        print_error "[2/6] HTTP port 5005 NOT listening"
    fi
    
    # Test 3: TCP port listening
    if sudo netstat -tulpn | grep -q ":8081 "; then
        print_success "[3/6] TCP port 8081 listening"
        ((tests_passed++))
    else
        print_error "[3/6] TCP port 8081 NOT listening"
    fi
    
    # Test 4: HTTP API responding
    if curl -s http://localhost:5005/status > /dev/null; then
        print_success "[4/6] HTTP API responding"
        ((tests_passed++))
    else
        print_error "[4/6] HTTP API NOT responding"
    fi
    
    # Test 5: Firebase key exists
    if [ -f "${APP_DIR}/firebase-key.json" ]; then
        print_success "[5/6] Firebase key exists"
        ((tests_passed++))
    else
        print_error "[5/6] Firebase key NOT found"
    fi
    
    # Test 6: Internet connectivity
    if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
        print_success "[6/6] Internet connectivity OK"
        ((tests_passed++))
    else
        print_error "[6/6] Internet connectivity FAILED"
    fi
    
    echo ""
    if [ $tests_passed -eq $tests_total ]; then
        print_success "ALL TESTS PASSED ($tests_passed/$tests_total)"
    else
        print_error "SOME TESTS FAILED ($tests_passed/$tests_total passed)"
    fi
}

# Main script
case "${1}" in
    "status")
        check_service_status
        ;;
    "logs")
        check_logs
        ;;
    "ports")
        check_ports
        ;;
    "network")
        check_network
        ;;
    "clients")
        check_clients
        ;;
    "test")
        test_connections
        ;;
    "resources")
        check_resources
        ;;
    "firebase")
        check_firebase
        ;;
    "all"|"")
        check_all
        ;;
    "help"|"-h"|"--help")
        print_header "MONITORING SCRIPT HELP"
        echo "Usage: ./monitor.sh [command]"
        echo ""
        echo "Commands:"
        echo "  status    - Check service status"
        echo "  logs      - View application logs"
        echo "  ports     - Check port status"
        echo "  network   - Check network configuration"
        echo "  clients   - Check connected clients"
        echo "  test      - Test connections"
        echo "  resources - Check system resources"
        echo "  firebase  - Check Firebase configuration"
        echo "  all       - Run all checks (default)"
        echo "  help      - Show this help"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use './monitor.sh help' for usage information"
        exit 1
        ;;
esac