# common.ps1 - shared helpers for codesys-connect (dot-source)
# Install resolution mirrors codesys-sync: explicit param / env / match project version.

function Get-CodesysInstalls {
    $bases = @()
    foreach ($v in @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        $(if ($env:SystemDrive) { Join-Path $env:SystemDrive 'Program Files' }),
        $(if ($env:SystemDrive) { Join-Path $env:SystemDrive 'Program Files (x86)' }),
        'C:\Program Files',
        'C:\Program Files (x86)'
    )) {
        if ($v -and (Test-Path $v) -and ($bases -notcontains $v)) { $bases += $v }
    }
    $found = @()
    foreach ($base in $bases) {
        Get-ChildItem $base -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "CODESYS 3.5*" } | ForEach-Object {
                $exeCandidate = Join-Path $_.FullName "CODESYS\Common\CODESYS.exe"
                if (Test-Path $exeCandidate) {
                    $m = [regex]::Match($_.Name, 'CODESYS\s+(3\.5\.\d+\.\d+)')
                    $ver = if ($m.Success) { $m.Groups[1].Value } else { "0.0.0" }
                    $found += [pscustomobject]@{
                        Exe = $exeCandidate
                        Version = $ver
                        InstallName = $_.Name
                    }
                }
            }
    }
    $found | Sort-Object {
        $p = @($_.Version -split '\.') | ForEach-Object { [int]$_ }
        while ($p.Count -lt 4) { $p += 0 }
        ($p[0] * 1000000) + ($p[1] * 10000) + ($p[2] * 100) + $p[3]
    }
}

function Get-ProfileForExe {
    param([string]$Exe)
    $commonDir = Split-Path -Parent $Exe
    $csDir     = Split-Path -Parent $commonDir
    $profDir   = Join-Path $csDir "Profiles"
    $pf = Get-ChildItem $profDir -Filter "*.profile.xml" -File -ErrorAction SilentlyContinue |
          Sort-Object Name | Select-Object -First 1
    if (-not $pf) { throw "No profile found in $profDir" }
    $pf.Name -replace '\.profile\.xml$', ''
}

