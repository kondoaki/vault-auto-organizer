# Migrating an Obsidian Vault off iCloud to Local + Syncthing + Git + iOS

End-to-end runbook for moving an Obsidian Vault out of iCloud Drive onto a
plain local directory, syncing it across machines via Syncthing, layering
Git history on top, and folding in iPhone/iPad through SyncTrain.

## Phase overview

| Phase | What it covers |
|-------|----------------|
| **Phase 0** | Migrate iCloud Vault → local `~/Vault` via rsync |
| **Phase 1** | Install Syncthing on each Mac (laptop / always-on) |
| **Phase 2** | Pair devices and configure the shared folder |
| **Phase 3** | Add a Git history layer (GitHub or self-hosted) |
| **Phase 4** | Add iOS devices (iPhone / iPad) via SyncTrain |

Phase 0 is a one-time migration. Phases 1–4 are also useful when adding
new devices or rebuilding a machine.

---

## Phase 0: iCloud → local migration

### Plan

| Item | Value |
|---|---|
| **Source** | `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>` |
| **Destination** | `~/Vault` |
| **Method** | `rsync` copy → verify → delete source (two-stage) |
| **Required tool** | Homebrew `rsync` v3+ (must support `--iconv`) |
| **Expected duration** | Depends on Vault size (≈5–30 min for several GB) |
| **Rollback** | Keep the source side around for 1–2 weeks for instant recovery |

### Why migrate

- Escape iCloud's sync delays, duplicate-file behavior, and dataless
  placeholder pitfalls (placeholders race with `git add` and produce
  `Resource deadlock avoided` errors under launchd jobs)
- Get consistent, immediate filesystem semantics
- Set the stage for Syncthing + Git workflows below

---

### 0-1. Install Homebrew rsync (required)

macOS ships an Apple-built `openrsync` whose handling of non-ASCII
filenames is broken — it aborts mid-transfer with `Illegal byte sequence`
on names that need NFD↔NFC normalization (any non-ASCII characters,
e.g. accented Latin, CJK, emoji-bearing names). Use upstream rsync v3
from Homebrew instead.

#### Check the current rsync

```bash
which rsync
rsync --version | head -3
```

- `/opt/homebrew/bin/rsync` and `version 3.x.x` → ✅ skip ahead
- `/usr/bin/rsync` or `openrsync` in the version string → run the next steps

#### Install Homebrew rsync

```bash
brew install rsync

# Confirm install location
brew --prefix rsync
ls -la "$(brew --prefix rsync)/bin/rsync"
```

#### Verify PATH ordering

If Homebrew is set up correctly, `/opt/homebrew/bin` should be ahead of
`/usr/bin` in `PATH`:

```bash
which rsync
# → /opt/homebrew/bin/rsync

rsync --version | head -1
# → rsync  version 3.x.x  protocol version 31
```

#### If PATH isn't picking up brew rsync

```bash
# Check whether brew shellenv is wired up
grep "brew shellenv" ~/.zprofile

# If not, add it (Apple Silicon)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile

# Reload
exec zsh -l
```

##### Common gotcha

Integrated terminals in VS Code, Cursor, tmux, etc. sometimes start as
non-login shells and skip `.zprofile`. As a belt-and-suspenders, add the
same wiring to `.zshrc`:

```bash
# Top of .zshrc — safe to run multiple times
if [[ -x /opt/homebrew/bin/brew ]] && [[ ":$PATH:" != *":/opt/homebrew/bin:"* ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
```

#### Confirm `--iconv` is available

```bash
rsync --help 2>&1 | grep iconv
# → --iconv=CONVERT_SPEC ...
```

> `--iconv=utf-8-mac,utf-8` only exists in upstream rsync v3. Without it,
> rsync will fail with `Illegal byte sequence` on any filename that uses
> non-ASCII characters.

### 0-2. Stash the long paths in shell variables

Typing the source path repeatedly invites mistakes. Define them once:

```bash
SRC="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>"
DST="$HOME/Vault"

# Sanity check
ls -la "$SRC" | head
echo "$DST"
```

> The literal `~` characters inside `iCloud~md~obsidian` are part of the
> directory name; quoting the variable is enough, no escaping needed.

### 0-3. Quit Obsidian completely

Quit via the menu (`Obsidian → Quit Obsidian` / `Cmd + Q`) and confirm
nothing is left in the Dock:

```bash
pgrep -lf Obsidian
# Empty output = ok
```

### 0-4. Force iCloud to materialize every file

If "Optimize Mac Storage" is on, files marked with the cloud icon (☁️) are
dataless placeholders — the bytes live in the cloud, not on disk. Pull
them all down before moving:

```bash
brctl download "$SRC"

# Visually verify in Finder that no cloud icons remain
open "$SRC"
```

> `brctl` is shipped with macOS. The command blocks until the download
> finishes and can take several minutes for large Vaults.

### 0-5. Record current size and file count

These numbers are the verification baseline:

```bash
du -sh "$SRC"
find "$SRC" -type f | wc -l
find "$SRC" -type f -not -path '*/\.git/*' | wc -l
```

Note them down:

```
Size:  ____ GB
Files: ____
```

### 0-6. Take a backup (strongly recommended)

