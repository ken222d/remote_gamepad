# 手元の PC (Windows) で実行する。iPhone の入力を自宅の PC へ転送する
# 「管理者として実行」した PowerShell で:
# 先に手元の PC で PC 用 Remote Gamepad ソフトを起動し、iPhone を接続しておく

$IP       = if ($env:IP)       { $env:IP }       else { "x.x.x.x" }  # 自宅の PC の Tailscale IP
$NUMBER   = if ($env:NUMBER)   { $env:NUMBER }   else { "x" }           # remote_desktop_contoll.sh と同じにする
$IPHONEIP = if ($env:IPHONEIP) { $env:IPHONEIP } else { "x.x.x.x" }     # iPhone の IP (手元の Wi-Fi での IP)

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Error "管理者として実行した PowerShell で実行してください (パケットを読むのに必要)"
    exit 1
}

python "$PSScriptRoot\scripts\remote_gamepad_forward.py" --to "${IP}:${NUMBER}" --src $IPHONEIP -v
