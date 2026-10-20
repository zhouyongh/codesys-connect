# codesys-connect

Compact CODESYS online CLI for AI agents. One command, one line - no MCP JSON dumps.

MCP servers for CODESYS can do the same job (download / start / read / write). They work, but every call drags along tool schemas and verbose JSON replies, which burns tokens fast. This CLI keeps only the verbs and the values:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File cc.ps1 connect -Project D:\repo\projects\SmAxis3.project -UserFile user.txt
powershell -NoProfile -ExecutionPolicy Bypass -File cc.ps1 download
powershell -NoProfile -ExecutionPolicy Bypass -File cc.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File cc.ps1 write GVL.g_bEnable:=TRUE GVL.g_bMove:=TRUE
powershell -NoProfile -ExecutionPolicy Bypass -File cc.ps1 read GVL.g_bPoweredAll GVL.g_lrTargetPos
```

| Command | What it does | Typical output |
|---|---|---|
| `connect` / `status` / `disconnect` | Session, gateway, login | `OK connected=1` ... |
| `download` | Push program into the soft PLC | `OK downloaded=1` |
| `start` / `stop` | Run / stop the PLC | `OK started=1` |
| `read` / `write` | Symbol I/O | `GVL.x=12.5` / `OK written=N` |

Pairs with [codesys-sync](https://github.com/zhouyongh/codesys-sync): edit project source there, download and control here.

Built on the CODESYS Scripting Engine (`online` API). Windows + PowerShell 5.1. Agent skill included (`SKILL.md`).

## Quick start

1. Requirements: Windows, PowerShell 5.1+, a local CODESYS 3.5.x install (Scripting Engine included), and a running soft PLC (e.g. SoftMotion Win 64 / Control Win) whose user exists in the device user DB.
2. Clone this repo (or drop the folder into your agent's skills directory).
3. Copy `user.txt.example` to `user.txt`, fill in username/password, keep it local.
4. `cc.ps1 connect -Project <your .project> -UserFile user.txt` then `download` / `start` / `read` / `write`.
   - Real PLC: add `-Address <ip> -Port <port>` (default is local SoftMotion `127.0.0.1:11740`).
   - Non-`projects/<name>.project` layout: pass `-ProjectInfo <path to _project_info.txt or *_lastexport.txt>` if version auto-detect warns.

Any repo layout works. Login never auto-downloads: `-Change Never|Try|Keep` is honored as given; only `download` loads a program (`Force`).

Works out of the box with [codesys-sync](https://github.com/zhouyongh/codesys-sync) projects (`projects/` + `src/plc/` layout).

## Credentials

Not hardcoded. Use `-User` / `-Password`, or `-UserFile` (see `user.txt.example`). Values are stored in `%USERPROFILE%\.codesys-connect\session.txt` - keep that file local.

Full interface: [SKILL.md](SKILL.md).