```bash
cd /tmp
zip -r "vault-backup-$(date +%Y%m%d-%H%M%S).zip" "$SRC"
ls -lh /tmp/vault-backup-*.zip
```

### 0-7. Confirm the destination is clean

`rsync` will create `~/Vault` if it doesn't exist:

```bash
ls -la "$DST" 2>/dev/null && echo "⚠️  exists, inspect first" || echo "✅ clean"
```

### 0-8. Dry run

Verify what would be transferred without writing anything:

```bash
rsync -avhn --progress --iconv=utf-8-mac,utf-8 "$SRC/" "$DST/"
```

Sanity checks:
- `.obsidian/` is included
- `.trash/` is included if it exists
- Attachments (images, PDFs) are present
- No surprise garbage (`.DS_Store` clusters, etc.)

> **Trailing slash on both sides is mandatory.** Drop one and you'll end
> up with `~/Vault/<VaultName>/` (a nested directory).

> **What `--iconv=utf-8-mac,utf-8` does**: macOS stores filenames in
> NFD (decomposed) form on its native filesystems; most other platforms
> and many tools assume NFC (composed). This flag converts NFD↔NFC during
> transfer. Required whenever filenames contain non-ASCII characters.
> Syntax is `<sender>,<receiver>`.

### 0-9. Real run

```bash
rsync -avh --progress --iconv=utf-8-mac,utf-8 "$SRC/" "$DST/"
```

| Flag | Meaning |
|---|---|
| `-a` | Archive mode (preserve perms, timestamps, symlinks) |
| `-v` | Verbose (print transferred file names) |
| `-h` | Human-readable sizes |
| `--progress` | Per-file progress meter |
| `--iconv=utf-8-mac,utf-8` | NFD↔NFC normalization for non-ASCII filenames |

Final summary should look like:

```
sent xxx,xxx,xxx bytes  received xxx bytes  xx,xxx,xxx.xx bytes/sec
total size is xxx,xxx,xxx  speedup is 1.00
```

### 0-10. Verify

#### Re-run rsync and expect zero diff

```bash
rsync -avhn --progress --iconv=utf-8-mac,utf-8 "$SRC/" "$DST/"
```

The output should list **no files** — only the summary line.

#### Compare size and file count

```bash
echo "=== Source ==="
du -sh "$SRC"
find "$SRC" -type f | wc -l

echo "=== Destination ==="
du -sh "$DST"
find "$DST" -type f | wc -l
```

A 1–2 file delta is normal (e.g. macOS-injected `.DS_Store`).

#### Check critical files exist

```bash
ls -la "$DST/.obsidian/" | head
ls "$DST/.obsidian/plugins/" 2>/dev/null
ls "$DST/.obsidian/themes/" 2>/dev/null
```

### 0-11. Open the new Vault in Obsidian

1. Launch Obsidian
2. Click the **Vault switcher** (lower-left) → **Open folder as vault**
3. Pick `~/Vault`
4. Smoke-test:
   - [ ] Note list looks right
   - [ ] Graph view renders without broken links
   - [ ] Plugin list matches (Settings → Community plugins)
   - [ ] Theme is applied
   - [ ] Hotkeys work
   - [ ] Attachments (images, PDFs) display
   - [ ] Search (`Cmd + Shift + F`) works

### 0-12. Remove the old Vault from Obsidian's list (don't delete the folder yet)

In the Vault switcher, **Remove from list** the old iCloud entry. **Do not
delete the folder itself yet** — that's the rollback path.

### 0-13. Parallel period (1–2 weeks)

Run on the new Vault while the old one stays available as fallback.

#### During this period

- [ ] Use the new Vault daily, watch for missing data or breakage
- [ ] Set up Syncthing (**Phase 1**)
- [ ] Re-check Obsidian on iPhone / iPad

#### Don't do these

- ❌ Edit the old iCloud Vault (the two histories will diverge)
- ❌ Delete the old folder

### 0-14. Delete the old Vault (after the parallel period)

After 1–2 weeks of clean operation:

```bash
# Last look
ls -la "$SRC"

# Delete
rm -rf "$SRC"

# Confirm it's gone from iCloud
ls "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/"
```

> If you keep the `iCloud~md~obsidian` directory itself, you can return
> to iCloud-based Vaults later if needed.

### 0-15. Post-migration housekeeping

#### Confirm "Documents sync" is off in iCloud Drive

`~/Vault` is outside `Documents`, so this is normally moot — but worth
verifying: System Settings → Apple ID → iCloud → iCloud Drive →
"Sync this Mac" → Documents folder checkbox.

#### Add shell aliases

In `~/.zshrc`:

```bash
# Obsidian Vault
alias vault='cd ~/Vault'
alias ovault='open -a Obsidian ~/Vault'
```

Reload:

```bash
source ~/.zshrc
```

#### Optional: exclude from Time Machine

If Git is your history-of-record, you can skip Time Machine for the Vault:

```bash
sudo tmutil addexclusion ~/Vault
```

> If you want belt-and-suspenders backups, leave it included.

### Phase 0 troubleshooting

#### Notes don't appear when opening the Vault

Check `.obsidian/` was copied:

```bash
ls -la ~/Vault/.obsidian/
```

#### Plugins disappeared

```bash
ls ~/Vault/.obsidian/plugins/
```

