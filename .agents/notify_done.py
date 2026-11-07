import ctypes
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
