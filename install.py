import ctypes
import json
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_EXTS = (".mp3", ".wav")
HOOK_KEY = "completion-sound"
SOUND_BASENAME = "notification"  # installed as notification.mp3 / notification.wav

GLOBAL_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".gemini", "config")
LOCAL_AGENTS_DIR = os.path.join(SCRIPT_DIR, ".agents")
WINDOWS_MEDIA_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Media")

# Small player that runs in a detached process: argv = [path, mci_device_type]
PLAYER_CODE = """
import ctypes, sys
w = ctypes.windll.winmm
p, t = sys.argv[1], sys.argv[2]
w.mciSendStringW('close agy_play', None, 0, None)
if w.mciSendStringW('open "%s" type %s alias agy_play' % (p, t), None, 0, None) == 0:
    w.mciSendStringW('play agy_play wait', None, 0, None)
    w.mciSendStringW('close agy_play', None, 0, None)
"""

NOTIFY_SCRIPT_CODE = r'''import ctypes
import json
import msvcrt
import os
import subprocess
import sys
import time

AUDIO_EXTS = (".mp3", ".wav")
DEBOUNCE_FILE = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", r"C:\Windows\Temp")), "agy_notify_last.lock")
DEBOUNCE_SECONDS = 2.0

PLAYER_CODE = """
import ctypes, sys
w = ctypes.windll.winmm
p, t = sys.argv[1], sys.argv[2]
w.mciSendStringW('close agy_play', None, 0, None)
if w.mciSendStringW('open "%s" type %s alias agy_play' % (p, t), None, 0, None) == 0:
    w.mciSendStringW('play agy_play wait', None, 0, None)
    w.mciSendStringW('close agy_play', None, 0, None)
"""

def is_debounced():
    now = time.time()
    try:
        lock_fd = os.open(DEBOUNCE_FILE, os.O_RDWR | os.O_CREAT)
        with open(lock_fd, "r+", encoding="utf-8", closefd=True) as f:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return True
            try:
                content = f.read().strip()
                if content:
                    last_time = float(content)
                    if 0 <= (now - last_time) < DEBOUNCE_SECONDS:
                        return True
                f.seek(0)
                f.truncate()
                f.write(f"{now:.4f}")
                f.flush()
            finally:
                try:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
    except Exception:
        pass
    return False

def read_stdin_safe():
    try:
        h = msvcrt.get_osfhandle(sys.stdin.fileno())
        avail = ctypes.c_ulong()
        success = ctypes.windll.kernel32.PeekNamedPipe(h, None, 0, None, ctypes.byref(avail), None)
        if success and avail.value > 0:
            return sys.stdin.read(avail.value)
    except Exception:
        pass
    return ""

def find_sound_file(workspace_paths=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, ".."))

    # Priority 1: sound chosen during installation
    specific = []
    for base in (os.path.join(parent_dir, "sounds"), script_dir):
        for ext in AUDIO_EXTS:
            specific.append(os.path.join(base, "notification" + ext))
    specific += [
        os.path.join(parent_dir, "sounds", "woeoeoeoe_woeoeoeoeoe_woeoeoeoe.mp3"),
        os.path.join(script_dir, "woeoeoeoe_woeoeoeoeoe_woeoeoeoe.mp3"),
        os.path.join(parent_dir, "woeoeoeoe_woeoeoeoeoe_woeoeoeoe.mp3"),
    ]
    for p in specific:
        if os.path.isfile(p):
            return p

    # Priority 2: Check active workspace if provided
    if workspace_paths:
        for ws in workspace_paths:
            for root, _, files in os.walk(ws):
                if ".git" in root or ".agents" in root:
                    continue
                for f in files:
                    if f.lower().endswith(AUDIO_EXTS):
                        return os.path.join(root, f)

    # Priority 3: Check parent dir for any mp3 or wav
    for root, _, files in os.walk(parent_dir):
        if ".git" in root or "node_modules" in root:
            continue
        for f in files:
            if f.lower().endswith(AUDIO_EXTS):
                return os.path.join(root, f)

    return None

def main():
    workspace_paths = []
    raw_input = read_stdin_safe()
    if raw_input:
        try:
            data = json.loads(raw_input)
            if data.get("terminationReason") == "USER_CANCELED":
                print(json.dumps({}))
                return
            workspace_paths = data.get("workspacePaths", [])
        except Exception:
            pass

    sound_file = find_sound_file(workspace_paths)
    if sound_file:
        if is_debounced():
            print(json.dumps({}))
            return
        sound_file = os.path.abspath(sound_file)
        device_type = "waveaudio" if sound_file.lower().endswith(".wav") else "mpegvideo"
        DETACHED_PROCESS = 0x00000008
        try:
            subprocess.Popen(
                [sys.executable, "-c", PLAYER_CODE, sound_file, device_type],
                creationflags=DETACHED_PROCESS,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    # Antigravity hook contract: return JSON object on stdout
    print(json.dumps({}))

if __name__ == "__main__":
    main()
'''


