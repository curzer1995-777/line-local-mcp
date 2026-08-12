from __future__ import annotations

import getpass
import importlib.resources
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import Settings
from .database import LineDatabase, LineDatabaseError


class BootstrapError(RuntimeError):
    pass


def _run_checked(command: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BootstrapError(f"Setup command failed: {Path(command[0]).name}") from exc


def _snapshot_for_verification(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{source}{suffix}")
        if candidate.exists():
            shutil.copy2(candidate, Path(f"{destination}{suffix}"))
    return destination


def _quoted_lldb_path(path: Path) -> str:
    return shlex.quote(str(path))


def setup_key() -> None:
    if platform.system() != "Darwin":
        raise BootstrapError("Key setup currently supports macOS only.")
    source_app = Path(os.environ.get("LINE_MCP_APP_PATH", "/Applications/LINE.app"))
    if not source_app.is_dir():
        raise BootstrapError("LINE Desktop was not found in /Applications.")
    for required in ("codesign", "lldb", "security"):
        if shutil.which(required) is None:
            raise BootstrapError(f"Required macOS tool is unavailable: {required}")

    settings = Settings.from_env()
    database = LineDatabase(settings)
    source_db = database.resolve_path()
    print("This one-time step opens a temporary LINE copy.")
    print("Sign in to the same LINE account whose local history you want to read.")
    print("The original LINE app and database will not be modified.")

    process_handle: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryDirectory(prefix="line-local-mcp-setup-") as temp_value:
        temp_dir = Path(temp_value)
        copied_app = temp_dir / "LINE Setup Copy.app"
        print("Preparing the temporary LINE copy...")
        shutil.copytree(source_app, copied_app, symlinks=True)

        entitlements_resource = importlib.resources.files("line_local_mcp").joinpath(
            "data/bootstrap_entitlements.plist"
        )
        scanner_resource = importlib.resources.files("line_local_mcp").joinpath("bootstrap_lldb.py")
        with (
            importlib.resources.as_file(entitlements_resource) as entitlements,
            importlib.resources.as_file(scanner_resource) as scanner,
        ):
            _run_checked(
                [
                    "codesign",
                    "--force",
                    "--deep",
                    "--sign",
                    "-",
                    "--entitlements",
                    str(entitlements),
                    str(copied_app),
                ]
            )
            executable = copied_app / "Contents/MacOS/LINE"
            try:
                try:
                    process_handle = subprocess.Popen(
                        [str(executable)],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except OSError as exc:
                    raise BootstrapError("The temporary LINE setup window did not start.") from exc
                process_id = process_handle.pid
                input("After the temporary LINE copy finishes signing in and chats appear, press Return: ")

                verify_snapshot = _snapshot_for_verification(source_db, temp_dir / "verify")
                environment = dict(os.environ)
                environment.update(
                    {
                        "LINE_MCP_BOOTSTRAP_PYTHON": sys.executable,
                        "LINE_MCP_VERIFY_SNAPSHOT": str(verify_snapshot),
                        "LINE_MCP_KEYCHAIN_ACCOUNT": getpass.getuser(),
                        "LINE_MCP_KEYCHAIN_SERVICE": settings.keychain_service,
                    }
                )
                try:
                    result = subprocess.run(
                        [
                            "lldb",
                            "-p",
                            str(process_id),
                            "-o",
                            f"command script import {_quoted_lldb_path(scanner)}",
                            "-o",
                            "line_local_mcp_find_key",
                            "-o",
                            "detach",
                            "-o",
                            "quit",
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env=environment,
                        timeout=240,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise BootstrapError("Timed out while verifying the temporary LINE copy.") from exc
                if "LINE_LOCAL_MCP_KEY_STORED" not in result.stdout:
                    raise BootstrapError(
                        "No matching LINE database key was found. Confirm the temporary copy used the same account."
                    )
            finally:
                if process_handle is not None and process_handle.poll() is None:
                    try:
                        process_handle.terminate()
                        process_handle.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process_handle.kill()
                        process_handle.wait(timeout=10)
    print("LINE database key verified and stored in macOS Keychain.")
