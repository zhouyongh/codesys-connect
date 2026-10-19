---
name: codesys-connect
description: Compact CODESYS online CLI for AI - connect/disconnect, read/write PLC variables, download/start/stop a running CODESYS Control / SoftMotion Win target, one command one short line (no MCP JSON dumps). Built on the CODESYS Scripting Engine online API (global `online` object). Use when the user wants to connect to CODESYS, login to a soft PLC, download a program, start/stop the PLC, read or write variables, codesys-connect, or close the loop with codesys-sync (export/import project -> download -> run -> control).
---

# codesys-connect - compact CODESYS online control

Token-efficient online access to a CODESYS soft PLC (SoftMotion Win / Control Win). One command -> one short result. Session fields (project, user, password, device, app) are stored in `%USERPROFILE%\.codesys-connect\session.txt` so later calls stay one-liners.

Pairs with **codesys-sync**: create/import the project there, then `download` / `start` / `read` / `write` here.

## Interface

```powershell
# first time: bind project + credentials (either -User/-Password or -UserFile)
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 connect `
    -Project <abs path to .project> -User <name> -Password <pw> [-Device Device] [-App Application]

# or read credentials from a local file (do not commit it):
#   user.txt line1 = username, line2 = password
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 connect `
    -Project <abs path to .project> -UserFile <path to user.txt>

# then compact ops (session reused)
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 download
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 stop
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 read GVL.bStart GVL.Axis_X.fActPosition
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 write GVL.bStart:=TRUE GVL.fVel:=100
powershell -NoProfile -ExecutionPolicy Bypass -File <codesys-connect>\cc.ps1 disconnect
```

| Command | Meaning | Compact output |
|---|---|---|
| `connect` | Set session, connect device, login application (online change as needed) | `OK connected=1 logged_in=1 user=... app=...` |
| `status` | Connection / login / app + operation state | `connected=... user=... logged_in=... app_state=... op_state=...` |
| `download` | Force download + login (program into the soft PLC) | `OK downloaded=1 app_state=... op_state=...` |
| `start` / `stop` | PLC run / stop | `OK started=1 op_state=...` |
| `read` | Read one or more symbols | `GVL.x=12.5` per line |
| `write` | Write `name=value` pairs | `name=value` lines + `OK written=N` |
| `disconnect` / `logout` | Logout + disconnect | `OK logged_in=0` |

Exit code 0 on success; 1 when any line starts with `ERR`. Never trust CODESYS process exit codes.

## How it works

CODESYS `--noUI --runscript=online_ops.py` (same headless route as codesys-sync). The script environment exposes a global `online` (`ScriptOnline`) with `create_online_device` / `create_online_application` / `set_default_credentials` / `login(OnlineChangeOption, delete_foreign)` / `read_value(s)` / `set_prepared_value` + `write_prepared_values` / `start` / `stop`. Credentials come from the session file (set via `-User`/`-Password` or `-UserFile`).

**Why not MCP?** MCP servers can do the same online job, but tool schemas and JSON envelopes burn context on every call. This CLI keeps only the verbs and the values - `name=value` lines.

## Credentials

Nothing is hardcoded. Three ways, pick one:

1. **Command line** (one-time, then session remembers it):
   `cc.ps1 connect -Project ... -User alice -Password secret`
2. **User file** (`-UserFile`): two lines - username, then password (or `user=` / `password=`).
   Keep this file local / gitignore it. See `user.txt.example`.
3. **Session file** `%USERPROFILE%\.codesys-connect\session.txt` - edit `user=` / `password=` directly.

The target login must exist in the **soft PLC user DB** (SoftMotion/Control Win). Create it in the IDE
(Online -> Device User Management), or copy a credentials file from a machine that already has the account.

## Parameters

| Flag | Meaning |
|---|---|
| `-Project` | Absolute `.project` path (required for `connect`) |
| `-User` / `-Password` | Target login (SoftMotion/Control user DB) |
| `-UserFile` | Credentials file (username, password) |
| `-Device` | Device node name (default: first PLC-like device) |
| `-App` | Application node name (default: first Application) |
| `-Change` | `Try` (default for connect) / `Force` (download) / `Keep` / `Never` |
| `-CodesysExe` / `-Profile` | Pin a CODESYS install; default matches the project's last-saved version (same rule as codesys-sync) |

## Closed-loop recipe (SoftMotion 3-axis)

1. **codesys-sync** create/import a SoftMotion project with 3 virtual axes (`SM_Drive_Virtual`) + `GVL` control bits + `PRG_Main`.
   - SoftMotion **Win V3** (32-bit): DeviceID `4102/0000 0001`
   - SoftMotion **Win V3 x64** (64-bit): DeviceID `4102/0000 0004` - must match the running soft PLC, or login fails with "target system ... is different from the connected device"
2. Open **CODESYS SoftMotion Win 64** (soft PLC running).
3. `cc.ps1 connect -Project <project> -User <name> -Password <pw>`
4. `cc.ps1 download` -> `cc.ps1 start`
5. `cc.ps1 write GVL.g_bEnable:=TRUE GVL.g_bMove:=TRUE`
6. `cc.ps1 read GVL.g_bPoweredAll GVL.g_bBusyAll`
7. `cc.ps1 stop` / `disconnect`

Verified: SoftMotion Win V3 **x64** + 3 virtual axes; `set_gateway_and_ip_address(Gateway-1, 127.0.0.1, 11740)` then login/download/start/read/write.

## Pitfalls

- Close the project in the IDE before `download`/`connect` that may save/upgrade; export/import of *source* is codesys-sync's job - this tool only talks **online**.
- Each command launches CODESYS headless (seconds, not ms). Batch variables into one `read` / `write` call rather than many.
- Output must stay compact - do not ask this tool for a full symbol dump; use codesys-sync export for that.
- `OnlineChangeOption.Force` replaces the running app; `Try` attempts online change. Use `Force` when logic changed.
- Credentials live in a local session file - do not commit it.

## Version pinning (read this)

Create/import the project and run **online** ops with the **same** CODESYS SP. Mixing (project saved by SP22, opened with SP17) marks objects incomplete and login fails. Auto-detect matches the project's last-saved version, same rule as codesys-sync; pin with `-CodesysExe` / `-Profile` when unsure.

SoftMotion device IDs:

| Runtime | DeviceID |
|---|---|
| SoftMotion Win V3 (32-bit) | `4102/0000 0001` |
| SoftMotion Win V3 **x64** | `4102/0000 0004` |
| Virtual axis `SM_Drive_Virtual` | `1024/FFFF 0001` |

## Files

| File | Role |
|---|---|
| `cc.ps1` | CLI entry (the only thing an agent needs to call) |
| `common.ps1` | install resolve + session + Invoke-CodesysOp |
| `online_ops.py` | IronPython backend (connect/read/write/...) |
| `user.txt.example` | credentials file template |