#### Graph view shows lots of broken links

Attachments may have been skipped:

```bash
find "$SRC" \( -name "*.png" -o -name "*.jpg" -o -name "*.pdf" \) | wc -l
find "$DST" \( -name "*.png" -o -name "*.jpg" -o -name "*.pdf" \) | wc -l
```

#### `Illegal byte sequence` / `mkstempat` errors during rsync

```
rsync: error: mkstempat: '...': Illegal byte sequence
rsync: error: utimensat (2): No such file or directory
```

You're running Apple's `openrsync` or rsync 2.6.9 — neither handles
NFD/NFC conversion correctly.

Fix:
1. `which rsync` — if it's `/usr/bin/rsync`, go back to **0-1**
2. Make sure `--iconv=utf-8-mac,utf-8` is on the command line
3. Resume — rsync is incremental, so a re-run picks up where it stopped

```bash
/opt/homebrew/bin/rsync -avh --progress \
  --iconv=utf-8-mac,utf-8 \
  "$SRC/" "$DST/"
```

#### `Permission denied` during rsync

macOS Full Disk Access. System Settings → Privacy & Security → Full Disk
Access → add your terminal app (Terminal.app, iTerm2, WezTerm, etc.).

#### `~/Vault` already exists

Inspect, then decide:

```bash
ls -la ~/Vault/
du -sh ~/Vault/
```

If it's not what you want, rename it out of the way:

```bash
mv ~/Vault ~/Vault.bak.$(date +%Y%m%d)
```

### Phase 0 one-shot snippet

```bash
# === 0. rsync verification / install ===
which rsync                                        # expect /opt/homebrew/bin/rsync
rsync --version | head -1                          # expect 3.x.x
# If not:
# brew install rsync && exec zsh -l

# === Vars ===
SRC="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/<VaultName>"
DST="$HOME/Vault"

# === Pre-flight ===
pgrep -lf Obsidian   # should be empty
brctl download "$SRC"
du -sh "$SRC"
find "$SRC" -type f | wc -l

# === Dry run ===
rsync -avhn --progress --iconv=utf-8-mac,utf-8 "$SRC/" "$DST/"

# === Real run ===
rsync -avh --progress --iconv=utf-8-mac,utf-8 "$SRC/" "$DST/"

# === Verify ===
rsync -avhn --progress --iconv=utf-8-mac,utf-8 "$SRC/" "$DST/"   # expect no diff
du -sh "$DST"
find "$DST" -type f | wc -l
ls -la "$DST/.obsidian/" | head
```

---

## Phase 1: Install Syncthing

### Plan

| Role | Device | Install method | Startup |
|------|--------|----------------|---------|
| Laptop / mobile | Travel Mac | Cask (`syncthing-app`, GUI) | Login item via app preferences |
| Always-on | Desktop, headless Mac | Formula (`syncthing`, CLI only) | Custom LaunchAgent (do **not** use `brew services`) |

Both options run the same Syncthing binary; only the GUI wrapper and
launch mechanism differ. **Do not run both on the same Mac** — they fight
over the config directory and port 8384.

> **Why not `brew services` on Apple Silicon Macs**: the auto-generated
> plist omits a `HOME` environment variable, so syncthing panics with
> `$HOME is not defined` on startup. See the always-on section below.

---

### Laptop / mobile Mac (Cask)

For day-to-day machines where you want a tray icon and the Web GUI ready.

#### Install

```bash
# Remove formula version if it's already there (can't coexist)
brew services stop syncthing 2>/dev/null
brew uninstall syncthing 2>/dev/null

# Install Cask
brew install --cask syncthing-app

# Launch
open -a Syncthing
```

A menu-bar icon appears and the Web GUI opens at `http://127.0.0.1:8384`.

#### Enable login startup

Menu-bar Syncthing icon → **Preferences** → **Start at login**.

#### Bundled CLI binary

The Cask ships a CLI inside the app bundle:

```
/Applications/Syncthing.app/Contents/Resources/syncthing/syncthing
```

Symlink it onto `PATH` if you want `syncthing cli` subcommands:

```bash
# Apple Silicon
ln -s /Applications/Syncthing.app/Contents/Resources/syncthing/syncthing /opt/homebrew/bin/syncthing

# Intel
ln -s /Applications/Syncthing.app/Contents/Resources/syncthing/syncthing /usr/local/bin/syncthing
```

The CLI just talks to the local API; it doesn't spawn another daemon.

#### Updates

Sparkle auto-updates is on by default. Manual check: tray icon →
**About** → **Check for Updates**.

---

### Always-on Mac (formula + custom LaunchAgent)

Headless / always-on machine that acts as the relay node. Ideal alongside
Tailscale + SSH.

> `brew services start syncthing` on Apple Silicon Macs panics at startup
> with `panic: Failed to get user home dir` because the auto-generated
> plist omits `HOME` from `EnvironmentVariables`. This section uses a
> hand-written plist loaded directly with `launchctl`.

#### Install