# --------------------------------------------------------------------------
# Audio helpers
# --------------------------------------------------------------------------

def device_type(path):
    return "waveaudio" if path.lower().endswith(".wav") else "mpegvideo"


def _mci(cmd):
    try:
        return ctypes.windll.winmm.mciSendStringW(cmd, None, 0, None)
    except Exception:
        return -1


def preview_sound(path):
    """Play a sound asynchronously inside this process (stops the previous preview)."""
    _mci("close agy_preview")
    if _mci(f'open "{os.path.abspath(path)}" type {device_type(path)} alias agy_preview') == 0:
        _mci("play agy_preview")
        print(f"   > Playing: {os.path.basename(path)}")
    else:
        print(f"   [!] Could not play: {path}")


def stop_preview():
    _mci("close agy_preview")


def play_detached(sound_path):
    """Play a sound in a detached process so it keeps playing after the installer exits."""
    print("\nPlaying test sound...")
    DETACHED_PROCESS = 0x00000008
    try:
        subprocess.Popen(
            [sys.executable, "-c", PLAYER_CODE, os.path.abspath(sound_path), device_type(sound_path)],
            creationflags=DETACHED_PROCESS,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"Error during test playback: {e}")


def is_audio(path):
    return os.path.isfile(path) and path.lower().endswith(AUDIO_EXTS)


def list_audio(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        (os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(AUDIO_EXTS)),
        key=lambda p: os.path.basename(p).lower(),
    )


def fmt_size(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        return "?"
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


def installed_sound(target_dir):
    for ext in AUDIO_EXTS:
        p = os.path.join(target_dir, SOUND_BASENAME + ext)
        if os.path.isfile(p):
            return p
    return None


def browse_for_file():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("   [!] File dialog not available (tkinter missing). Paste a path instead.")
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            parent=root,
            title="Choose notification sound",
            initialdir=SCRIPT_DIR,
            filetypes=[("Audio files", "*.mp3 *.wav"), ("MP3", "*.mp3"), ("WAV", "*.wav")],
        )
        root.destroy()
    except Exception as e:
        print(f"   [!] File dialog failed: {e}")
        return None
    return os.path.normpath(path) if path else None


class InputClosed(Exception):
    pass


def ask(prompt, default=None):
    """input() that survives a closed stdin: returns `default`, or raises InputClosed."""
    try:
        return input(prompt)
    except EOFError:
        print()
        if default is not None:
            return default
        raise InputClosed()


def clean_path_input(text):
    # Drag & drop into the console wraps paths with spaces in quotes
    return os.path.expandvars(os.path.expanduser(text.strip().strip('"').strip("'")))


def pick_from_list(title, files):
    """Sub-menu for a list of files. Returns chosen path or None (back)."""
    while True:
        print(f"\n{title}")
        for i, f in enumerate(files, 1):
            print(f"  [{i:>2}] {os.path.basename(f)}")
        print("  Type a number to select, 'p<number>' to preview, Enter to go back.")
        choice = ask("> ").strip().lower()
        if not choice:
            stop_preview()
            return None
        if choice.startswith("p") and choice[1:].strip().isdigit():
            idx = int(choice[1:].strip()) - 1
            if 0 <= idx < len(files):
                preview_sound(files[idx])
            continue
        if choice.isdigit() and 0 <= int(choice) - 1 < len(files):
            stop_preview()
            return files[int(choice) - 1]
        print("   [!] Invalid choice.")


