from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nibabel as nib
from nibabel.processing import resample_from_to
import numpy as np


def _strip_nii_gz(filename: str) -> str:
    if filename.endswith(".nii.gz"):
        return filename[: -len(".nii.gz")]
    return Path(filename).stem


def parse_bids_entities(filename: str) -> dict[str, str]:
    stem = _strip_nii_gz(filename)
    parts = stem.split("_")
    entities: dict[str, str] = {}
    if not parts:
        return entities

    # last component without '-' is treated as suffix (e.g., bold, boldref, T1w)
    if "-" not in parts[-1]:
        entities["suffix"] = parts[-1]

    for part in parts:
        if "-" not in part:
            continue
        key, value = part.split("-", 1)
        entities[key] = value
    return entities


@dataclass(frozen=True)
class Selection:
    space: str | None = None
    desc: str | None = "preproc"
    suffix: str | None = "bold"
    extension: str = ".nii.gz"
    subjects: list[str] | None = None
    sessions: list[str] | None = None
    tasks: list[str] | None = None
    runs: list[str] | None = None


def _as_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def selection_from_config(cfg: dict[str, Any]) -> Selection:
    select_cfg = cfg.get("select", {}) or {}
    if not isinstance(select_cfg, dict):
        raise ValueError("extract.select must be a mapping")

    return Selection(
        space=select_cfg.get("space"),
        desc=select_cfg.get("desc", "preproc"),
        suffix=select_cfg.get("suffix", "bold"),
        extension=select_cfg.get("extension", ".nii.gz"),
        subjects=_as_list(select_cfg.get("subjects")),
        sessions=_as_list(select_cfg.get("sessions")),
        tasks=_as_list(select_cfg.get("tasks")),
        runs=_as_list(select_cfg.get("runs")),
    )


@dataclass(frozen=True)
class ROIMask:
    name: str
    path: Path
    kind: str = "mask"  # mask|labels
    labels: list[int] | None = None
    resample: str = "nearest"  # nearest|none
    outputs: dict[str, bool] | None = None  # mean_timeseries|voxel_timeseries|masked_volume


def _load_roi_masks(extract_cfg: dict[str, Any]) -> list[ROIMask]:
    roi_cfg = extract_cfg.get("roi")
    if not roi_cfg:
        return []
    if not isinstance(roi_cfg, dict):
        raise ValueError("extract.roi must be a mapping")

    if not bool(roi_cfg.get("enabled", False)):
        return []

    masks_cfg = roi_cfg.get("masks", []) or []
    if not isinstance(masks_cfg, list):
        raise ValueError("extract.roi.masks must be a list")

    masks: list[ROIMask] = []
    for item in masks_cfg:
        if not isinstance(item, dict):
            raise ValueError("Each extract.roi.masks item must be a mapping")
        name = str(item.get("name") or "")
        path = item.get("path")
        if not name or not path:
            raise ValueError("Each ROI mask requires name and path")

        kind = str(item.get("kind", "mask")).lower()
        if kind not in ("mask", "labels"):
            raise ValueError(f"Unsupported ROI kind: {kind} (expected mask|labels)")

        labels_raw = item.get("labels")
        labels = [int(v) for v in labels_raw] if labels_raw is not None else None

        resample = str(item.get("resample", "nearest")).lower()
        if resample not in ("nearest", "none"):
            raise ValueError(f"Unsupported resample: {resample} (expected nearest|none)")

        outputs = item.get("outputs")
        if outputs is None:
            outputs = {"mean_timeseries": True, "voxel_timeseries": False, "masked_volume": False}
        if not isinstance(outputs, dict):
            raise ValueError("ROI outputs must be a mapping")
        outputs_bool = {str(k): bool(v) for k, v in outputs.items()}

        masks.append(
            ROIMask(
                name=name,
                path=Path(path),
                kind=kind,
                labels=labels,
                resample=resample,
                outputs=outputs_bool,
            )
        )
    return masks


def _match_one(entities: dict[str, str], key: str, allowed: list[str] | None) -> bool:
    if allowed is None:
        return True
    value = entities.get(key)
    if value is None:
        return False
    return value in allowed


