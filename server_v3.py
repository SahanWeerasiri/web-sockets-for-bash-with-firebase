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
import uuid
import hashlib

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*")

# TCP Server configuration
TCP_PORT = 8081
HTTP_PORT = 5005

# Client management
client_connections = {}  # {client_id: {'socket': socket, 'address': address, 'pc_name': name}}
client_listeners = {}    # {client_id: firebase_listener_reference}
client_lock = threading.Lock()
pending_sockets = []     # List of {'socket': socket, 'address': address, 'client_id': id}

# Initialize Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH"))
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv("FIREBASE_DATABASE_URL")
})

print("Firebase initialized successfully")

def generate_client_id(pc_name, address):
    """Generate a unique client ID based on PC name and connection info"""
    # Create a unique identifier using PC name, IP, and timestamp
    unique_string = f"{pc_name}_{address[0]}_{address[1]}_{datetime.now().isoformat()}"
    # Generate a short hash
    hash_obj = hashlib.sha256(unique_string.encode())
    client_id = hash_obj.hexdigest()[:16]  # Use first 16 characters
    return client_id

# Function to send message to specific client by ID
def send_to_client(client_id, message):
    """Send message to a specific client by ID"""
    with client_lock:
        if client_id in client_connections:
            try:
                client_socket = client_connections[client_id]['socket']
                client_socket.sendall((message + '\n').encode('utf-8'))
                return True
            except Exception as e:
                print(f"Error sending to client {client_id}: {e}")
                return False
        return False

# Firebase listener for specific client
def create_client_listener(client_id, pc_name):
    """Create a dedicated Firebase listener for a specific client"""
    def listener(event):
        timestamp = datetime.now().isoformat()
        
        print(f"\n[{timestamp}] Command for {pc_name} (ID: {client_id})")
        print(f"Path: {event.path}")
        print(f"Data: {event.data}")
        print("---")
        
        # Send command to specific client
        message = f"[{timestamp}] Firebase Change - Path: {event.path}, Data: {event.data}"
        send_to_client(client_id, message)
    
    # Listen to client-specific command path: /{client_id}/exe/command
    client_ref = db.reference(f'/{client_id}/exe/command')
    client_ref.listen(listener)
    
    return client_ref

