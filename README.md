# Firebase Real-Time Database to PowerShell Bridge

A Flask-based server that listens to Firebase Realtime Database changes and broadcasts them to PowerShell clients via TCP sockets, enabling remote command execution.

## Features

- 🔥 Real-time Firebase RTDB listener (no polling)
- 🌐 TCP broadcast server for PowerShell clients
- 🔄 Bi-directional communication (commands in, results out)
- 📡 WebSocket support for additional clients
- 🔐 Secure service account authentication

## Prerequisites

- Python 3.7+
- Firebase project with Realtime Database
- Firebase service account key JSON file
- PowerShell (for client)

## Installation

1. **Install Python dependencies:**
```bash
pip install -r requirements.txt
```

2. **Create `.env` file** in the project root:
```env
FIREBASE_DATABASE_URL=https://db-default-rtdb.firebaseio.com
FIREBASE_SERVICE_ACCOUNT_KEY_PATH=./serviceAccountKey.json
FLASK_HOST=127.0.0.1
PORT=5005
ALLOWED_COMMANDS=ls,cat,find,grep,ps,df,du,whoami,pwd
MAX_COMMAND_TIMEOUT=30
```

3. **Add your Firebase service account key:**
   - Download `serviceAccountKey.json` from Firebase Console
   - Place it in the project root directory

## Usage

### 1. Start the Server

```bash
python server.py
```

The server will start:
- Flask HTTP/WebSocket server on `http://127.0.0.1:5005`
- TCP broadcast server on `127.0.0.1:8081`
- Firebase listener monitoring your RTDB

### 2. Connect PowerShell Client

In a new PowerShell terminal:

```powershell
.\client.ps1
```

Or specify custom ports:
```powershell
.\client.ps1 127.0.0.1 8081 5005
```

### 3. Send Commands via Firebase

Update the Firebase RTDB at path `/command` with any command:

```json
{
  "command": "ls"
}
```

The client will:
- Receive the command via TCP broadcast
- Execute it in PowerShell
- Send output back to server via HTTP POST

## How It Works

```
Firebase RTDB → server.py → TCP Broadcast → client.ps1
                    ↑                            ↓
                    └──────── HTTP POST ─────────┘
```

1. Server listens to Firebase RTDB changes using Firebase SDK
2. When data changes, server broadcasts to all connected TCP clients
3. PowerShell client receives command and executes it
4. Client sends output back to server via `/upstream` endpoint
5. Server displays output in console

## API Endpoints

- `GET /` - Server status
- `GET /status` - Detailed status with client count
- `GET /recent-changes` - Last 50 Firebase changes
- `GET /tcp-clients` - List of connected TCP clients
- `POST /upstream` - Receive command output from clients

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FIREBASE_DATABASE_URL` | Your Firebase RTDB URL | Required |
| `FIREBASE_SERVICE_ACCOUNT_KEY_PATH` | Path to service account JSON | `./serviceAccountKey.json` |
| `FLASK_HOST` | Flask server host | `127.0.0.1` |
| `PORT` | Flask server port | `5005` |
| `ALLOWED_COMMANDS` | Comma-separated allowed commands | Not enforced |
| `MAX_COMMAND_TIMEOUT` | Command execution timeout (seconds) | Not enforced |

### Ports

- **5005** - Flask HTTP/WebSocket server
- **8081** - TCP broadcast server (hardcoded in server.py)

## Security Notes

⚠️ **Important:**
- This system executes arbitrary commands from Firebase
- Only use in trusted, controlled environments
- Consider implementing command validation
- Use firewall rules to restrict access
- Keep service account key secure

## Example Output

**Server Console:**
```
============================================================
Firebase RTDB Bridge Server Starting...
============================================================
Flask WebSocket server: http://127.0.0.1:5005
TCP Broadcast server: 127.0.0.1:8081
============================================================
TCP client connected: ('127.0.0.1', 54321)
[2025-11-30T16:40:11.332628] Data changed at path: /command
Data: ls
---
============================================================
UPSTREAM OUTPUT RECEIVED:
============================================================
    Directory: C:\Users\...
    Mode    LastWriteTime    Length Name
    ----    -------------    ------ ----
    -a----  11/30/2025       250    README.md
============================================================
```

**Client Console:**
```
Listening to broadcasts from 127.0.0.1:8081
[Broadcast] [2025-11-30T16:40:11] Firebase Change - Path: /command, Data: ls
Executing command: ls
Command executed successfully
Result sent to server
```

## Troubleshooting

**Client can't connect:**
- Ensure server is running first
- Check firewall settings
- Verify ports 5005 and 8081 are available

**Firebase authentication fails:**
- Verify `serviceAccountKey.json` path
- Check Firebase Database URL
- Ensure service account has RTDB permissions

**Commands not executing:**
- Check PowerShell execution policy
- Verify command is valid PowerShell syntax

## License

MIT
