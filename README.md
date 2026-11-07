# Antigravity Completion Notification Sound

Automatically plays a notification sound whenever Google Antigravity finishes a task or prompt turn.

## Features
- **Zero latency**: Plays asynchronously in the background via the native Windows multimedia API (`winmm.dll`) without blocking Antigravity or delaying responses.
- **Native & lightweight**: Uses standard Python libraries with no external packages required.
- **Flexible**: Choose between global setup (for all Antigravity projects) or local setup (scoped to this project).
- **Auto-cancellation aware**: Automatically skips playback if you cancel the turn.

## Quick Start

1. Double-click **`setup.bat`**.
2. Choose your installation mode:
   - **`[1] Global (Recommended)`**: Installs to `~/.gemini/config/` so the sound plays for **any** Antigravity project on your PC.
   - **`[2] Local`**: Installs to `.agents/` inside this project directory only.
3. Choose your sound:
   - a number: any `.mp3` / `.wav` in this folder (e.g. the included `woeoeoeoe_woeoeoeoeoe_woeoeoeoe.mp3`)
   - `B`: browse for a file with the Windows file dialog
   - `W`: pick one of the Windows system sounds
   - `K`: keep the sound that is already installed
   - or paste / drag & drop a file path into the window
   - `p<number>` (e.g. `p1`) previews a sound before you choose it
4. A test sound will play to confirm the setup works!

## Uninstall

Double-click **`uninstall.bat`** and choose global, local or both. It removes the hook entry from `hooks.json` (other hooks stay untouched), the script and the installed sound.

## Requirements
- Windows 10 / 11
- Python 3 added to `PATH` (`python --version`)

## Command-Line Usage
You can also run the installer non-interactively:
```bat
setup.bat --global
setup.bat --local --sound "C:\path\to\sound.wav"
uninstall.bat --global
uninstall.bat --both
```
