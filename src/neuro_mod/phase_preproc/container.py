from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class ContainerPaths:
    bids_dir: str = "/bids"
    out_dir: str = "/out"
    work_dir: str = "/work"
    fs_license_file: str = "/fs_license.txt"


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _ensure_abs(path: str) -> str:
    # Always resolve to absolute path and force forward slashes (Linux style)
    p = Path(path).expanduser().resolve()
    return str(p).replace("\\", "/")


def build_container_command(*, paths: dict, fmriprep: dict) -> list[str]:
    engine = str(fmriprep.get("engine", "singularity")).lower()
    image = fmriprep.get("image")
    if not image:
        raise ValueError("config.fmriprep.image is required")

    bids_dir = paths.get("bids_dir")
    derivatives_dir = paths.get("derivatives_dir")
    work_dir = paths.get("work_dir")
    if not bids_dir or not derivatives_dir or not work_dir:
        raise ValueError("config.paths.bids_dir / derivatives_dir / work_dir are required")

    participant_labels = _as_list(fmriprep.get("participant_labels"))
    extra_args = _as_list(fmriprep.get("extra_args"))
    fs_license_file = fmriprep.get("fs_license_file")
    container_paths = ContainerPaths()

    # NOTE:
    # Most fmriprep images already invoke `fmriprep` in the runscript/entrypoint.
    # Pass only arguments here to avoid accidentally doing `fmriprep fmriprep ...`.
    inner_cmd: list[str] = [
        container_paths.bids_dir,
        container_paths.out_dir,
        "participant",
        "-w",
        container_paths.work_dir,
    ]
    if participant_labels:
        inner_cmd.extend(["--participant-label", *participant_labels])
    if fs_license_file:
        inner_cmd.extend(["--fs-license-file", container_paths.fs_license_file])
    inner_cmd.extend(extra_args)

    bids_dir_abs = _ensure_abs(bids_dir)
    derivatives_dir_abs = _ensure_abs(derivatives_dir)
    work_dir_abs = _ensure_abs(work_dir)

    if engine != "singularity":
        raise ValueError(f"Unsupported engine: {engine} (expected singularity)")

    cleanenv = bool(fmriprep.get("cleanenv", True))
    cmd = ["singularity", "run"]
    if cleanenv:
        cmd.append("--cleanenv")
    cmd.extend(
        [
            "-B",
            f"{bids_dir_abs}:{container_paths.bids_dir}:ro",
            "-B",
            f"{derivatives_dir_abs}:{container_paths.out_dir}",
            "-B",
            f"{work_dir_abs}:{container_paths.work_dir}",
        ]
    )
    if fs_license_file:
        cmd.extend(["-B", f"{_ensure_abs(str(fs_license_file))}:{container_paths.fs_license_file}:ro"])
    cmd.append(str(image))
    cmd.extend(inner_cmd)
    return cmd


def format_command(cmd: Iterable[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_command(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    log_print: Callable[..., None] | None = None,
) -> None:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if log_print is None:
        subprocess.run(cmd, check=True, env=merged_env)
        return

    proc = subprocess.Popen(
        cmd,
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log_print(line, end="")
    ret = proc.wait()
    if ret != 0:
        raise subprocess.CalledProcessError(ret, cmd)


