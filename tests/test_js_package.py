"""
Tests for the npm package of wrappers/javascript (v1.9.0, F6).

package.json listed iso4217.json under "files", but the file was not in the directory, and `npm pack` omits a missing
entry without a word: the published tarball had index.js and no data, and index.js could not find the registry once
installed. These tests pack the real package, read the tarball, and install it into an empty project.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JS_DIR = PROJECT_ROOT / "wrappers" / "javascript"


def _pack(tmp_path: Path) -> tuple[Path, list[str]]:
    work = tmp_path / "pkg"
    shutil.copytree(JS_DIR, work, ignore=shutil.ignore_patterns("node_modules", "*.tgz"))
    r = subprocess.run(["npm", "pack", "--silent"], cwd=work, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
    tarballs = list(work.glob("*.tgz"))
    assert len(tarballs) == 1, tarballs
    with tarfile.open(tarballs[0]) as t:
        return tarballs[0], t.getnames()


def test_every_file_package_json_lists_exists(tmp_path):
    # The root cause: "files" named a file that was not there, and npm did not complain.
    listed = json.loads((JS_DIR / "package.json").read_text(encoding="utf-8"))["files"]
    missing = [f for f in listed if not (JS_DIR / f).exists()]
    assert missing == [], f"package.json lists files that do not exist: {missing}"


def test_npm_pack_includes_the_registry_and_it_is_the_current_one(tmp_path):
    tarball, names = _pack(tmp_path)
    assert "package/iso4217.json" in names, names
    for needed in ("package/index.js", "package/index.d.ts", "package/README.md", "package/package.json"):
        assert needed in names, (needed, names)
    with tarfile.open(tarball) as t:
        packed = t.extractfile("package/iso4217.json").read()
    assert packed == (PROJECT_ROOT / "iso4217.json").read_bytes(), "the packed registry is not the root registry"


def test_the_packed_package_loads_its_own_data_from_an_empty_directory(tmp_path):
    tarball, _ = _pack(tmp_path)
    app = tmp_path / "app"
    (app / "node_modules" / "iso4217-registry").mkdir(parents=True)
    with tarfile.open(tarball) as t:
        t.extractall(tmp_path / "unpacked")
    shutil.copytree(tmp_path / "unpacked" / "package", app / "node_modules" / "iso4217-registry", dirs_exist_ok=True)
    script = ("const {CurrencyRegistry} = require('iso4217-registry');"
              "const r = new CurrencyRegistry(); console.log(r.currency('USD').code, r.version);")
    r = subprocess.run(["node", "-e", script], cwd=app, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] == "USD"
