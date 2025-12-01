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

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
socketio = SocketIO(app, cors_allowed_origins="*")

# Store recent changes in memory (optional - for status endpoint)
recent_changes = []
MAX_CHANGES_STORED = 50

# TCP Broadcast server variables
tcp_clients = []
tcp_server = None
tcp_running = False
TCP_PORT = 8081  # Port for PowerShell clients to connect

# Initialize Firebase
cred = credentials.Certificate(os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY_PATH"))
firebase_admin.initialize_app(cred, {
    'databaseURL': os.getenv("FIREBASE_DATABASE_URL")
})

# Reference to your database location
ref = db.reference('/command')

# Function to broadcast to all TCP clients
def broadcast_to_tcp_clients(message):
    disconnected_clients = []
    
    for client_socket in tcp_clients:
        try:
            client_socket.sendall((message + '\n').encode('utf-8'))
        except:
            disconnected_clients.append(client_socket)
    
    # Remove disconnected clients
    for client in disconnected_clients:
        tcp_clients.remove(client)
        try:
            client.close()
        except:
            pass

# TCP Server function
def start_tcp_server():
    global tcp_server, tcp_running, tcp_clients
    
    tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp_server.bind(('127.0.0.1', TCP_PORT))
    tcp_server.listen(5)
    tcp_server.settimeout(1.0)  # Allow checking for shutdown
    
    tcp_running = True
    print(f"TCP broadcast server started on port {TCP_PORT}")
    
    while tcp_running:
        try:
            client_socket, client_address = tcp_server.accept()
            print(f"TCP client connected: {client_address}")
            tcp_clients.append(client_socket)
            
            # Send welcome message
            welcome_msg = "Connected to Firebase RTDB broadcast server"
            client_socket.sendall((welcome_msg + '\n').encode('utf-8'))
            
        except socket.timeout:
            continue
        except Exception as e:
            if tcp_running:  # Only print error if we're supposed to be running
                print(f"TCP server error: {e}")
    
    # Cleanup
    for client in tcp_clients:
        try:
            client.close()
        except:
            pass
    tcp_clients.clear()
    tcp_server.close()
    print("TCP broadcast server stopped")

# Listen for Firebase changes
def listener(event):
    timestamp = datetime.now().isoformat()
    change_info = {
        'timestamp': timestamp,
        'data': event.data,
        'path': event.path
    }
    
    print(f"[{timestamp}] Data changed at path: {event.path}")
    print(f"Data: {event.data}")
    print("---")
    
    # Store change in memory
    recent_changes.append(change_info)
    if len(recent_changes) > MAX_CHANGES_STORED:
        recent_changes.pop(0)
    
    # Emit to all connected WebSocket clients
    socketio.emit('firebase_change', change_info, namespace='/')
    
    # Broadcast to all TCP clients
    broadcast_message = f"[{timestamp}] Firebase Change - Path: {event.path}, Data: {event.data}"
    broadcast_to_tcp_clients(broadcast_message)

# Start listening in a separate thread
def start_firebase_listener():
    ref.listen(listener)
    print("Firebase listener started")

# Flask routes
@app.route('/')
def home():
    return jsonify({
        'status': 'running',
        'message': 'Firebase Realtime Database listener is active',
        'listening_to': os.getenv("FIREBASE_DATABASE_URL"),
        'tcp_broadcast_port': TCP_PORT,
        'connected_tcp_clients': len(tcp_clients)
    })

@app.route('/status')
def status():
    return jsonify({
        'status': 'active',
        'recent_changes_count': len(recent_changes),
        'max_stored': MAX_CHANGES_STORED,
        'connected_tcp_clients': len(tcp_clients),
        'tcp_broadcast_port': TCP_PORT
    })

@app.route('/upstream', methods=['POST'])
def output_upstream():
    # read body and print
    try:
        data = request.get_json()
        print("\n" + "="*60)
        print("UPSTREAM OUTPUT RECEIVED:")
        print("="*60)
        print(data.get('output', 'No output'))
        print("="*60 + "\n")
        # upload to output node in firebase
        output_ref = db.reference('/output')
        output_ref.push(data.get('output', 'No output'))
        return jsonify({'status': 'success', 'message': 'Output received'}), 200
    except Exception as e:
        print(f"Error processing upstream data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/recent-changes')
def get_recent_changes():
    return jsonify({
        'changes': recent_changes,
        'count': len(recent_changes)
    })

@app.route('/tcp-clients')
def get_tcp_clients():
    client_info = []
    for client in tcp_clients:
        try:
            client_info.append(str(client.getpeername()))
        except:
            client_info.append("disconnected")
    return jsonify({
        'connected_clients': client_info,
        'count': len(tcp_clients)
    })

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print(f"WebSocket client connected")
    emit('connection_response', {'status': 'connected', 'message': 'Successfully connected to Firebase listener'})

@socketio.on('disconnect')
def handle_disconnect():
    print("WebSocket client disconnected")

def cleanup():
    global tcp_running
    print("Shutting down servers...")
    tcp_running = False
    
    # Stop Firebase listener
    try:
        ref._stop_listening()
        print("Firebase listener stopped")
    except:
        pass

if __name__ == '__main__':
    # Start TCP broadcast server in background thread
    tcp_thread = threading.Thread(target=start_tcp_server, daemon=True)
    tcp_thread.start()
    
    # Start Firebase listener in background thread
    firebase_thread = threading.Thread(target=start_firebase_listener, daemon=True)
    firebase_thread.start()
    
    # Get port from environment or use default
    port = int(os.getenv('PORT', 5000))
    
    print("=" * 60)
    print("Firebase RTDB Bridge Server Starting...")
    print("=" * 60)
    print(f"Flask WebSocket server: http://127.0.0.1:{port}")
    print(f"TCP Broadcast server: 127.0.0.1:{TCP_PORT}")
    print(f"Firebase URL: {os.getenv('FIREBASE_DATABASE_URL')}")
    print("=" * 60)
    print("PowerShell clients can connect using:")
    print(f"  .\\listener.ps1 127.0.0.1 {TCP_PORT}")
    print("=" * 60)
    
    try:
        # Run Flask app with SocketIO
        socketio.run(app, host='127.0.0.1', port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\nReceived interrupt signal...")
    finally:
        cleanup()