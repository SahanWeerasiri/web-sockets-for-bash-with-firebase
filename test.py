# test2.py - Enhanced test
import socket
import requests
import time

def test_port_with_retry(host, port, retries=3):
    for i in range(retries):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True, f"Port {port} is OPEN"
        except Exception as e:
            pass
        time.sleep(2)
    return False, f"Port {port} is CLOSED or blocked"

def main():
    host = "152.67.161.227"
    
    print("="*50)
    print(f"Testing connection to OCI Server: {host}")
    print("="*50)
    
    # First test ping
    print("\n1. Testing basic connectivity (ping)...")
    try:
        import subprocess
        result = subprocess.run(['ping', '-n', '4', host], 
                              capture_output=True, text=True)
        if "TTL=" in result.stdout:
            print("   ✓ Server is reachable via ICMP")
        else:
            print("   ⚠ Server may not respond to ping")
    except:
        print("   ⚠ Could not test ping")
    
    # Test ports
    print("\n2. Testing TCP Port 8081...")
    open_8081, msg_8081 = test_port_with_retry(host, 8081)
    print(f"   {msg_8081}")
    
    print("\n3. Testing TCP Port 5005...")
    open_5005, msg_5005 = test_port_with_retry(host, 5005)
    print(f"   {msg_5005}")
    
    # If ports are open, test HTTP
    if open_5005:
        print("\n4. Testing HTTP server...")
        try:
            response = requests.get(f"http://{host}:5005/status", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ HTTP server is running")
                print(f"   ✓ Status: {data.get('status', 'unknown')}")
                print(f"   ✓ Clients connected: {data.get('connected_clients', 0)}")
            else:
                print(f"   ✗ HTTP error: {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("   ✗ Connection refused - server may not be running")
        except Exception as e:
            print(f"   ✗ Error: {e}")
    
    print("\n" + "="*50)
    print("SUMMARY:")
    print(f"Port 8081: {'OPEN' if open_8081 else 'CLOSED'}")
    print(f"Port 5005: {'OPEN' if open_5005 else 'CLOSED'}")
    
    if not open_8081 and not open_5005:
        print("\n⚠ TROUBLESHOOTING:")
        print("1. Check if server is running on OCI: ps aux | grep server_v3")
        print("2. Check OCI Security Lists for ports 5005 and 8081")
        print("3. Check instance firewall: sudo firewall-cmd --list-all")
        print("4. Ensure server binds to 0.0.0.0 not 127.0.0.1")
    print("="*50)

if __name__ == "__main__":
    main()