def choose_sound(current=None):
    """Interactive sound picker. Returns a path, or None to keep `current`/no sound."""
    local_files = []
    for f in list_audio(SCRIPT_DIR) + list_audio(os.path.join(SCRIPT_DIR, "sounds")):
        if f not in local_files:
            local_files.append(f)
    windows_files = list_audio(WINDOWS_MEDIA_DIR)

    default = "k" if current else ("1" if local_files else None)

    while True:
        print("\n" + "-" * 60)
        print(" Choose your notification sound")
        print("-" * 60)
        if current:
            print(f"  [K]  Keep currently installed sound ({os.path.basename(current)})")
        for i, f in enumerate(local_files, 1):
            print(f"  [{i:>2}] {os.path.basename(f)}  ({fmt_size(f)})")
        if not local_files:
            print("       (no .mp3/.wav files found in this folder)")
        print("  [B]  Browse for a file...")
        if windows_files:
            print(f"  [W]  Windows system sounds ({len(windows_files)})")
        print()
        print("  Tip: 'p<number>' previews a sound (e.g. p1), 'pk' the current one.")
        print("       You can also paste or drag & drop a file path here.")
        hint = f"Default: {default.upper()}" if default else "no default"
        choice = ask(f"\nEnter choice [{hint}]: ").strip()
        low = choice.lower()

        if not choice:
            if default == "k":
                return current
            if default:
                return local_files[0]
            print("   [!] Please choose a sound.")
            continue

        if low == "k" and current:
            stop_preview()
            return current

        if low == "pk" and current:
            preview_sound(current)
            continue

        if low.startswith("p") and low[1:].strip().isdigit():
            idx = int(low[1:].strip()) - 1
            if 0 <= idx < len(local_files):
                preview_sound(local_files[idx])
            else:
                print("   [!] No sound with that number.")
            continue

        if low.isdigit():
            idx = int(low) - 1
            if 0 <= idx < len(local_files):
                stop_preview()
                return local_files[idx]
            print("   [!] No sound with that number.")
            continue

        if low == "b":
            path = browse_for_file()
            if path and confirm_sound(path):
                return path
            continue

        if low == "w" and windows_files:
            path = pick_from_list("Windows system sounds:", windows_files)
            if path:
                return path
            continue

        path = clean_path_input(choice)
        if is_audio(path):
            if confirm_sound(path):
                return path
            continue
        if os.path.isfile(path):
            print("   [!] Only .mp3 and .wav files are supported.")
        else:
            print("   [!] Invalid choice or file not found.")


def confirm_sound(path):
    print(f"\nSelected: {path}")
    while True:
        ans = ask("Use this sound? [Y]es / [n]o / [p]review: ").strip().lower()
        if ans in ("", "y", "yes", "j", "ja"):
            stop_preview()
            return True
        if ans in ("n", "no", "nein"):
            stop_preview()
            return False
        if ans == "p":
            preview_sound(path)


# --------------------------------------------------------------------------
# Install / uninstall
# --------------------------------------------------------------------------

def update_hooks_json(hooks_file_path, command_str):
    hooks = {}
    if os.path.isfile(hooks_file_path):
        try:
            with open(hooks_file_path, "r", encoding="utf-8") as f:
                hooks = json.load(f)
        except Exception:
            hooks = {}

    hooks[HOOK_KEY] = {
        "Stop": [
            {
                "type": "command",
                "command": command_str,
                "timeout": 10
            }
        ]
    }

    with open(hooks_file_path, "w", encoding="utf-8") as f:
        json.dump(hooks, f, indent=2)


def remove_hook(hooks_file_path):
    if not os.path.isfile(hooks_file_path):
        return False
    try:
        with open(hooks_file_path, "r", encoding="utf-8") as f:
            hooks = json.load(f)
    except Exception:
        print(f"   [!] Could not read {hooks_file_path}, leaving it untouched.")
        return False
    if not isinstance(hooks, dict) or HOOK_KEY not in hooks:
        return False
    del hooks[HOOK_KEY]
    if hooks:
        with open(hooks_file_path, "w", encoding="utf-8") as f:
            json.dump(hooks, f, indent=2)
        print(f"-> Removed hook entry from: {hooks_file_path}")
    else:
        os.remove(hooks_file_path)
        print(f"-> Deleted: {hooks_file_path}")
    return True