```bash
# Remove Cask if it's there (can't coexist)
brew uninstall --cask syncthing-app 2>/dev/null

# Clear any brew services state
brew services stop syncthing 2>/dev/null
sudo brew services stop syncthing 2>/dev/null
launchctl bootout gui/$(id -u)/homebrew.mxcl.syncthing 2>/dev/null
sudo launchctl bootout system/homebrew.mxcl.syncthing 2>/dev/null
rm -f ~/Library/LaunchAgents/homebrew.mxcl.syncthing.plist
sudo rm -f /Library/LaunchDaemons/homebrew.mxcl.syncthing.plist 2>/dev/null

# Install formula
brew install syncthing

# Verify
ls -la /opt/homebrew/opt/syncthing/bin/syncthing
/opt/homebrew/opt/syncthing/bin/syncthing --version
```

#### Why we avoid `brew services`

`brew services start syncthing` produces:

- An auto-generated plist without `HOME` in `EnvironmentVariables`
- A syncthing process launched via `launchctl` with no `$HOME` →
  panic during init
- `KeepAlive=true` then loops the panicking process, ballooning the log
- Editing the plist by hand is futile: the next `brew services start`
  rewrites it

Setting `HOME` in `.zprofile` / `.zshrc` doesn't help because launchd
doesn't go through a shell. **The only reliable fix is to put `HOME` in
the plist's `EnvironmentVariables`** — which means owning the plist
yourself.

#### Create the log directory

```bash
mkdir -p ~/Library/Logs/syncthing
```

#### Hand-written plist

Replace `<rdn>` with your reverse-DNS prefix (e.g. `com.example`) — any
unique label works as long as it doesn't clash with `homebrew.mxcl.*`.

```bash
RDN="<rdn>"   # e.g. com.example

cat > ~/Library/LaunchAgents/${RDN}.syncthing.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${RDN}.syncthing</string>

    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/opt/syncthing/bin/syncthing</string>
        <string>--no-browser</string>
        <string>--no-restart</string>
        <string>--logflags=0</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/syncthing/syncthing.log</string>

    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/syncthing/syncthing.log</string>
</dict>
</plist>
EOF
```

The heredoc expands `${HOME}` and `${RDN}` to literal strings, so the
written plist contains no shell variables.

#### Design notes

- **Custom Label prefix** avoids colliding with `homebrew.mxcl.*` if you
  ever re-enable `brew services` for something else
- **Plist lives under `~/Library/LaunchAgents/`** — user-scope LaunchAgent
- **Binary path points into the brew prefix** so `brew upgrade syncthing`
  takes effect on next restart
- **Logs go to `~/Library/Logs/syncthing/`** instead of brew's
  `/opt/homebrew/var/log/`, so Console.app surfaces them

#### Validate and load

```bash
# Syntax check
plutil -lint ~/Library/LaunchAgents/${RDN}.syncthing.plist

# Sanity check the rendered output (HOME should be a literal path)
cat ~/Library/LaunchAgents/${RDN}.syncthing.plist

# Load
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/${RDN}.syncthing.plist

# Verify
sleep 3
pgrep -lf syncthing                                  # should show a PID
launchctl list | grep "${RDN}.syncthing"             # PID is numeric, not "-"
curl -sI http://127.0.0.1:8384 | head -1             # HTTP/1.1 200 OK
tail -30 ~/Library/Logs/syncthing/syncthing.log      # startup log
```

A clean startup log contains a line like `INFO: syncthing v...`.

#### Operational aliases (`.zshrc`)

Put these in `.zshrc` (not `.zprofile`) so they're available in editor
integrated terminals:

```bash
RDN="<rdn>"   # same value used above
alias st-start="launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/${RDN}.syncthing.plist"
alias st-stop="launchctl bootout gui/\$(id -u)/${RDN}.syncthing"
alias st-restart="launchctl kickstart -k gui/\$(id -u)/${RDN}.syncthing"
alias st-status="launchctl list | grep ${RDN}.syncthing"
alias st-log='tail -f ~/Library/Logs/syncthing/syncthing.log'
alias st-gui='open http://127.0.0.1:8384'
```

Reload:

```bash
source ~/.zshrc
```

#### Optional: LaunchDaemon variant

If you need syncthing running before any user logs in, install the plist
as a system-wide LaunchDaemon. Note that the config directory becomes
`/var/root/Library/Application Support/Syncthing/` — your user-scope
config does **not** carry over.

```bash
# Copy plist to system location
sudo cp ~/Library/LaunchAgents/${RDN}.syncthing.plist /Library/LaunchDaemons/

# Take ownership as root
sudo chown root:wheel /Library/LaunchDaemons/${RDN}.syncthing.plist

# Rewrite HOME and log paths to /var/root
sudo /usr/bin/python3 - <<PYEOF
import plistlib
path = '/Library/LaunchDaemons/${RDN}.syncthing.plist'
with open(path, 'rb') as f:
    plist = plistlib.load(f)
plist['EnvironmentVariables']['HOME'] = '/var/root'
plist['StandardOutPath'] = '/var/root/Library/Logs/syncthing/syncthing.log'
plist['StandardErrorPath'] = '/var/root/Library/Logs/syncthing/syncthing.log'
with open(path, 'wb') as f:
    plistlib.dump(plist, f)
PYEOF

# Log dir
sudo mkdir -p /var/root/Library/Logs/syncthing

# Stop the user-scope agent first
launchctl bootout gui/$(id -u)/${RDN}.syncthing 2>/dev/null

# Load as system daemon
sudo launchctl bootstrap system /Library/LaunchDaemons/${RDN}.syncthing.plist
```

