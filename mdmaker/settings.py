"""Load input/output from config.json (VS Code / offline run, no CLI args)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS: dict[str, Any] = {
    "input": "",
    "input_root": "input",
    "output_root": "output",
    "output_llm": "llm",
    "output_reading": "reading",
    "purpose": "all",
    "title": None,
    "report": True,
    "table_images": True,
    "figure_images": True,
    "overwrite": False,
    "persian_digits": False,
    "split_llm": False,
}

INVALID_DIR_CHARS = '<>:"/\\|?*'
SUPPORTED_SUFFIXES = {".pdf", ".docx"}
PURPOSES = ("llm", "reading")


def load_config() -> dict[str, Any]:
    data = dict(DEFAULTS)
    if CONFIG_PATH.is_file():
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data.update(loaded)
    raw_input = data.get("input")
    if isinstance(raw_input, str) and raw_input.strip():
        data["input"] = _resolve(raw_input.strip())
    else:
        data["input"] = None
    data["input_root"] = _resolve(data.get("input_root") or "input")
    data["output_root"] = _resolve(data.get("output_root") or "output")
    purpose = str(data.get("purpose") or "all").strip().lower()
    if purpose not in {"llm", "reading", "all"}:
        purpose = "all"
    data["purpose"] = purpose
    data["purposes"] = PURPOSES if purpose == "all" else (purpose,)
    data["table_images"] = _as_bool(data.get("table_images"), True)
    data["figure_images"] = _as_bool(data.get("figure_images"), True)
    data["overwrite"] = _as_bool(data.get("overwrite"), False)
    data["persian_digits"] = _as_bool(data.get("persian_digits"), False)
    data["split_llm"] = _as_bool(data.get("split_llm"), False)
    return data


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def selected_purposes(cfg: dict[str, Any]) -> tuple[str, ...]:
    return tuple(cfg.get("purposes") or ("llm", "reading"))


def collect_inputs(cfg: dict[str, Any]) -> list[Path]:
    src = cfg.get("input")
    if src is not None:
        path = Path(src)
        if not path.is_file():
            raise FileNotFoundError(f"Input not found: {path}")
        return [path]
    root = Path(cfg["input_root"])
    if not root.is_dir():
        raise FileNotFoundError(
            f"input is empty and input_root does not exist: {root}"
        )
    files = sorted(
        p for p in root.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        raise FileNotFoundError(f"No PDF/DOCX files in {root}")
    return files


def job_folder_name(stem: str) -> str:
    name = "".join("_" if c in INVALID_DIR_CHARS else c for c in stem).strip(" .")
    return name or "document"


def unique_job_dir(parent: Path, stem: str) -> Path:
    """parent/input_file, then parent/input_file(2), parent/input_file(3), ..."""
    base = job_folder_name(stem)
    candidate = parent / base
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = parent / f"{base}({n})"
        if not candidate.exists():
            return candidate
        n += 1


def branch_root(cfg: dict[str, Any], purpose: str) -> Path:
    """output_root / output_llm  (or an absolute path if configured that way)."""
    key = "output_llm" if purpose == "llm" else "output_reading"
    name = cfg.get(key) or purpose
    path = Path(str(name))
    if path.is_absolute():
        return path
    return Path(cfg["output_root"]) / path


def output_layout(input_path: Path, cfg: dict[str, Any], purpose: str) -> dict[str, Any]:
    """
    output/llm/<input_file>/
      <input_file>.md
      assets/...
    """
    job = job_folder_name(input_path.stem)
    parent = branch_root(cfg, purpose)
    if cfg.get("overwrite"):
        job_dir = parent / job
    else:
        job_dir = unique_job_dir(parent, input_path.stem)
    assets_dir = job_dir / "assets"
    return {
        "purpose": purpose,
        "job": job,
        "job_dir": job_dir,
        "assets_dir": assets_dir,
        "markdown": job_dir / f"{job}.md",
        "assets_rel": "assets",
    }


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path