# Handle individual client connection
def handle_client_connection(client_socket, client_address):
    """Handle a single client connection in a dedicated thread"""
    client_id = None
    
    try:
        print(f"\n[New Connection] Client connected from {client_address}")
        
        # Generate temporary ID for this pending connection
        temp_id = str(uuid.uuid4())[:8]
        
        # Add to pending sockets
        with client_lock:
            pending_sockets.append({
                'socket': client_socket, 
                'address': client_address,
                'temp_id': temp_id
            })
        
        # Send welcome message
        welcome_msg = "Connected to Firebase RTDB Command Server"
        client_socket.sendall((welcome_msg + '\n').encode('utf-8'))
        
        # Wait for client registration via HTTP
        print(f"Waiting for client registration from {client_address} (temp: {temp_id})...")
        
        # Keep connection alive while waiting for registration
        client_socket.settimeout(None)
        
        while True:
            # Check if this socket has been registered
            with client_lock:
                registered_client = None
                for cid, info in client_connections.items():
                    if info['socket'] == client_socket:
                        registered_client = cid
                        break
                
                if registered_client:
                    client_id = registered_client
                    break
            
            # Small sleep to avoid busy waiting
            threading.Event().wait(0.5)
        
        pc_name = client_connections[client_id]['pc_name']
        print(f"[Registered] Client '{pc_name}' (ID: {client_id}) from {client_address}")
        
        # Keep connection alive
        while True:
            threading.Event().wait(1)
            
            # Check if client is still registered
            with client_lock:
                if client_id not in client_connections:
                    print(f"[Disconnected] Client '{pc_name}' (ID: {client_id}) removed from registry")
                    break
    
    except Exception as e:
        print(f"[Error] Client handler error for {client_address}: {e}")
    
    finally:
        # Cleanup
        if client_id:
            with client_lock:
                if client_id in client_connections:
                    pc_name = client_connections[client_id]['pc_name']
                    print(f"\n[Cleanup] Removing client '{pc_name}' (ID: {client_id})")
                    
                    # Stop Firebase listener
                    if client_id in client_listeners:
                        try:
                            client_listeners[client_id].close()
                            del client_listeners[client_id]
                            print(f"[Cleanup] Stopped Firebase listener for '{pc_name}'")
                        except:
                            pass
                    
                    # Update Firebase status
                    try:
                        db.reference(f'/{client_id}/status').set('disconnected')
                        print(f"[Cleanup] Updated Firebase status for '{pc_name}'")
                    except:
                        pass
                    
                    # Remove from connections
                    del client_connections[client_id]
        
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
        pc_name = data.get('client_name', 'unknown')
        output = data.get('output', '')
        status = data.get('status', '')
        
        # Handle client registration
        if status == 'connected':
            print(f"\n[Registration] PC '{pc_name}' registering...")
            
            with client_lock:
                # Find a pending socket for this client
                if pending_sockets:
                    # Assign the first pending socket
                    pending_info = pending_sockets.pop(0)
                    assigned_socket = pending_info['socket']
                    client_address = pending_info['address']
                    
                    # Generate unique client ID
                    client_id = generate_client_id(pc_name, client_address)
                    
                    print(f"[Registration] Generated ID: {client_id}")
                    print(f"[Registration] Assigned socket from {client_address} to '{pc_name}'")
                    
                    # Register new client
                    client_connections[client_id] = {
                        'socket': assigned_socket,
                        'address': client_address,
                        'pc_name': pc_name
                    }
                    
                    # Start Firebase listener for this client
                    listener_ref = create_client_listener(client_id, pc_name)
                    client_listeners[client_id] = listener_ref
                    print(f"[Firebase] Started listener at /{client_id}/exe/command")
                    
                    # Update Firebase with client info
                    client_ref = db.reference(f'/{client_id}')
                    client_ref.update({
                        'pc_name': pc_name,
                        'status': 'connected',
                        'last_seen': datetime.now().isoformat(),
                        'address': f"{client_address[0]}:{client_address[1]}"
                    })
                    
                    print(f"[Registration] Client '{pc_name}' (ID: {client_id}) registered successfully")
                    print(f"[Status] Total clients: {len(client_connections)}")
                    
                    # Return the client ID to the client
                    return jsonify({
                        'status': 'success', 
                        'message': 'Client registered',
                        'client_id': client_id
                    }), 200
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'No pending connection found'
                    }), 400
        
        # Handle command output - need client_id
        client_id = data.get('client_id')
        if not client_id:
            # Try to find client by PC name (backward compatibility)
            with client_lock:
                for cid, info in client_connections.items():
                    if info['pc_name'] == pc_name:
                        client_id = cid
                        break
        
        if output and client_id:
            print(f"\n{'='*60}")
            print(f"UPSTREAM FROM: {pc_name} (ID: {client_id})")
            print(f"{'='*60}")
            print(f"OUTPUT:\n{str(output)[:100]}")
            print(f"{'='*60}")
            print(f"Uploading to Firebase: /{client_id}/exe/output")
            print("="*60 + "\n")
            
            # Upload to Firebase
            output_ref = db.reference(f'/{client_id}/exe/output')
            output_ref.set(output)
            
            # Update last seen
            db.reference(f'/{client_id}/last_seen').set(datetime.now().isoformat())
        elif output and not client_id:
            print(f"\n{'='*60}")
            print(f"WARNING: Output received from {pc_name} but no client_id!")
            print(f"{'='*60}")
            print(f"OUTPUT:\n{output}")
            print(f"{'='*60}")
            print("Cannot upload to Firebase without client_id")
            print("="*60 + "\n")
        
        return jsonify({'status': 'success', 'message': 'Data received'}), 200
    
    except Exception as e:
        print(f"[Error] Processing upstream data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/clients', methods=['GET'])
def list_clients():
    """List all connected clients"""
    with client_lock:
        clients = []
        for client_id, info in client_connections.items():
            clients.append({
                'id': client_id,
                'pc_name': info.get('pc_name', 'unknown'),
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
            'pending_connections': len(pending_sockets),
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
    print("Firebase RTDB Multi-Client Command Server v3")
    print("=" * 60)
    print(f"HTTP/WebSocket Server: http://0.0.0.0:{port}")
    print(f"TCP Command Server: 0.0.0.0:{TCP_PORT}")
    print(f"Firebase URL: {os.getenv('FIREBASE_DATABASE_URL')}")
    print("=" * 60)
    print("\nDatabase Structure:")
    print("  /{client_id}/")
    print("    ├─ pc_name: Computer name")
    print("    ├─ status: connected/disconnected")
    print("    ├─ last_seen: ISO timestamp")
    print("    ├─ address: IP:Port")
    print("    └─ exe/")
    print("       ├─ command: Commands to execute")
    print("       └─ output: Command outputs")
    print("=" * 60)
    print("\nEach client gets:")
    print("  - Unique client ID (hash of PC name + connection)")
    print("  - Dedicated TCP connection")
    print("  - Separate thread handler")
    print("  - Individual Firebase listener at /{client_id}/exe/command")
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