def remove_file(path):
    if os.path.isfile(path):
        os.remove(path)
        print(f"-> Deleted: {path}")
        return True
    return False


def remove_dir_if_empty(path):
    try:
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
            print(f"-> Removed empty folder: {path}")
    except OSError:
        pass


def install_sound(sound_source, target_dir):
    """Copy the chosen sound to target_dir/notification.<ext>. Returns installed path."""
    os.makedirs(target_dir, exist_ok=True)
    ext = os.path.splitext(sound_source)[1].lower()
    dest = os.path.join(target_dir, SOUND_BASENAME + ext)
    if os.path.abspath(sound_source) == os.path.abspath(dest):
        return dest
    for e in AUDIO_EXTS:  # avoid a stale notification.<other ext> taking priority
        old = os.path.join(target_dir, SOUND_BASENAME + e)
        if os.path.isfile(old):
            os.remove(old)
    shutil.copy2(sound_source, dest)
    print(f"-> Sound copied to: {dest}")
    return dest


def global_sound_dir():
    return os.path.join(GLOBAL_CONFIG_DIR, "sounds")


def setup_global(sound_source):
    scripts_dir = os.path.join(GLOBAL_CONFIG_DIR, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)

    dest_sound = install_sound(sound_source, global_sound_dir()) if sound_source else None

    dest_script = os.path.join(scripts_dir, "notify_done.py")
    with open(dest_script, "w", encoding="utf-8") as f:
        f.write(NOTIFY_SCRIPT_CODE)
    print(f"-> Script installed at: {dest_script}")

    hooks_file = os.path.join(GLOBAL_CONFIG_DIR, "hooks.json")
    update_hooks_json(hooks_file, "python scripts/notify_done.py")
    print(f"-> Hooks updated at: {hooks_file}")

    print("\n[SUCCESS] Global setup complete! Sound will play for ALL Antigravity projects on this PC.")
    if dest_sound:
        play_detached(dest_sound)


def setup_local(sound_source):
    os.makedirs(LOCAL_AGENTS_DIR, exist_ok=True)

    dest_sound = install_sound(sound_source, LOCAL_AGENTS_DIR) if sound_source else None

    dest_script = os.path.join(LOCAL_AGENTS_DIR, "notify_done.py")
    with open(dest_script, "w", encoding="utf-8") as f:
        f.write(NOTIFY_SCRIPT_CODE)
    print(f"-> Script installed at: {dest_script}")

    hooks_file = os.path.join(LOCAL_AGENTS_DIR, "hooks.json")
    update_hooks_json(hooks_file, "python notify_done.py")
    print(f"-> Hooks updated at: {hooks_file}")

    git_dir = os.path.join(SCRIPT_DIR, ".git")
    if not os.path.isdir(git_dir):
        try:
            subprocess.run(["git", "init"], cwd=SCRIPT_DIR, capture_output=True)
            print("-> Initialized Git repository for Antigravity discovery.")
        except Exception:
            pass

    print("\n[SUCCESS] Local setup complete! Sound will play in this project directory.")
    if dest_sound:
        play_detached(dest_sound)


def is_installed_global():
    return (
        os.path.isfile(os.path.join(GLOBAL_CONFIG_DIR, "scripts", "notify_done.py"))
        or installed_sound(global_sound_dir()) is not None
    )


def is_installed_local():
    return os.path.isfile(os.path.join(LOCAL_AGENTS_DIR, "notify_done.py"))


def uninstall_global():
    print("\nRemoving global installation...")
    scripts_dir = os.path.join(GLOBAL_CONFIG_DIR, "scripts")
    sounds_dir = global_sound_dir()
    changed = remove_hook(os.path.join(GLOBAL_CONFIG_DIR, "hooks.json"))
    changed |= remove_file(os.path.join(scripts_dir, "notify_done.py"))
    for ext in AUDIO_EXTS:
        changed |= remove_file(os.path.join(sounds_dir, SOUND_BASENAME + ext))
    pycache = os.path.join(scripts_dir, "__pycache__")
    if os.path.isdir(pycache):
        for f in os.listdir(pycache):
            if f.startswith("notify_done."):
                remove_file(os.path.join(pycache, f))
        remove_dir_if_empty(pycache)
    remove_dir_if_empty(scripts_dir)
    remove_dir_if_empty(sounds_dir)
    print("[DONE] Global installation removed." if changed else "Nothing to remove (global).")