For most setups the LaunchAgent variant is enough; only switch when you
genuinely need pre-login startup.

#### Web GUI access from outside the host

By default the GUI only binds to `127.0.0.1:8384`.

To reach it over Tailscale, edit the config:

```bash
# LaunchAgent
~/Library/Application\ Support/Syncthing/config.xml

# LaunchDaemon
/var/root/Library/Application\ Support/Syncthing/config.xml
```

Change the `<gui>` `<address>` to:

```xml
<address>0.0.0.0:8384</address>
```

**Set a GUI username and password before exposing it**, then restart:

```bash
st-restart
# LaunchDaemon
sudo launchctl kickstart -k system/${RDN}.syncthing
```

If you're staying inside Tailscale, binding to the `tailscale0` interface
IP rather than `0.0.0.0` is safer.

#### Updates

```bash
# New binary
brew upgrade syncthing

# Restart so the new binary is picked up
st-restart
```

The plist is yours, so brew won't overwrite it. Optional helper:

```bash
syncthing-upgrade() {
    brew upgrade syncthing && st-restart
}
```

#### Troubleshooting: doesn't start

```bash
# Process status — PID shown as "-" means the last start failed
launchctl list | grep ${RDN}.syncthing
# e.g. "-  78  ${RDN}.syncthing"  → exit code 78 = config error

# syncthing log
tail -100 ~/Library/Logs/syncthing/syncthing.log

# launchd log
log show --predicate 'subsystem == "com.apple.xpc.launchd"' --last 5m | grep ${RDN}

# Plist syntax
plutil -lint ~/Library/LaunchAgents/${RDN}.syncthing.plist

# Reproduce manually
/opt/homebrew/opt/syncthing/bin/syncthing --no-browser --no-restart
```

A `$HOME is not defined` panic means the plist's `EnvironmentVariables`
section didn't end up with a literal `HOME` value. Check the rendered
file.

---

## Phase 2: Pair devices and configure shared folders

**Drive folder sharing from the always-on Mac.** Treat it as the source of
truth and the backup hub; the laptop is the consumer.

### Step 1: register devices on each side

With Syncthing running on both Macs:

1. On each device's Web GUI, **Actions → Show ID** and copy the Device ID
2. On the other device, **Add Remote Device**, paste the ID, give it a
   readable name
3. When the laptop registers the always-on Mac, tick **Introducer** under
   **Advanced** so future devices auto-pair via the hub
4. Once both sides accept, the connection turns green (`Connected`)

#### With Tailscale

If you're on a Tailnet, hard-coding the Tailscale IP into **Addresses**
is the most reliable path, e.g.:

```
tcp://100.x.x.x:22000
```

### Step 2: add the folder on the always-on Mac (source)

Web GUI → **Add Folder**:

1. **General**:
   - **Folder Label**: `Obsidian Vault` (anything readable)
   - **Folder ID**: keep the auto-generated value
   - **Folder Path**: existing Vault path on this machine, e.g. `~/Vault`
2. **Sharing**: tick the laptop
3. **File Versioning**:
   - **Type**: `Simple File Versioning`
   - **Keep Versions**: `30` (keeps 30 historical revisions per file)
   - Older revisions live in `.stversions/` at the Vault root
4. **Advanced**:
   - **Folder Type**: `Send & Receive`
   - **Ignore Permissions**: ON
5. **Save**

### Step 3: accept the share on the laptop (destination)

Saving on the source side fires a share notification on the laptop:

1. Click **Add** in the notification
2. **Important**: change **Folder Path** to the existing Vault location
   on this Mac. The default (`~/Sync/<folder-name>`) is **not** what you
   want.
3. **File Versioning**: **No File Versioning** (keep versioning
   centralized on the always-on Mac)
4. **Advanced**:
   - **Folder Type**: `Send & Receive`
   - **Ignore Permissions**: ON
5. **Save**

### Step 4: confirm sync

Both sides should report `Up to Date`, and **Shared With** lists the
peer's name.

### Why this versioning split

| Role | Device | File Versioning |
|------|--------|----------------|
| Source / backup hub | Always-on Mac | `Simple File Versioning` × 30 |
| Consumer | Laptop | None |

- A delete on the laptop is recoverable from the always-on Mac's
  `.stversions/`
- Skipping versioning on the laptop saves disk and avoids two recovery
  surfaces
- `.stversions/` lives at the Vault root on the always-on Mac. Add it to
  Obsidian's **Excluded files** under settings if you don't want it in
  search results

---

## Phase 2 supplement: Vault-specific Syncthing config

### Per-machine `.stignore`

Syncthing intentionally does **not** sync `.stignore`. Create one in the
Vault root on every machine:

```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/workspaces.json
.trash
.DS_Store
.git
.git/**
*.sync-conflict-*
.stversions
```

- `workspace.json` family — per-device Obsidian layout, must not sync.
  Plugin settings (`.obsidian/plugins/`) are usually fine to sync.
- `.git` and `.git/**` — never sync the Git directory. Concurrent writes
  by Syncthing and Git into `objects/` or `index` will corrupt the repo.
  Keep Git history flowing through a real Git remote (next phase).