function Resolve-CodesysInstall {
    param(
        [string]$Exe = "",
        [string]$ProfileName = "",
        [string]$ProjectFile = ""
    )
    if (-not $Exe) { $Exe = $env:CODESYS_CONNECT_EXE }
    if (-not $Exe) { $Exe = $env:CODESYS_SYNC_EXE }
    if (-not $ProfileName) { $ProfileName = $env:CODESYS_CONNECT_PROFILE }
    if (-not $ProfileName) { $ProfileName = $env:CODESYS_SYNC_PROFILE }

    if (-not $Exe) {
        $installs = @(Get-CodesysInstalls)
        if ($installs.Count -eq 0) { throw "No CODESYS 3.5 installation found." }
        $want = $null
        if ($ProjectFile -and (Test-Path $ProjectFile)) {
            # sidecar from codesys-sync export or lastexport stamp
            $projDir = Split-Path -Parent $ProjectFile          # ...\projects
            $repo    = Split-Path -Parent $projDir              # repo root
            $base = [System.IO.Path]::GetFileNameWithoutExtension($ProjectFile)
            $safe = ($base -replace '[\\/:*?"<>|\s\(\)（）]+', '-').Trim('-')
            $candidates = @(
                (Join-Path $repo ("src\plc\" + $safe + "\_project_info.txt")),
                (Join-Path $repo ("src\plc\" + $base + "\_project_info.txt")),
                (Join-Path $repo (".codesys-sync\" + $safe + "_lastexport.txt")),
                (Join-Path $repo (".codesys-sync\" + $base + "_lastexport.txt"))
            )
            foreach ($c in $candidates) {
                if (Test-Path $c) {
                    $line = Select-String -Path $c -Pattern '^\s*compiler(?:_version)?\s*[:=]\s*([0-9.]+)' | Select-Object -First 1
                    if ($line) { $want = $line.Matches[0].Groups[1].Value; break }
                }
            }
        }
        if ($want) {
            $match = $installs | Where-Object { $_.Version -eq $want } | Select-Object -First 1
            if (-not $match) {
                $prefix = ($want -split '\.')[0..2] -join '.'
                $match = $installs | Where-Object { $_.Version -like "$prefix*" } | Select-Object -First 1
            }
            if ($match) {
                $Exe = $match.Exe
                Write-Host "CODESYS install matched project version $want -> $($match.InstallName)"
            } else {
                throw "No CODESYS install matches project version $want"
            }
        } else {
            $newest = $installs | Select-Object -Last 1
            $Exe = $newest.Exe
            Write-Host "WARN: project version unknown; using $($newest.InstallName)"
        }
    }
    if (-not (Test-Path $Exe)) { throw "CODESYS.exe not found: $Exe" }
    if (-not $ProfileName) { $ProfileName = Get-ProfileForExe $Exe }
    [pscustomobject]@{ Exe = $Exe; Profile = $ProfileName }
}

function Get-ConnectSessionPath {
    $dir = Join-Path $env:USERPROFILE ".codesys-connect"
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    Join-Path $dir "session.txt"
}

function Read-ConnectSession {
    $p = Get-ConnectSessionPath
    $h = @{}
    if (Test-Path $p) {
        Get-Content $p -Encoding UTF8 | ForEach-Object {
            if ($_ -match '^\s*([^#=]+)=(.*)$') {
                $h[$matches[1].Trim()] = $matches[2].Trim()
            }
        }
    }
    $h
}

function Write-ConnectSession {
    param([hashtable]$h)
    $p = Get-ConnectSessionPath
    $lines = $h.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Key)=$($_.Value)" }
    Set-Content -Path $p -Value $lines -Encoding UTF8
}

# Run an IronPython op via CODESYS --runscript; stdout is the compact result.
# $Op: connect|disconnect|read|write|download|start|stop|status
# $Args: hashtable of op-specific fields
function Invoke-CodesysOp {
    param(
        [string]$Op,
        [hashtable]$OpArgs = @{},
        [string]$CodesysExe = "",
        [string]$Profile = "",
        [string]$ProjectFile = ""
    )
    $session = Read-ConnectSession
    if (-not $ProjectFile) { $ProjectFile = $session["project"] }
    $install = Resolve-CodesysInstall -Exe $CodesysExe -ProfileName $Profile -ProjectFile $ProjectFile

    $work = Join-Path $env:USERPROFILE ".codesys-connect\work"
    New-Item -ItemType Directory -Force -Path $work | Out-Null
    $target = Join-Path $work "target.txt"
    $result = Join-Path $work "result.txt"
    $log    = Join-Path $work "log.txt"
    if (Test-Path $result) { Remove-Item $result -Force }

    $lines = @(
        "op=$Op",
        "project=$ProjectFile",
        "result=$result",
        "log=$log"
    )
    foreach ($k in $OpArgs.Keys) { $lines += "$k=$($OpArgs[$k])" }
    # merge session fields not overridden
    foreach ($k in @("user","password","device","app","gateway")) {
        if (-not $OpArgs.ContainsKey($k) -and $session[$k]) { $lines += "$k=$($session[$k])" }
    }
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($target, $lines, $utf8)
    $env:CODESYS_CONNECT_TARGET = $target

    $bat = Join-Path $work "run_op.bat"
    [System.IO.File]::WriteAllLines($bat, @(
        "@echo off",
        "set CODESYS_CONNECT_TARGET=$target",
        "`"$($install.Exe)`" --noUI --profile=`"$($install.Profile)`" --runscript=`"$(Join-Path $PSScriptRoot 'online_ops.py')`"",
        "exit /b %ERRORLEVEL%"
    ), [System.Text.Encoding]::ASCII)
    # swallow CODESYS progress spam on stderr; result file is the truth
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = & cmd /c "`"$bat`"" 2>&1 | Out-Null
    } catch {
    } finally {
        $ErrorActionPreference = $old
    }

    if (Test-Path $result) {
        Get-Content $result -Encoding UTF8
    } else {
        Write-Host "ERR no result (see $log)"
        if (Test-Path $log) { Get-Content $log -Encoding UTF8 | Select-Object -Last 20 }
        exit 1
    }
}
