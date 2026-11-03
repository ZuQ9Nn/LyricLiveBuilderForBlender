"""Find the Unity editor and tell whether a project is open (design §9.5, prototype S0-04)."""
import glob
import json
import os
import sys

VERSION = "2022.3.22f1"


def _hub_dirs():
    if sys.platform == "darwin":
        return ["/Applications/Unity/Hub/Editor"]
    if not sys.platform.startswith("win"):
        return [os.path.expanduser("~/Unity/Hub/Editor")]
    dirs = [r"C:\Program Files\Unity\Hub\Editor"]
    sec = os.path.join(os.environ.get("APPDATA", ""), "UnityHub", "secondaryInstallPath.json")
    try:
        with open(sec, encoding="utf-8") as f:
            p = json.load(f)
        if isinstance(p, str) and p:
            dirs.append(p)
    except (OSError, ValueError):
        pass
    return dirs


def _exe(folder):
    if sys.platform == "darwin":
        return os.path.join(folder, "Unity.app", "Contents", "MacOS", "Unity")
    return os.path.join(folder, "Editor", "Unity.exe" if sys.platform.startswith("win") else "Unity")


def _hub_editor_files():
    """Editors listed in Unity Hub's own JSON files: not every Hub version has them (S0-04)."""
    found = []
    for path in glob.glob(os.path.join(os.environ.get("APPDATA", ""), "UnityHub", "editors*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        for it in (data.values() if isinstance(data, dict) else data):
            if isinstance(it, dict):
                loc = it.get("location")
                loc = loc[0] if isinstance(loc, list) and loc else loc
                if isinstance(loc, str):
                    found.append((str(it.get("version", "")), loc))
    return found


def find_unity(explicit="", version=VERSION):
    """(path or None, other 2022.3 editors found)."""
    if explicit:
        return (explicit, []) if os.path.isfile(explicit) else (None, [])
    others = []
    for d in _hub_dirs():
        exe = _exe(os.path.join(d, version))
        if os.path.isfile(exe):
            return exe, []
        others += [_exe(x) for x in glob.glob(os.path.join(d, "2022.3.*")) if os.path.isfile(_exe(x))]
    for ver, loc in _hub_editor_files():
        exe = loc if os.path.isfile(loc) else _exe(loc)
        if ver == version and os.path.isfile(exe):
            return exe, []
        if ver.startswith("2022.3.") and os.path.isfile(exe):
            others.append(exe)
    return None, sorted(set(others))


def is_project(path):
    return os.path.isdir(os.path.join(path, "Assets")) and os.path.isdir(os.path.join(path, "ProjectSettings"))


def project_is_open(project):
    """Unity keeps Temp/UnityLockfile open while the editor runs; Windows refuses to open it then."""
    lock = os.path.join(project, "Temp", "UnityLockfile")
    if not os.path.exists(lock):
        return False
    try:
        with open(lock, "a"):
            return False                                  # a stale lock left by a crash
    except OSError:
        return True


def has_timeline(project):
    """The build scripts need the Timeline package (VRChat world projects have it; an empty project may not)."""
    for name in ("manifest.json", "packages-lock.json"):
        try:
            with open(os.path.join(project, "Packages", name), encoding="utf-8") as f:
                if "com.unity.timeline" in json.load(f).get("dependencies", {}):
                    return True
        except (OSError, ValueError):
            pass
    return False