- `*.sync-conflict-*` — defensive: stops conflict files from breeding
  across devices if they ever appear
- `.stversions` — versioning directory on the source Mac, must not sync

To copy the file across machines, scp is fine:

```bash
scp ~/Vault/.stignore <user>@<other-mac>:~/Vault/.stignore
```

### Editing `.stignore` from the Web GUI

Same effect without touching files:

1. Folder card → **Edit**
2. **Ignore Patterns** tab
3. Paste the rules → **Save**

Useful for editing remote machines' rules without SSH.

### Operational notes

- Always start the first sync from the side that **has** the data. If you
  start from the empty side, Syncthing will happily delete the populated
  side
- Syncthing is a sync tool, not a backup tool. Pair it with Time Machine
  or a Git remote
- Moving the Vault directory? Pause the folder in Syncthing first

---

## Phase 3: Git history layer (per-machine repos)

Files sync via Syncthing in real time; commit history syncs via a Git
remote. Both Macs can `commit` / `diff` / `log` independently, so the
laptop has full history offline.

```
[ Laptop ]                          [ Always-on Mac ]
  Vault/                              Vault/
  ├── *.md  ←─── Syncthing ────→    ├── *.md
  ├── .obsidian/                      ├── .obsidian/
  └── .git/  (per-machine)            └── .git/  (per-machine)
       │                                   │
       └────── Git remote (GitHub /  ──────┘
              GitHub Enterprise / etc.)
                   (history of record)
```

### Step 1: create an empty Git remote

On GitHub, GitHub Enterprise, Gitea, or whichever forge you use, create
a new private repo, e.g. `<owner>/obsidian-vault`.

**Don't initialize with `.gitignore` or `README`** — that creates a
divergent root commit you'd have to reconcile later.

### Step 2: initialize Git on the always-on Mac and push

```bash
cd ~/Vault

# Init
git init -b main

# .gitignore
cat > .gitignore <<'EOF'
# macOS
.DS_Store

# Obsidian workspace files
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/workspaces.json
.obsidian/cache

# Trash
.trash/

# Syncthing artifacts
.stfolder/
.stversions/
*.sync-conflict-*

# Syncthing ignore files (per-machine)
.stignore
.stignore-local
EOF

# First commit
git add .
git commit -m "Initial commit"

# Wire up remote and push
git remote add origin git@<git-host>:<owner>/obsidian-vault.git
git push -u origin main
```

### Step 3: wait for `.gitignore` to land on the laptop

`.gitignore` is just a regular file, so Syncthing carries it. Confirm
`Up to Date` on the laptop side first.

### Step 4: attach `.git` on the laptop without re-cloning

The Vault is already on disk via Syncthing — don't `git clone`. Initialize
in place and reset to the remote:

```bash
cd ~/Vault

git init -b main
git remote add origin git@<git-host>:<owner>/obsidian-vault.git
git fetch origin

# No --hard: working tree belongs to Syncthing
git reset origin/main

git branch --set-upstream-to=origin/main main

# Status check
git status
```

Possible outcomes:

- `nothing to commit, working tree clean` → done
- `modified: ...` → Syncthing-side and Git-side differ; review before
  acting

If Syncthing's copy is the truth:

```bash
git diff
git add .
git commit -m "Sync working tree state"
git push
```

If the remote is the truth (destructive — be sure):

```bash
git checkout -- .
```

### Daily flow

#### Always-on Mac (primary)

```bash
cd ~/Vault
git add .
git commit -m "Update notes"
git push
```

#### Laptop (secondary)

```bash
# Read history
git log --oneline -20
git diff HEAD~1

# Committing? Always pull → commit → push in one go
git pull --rebase
git add .
git commit -m "External edits"
git push
```

### Operational notes

#### Push immediately after committing on the laptop

If you commit on the laptop and walk away, Syncthing will deliver your
changes to the always-on Mac, where another commit may form on top of
yours — and now history has diverged across machines. Habit: commit and
push as one sequence.

#### Pause Syncthing during destructive Git operations

`rebase`, `merge`, `reset --hard`, etc. — pause Syncthing first
(**Pause All** in the Web GUI). Routine `add` / `commit` / `push` is fine
without pausing.

#### Files that arrive via Syncthing show up as Git changes

Expected:

```bash
git status
# modified: notes/today.md   ← arrived from the laptop via Syncthing
```

Just `git add . && git commit` on the always-on Mac and push. Laptop-origin
edits can land in the remote either from the laptop or from the always-on
Mac — both work.

---

## Phase 4: iOS via SyncTrain

Sync the Vault to iPhone / iPad in near-real time. SyncTrain is an
open-source SwiftUI Syncthing client.

### Plan

| Item | Value |
|------|-------|
| Devices | iPhone + iPad |
| Sync scope | Full Vault (delta sync, bit-identical to Mac) |
| App | SyncTrain (free, open source) |
| Peer | Always-on Mac (relay), reached via Tailscale |
| Trigger | Apple Shortcut to nudge SyncTrain on Obsidian launch |

### Topology

```
[ iPhone (SyncTrain) ]   [ iPad (SyncTrain) ]
       ↑↓                       ↑↓
        Tailscale + Syncthing
              ↓
[ Always-on Mac (relay, 24/7) ]
              ↑↓
[ Laptop (Cask Syncthing) ]
```

