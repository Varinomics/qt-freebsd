#!/usr/bin/env python3
"""Publishable Qt SDK identity, acquisition and FreeBSD installation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request


REPOSITORY = "Varinomics/qt-freebsd"
PREFIX = Path("/opt/qt-freebsd")
ARCHIVE = "qt-freebsd-15-amd64.tar.xz"
COMPONENTS = (
    "Core", "Gui", "GuiPrivate", "Qml", "Quick", "QuickControls2",
    "QuickLayouts", "QuickShapes", "ShaderTools", "Test",
)
MODULES = ("qtbase", "qtdeclarative", "qtshadertools")


def version(value):
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", value):
        raise ValueError(f"Expected a released numeric version, received {value!r}")
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (3 - len(parts))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def validate_manifest(manifest, minimum):
    if manifest["format"] != "qt-freebsd-sdk-1":
        raise ValueError("Unsupported Qt SDK manifest format")
    if manifest["abi"] != "FreeBSD:15:amd64" or manifest["prefix"] != str(PREFIX):
        raise ValueError("The published SDK has an incompatible ABI or installation prefix")
    if version(manifest["qt_version"])[0] != 6:
        raise ValueError("This SDK consumer requires the Qt 6 integration generation")
    if version(manifest["qt_version"]) < version(minimum):
        raise ValueError(f"Published Qt {manifest['qt_version']} does not satisfy Qt >= {minimum}")
    if not set(MODULES).issubset(manifest["modules"]):
        raise ValueError("The SDK is missing required Qt source modules")
    if not set(COMPONENTS).issubset(manifest["components"]):
        raise ValueError("The SDK is missing required Qt CMake components")
    if manifest["configuration"] != "shared-release-desktop-opengl-xcb":
        raise ValueError("The SDK does not provide the required shared desktop Qt configuration")
    if manifest["archive"]["name"] != ARCHIVE:
        raise ValueError("Unexpected SDK archive name")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest["archive"]["sha256"]):
        raise ValueError("Invalid SDK archive checksum")
    packages = manifest["runtime_packages"]
    if not packages or not all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+.-]*", item) for item in packages):
        raise ValueError("Invalid runtime package list")


def verify_files(directory, minimum):
    manifest = json.loads((directory / "sdk.json").read_text(encoding="utf-8"))
    validate_manifest(manifest, minimum)
    checksums = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        checksums[name] = digest
    for name in ("sdk.json", ARCHIVE):
        if sha256(directory / name) != checksums.get(name):
            raise ValueError(f"Checksum mismatch for {name}")
    if checksums[ARCHIVE] != manifest["archive"]["sha256"]:
        raise ValueError("SDK manifest and checksum file disagree")
    return manifest


def download(url, path):
    # Public asset requests carry no credential through GitHub's CDN redirect.
    with urllib.request.urlopen(url, timeout=120) as response, path.open("wb") as stream:
        shutil.copyfileobj(response, stream)


def fetch(args):
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", os.getcwd())).resolve()
    directory = (workspace / args.directory).resolve()
    if directory == workspace or not directory.is_relative_to(workspace):
        raise ValueError("The SDK directory must be a child of the consumer workspace")
    version(args.minimum_qt_version)
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "qt-freebsd-sdk"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPOSITORY}/releases/latest", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError(
                f"No Qt SDK release is available from {REPOSITORY}. "
                "Publish a compatible SDK using its manual producer; this action never builds Qt.") from error
        raise
    if release["draft"] or release["prerelease"]:
        raise ValueError("The selected SDK release is not a completed stable publication")
    assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
    required = ("sdk.json", "SHA256SUMS", ARCHIVE)
    missing = set(required) - assets.keys()
    if missing:
        raise ValueError(f"Release {release['tag_name']} is incomplete: missing {sorted(missing)}")
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qt-freebsd-download-", dir=directory) as scratch:
        staging = Path(scratch)
        for name in required:
            download(assets[name], staging / name)
        manifest = verify_files(staging, args.minimum_qt_version)
        if manifest["release"] != release["tag_name"]:
            raise ValueError("SDK manifest belongs to a different release")
        for name in required:
            (staging / name).replace(directory / name)
    shutil.copyfile(Path(__file__).resolve(), directory / "sdk.py")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"directory={directory}\nprefix={PREFIX}\nrelease={release['tag_name']}\n")
    print(f"Acquired Qt {manifest['qt_version']} from {REPOSITORY}@{release['tag_name']}")


def check_installation(prefix):
    for component in COMPONENTS:
        config = prefix / "lib/cmake" / f"Qt6{component}" / f"Qt6{component}Config.cmake"
        if not config.is_file():
            raise ValueError(f"SDK component is absent: {config}")
    for name in ("bin/qtpaths", "bin/qsb", "plugins/platforms/libqxcb.so", "plugins/platforms/libqoffscreen.so"):
        if not (prefix / name).is_file():
            raise ValueError(f"Required Qt SDK file is absent: {name}")


def install(args):
    manifest = verify_files(args.directory.resolve(), args.minimum_qt_version)
    if platform.system() != "FreeBSD" or platform.machine() != "amd64":
        raise ValueError("This SDK must be installed in a FreeBSD amd64 environment")
    if command("pkg", "config", "ABI") != manifest["abi"]:
        raise ValueError("The VM's package ABI does not match the SDK")
    userland = command("freebsd-version", "-u")
    baseline = manifest["freebsd_userland"]
    if version(userland.split("-", 1)[0]) < version(baseline.split("-", 1)[0]):
        raise ValueError(f"SDK requires FreeBSD >= {baseline}; the VM has {userland}")
    if PREFIX.exists():
        raise ValueError(f"Refusing to mix this SDK with an existing installation at {PREFIX}")
    subprocess.run(["pkg", "install", "-y", *manifest["runtime_packages"]], check=True)
    PREFIX.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="qt-freebsd-install-", dir=PREFIX.parent) as scratch:
        staging = Path(scratch) / "qt"
        staging.mkdir()
        with tarfile.open(args.directory / ARCHIVE, "r:xz") as archive:
            archive.extractall(staging, filter="data")
        check_installation(staging)
        identity = json.loads((staging / "source-build-identity.json").read_text(encoding="utf-8"))
        if identity != {key: value for key, value in manifest.items() if key != "archive"}:
            raise ValueError("Installed SDK identity differs from the release manifest")
        staging.rename(PREFIX)
    actual_version = command(str(PREFIX / "bin/qtpaths"), "--qt-version")
    if actual_version != manifest["qt_version"]:
        raise ValueError(f"Installed Qt {actual_version} differs from its published identity")
    for library in ("lib/libQt6Core.so", "lib/libQt6Gui.so", "lib/libQt6Quick.so", "plugins/platforms/libqxcb.so"):
        dependencies = command("ldd", str(PREFIX / library))
        if "not found" in dependencies:
            raise ValueError(f"Unresolved runtime dependency for {library}:\n{dependencies}")
    print(f"Installed Qt {actual_version} ({manifest['release']}) at {PREFIX}")


def package(args):
    if platform.system() != "FreeBSD" or command("pkg", "config", "ABI") != "FreeBSD:15:amd64":
        raise ValueError("The SDK producer requires FreeBSD:15:amd64")
    check_installation(PREFIX)
    qt_version = command(str(PREFIX / "bin/qtpaths"), "--qt-version")
    if qt_version != args.qt_version or version(qt_version) < version("6.12"):
        raise ValueError("Installed Qt does not match the selected source or required minimum")
    if sha256(args.source_archive) != args.source_sha256:
        raise ValueError("Qt source archive checksum mismatch")
    source_url = (
        f"https://download.qt.io/official_releases/qt/{'.'.join(qt_version.split('.')[:2])}/"
        f"{qt_version}/single/{args.source_archive.name}")
    runtime_packages = args.runtime_packages.read_text(encoding="utf-8").split()
    identity = {
        "format": "qt-freebsd-sdk-1",
        "release": args.release,
        "qt_version": qt_version,
        "source_url": source_url,
        "source_sha256": args.source_sha256,
        "source_asset": args.source_archive.name,
        "producer_revision": os.environ["GITHUB_SHA"],
        "producer_run": f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
        "abi": "FreeBSD:15:amd64",
        "freebsd_userland": command("freebsd-version", "-u"),
        "compiler": command("c++", "--version"),
        "configuration": "shared-release-desktop-opengl-xcb",
        "modules": list(MODULES),
        "components": list(COMPONENTS),
        "prefix": str(PREFIX),
        "runtime_packages": runtime_packages,
        "installed_packages": command("pkg", "query", "%n-%v").splitlines(),
    }
    write_json(PREFIX / "source-build-identity.json", identity)
    args.directory.mkdir(parents=True, exist_ok=True)
    archive_path = args.directory / ARCHIVE
    with tarfile.open(archive_path, "w:xz", preset=6) as archive:
        archive.add(PREFIX, arcname=".")
    manifest = {**identity, "archive": {"name": ARCHIVE, "sha256": sha256(archive_path)}}
    validate_manifest(manifest, "6.12")
    write_json(args.directory / "sdk.json", manifest)
    source_output = args.directory / args.source_archive.name
    if args.source_archive.resolve() != source_output.resolve():
        shutil.copyfile(args.source_archive, source_output)
    assets = (archive_path, args.directory / "sdk.json", source_output)
    for asset in assets:
        if asset.stat().st_size >= 2 * 1024**3:
            raise ValueError(f"Release asset exceeds GitHub's 2 GiB limit: {asset.name}")
    (args.directory / "SHA256SUMS").write_text(
        "".join(f"{sha256(asset)}  {asset.name}\n" for asset in assets), encoding="utf-8")
    print(f"Packaged Qt {qt_version} as {archive_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("fetch", fetch), ("install", install), ("package", package)):
        child = commands.add_parser(name)
        child.set_defaults(handler=handler)
        child.add_argument("--directory", type=Path, required=True)
        if name in ("fetch", "install"):
            child.add_argument("--minimum-qt-version", required=True)
        else:
            child.add_argument("--qt-version", required=True)
            child.add_argument("--source-sha256", required=True)
            child.add_argument("--source-archive", type=Path, required=True)
            child.add_argument("--runtime-packages", type=Path, required=True)
            child.add_argument("--release", required=True)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print(f"qt-freebsd: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
