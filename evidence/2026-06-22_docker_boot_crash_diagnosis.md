# Docker Desktop boot-crash — root cause + factory reset (2026-06-22)

Machine: Windows 11 (10.0.26200), Docker Desktop 4.60.1, engine 29.2.0, WSL2.

## Symptom
"Docker Desktop" GUI verdwijnt ~5s na start. `com.docker.service` draait wel.
`docker version --format '{{.Server.Version}}'` faalt (pipe niet gevonden / 500).

## Investigation (systematic-debugging)
Logs gelezen: `%LOCALAPPDATA%\Docker\log\host\{com.docker.backend.exe,monitor,
com.docker.diagnose}.log`.

Bevindingen:
1. Backend bereikt `state:running`, GUI pollt `/diagnostics/status`, dan
   `eventErrorDialog` → user/auto klikt **Quit** → `exit status 150`. Geen stille crash;
   er kwam een error-dialog op.
2. Echte fatale regel in backend-log:
   ```
   backend crashed: starting services: initializing Inference manager:
   listening on unix://...\Docker\run\dockerInference:
   remove ...\dockerInference: The file cannot be accessed by the system.
   (listener: The filename, directory name, or volume label syntax is incorrect.)
   ```
3. `wsl -l -v`: `docker-desktop`-distro was leeg/kapot (na eerdere vhdx-delete) —
   `getpwuid(0) failed`, `execvpe(echo) failed: No such file or directory` → lege ext4.
   Dit was een SYMPTOOM, niet de hoofdoorzaak.
4. Na distro-unregister + relaunch: zelfde crash-klasse op een ANDERE socket:
   `initializing Secrets Engine: listening on ...\docker-secrets-engine\engine.sock`.

## Root cause
Docker crasht bij elke boot tijdens service-init op het **binden van een AF_UNIX
socket**. De socket-bestanden zijn **dangling reparse points / symlinks**:
- `attrib` → "The target of the symbolic link ... does not exist"
- `Get-Item` → Mode `la---`, LinkType/Target leeg, Attributes `ReparsePoint`
- Win32 file-API kan ze niet openen/lezen/verwijderen → **Error 1920**
  (ERROR_CANT_ACCESS_FILE).

5 geblokkeerde sockets gevonden: `run\dockerInference`,
`run.stale-*\{dockerInference,userAnalyticsOtlpHttp.sock}`,
`run_broken_*\dockerInference`, `docker-secrets-engine\engine.sock`.

## Wat NIET werkt (getest)
`Remove-Item -Force`, `cmd del /f`, `[IO.File]::Delete`, `fsutil reparsepoint delete`,
`rmdir` op het bestand — allemaal 1920. `wsl --shutdown` releaset niets.
`Remove-Item -Recurse` op de parent faalt ook (recursie opent de children).
`EnableInference=false` stond al correct in settings-store.json maar de Inference/
Secrets manager bindt de socket tóch (4.60.1).

## Fix: factory reset via CLI (handmatige state-wipe)
Geen reset-subcommand in admin/backend/diagnose/docker-desktop CLI in 4.60.1.
Handmatig (= wat factory-reset intern doet), met **rename i.p.v. delete** voor de
socket-mappen (rename opent de children niet):
1. Kill GUI/backend-procs op naam; `wsl --unregister docker-desktop`; `wsl --shutdown`.
2. `Rename-Item %LOCALAPPDATA%\Docker -> Docker.factoryreset-20260622`.
3. `Remove-Item %APPDATA%\Docker -Recurse` (clean, geen sockets).
4. `Rename-Item %LOCALAPPDATA%\docker-secrets-engine -> ...broken-20260622`.
5. Start "Docker Desktop.exe" → herprovisiont distro uit
   `resources\docker-desktop.iso` (724MB) + verse `\Docker` + verse sockets.

## Doel / verificatie
`docker version --format '{{.Server.Version}}'` geeft server-versie +
`docker run --rm hello-world` werkt.

## RESULTAAT — TIJDELIJK up (10:21), daarna recidief
```
docker version  -> client=29.2.0 server=29.2.0
wsl -l -v       -> docker-desktop  Running  2  (herprovisioned)
docker run --rm hello-world -> "Hello from Docker!"  exit=0
```
Engine kwam up na factory-reset, hello-world OK. MAAR bij de volgende boot crashte
Docker opnieuw — eerst weer op `dockerInference` (factory-reset had settings gereset
naar `EnableInference: true`), na `EnableInference=false`+`EnableDockerAI=false` sprong
de crash naar **`Secrets Engine` → docker-secrets-engine\engine.sock** (zelfde 1920).

## DEFINITIEVE DIAGNOSE (recidief-analyse)
Feature-uitzetten is dweilen: elke AF_UNIX-socket die Docker in `%LOCALAPPDATA%`
aanmaakt wordt een onbruikbare reparse-point. Crash verschuift gewoon naar de volgende
socket-bindende service in de init-keten (Inference → Secrets Engine → ...). Secrets
Engine heeft geen disable-toggle. Dit is een ENVIRONMENTAL/driver-oorzaak boven Docker:
iets mangelt AF_UNIX-socketcreatie op dit volume.

Verdachten (allen actief): **Windows Defender real-time + on-access + tamper-protection
AAN** (hoofdverdachte, klassieke oorzaak van "socket born inaccessible"), ProtonVPN
WireGuard service, Netbird. `fltmc filters` (minifilter-lijst) + Defender-exclusions
vereisen admin — niet uitgevoerd deze sessie.

## STATUS: gepauzeerd (gebruikerskeuze)
Docker met rust gelaten tot er admin-tijd is. Notebook draait zonder lokale Docker:
edge-deploy-cel heeft guard (`docker info` returncode → skip). Cloud-deploy (Render)
werkt onafhankelijk. Alle Docker GUI/backend-procs gestopt; `com.docker.service` blijft
idle als Windows-service.

## Volgende sessie (met admin PowerShell)
1. `fltmc filters` → zie welke minifilter `\Docker\run` socket-IO hookt.
2. Defender-exclusion: `Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Docker",
   "$env:LOCALAPPDATA\docker-secrets-engine"` + exclusion voor com.docker.backend.exe.
3. Test eventueel on-access kort uit (`Set-MpPreference -DisableRealtimeMonitoring $true`)
   → launch Docker → kijk of socket clean bindt. Daarna weer aan.
4. Alternatief: Hyper-V backend i.p.v. WSL2 (omzeilt WSL↔Win9p socket-bridge), of
   Docker-versie wisselen (4.60.1 AF_UNIX-cleanup-bug).

## Restanten
Geïsoleerde husks blijven staan (onverwijderbaar via Win32, maar buiten Docker's
actieve paden, dus genegeerd):
- `%LOCALAPPDATA%\Docker.factoryreset-20260622\` (bevat dode reparse-sockets)
- `%LOCALAPPDATA%\docker-secrets-engine.broken-20260622\`
Op te ruimen via admin/`chkdsk` of bij volgende Windows-reset; niet nodig voor werking.
