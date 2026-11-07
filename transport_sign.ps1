# 手元の PC (Windows) で実行する。iPhone の入力を自宅の PC へ転送する
# 「管理者として実行」した PowerShell で:
#   powershell -ExecutionPolicy Bypass -File .\transport_sign.ps1
# 先に手元の PC で PC 用 Remote Gamepad ソフトを起動し、iPhone を接続しておく
# 使う設定 (remote_gamepad.env): IP, NUMBER, IPHONEIP

# 個人の設定 remote_gamepad.env (git の対象外) を読む。同名の環境変数があればそちらを優先する
$Config = Join-Path $PSScriptRoot "remote_gamepad.env"
$Settings = @{}
if (Test-Path $Config) {
    foreach ($line in Get-Content $Config) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"?([^"]*?)"?\s*$') {
            $Settings[$Matches[1]] = $Matches[2]
        }
    }
}

# 未設定か見本の x のままなら、設定方法を表示して終了する
function Require([string]$Name, [string]$Description) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) { $value = $Settings[$Name] }
    if (-not $value -or $value -like "*x*") {
        if (Test-Path $Config) { $how = "$Config の $Name= を書き換えてください。" }
        else { $how = "copy $PSScriptRoot\remote_gamepad.env.example $Config で作り、$Name= を書き換えてください。" }
        Write-Error "$Name ($Description) が設定されていません。$how"
        exit 1
    }
    return $value
}

$IP       = Require "IP" "自宅の PC の Tailscale IP"
$NUMBER   = Require "NUMBER" "転送に使う UDP ポート"
$IPHONEIP = Require "IPHONEIP" "iPhone の IP"

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Error "管理者として実行した PowerShell で実行してください (パケットを読むのに必要)"
    exit 1
}

python "$PSScriptRoot\scripts\remote_gamepad_forward.py" --to "${IP}:${NUMBER}" --src $IPHONEIP -v