### Prerequisites

- Phases 1–3 are done
- Always-on Mac's Syncthing is running 24/7
- iPhone and iPad have Tailscale installed and signed in

### iOS background limits (important)

iOS aggressively suspends background apps for power. Even SyncTrain
**cannot stay in real-time sync indefinitely** in the background. To
mitigate:

- Use Apple Shortcuts to nudge SyncTrain when Obsidian launches
- While SyncTrain is foreground, sync runs normally — long writing
  sessions are fine
- "iPhone is up-to-date the moment I open it on the go" requires the
  Shortcut automation below

### 4-1. Install SyncTrain

App Store → search **SyncTrain** → install on iPhone and iPad.

> Free; basic functionality is unrestricted (no Mobius-Sync-style 20MB
> cap). In-app tipping for support is available.

### 4-2. First-run setup (iPhone / iPad)

1. Launch SyncTrain
2. Grant network access on first launch
3. Note the Device ID under **This Device** (you'll register it on the
   always-on Mac)
4. Rename the device for clarity, e.g. `iphone-<owner>`, `ipad-<owner>`

### 4-3. Register iOS devices on the always-on Mac

Web GUI on the always-on Mac (`http://127.0.0.1:8384` or via Tailscale):

1. **Add Remote Device**
2. Paste the iPhone's Device ID, set a readable name
3. **Advanced**:
   - Leave **Addresses** as `dynamic` (Tailscale resolves), **or**
   - Hard-code the Tailscale IP: `tcp://100.x.x.x:22000`
4. **Save**

Repeat for the iPad.

### 4-4. Register the always-on Mac on each iOS device

In SyncTrain on the iPhone:

1. **Devices** tab → `+` → paste the always-on Mac's Device ID
2. Name it, e.g. `home-mac`
3. **Strongly recommended**: hard-code the Tailscale IP:
   - `tcp://100.x.x.x:22000`
4. **Save**

Same on iPad. Once both sides accept, **Devices** shows `Connected`
(green).

### 4-5. Share the Vault folder from the always-on Mac

Web GUI on the always-on Mac:

1. Vault folder → **Edit** → **Sharing**
2. Tick the iPhone and the iPad
3. **Save**

Both iOS devices receive a share request.

### 4-6. Accept the folder on each iOS device

In SyncTrain on the iPhone:

1. **Folders** tab → tap the incoming Vault folder → **Accept**
2. **Important**: choose where to store it:
   - **Under `On My iPhone`**: visible to other apps (Obsidian) via Files
   - **Inside SyncTrain's sandbox**: invisible to other apps (Obsidian
     can't open it)
   → Pick **`On My iPhone`**. The path will be
   `Files → On My iPhone → SyncTrain → Vault`.
3. When asked about selective sync, choose **Sync everything** if you
   want a full mirror
4. Sync starts

Same on iPad (use `On My iPad`).

> **Storage**: a large Vault may strain iPhone storage. Section 4-9
> covers selective sync.

### 4-7. Open the Vault in iOS Obsidian

#### iPhone / iPad

1. Install **Obsidian** from the App Store if you haven't
2. Launch Obsidian
3. Pick **Open folder as vault** (not Create new vault)
4. Browse → `On My iPhone` (or `On My iPad`) → `SyncTrain` → `Vault`

#### If Obsidian doesn't see the SyncTrain folder

iOS File Provider sometimes doesn't surface the folder. Fix:

1. SyncTrain → **Settings** → **Show Files in Files app**: ON
2. iOS Files app → **Browse** → top-right `...` → **Edit** → make sure
   **On My iPhone** is checked
3. Retry **Open folder as vault** in Obsidian

### 4-8. Apple Shortcut: auto-sync on Obsidian launch

Counter the iOS background limit by triggering SyncTrain when Obsidian
opens.

#### Build the Shortcut