def uninstall_local():
    print("\nRemoving local installation...")
    changed = remove_hook(os.path.join(LOCAL_AGENTS_DIR, "hooks.json"))
    changed |= remove_file(os.path.join(LOCAL_AGENTS_DIR, "notify_done.py"))
    for ext in AUDIO_EXTS:
        changed |= remove_file(os.path.join(LOCAL_AGENTS_DIR, SOUND_BASENAME + ext))
    remove_dir_if_empty(LOCAL_AGENTS_DIR)
    print("[DONE] Local installation removed." if changed else "Nothing to remove (local).")


def run_uninstall(mode):
    print("=" * 60)
    print("   Antigravity Completion Notification Sound Uninstaller")
    print("=" * 60)

    g, l = is_installed_global(), is_installed_local()
    print(f"Global installation: {'found' if g else 'not found'}  ({GLOBAL_CONFIG_DIR})")
    print(f"Local installation:  {'found' if l else 'not found'}  ({LOCAL_AGENTS_DIR})")

    if not mode:
        if not g and not l:
            print("\nNothing installed - nothing to do.")
            return
        print("\nWhat would you like to remove?")
        print("  [1] Global")
        print("  [2] Local")
        print("  [3] Both")
        print("  [0] Cancel")
        default = "3" if g and l else ("1" if g else "2")
        choice = ask(f"Enter choice [Default: {default}]: ", default).strip() or default
        mode = {"1": "global", "2": "local", "3": "both"}.get(choice)
        if not mode:
            print("Cancelled.")
            return

    if mode in ("global", "both"):
        uninstall_global()
    if mode in ("local", "both"):
        uninstall_local()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv):
    opts = {"mode": None, "sound": None, "uninstall": False}
    i = 0
    while i < len(argv):
        arg = argv[i].lower().lstrip("-/")
        if arg in ("uninstall", "u", "remove"):
            opts["uninstall"] = True
        elif arg in ("global", "g", "1"):
            opts["mode"] = "global"
        elif arg in ("local", "l", "2"):
            opts["mode"] = "local"
        elif arg in ("both", "all"):
            opts["mode"] = "both"
        elif arg in ("sound", "s") and i + 1 < len(argv):
            i += 1
            opts["sound"] = clean_path_input(argv[i])
        else:
            print(f"[WARNING] Ignoring unknown argument: {argv[i]}")
        i += 1
    return opts


def main():
    opts = parse_args(sys.argv[1:])

    if opts["uninstall"]:
        run_uninstall(opts["mode"])
        return

    print("=" * 60)
    print("   Antigravity Completion Notification Sound Installer")
    print("=" * 60)

    mode = opts["mode"] if opts["mode"] in ("global", "local") else None
    if not mode:
        print("\nWhere would you like to set up the notification sound?")
        print("  [1] Global (Recommended: Plays for ALL projects on this PC)")
        print("  [2] Local only (Plays only for this project folder)")
        print()
        choice = ask("Enter choice [1/2, Default: 1]: ", "").strip()
        mode = "local" if choice == "2" else "global"

    current = installed_sound(global_sound_dir() if mode == "global" else LOCAL_AGENTS_DIR)

    if opts["sound"]:
        if not is_audio(opts["sound"]):
            print(f"[ERROR] Not a valid .mp3/.wav file: {opts['sound']}")
            sys.exit(1)
        sound_source = opts["sound"]
    else:
        try:
            sound_source = choose_sound(current)
        except InputClosed:  # no console input available -> use defaults
            files = list_audio(SCRIPT_DIR)
            sound_source = current or (files[0] if files else None)

    if sound_source:
        print(f"\nUsing sound: {sound_source}")
    else:
        print("\n[WARNING] No sound selected - only the hook will be installed.")

    print()
    if mode == "global":
        setup_global(sound_source)
    else:
        setup_local(sound_source)


if __name__ == "__main__":
    main()
