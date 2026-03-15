from __future__ import annotations

import argparse
from pathlib import Path

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


def _warn_if_missing_fs_license(cfg: object) -> None:
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
    print("WARNING: FreeSurfer license not set. fmriprep typically requires it even with --fs-no-reconall.")
    print("         Set `fmriprep.fs_license_file` in the YAML config, or export `FS_LICENSE` on the host.")


def _cmd_run(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    _sanity_check_bids_niftis(Path(cfg.paths["bids_dir"]))
    _warn_if_missing_fs_license(cfg)
    Path(cfg.paths["derivatives_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg.paths["work_dir"]).mkdir(parents=True, exist_ok=True)
    cmd = build_container_command(paths=cfg.paths, fmriprep=cfg.fmriprep)
    if args.dry_run:
        print(format_command(cmd))
        return
    run_command(cmd)


def _cmd_extract(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    derivatives_dir = Path(cfg.paths["derivatives_dir"])
    fmriprep_dir = Path(cfg.extract.get("fmriprep_dir") or (derivatives_dir / "fmriprep"))
    out_dir = Path(cfg.paths["arrays_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    written = extract_arrays_from_fmriprep(fmriprep_dir=fmriprep_dir, out_dir=out_dir, extract_cfg=cfg.extract)
    print(f"Wrote {len(written)} file(s) under {out_dir}")


def _cmd_run_extract(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    _sanity_check_bids_niftis(Path(cfg.paths["bids_dir"]))
    _warn_if_missing_fs_license(cfg)
    Path(cfg.paths["derivatives_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg.paths["work_dir"]).mkdir(parents=True, exist_ok=True)
    cmd = build_container_command(paths=cfg.paths, fmriprep=cfg.fmriprep)
    if args.dry_run:
        print(format_command(cmd))
    else:
        run_command(cmd)

    derivatives_dir = Path(cfg.paths["derivatives_dir"])
    fmriprep_dir = Path(cfg.extract.get("fmriprep_dir") or (derivatives_dir / "fmriprep"))
    out_dir = Path(cfg.paths["arrays_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    written = extract_arrays_from_fmriprep(fmriprep_dir=fmriprep_dir, out_dir=out_dir, extract_cfg=cfg.extract)
    print(f"Wrote {len(written)} file(s) under {out_dir}")


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
    args.func(args)


if __name__ == "__main__":
    main()