1. iPhone / iPad → **Shortcuts** app
2. `+` → **Add Action**
3. Search `SyncTrain`
4. Add **Photon** (SyncTrain's sync action)
5. Parameters:
   - **Folder**: pick the Vault
   - **Direction**: `Both`
   - **Wait until completion**: ON

#### Auto-run on Obsidian launch

1. Shortcuts → **Automation** tab → `+`
2. **When opening App** → select **Obsidian**
3. Run the Shortcut you just made
4. **Run Immediately**: ON (no confirmation prompt)

Now every time you open Obsidian, SyncTrain wakes up and syncs.

#### Optional: home-screen "Sync now" button

Add the same Shortcut to the home screen. Tap before heading out to grab
the latest.

### 4-9. Selective sync (optional, for tight storage)

If iOS storage is tight:

1. SyncTrain → folder → **Selective Sync**
2. Pick the subfolders / files you want local
3. Everything else shows as a cloud icon in Files; tap to fetch on demand

> Selective sync breaks Obsidian's graph view for non-local notes (links
> point to files that aren't on this device). Trade-off: storage vs.
> completeness.

### 4-10. `.stignore` on iOS

SyncTrain doesn't auto-sync `.stignore` either. Set it via the Web GUI on
the iOS device:

1. On the always-on Mac, copy the Vault folder's `Ignore Patterns`
2. In SyncTrain, open the same folder's settings
3. Paste the same lines into **Ignore Patterns**

Same content as Phase 2:

```
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/workspaces.json
.trash
.DS_Store
.git
.git/**
*.sync-conflict-*
.stversions
```

> `.obsidian/workspace-mobile.json` is generated on iOS — must be
> ignored, otherwise iOS and Mac will fight over it.

### 4-11. Smoke test

1. On the always-on Mac, create `test-ios.md` with some content
2. Open SyncTrain on the iPhone → sync runs
3. Open Obsidian on the iPhone → confirm `test-ios.md` is visible
4. Edit a different note in iOS Obsidian → save
5. Foreground SyncTrain → wait for sync to complete
6. On the Mac, confirm the edit landed
7. Repeat on iPad

### 4-12. Operational notes

#### Avoid simultaneous edits

iOS sync timing is at the mercy of background limits. Editing the same
file on the Mac and then the iPhone seconds later is a recipe for a
conflict file.

Habits:

- Bring SyncTrain to the foreground before opening Obsidian on iOS (the
  automation handles this)
- Wait a few seconds after a save before switching devices on the same
  file

#### `workspace-mobile.json` conflicts

iOS Obsidian rewrites `.obsidian/workspace-mobile.json` constantly. If
your `.stignore` doesn't exclude it, you'll see daily conflict files.
Double-check section 4-10.

#### Battery

Foreground SyncTrain uses the network continuously. Default to letting
it sit in the background and use the Shortcut to wake it on demand.

#### Tailscale interaction

When Tailscale drops on iOS (e.g. transient VPN reconnect), SyncTrain
can't reach the always-on Mac. Recovery is automatic when Tailscale
reconnects, but a long outage stalls sync. If iOS sync seems stuck,
check Tailscale first.

### Phase 4 checklist

- [ ] SyncTrain installed on iPhone and iPad
- [ ] Tailscale signed in on both
- [ ] Both iOS Device IDs registered as Remote Devices on the always-on
      Mac
- [ ] Always-on Mac registered as Remote Device on both iOS devices
      (Tailscale IP)
- [ ] Vault folder shared from the always-on Mac to both iOS devices
- [ ] Each iOS device accepts the folder under `On My iPhone` /
      `On My iPad`
- [ ] iOS Obsidian opens the Vault via **Open folder as vault** →
      `SyncTrain` → `Vault`
- [ ] `.stignore` set on each iOS device via Web GUI
- [ ] Apple Shortcut auto-runs SyncTrain when Obsidian launches
- [ ] Bidirectional smoke test passed (Mac ↔ iOS, both directions)

---

## Troubleshooting

### `brew services start syncthing` fails with `error 78` / `$HOME is not defined`

Known issue on Apple Silicon Macs. The auto-generated plist has no `HOME`
in `EnvironmentVariables`, syncthing panics, `KeepAlive=true` loops the
crash, and the log fills with panic messages.

**Fix**: don't use `brew services` — switch to the custom LaunchAgent in
Phase 1 ("Always-on Mac"). Setting `HOME` in `.zprofile` / `.zshrc`
doesn't help: launchd never goes through a shell.

```bash
# Wipe brew services state
brew services stop syncthing 2>/dev/null
launchctl bootout gui/$(id -u)/homebrew.mxcl.syncthing 2>/dev/null
rm -f ~/Library/LaunchAgents/homebrew.mxcl.syncthing.plist

# Truncate any bloated panic log
> /opt/homebrew/var/log/syncthing.log

# Then build the custom LaunchAgent — see Phase 1
```

### Cask and formula installed at the same time

```bash
# Stop everything
brew services stop syncthing 2>/dev/null
sudo brew services stop syncthing 2>/dev/null
osascript -e 'quit app "Syncthing"'

# Keep one
brew uninstall --cask syncthing-app  # keep formula
# or
brew uninstall syncthing             # keep Cask

# Config dir is shared, so settings carry over
ls ~/Library/Application\ Support/Syncthing/
```

### Conflict files (`*.sync-conflict-*`) keep appearing

- Two devices edited the same file at the same time. Open in Obsidian and
  resolve manually
- The `obsidian-syncthing-integration` plugin lets you diff and merge
  inside Obsidian
- Long-term fix: save and wait for sync to finish before switching
  devices

### Recover deletions from `.stversions`

The always-on Mac keeps versioning, so deletes and overwrites are
recoverable:

```bash
# On the always-on Mac
ls -la ~/Vault/.stversions/

# Past versions of a specific file
ls -la ~/Vault/.stversions/notes/

# Filenames carry timestamps, e.g.
# today~20260504-143022.md

# Restore (strip the timestamp)
cp ~/Vault/.stversions/notes/today~20260504-143022.md \
   ~/Vault/notes/today.md
```

The restored file syncs to the laptop automatically.

### Git ↔ Syncthing interactions

#### `.git/index.lock` errors

Syncthing reached into `.git/`. Verify `.stignore` actually excludes it:

```bash
grep -E '^\.git' ~/Vault/.stignore
# .git
# .git/**
```

#### `git pull` conflicts on the laptop

Files arrived via Syncthing while the laptop was behind on Git. Stash,
pull, pop:

```bash
git stash
git pull --rebase
git stash pop
# Resolve any conflicts manually
```
