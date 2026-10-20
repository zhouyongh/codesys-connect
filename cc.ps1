# cc.ps1 - codesys-connect CLI (compact one-line result per call)
# Usage:
#   cc.ps1 connect -Project <path> [-User <name> -Password <pw>] [-UserFile <path>]
#                  [-Device name] [-App name] [-Address ip] [-Port n]
#                  [-DeviceName name] [-Gateway name] [-ProjectInfo <sidecar>]
#                  [-Change Force|Try|Keep|Never]
#   cc.ps1 read  <var> [<var>...]
#   cc.ps1 write <name>=<value> [<name>=<value>...]
#   cc.ps1 start | stop | download | status | disconnect
# Session: %USERPROFILE%\.codesys-connect\session.txt
# Credentials: -User/-Password or -UserFile (line1=user, line2=password, or user=/password=).
# Target: -Address/-Port default to 127.0.0.1:11740 (local SoftMotion). Set both for a real PLC.
# -Change is never auto-escalated to Force (Force = full download / wipes variables).
param(
    [Parameter(Position = 0)]
    [string]$Command = "status",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest = @(),
    [string]$Project = "",
    [string]$User = "",
    [string]$Password = "",
    [string]$UserFile = "",
    [string]$Device = "",
    [string]$App = "",
    [string]$Change = "",
    [string]$Address = "",
    [string]$Port = "",
    [string]$DeviceName = "",
    [string]$Gateway = "",
    [string]$ProjectInfo = "",
    [string]$CodesysExe = "",
    [string]$Profile = ""
)
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
. (Join-Path $PSScriptRoot "common.ps1")

if ($UserFile) {
    if (-not (Test-Path $UserFile)) { Write-Host "ERR UserFile not found: $UserFile"; exit 1 }
    $raw = Get-Content $UserFile -Encoding UTF8 | Where-Object { $_.Trim() -ne "" -and -not $_.Trim().StartsWith("#") }
    foreach ($line in $raw) {
        if ($line -match '^\s*user\s*[:=]\s*(.+)$') { $User = $matches[1].Trim() }
        elseif ($line -match '^\s*password\s*[:=]\s*(.+)$') { $Password = $matches[1].Trim() }
        elseif (-not $User) { $User = $line.Trim() }
        elseif (-not $Password) { $Password = $line.Trim() }
    }
    if (-not $User) { Write-Host "ERR UserFile has no user"; exit 1 }
}

$session = Read-ConnectSession
if ($Project)     { $session["project"]     = $Project }
if ($User)        { $session["user"]        = $User }
if ($Password)    { $session["password"]    = $Password }
if ($Device)      { $session["device"]      = $Device }
if ($App)         { $session["app"]         = $App }
if ($Change)      { $session["change"]      = $Change }
if ($Address)     { $session["address"]     = $Address }
if ($Port)        { $session["port"]        = $Port }
if ($DeviceName)  { $session["device_name"] = $DeviceName }
if ($Gateway)     { $session["gateway"]     = $Gateway }
if ($ProjectInfo) { $session["project_info"] = $ProjectInfo }
$sessionKeysTouched = @($Project, $User, $Password, $Device, $App, $Change, $Address, $Port, $DeviceName, $Gateway, $ProjectInfo) |
    Where-Object { $_ -ne "" -and $null -ne $_ }
if ($sessionKeysTouched.Count -gt 0) { Write-ConnectSession $session }

$argsH = @{}
if ($session["change"]) { $argsH["change"] = $session["change"] }

function Split-Pairs([string[]]$items) {
    $pairs = @()
    foreach ($it in $items) {
        # accept both name=value and name:=value (ST style)
        if ($it -match '^\s*([^:=]+)\s*:?=\s*(.*)$') {
            $pairs += "$($matches[1].Trim())=$($matches[2].Trim())"
        } else {
            Write-Host "ERR skip malformed pair: $it"; exit 1
        }
    }
    return ($pairs -join ";")
}

switch ($Command.ToLower()) {
    "connect" {
        if (-not $session["project"]) { Write-Host "ERR -Project required"; exit 1 }
        if ($Rest.Count -gt 0) { Write-Host "ERR connect takes no positional args"; exit 1 }
        $argsH["change"] = if ($session["change"]) { $session["change"] } else { "Try" }
        $out = Invoke-CodesysOp -Op connect -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile `
            -ProjectFile $session["project"] -ProjectInfo $session["project_info"]
    }
    "disconnect" { $out = Invoke-CodesysOp -Op disconnect -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile }
    "logout"     { $out = Invoke-CodesysOp -Op logout -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile }
    "login"      { $out = Invoke-CodesysOp -Op login -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile }
    "download"   {
        $argsH["change"] = if ($session["change"]) { $session["change"] } else { "Force" }
        $out = Invoke-CodesysOp -Op download -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile
    }
    "start"      { $out = Invoke-CodesysOp -Op start -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile }
    "stop"       { $out = Invoke-CodesysOp -Op stop -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile }
    "status"     { $out = Invoke-CodesysOp -Op status -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile }
    "read" {
        if ($Rest.Count -eq 0) { Write-Host "ERR read needs at least one variable"; exit 1 }
        $argsH["vars"] = ($Rest -join ",")
        $out = Invoke-CodesysOp -Op read -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile
    }
    "write" {
        if ($Rest.Count -eq 0) { Write-Host "ERR write needs name=value pairs"; exit 1 }
        $argsH["pairs"] = Split-Pairs $Rest
        $out = Invoke-CodesysOp -Op write -OpArgs $argsH -CodesysExe $CodesysExe -Profile $Profile
    }
    default {
        Write-Host "ERR unknown command: $Command (connect|disconnect|read|write|download|start|stop|status)"
        exit 1
    }
}

$out | ForEach-Object { Write-Host $_ }
$bad = @($out | Where-Object { $_ -like "ERR*" -or $_ -like "FATAL*" })
if ($bad.Count -gt 0) { exit 1 }
exit 0
