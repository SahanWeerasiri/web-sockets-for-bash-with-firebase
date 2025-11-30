# PowerShell Socket Server with Message Sending
# Run: .\server.ps1

$port = 8081
$ip = "127.0.0.1"

# Create TCP listener
$listener = New-Object System.Net.Sockets.TcpListener($ip, $port)
$listener.Start()

Write-Host "Server started on $ip`:$port" -ForegroundColor Green
Write-Host "Commands:" -ForegroundColor Yellow
Write-Host "  - Type 'broadcast <message>' to send to all clients" -ForegroundColor Yellow
Write-Host "  - Type 'quit' to stop server" -ForegroundColor Yellow
Write-Host "  - Press Enter to check for new connections" -ForegroundColor Yellow
Write-Host ""

$clients = @()

# Function to send message to all clients
function Send-ToAllClients {
    param([string]$message)
    foreach ($clientObj in $clients) {
        try {
            $clientObj.Writer.WriteLine($message)
            $clientObj.Writer.Flush()
        }
        catch {
            Write-Host "Failed to send to client: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

# Function to remove disconnected clients
function Remove-DisconnectedClients {
    for ($i = $clients.Count - 1; $i -ge 0; $i--) {
        if (!$clients[$i].Client.Connected) {
            $clients[$i].Reader.Close()
            $clients[$i].Writer.Close()
            $clients[$i].Client.Close()
            $clients.RemoveAt($i)
            Write-Host "Cleaned up disconnected client" -ForegroundColor Yellow
        }
    }
}

try {
    while ($true) {
        # Check for new connections without blocking
        if ($listener.Pending()) {
            $client = $listener.AcceptTcpClient()
            $stream = $client.GetStream()
            $reader = New-Object System.IO.StreamReader($stream)
            $writer = New-Object System.IO.StreamWriter($stream)
            $writer.AutoFlush = $true
            
            $clientObj = [PSCustomObject]@{
                Client = $client
                Stream = $stream
                Reader = $reader
                Writer = $writer
            }
            
            $clients += $clientObj
            Write-Host "New client connected! Total clients: $($clients.Count)" -ForegroundColor Green
            
            # Send welcome message
            $writer.WriteLine("Welcome to the server! You are client #$($clients.Count)")
        }
        
        # Check for messages from clients
        foreach ($clientObj in $clients) {
            if ($clientObj.Stream.DataAvailable) {
                $message = $clientObj.Reader.ReadLine()
                if ($message) {
                    $timestamp = Get-Date -Format "HH:mm:ss"
                    Write-Host "[$timestamp] Client: $message" -ForegroundColor White
                    
                    # Echo back to the client
                    $clientObj.Writer.WriteLine("Server echo: $message")
                    
                    # Broadcast to all other clients
                    foreach ($otherClient in $clients) {
                        if ($otherClient -ne $clientObj) {
                            try {
                                $otherClient.Writer.WriteLine("Broadcast from client: $message")
                            }
                            catch {
                                # Client probably disconnected
                            }
                        }
                    }
                    
                    # Check for quit command from client
                    if ($message -eq "quit") {
                        $clientObj.Client.Close()
                    }
                }
            }
        }
        
        # Check for server console input
        if ([Console]::KeyAvailable) {
            $serverInput = Read-Host
            if ($serverInput) {
                if ($serverInput -eq "quit") {
                    break
                }
                elseif ($serverInput.StartsWith("broadcast ")) {
                    $broadcastMessage = $serverInput.Substring(10)
                    Send-ToAllClients "SERVER BROADCAST: $broadcastMessage"
                    Write-Host "Broadcasted: $broadcastMessage" -ForegroundColor Magenta
                }
                else {
                    # Send to all clients
                    Send-ToAllClients "SERVER: $serverInput"
                    Write-Host "Sent to all clients: $serverInput" -ForegroundColor Magenta
                }
            }
        }
        
        # Clean up disconnected clients
        Remove-DisconnectedClients
        
        Start-Sleep -Milliseconds 100
    }
}
finally {
    # Close all clients
    foreach ($clientObj in $clients) {
        $clientObj.Reader.Close()
        $clientObj.Writer.Close()
        $clientObj.Client.Close()
    }
    $listener.Stop()
    Write-Host "Server stopped" -ForegroundColor Red
}