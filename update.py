"""Brings this folder to the newest version of the app. Your searches, marks, people and settings are kept.

    python update.py            download the newest version and replace the program's files
    python update.py --check    only say what would change; nothing is written

The app does the same from its own window ("a new version is ready", one click). What happens either way: one
download of the published code (a ZIP from GitHub, or `git pull` when this folder is a git clone), then every
program file that differs is replaced. The folder `data` (everything that is yours) is never read, sent or changed,
except that the files being replaced are first copied to `data/backup/<time>/`, so you can go back.
Nothing about you or this computer is sent: it is a plain download.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# The repository by its number at GitHub, so the address keeps working if the repository is renamed or moved.
# LUACH_UPDATE_FROM names another place with the same two addresses under it (a mirror, or a test).
REPO = (os.environ.get("LUACH_UPDATE_FROM") or "https://api.github.com/repositories/1461433378").rstrip("/")
KEEP = ("data/", "local_settings.py", "_old_v1/")   # never written, whatever a download holds


class UpdateError(Exception):
    pass


def number(version):
    """"1.10.2" -> (1, 10, 2), so that versions compare as numbers."""
    return tuple(int(x) for x in re.findall(r"\d+", str(version or ""))[:4]) or (0,)


def local_version():
    """What this folder holds: {"version", "date", "releases": [{"version", "date", "he": [...], "en": [...]}]}."""
    try:
        return json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fetch(path, accept, timeout):
    req = urllib.request.Request(REPO + path, headers={"User-Agent": "luach-echad-update", "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except (urllib.error.URLError, OSError) as e:
        hint = ""
        if "CERTIFICATE" in str(e).upper():
            hint = (" (on macOS: run \"Install Certificates.command\" from the Python folder in Applications once, "
                    "then try again)")
        raise UpdateError(f"The download did not work: {e}{hint}") from e


def published_version(timeout=10):
    """The newest published version.json. One small request; nothing about this computer goes with it."""
    try:
        got = json.loads(fetch("/contents/version.json?ref=main", "application/vnd.github.raw+json", timeout))
    except ValueError as e:
        raise UpdateError("The published version file could not be read") from e
    if not isinstance(got, dict):
        raise UpdateError("The published version file could not be read")
    return got


def news_since(info, version):
    """The releases in a version file that are newer than `version`, newest first, as plain short texts."""
    out = []
    for r in info.get("releases") or []:
        if not isinstance(r, dict) or number(r.get("version")) <= number(version):
            continue
        lines = lambda key: [str(t)[:300] for t in (r.get(key) or []) if isinstance(t, str)][:12]
        out.append({"version": str(r.get("version"))[:20], "date": str(r.get("date") or "")[:10],
                    "he": lines("he"), "en": lines("en")})
    return sorted(out, key=lambda r: number(r["version"]), reverse=True)[:10]


def is_clone():
    return (ROOT / ".git").exists() and bool(shutil.which("git"))


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def from_git(check):
    """A git clone updates itself with git; local changes to the program's files make git refuse, which is right."""
    if git("fetch", "--quiet").returncode:
        raise UpdateError("git could not reach the repository. Nothing was changed.")
    names = [n for n in git("diff", "--name-only", "HEAD", "@{upstream}").stdout.splitlines() if n.strip()]
    if check or not names:
        return {"updated": False, "changed": names, "new": [], "backup": None}
    done = git("pull", "--ff-only")
    if done.returncode:
        raise UpdateError("git could not update this folder: " + (done.stderr or done.stdout).strip()[-300:]
                          + "\nNothing was changed.")
    return {"updated": True, "changed": names, "new": [], "backup": None}


def from_zip(check):
    try:
        pack = zipfile.ZipFile(io.BytesIO(fetch("/zipball/main", "application/vnd.github+json", 90)))
    except zipfile.BadZipFile as e:
        raise UpdateError("The download was not complete. Nothing was changed.") from e
    names = [n for n in pack.namelist() if not n.endswith("/")]
    if not names:
        raise UpdateError("The download was empty. Nothing was changed.")
    top = names[0].split("/", 1)[0] + "/"
    if top + "app.py" not in names:
        raise UpdateError("The download does not look like the app. Nothing was changed.")
    changed, new, todo = [], [], []
    for name in names:
        if not name.startswith(top):
            continue
        rel = name[len(top):]
        target = (ROOT / rel).resolve()
        if not rel or ROOT not in target.parents or any(rel == k or rel.startswith(k) for k in KEEP):
            continue   # a path outside this folder, or one of yours: left alone
        data = pack.read(name)
        if target.is_file() and target.read_bytes() == data:
            continue
        (changed if target.exists() else new).append(rel)
        todo.append((rel, target, data))
    if check or not todo:
        return {"updated": False, "changed": changed, "new": new, "backup": None}
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    backup = ROOT / "data" / "backup" / stamp
    backup.mkdir(parents=True, exist_ok=True)   # also when every file is new: the folder marks this update
    for rel, target, data in todo:
        if target.is_file():
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup / rel)
    (backup / "_added.json").write_text(json.dumps(new), encoding="utf-8")   # so that going back can remove them
    for rel, target, data in todo:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return {"updated": True, "changed": changed, "new": new, "backup": f"data/backup/{stamp}/"}


def apply(check=False):
    """Bring the folder to the newest published version. check=True writes nothing.
    -> {"updated", "changed", "new", "backup", "was", "version", "news"}"""
    was = local_version().get("version")
    out = from_git(check) if is_clone() else from_zip(check)
    now = local_version()
    out.update(was=was, version=now.get("version"), news=news_since(now, was) if out["updated"] else [])
    return out


def main():
    check = "--check" in sys.argv[1:]
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    manifest = ROOT / "extension" / "manifest.json"
    before = manifest.read_bytes() if manifest.is_file() else b""
    try:
        res = apply(check)
    except UpdateError as e:
        sys.exit(str(e))
    files = res["changed"] + res["new"]
    if not files:
        print(f"Already the newest version{' (' + res['version'] + ')' if res['version'] else ''}.")
        return
    if check:
        print(f"A newer version is published: {len(res['changed'])} files would change, {len(res['new'])} are new.")
        for rel in files:
            print("  ", rel)
        return
    print(f"Updated{' to version ' + res['version'] if res['version'] else ''}: "
          f"{len(res['changed'])} files changed, {len(res['new'])} new.")
    for r in res["news"]:
        print(f"\nNew in {r['version']}:")
        for line in r["en"] or r["he"]:
            print("  -", line)
    if res["backup"]:
        print(f"\nThe files that were replaced are kept in {res['backup']}")
    print("\nYour searches, marks and settings (the folder \"data\") were not touched.")
    print("Now: close the app's window if it is open, and start it again (start.cmd / start.sh).")
    if manifest.is_file() and manifest.read_bytes() != before:
        print("The browser extension changed too. It reloads itself when the app starts; if the app asks you to,")
        print("open chrome://extensions and click the reload arrow of the app's extension.")


if __name__ == "__main__":
    main()