def is_selected(path: Path, sel: Selection) -> bool:
    if not path.name.endswith(sel.extension):
        return False
    entities = parse_bids_entities(path.name)

    if sel.space and entities.get("space") != sel.space:
        return False
    if sel.desc and entities.get("desc") != sel.desc:
        return False
    if sel.suffix and entities.get("suffix") != sel.suffix:
        return False

    if not _match_one(entities, "sub", sel.subjects):
        return False
    if not _match_one(entities, "ses", sel.sessions):
        return False
    if not _match_one(entities, "task", sel.tasks):
        return False
    if not _match_one(entities, "run", sel.runs):
        return False

    return True


def iter_selected_niftis(fmriprep_dir: Path, sel: Selection) -> list[Path]:
    if not fmriprep_dir.exists():
        raise FileNotFoundError(f"fmriprep_dir not found: {fmriprep_dir}")
    candidates = [p for p in fmriprep_dir.rglob(f"*{sel.extension}") if p.is_file()]
    return [p for p in candidates if is_selected(p, sel)]


def _transpose_to_txyz(data: np.ndarray) -> np.ndarray:
    if data.ndim != 4:
        return data
    # nifti convention: (x, y, z, t) -> (t, x, y, z)
    return np.moveaxis(data, -1, 0)


def extract_one(
    nifti_path: Path,
    *,
    out_path: Path,
    dtype: str = "float32",
    transpose: str = "txyz",
) -> None:
    img = nib.load(str(nifti_path))
    data = img.get_fdata(dtype=np.dtype(dtype))
    if transpose.lower() == "txyz":
        data = _transpose_to_txyz(data)
    elif transpose.lower() in ("none", "xyzt"):
        pass
    else:
        raise ValueError(f"Unsupported transpose: {transpose} (expected txyz|xyzt|none)")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, data=data)

    tr = None
    try:
        zooms = img.header.get_zooms()
        if len(zooms) >= 4:
            tr = float(zooms[3])
    except Exception:
        tr = None

    meta = {
        "source_nifti": str(nifti_path),
        "saved_npz": str(out_path),
        "shape_saved": list(map(int, data.shape)),
        "dtype_saved": str(data.dtype),
        "affine": img.affine.tolist(),
        "tr": tr,
    }
    meta_path = out_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _roi_mask_to_func_space(
    *,
    roi_img: nib.spatialimages.SpatialImage,
    func_img: nib.spatialimages.SpatialImage,
    mode: str,
) -> nib.spatialimages.SpatialImage:
    if mode == "none":
        return roi_img
    if mode != "nearest":
        raise ValueError(f"Unsupported resample mode: {mode}")

    if roi_img.shape[:3] == func_img.shape[:3] and np.allclose(roi_img.affine, func_img.affine):
        return roi_img

    return resample_from_to(roi_img, (func_img.shape[:3], func_img.affine), order=0)


def _roi_boolean_mask(*, roi_data: np.ndarray, kind: str, labels: list[int] | None) -> np.ndarray:
    if roi_data.ndim != 3:
        raise ValueError(f"ROI mask/atlas must be 3D, got shape={roi_data.shape}")
    if kind == "mask":
        return roi_data != 0
    if kind == "labels":
        if not labels:
            return roi_data != 0
        return np.isin(roi_data.astype(np.int64, copy=False), np.asarray(labels, dtype=np.int64))
    raise ValueError(f"Unsupported ROI kind: {kind}")


def _roi_outputs_paths(volume_out_path: Path, roi_name: str) -> dict[str, Path]:
    stem = volume_out_path.stem  # already without .npz
    parent = volume_out_path.parent
    base = parent / f"{stem}_roi-{roi_name}"
    return {
        "mean_timeseries": base.with_name(base.name + "_stat-meanTs.npz"),
        "voxel_timeseries": base.with_name(base.name + "_stat-voxelTs.npz"),
        "masked_volume": base.with_name(base.name + "_desc-maskedVol.npz"),
    }


