"""S0-04 (Python side): find the Unity editor and tell whether a project is open.

Runs on Windows (inside Blender). Search order follows the design (03 §9.5).
"""
import glob
import json
import os
import subprocess

VERSION = "2022.3.22f1"


def _hub_dirs():
    dirs = [r"C:\Program Files\Unity\Hub\Editor"]
    appdata = os.environ.get("APPDATA", "")
    sec = os.path.join(appdata, "UnityHub", "secondaryInstallPath.json")
    try:
        with open(sec, encoding="utf-8") as f:
            p = json.load(f)
        if isinstance(p, str) and p:
            dirs.append(p)
    except (OSError, ValueError):
        pass
    return dirs


def _hub_editor_files():
    """Editors registered in Unity Hub's own JSON files (format differs between Hub versions)."""
    found = []
    for path in glob.glob(os.path.join(os.environ.get("APPDATA", ""), "UnityHub", "editors*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        items = data.values() if isinstance(data, dict) else data
        for it in items:
            if isinstance(it, dict):
                loc = it.get("location")
                loc = loc[0] if isinstance(loc, list) and loc else loc
                if isinstance(loc, str):
                    found.append((it.get("version", ""), loc))
    return found


def find_unity(explicit=None, version=VERSION):
    """Returns (path, exact_version_found, other_2022_3_candidates)."""
    if explicit and os.path.isfile(explicit):
        return explicit, True, []
    others = []
    for d in _hub_dirs():
        exe = os.path.join(d, version, "Editor", "Unity.exe")
        if os.path.isfile(exe):
            return exe, True, []
        others += glob.glob(os.path.join(d, "2022.3.*", "Editor", "Unity.exe"))
    for ver, loc in _hub_editor_files():
        exe = loc if loc.lower().endswith(".exe") else os.path.join(loc, "Unity.exe")
        if ver == version and os.path.isfile(exe):
            return exe, True, []
        if ver.startswith("2022.3.") and os.path.isfile(exe):
            others.append(exe)
    return None, False, sorted(set(others))


def project_is_open(project):
    """Unity keeps Temp/UnityLockfile open while the editor runs; Windows refuses to open it then."""
    lock = os.path.join(project, "Temp", "UnityLockfile")
    if not os.path.exists(lock):
        return False
    try:
        with open(lock, "a"):
            return False                 # stale lock file left by a crash
    except OSError:
        return True


def run_batch(unity, project, method, extra_args, log_path):
    cmd = [unity, "-batchmode", "-nographics", "-quit", "-projectPath", project,
           "-executeMethod", method, "-logFile", log_path] + list(extra_args)
    return subprocess.Popen(cmd)
