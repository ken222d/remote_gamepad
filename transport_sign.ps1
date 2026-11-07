# Run on the local Windows PC: forward iPhone Remote Gamepad input to the home PC.
# Start the Remote Gamepad PC app and connect the iPhone first, then in an
# Administrator PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\transport_sign.ps1
# Settings (remote_gamepad.env): IP, NUMBER, IPHONEIP
#
# Keep this file ASCII only. Windows PowerShell 5.1 reads non-BOM files as
# Shift-JIS, so any Japanese text here breaks parsing (see README).

# Read personal settings from remote_gamepad.env (ignored by git).
# Environment variables with the same name take precedence.
$Config = Join-Path $PSScriptRoot "remote_gamepad.env"
$Settings = @{}
if (Test-Path $Config) {
    # -Encoding UTF8: the file may contain Japanese comments
    foreach ($line in Get-Content $Config -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"?([^"]*?)"?\s*$') {
            $Settings[$Matches[1]] = $Matches[2]
        }
    }
}

# Exit with instructions when a setting is missing or still the x.x.x.x placeholder
function Require([string]$Name, [string]$Description) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) { $value = $Settings[$Name] }
    if (-not $value -or $value -like "*x*") {
        if (Test-Path $Config) { $how = "Edit $Name= in $Config" }
        else { $how = "Run: copy $PSScriptRoot\remote_gamepad.env.example $Config  and edit $Name=" }
        Write-Error "$Name ($Description) is not set. $how"
        exit 1
    }
    return $value
}

$IP       = Require "IP" "Tailscale IP of the home PC"
$NUMBER   = Require "NUMBER" "UDP port for forwarding"
$IPHONEIP = Require "IPHONEIP" "IP of the iPhone"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Error "Run this in an Administrator PowerShell (needed to read packets)"
    exit 1
}

python "$PSScriptRoot\scripts\remote_gamepad_forward.py" --to "${IP}:${NUMBER}" --src $IPHONEIP -v
