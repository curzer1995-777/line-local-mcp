"""LLDB command loaded only into a temporary, user-authorized LINE copy."""

from __future__ import annotations

import os
import re
import subprocess

import lldb


PATTERNS = (
    re.compile(rb"(?i)([0-9a-f]{32}).{0,256}?mse"),
    re.compile(rb"(?i)mse.{0,256}?([0-9a-f]{32})"),
)


def _verify(candidate: bytes) -> bool:
    python = os.environ["LINE_MCP_BOOTSTRAP_PYTHON"]
    process = subprocess.run(
        [python, "-m", "line_local_mcp.verify_key"],
        input=candidate.decode("ascii"),
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ,
        timeout=10,
        check=False,
    )
    return process.returncode == 0


def _store(candidate: bytes) -> None:
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            os.environ["LINE_MCP_KEYCHAIN_ACCOUNT"],
            "-s",
            os.environ["LINE_MCP_KEYCHAIN_SERVICE"],
            "-w",
            candidate.decode("ascii"),
            "-U",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=True,
    )


def line_local_mcp_find_key(debugger, command, result, internal_dict):
    process = debugger.GetSelectedTarget().GetProcess()
    regions = process.GetMemoryRegions()
    error = lldb.SBError()
    seen: set[bytes] = set()
    scanned = 0
    candidates = 0

    for index in range(regions.GetSize()):
        region = lldb.SBMemoryRegionInfo()
        regions.GetMemoryRegionAtIndex(index, region)
        if not region.IsReadable():
            continue
        base = region.GetRegionBase()
        end = region.GetRegionEnd()
        if base == lldb.LLDB_INVALID_ADDRESS:
            continue
        size = end - base
        if size <= 0 or size > 64 * 1024 * 1024:
            continue

        offset = 0
        tail = b""
        while offset < size:
            chunk_size = min(4 * 1024 * 1024, size - offset)
            data = process.ReadMemory(base + offset, chunk_size, error)
            offset += chunk_size
            if not error.Success() or not data:
                continue
            scanned += len(data)
            buffer = tail + data
            tail = buffer[-512:]
            if b"mse" not in buffer.lower():
                continue
            for pattern in PATTERNS:
                for match in pattern.finditer(buffer):
                    candidate = match.group(1).lower()
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    candidates += 1
                    if _verify(candidate):
                        _store(candidate)
                        result.PutCString(
                            f"LINE_LOCAL_MCP_KEY_STORED scanned={scanned} candidates={candidates}"
                        )
                        return
    result.PutCString(
        f"LINE_LOCAL_MCP_KEY_NOT_FOUND scanned={scanned} candidates={candidates}"
    )


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand(
        "command script add -f bootstrap_lldb.line_local_mcp_find_key line_local_mcp_find_key"
    )