def extract_roi(
    *,
    nifti_path: Path,
    volume_out_path: Path,
    roi: ROIMask,
    dtype: str,
    transpose: str,
) -> list[Path]:
    func_img = nib.load(str(nifti_path))
    func_data = func_img.get_fdata(dtype=np.dtype(dtype))
    if func_data.ndim != 4:
        raise ValueError(f"Expected 4D functional image for ROI extraction, got shape={func_data.shape}: {nifti_path}")

    roi_path = roi.path.expanduser().resolve()
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI file not found: {roi_path}")

    roi_img = nib.load(str(roi_path))
    roi_img = _roi_mask_to_func_space(roi_img=roi_img, func_img=func_img, mode=roi.resample)
    roi_data = np.asanyarray(roi_img.dataobj)
    roi_mask = _roi_boolean_mask(roi_data=roi_data, kind=roi.kind, labels=roi.labels)

    vol_data = func_data
    if transpose.lower() == "txyz":
        vol_data = _transpose_to_txyz(vol_data)  # (t,x,y,z)
        roi_mask_broadcast = roi_mask[None, ...]
        t_dim = vol_data.shape[0]
        flat = vol_data.reshape(t_dim, -1)
        mask_flat = roi_mask.reshape(-1)
    elif transpose.lower() in ("none", "xyzt"):
        # (x,y,z,t)
        roi_mask_broadcast = roi_mask[..., None]
        t_dim = vol_data.shape[-1]
        flat = vol_data.reshape(-1, t_dim).T  # (t, nvox_all)
        mask_flat = roi_mask.reshape(-1)
    else:
        raise ValueError(f"Unsupported transpose: {transpose} (expected txyz|xyzt|none)")

    if int(mask_flat.sum()) == 0:
        raise ValueError(f"ROI '{roi.name}' selects 0 voxels after resampling")

    outputs = roi.outputs or {}
    out_paths = _roi_outputs_paths(volume_out_path, roi.name)
    written: list[Path] = []

    if outputs.get("voxel_timeseries", False) or outputs.get("mean_timeseries", False):
        vox_ts = flat[:, mask_flat]  # (t, nvox)

        if outputs.get("voxel_timeseries", False):
            p = out_paths["voxel_timeseries"]
            p.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(p, data=vox_ts)
            (p.with_suffix(".json")).write_text(
                json.dumps(
                    {
                        "source_nifti": str(nifti_path),
                        "roi_name": roi.name,
                        "roi_path": str(roi_path),
                        "kind": "voxel_timeseries",
                        "shape_saved": list(map(int, vox_ts.shape)),
                        "dtype_saved": str(vox_ts.dtype),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            written.append(p)

        if outputs.get("mean_timeseries", False):
            mean_ts = vox_ts.mean(axis=1)
            p = out_paths["mean_timeseries"]
            p.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(p, data=mean_ts)
            (p.with_suffix(".json")).write_text(
                json.dumps(
                    {
                        "source_nifti": str(nifti_path),
                        "roi_name": roi.name,
                        "roi_path": str(roi_path),
                        "kind": "mean_timeseries",
                        "shape_saved": list(map(int, mean_ts.shape)),
                        "dtype_saved": str(mean_ts.dtype),
                        "n_voxels": int(mask_flat.sum()),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            written.append(p)

    if outputs.get("masked_volume", False):
        masked = np.where(roi_mask_broadcast, vol_data, 0)
        p = out_paths["masked_volume"]
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(p, data=masked)
        (p.with_suffix(".json")).write_text(
            json.dumps(
                {
                    "source_nifti": str(nifti_path),
                    "roi_name": roi.name,
                    "roi_path": str(roi_path),
                    "kind": "masked_volume",
                    "shape_saved": list(map(int, masked.shape)),
                    "dtype_saved": str(masked.dtype),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        written.append(p)

    return written


def extract_arrays_from_fmriprep(*, fmriprep_dir: str | Path, out_dir: str | Path, extract_cfg: dict[str, Any]) -> list[Path]:
    fmriprep_dir = Path(fmriprep_dir)
    out_dir = Path(out_dir)

    selection = selection_from_config(extract_cfg)
    niftis = iter_selected_niftis(fmriprep_dir, selection)
    if not niftis:
        raise FileNotFoundError(f"No matching NIfTI found under {fmriprep_dir} (selection={selection})")

    output_cfg = extract_cfg.get("output", {}) or {}
    if not isinstance(output_cfg, dict):
        raise ValueError("extract.output must be a mapping")
    dtype = str(output_cfg.get("dtype", "float32"))
    transpose = str(output_cfg.get("transpose", "txyz"))
    roi_masks = _load_roi_masks(extract_cfg)

    written: list[Path] = []
    for nifti in niftis:
        rel = nifti.relative_to(fmriprep_dir)
        out_name = f"{_strip_nii_gz(rel.name)}.npz"
        out_path = out_dir / rel.parent / out_name
        extract_one(nifti, out_path=out_path, dtype=dtype, transpose=transpose)
        written.append(out_path)
        for roi in roi_masks:
            written.extend(extract_roi(nifti_path=nifti, volume_out_path=out_path, roi=roi, dtype=dtype, transpose=transpose))
    return written
