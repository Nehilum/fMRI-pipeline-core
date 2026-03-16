from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from .config import load_config
from .container import build_container_command, format_command, run_command
from .extract import extract_arrays_from_fmriprep


def _sanity_check_bids_niftis(bids_dir: Path, *, max_files: int = 50) -> None:
    if not bids_dir.exists():
        raise FileNotFoundError(f"BIDS dir not found: {bids_dir}")

    checked = 0
    for nifti in bids_dir.rglob("*.nii.gz"):
        if not nifti.is_file():
            continue
        checked += 1
        if nifti.stat().st_size == 0:
            raise ValueError(
                "Found a 0-byte NIfTI under bids_dir; fmriprep cannot run on empty placeholder files. "
                f"Example: {nifti}"
            )
        if checked >= max_files:
            break


def _warn_if_missing_fs_license(cfg: object, *, log_print: Callable[..., None] | None = None) -> None:
    try:
        fmriprep_cfg = getattr(cfg, "fmriprep")
    except Exception:
        return
    if not isinstance(fmriprep_cfg, dict):
        return
    if fmriprep_cfg.get("fs_license_file"):
        return
    # If the env var is set but not a host file, we still can't infer it here.
    # fmriprep will report details; we provide a short heads-up.
    import os

    if os.environ.get("FS_LICENSE"):
        return
    log = log_print or print
    log("WARNING: FreeSurfer license not set. fmriprep typically requires it even with --fs-no-reconall.")
    log("         Set `fmriprep.fs_license_file` in the YAML config, or export `FS_LICENSE` on the host.")


def _resolve_fmriprep_dir(cfg: object, *, log_print: Callable[..., None] | None = None) -> Path:
    try:
        paths = getattr(cfg, "paths")
        extract_cfg = getattr(cfg, "extract")
    except Exception as exc:
        raise ValueError("Invalid config: missing paths/extract") from exc

    if not isinstance(paths, dict) or not isinstance(extract_cfg, dict):
        raise ValueError("Invalid config: expected mappings at paths/extract")

    derivatives_dir = Path(paths["derivatives_dir"])
    explicit = extract_cfg.get("fmriprep_dir")
    fmriprep_dir = Path(explicit) if explicit else (derivatives_dir / "fmriprep")

    if fmriprep_dir.exists():
        return fmriprep_dir

    if derivatives_dir.exists():
        has_dataset_desc = (derivatives_dir / "dataset_description.json").exists()
        has_subjects = any(derivatives_dir.glob("sub-*"))
        if has_dataset_desc or has_subjects:
            log = log_print or print
            log(f"NOTE: fmriprep_dir not found at {fmriprep_dir}; using {derivatives_dir}")
            return derivatives_dir

    return fmriprep_dir


def _open_log_file(command: str) -> tuple[TextIO, Callable[..., None], Path]:
    log_dir = Path("outputs") / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{timestamp}_{command}.log"
    log_file = log_path.open("w", encoding="utf-8")

    def log_print(*args: object, **kwargs: object) -> None:
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        msg = str(sep).join(str(a) for a in args)
        print(msg, end=end, flush=True)
        log_file.write(msg + str(end))
        log_file.flush()

    return log_file, log_print, log_path


def _cmd_run(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    Path(cfg.paths["derivatives_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg.paths["work_dir"]).mkdir(parents=True, exist_ok=True)
    cmd = build_container_command(paths=cfg.paths, fmriprep=cfg.fmriprep)
    if args.dry_run:
        args.log_print(format_command(cmd))
        return
    _sanity_check_bids_niftis(Path(cfg.paths["bids_dir"]))
    _warn_if_missing_fs_license(cfg, log_print=args.log_print)
    run_command(cmd, log_print=args.log_print)


def _cmd_extract(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    fmriprep_dir = _resolve_fmriprep_dir(cfg, log_print=args.log_print)
    out_dir = Path(cfg.paths["arrays_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    written = extract_arrays_from_fmriprep(fmriprep_dir=fmriprep_dir, out_dir=out_dir, extract_cfg=cfg.extract)
    args.log_print(f"Wrote {len(written)} file(s) under {out_dir}")


def _cmd_run_extract(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    Path(cfg.paths["derivatives_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg.paths["work_dir"]).mkdir(parents=True, exist_ok=True)
    cmd = build_container_command(paths=cfg.paths, fmriprep=cfg.fmriprep)
    if args.dry_run:
        args.log_print(format_command(cmd))
        return

    _sanity_check_bids_niftis(Path(cfg.paths["bids_dir"]))
    _warn_if_missing_fs_license(cfg, log_print=args.log_print)
    run_command(cmd, log_print=args.log_print)

    fmriprep_dir = _resolve_fmriprep_dir(cfg, log_print=args.log_print)
    out_dir = Path(cfg.paths["arrays_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    written = extract_arrays_from_fmriprep(fmriprep_dir=fmriprep_dir, out_dir=out_dir, extract_cfg=cfg.extract)
    args.log_print(f"Wrote {len(written)} file(s) under {out_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fmri-modulation-fmriprep", add_help=True)
    parser.add_argument("--config", required=True, help="Path to YAML config")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run fmriprep container")
    run_p.add_argument("--dry-run", action="store_true", help="Print command only")
    run_p.set_defaults(func=_cmd_run)

    extract_p = sub.add_parser("extract", help="Extract (t,x,y,z) arrays from fmriprep outputs")
    extract_p.set_defaults(func=_cmd_extract)

    run_extract_p = sub.add_parser("run-extract", help="Run fmriprep then extract arrays")
    run_extract_p.add_argument("--dry-run", action="store_true", help="Print fmriprep command only (still extracts)")
    run_extract_p.set_defaults(func=_cmd_run_extract)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    log_file, log_print, _ = _open_log_file(args.command)
    try:
        args.log_print = log_print
        args.func(args)
    except Exception:
        log_print(traceback.format_exc(), end="")
        sys.exit(1)
    finally:
        log_file.close()


if __name__ == "__main__":
    main()
