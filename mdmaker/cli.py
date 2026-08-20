"""Run from VS Code or: python run.py  (paths come from config.json)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .convert import convert_both
from .postprocess import has_persian, to_persian_digits, write_llm_parts, yaml_header
from .settings import collect_inputs, load_config, output_layout, selected_purposes


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    purposes = selected_purposes(cfg)
    try:
        sources = collect_inputs(cfg)
    except FileNotFoundError as exc:
        print(exc)
        print("Set input or input_root in config.json")
        return 1

    failures: list[str] = []
    for src in sources:
        print(f"=== {src.name} ===")
        try:
            convert_one(src, cfg, purposes)
        except Exception as exc:
            failures.append(f"{src}: {exc}")
            print(f"Failed: {exc}")
    if failures:
        print("Failures:")
        for item in failures:
            print(f"  - {item}")
        return 1
    return 0


def convert_one(src, cfg, purposes: tuple[str, ...] | None = None, *, quiet: bool = False) -> dict:
    """Convert one PDF/DOCX. Returns output paths, markdown text, and warnings."""
    purposes = purposes or selected_purposes(cfg)
    overwrite = bool(cfg.get("overwrite"))
    layouts = {purpose: output_layout(src, cfg, purpose) for purpose in purposes}
    jobs = {}
    for purpose, layout in layouts.items():
        _prepare_job_dir(layout, overwrite)
        jobs[purpose] = layout["assets_dir"]
        if not quiet:
            print(f"{purpose}: {layout['job_dir']}")
    bundle = convert_both(
        src,
        title=cfg.get("title"),
        jobs=jobs,
        images_rel="assets",
        purposes=purposes,
        table_images=bool(cfg.get("table_images", True)),
        figure_images=bool(cfg.get("figure_images", True)),
    )
    outputs = []
    for purpose, layout in layouts.items():
        md = bundle["texts"][purpose]
        title = cfg.get("title") or src.stem
        md = yaml_header(
            title=title,
            source=src,
            purpose=purpose,
            tables=int(bundle.get("table_count") or 0),
            figures=len(bundle.get("figure_names") or []),
            lang="fa" if has_persian(md) else "und",
        ) + md
        if cfg.get("persian_digits"):
            md = to_persian_digits(md)
        layout["markdown"].write_text(md, encoding="utf-8")
        if not quiet:
            print(f"  wrote {layout['markdown']}")
        parts = []
        if purpose == "llm" and cfg.get("split_llm"):
            parts = [str(p) for p in write_llm_parts(md, layout["job_dir"])]
            if not quiet:
                for part in parts:
                    print(f"  wrote {part}")
        log_path = _write_convert_log(src, cfg, purpose, layout, bundle)
        if not quiet:
            print(f"  wrote {log_path}")
        outputs.append(
            {
                "purpose": purpose,
                "path": str(layout["markdown"]),
                "folder": str(layout["job_dir"]),
                "markdown": md,
                "parts": parts,
            }
        )
    if not quiet and bundle["warnings"]:
        print("Warnings:")
        for w in bundle["warnings"]:
            print(f"  - {w}")
    if not quiet and cfg.get("report"):
        for key, fmap in bundle["maps"].items():
            named = sum(1 for g in fmap.glyphs.values() if g.unicode)
            print(
                f"{key}: {fmap.name} method={fmap.method} mapped={named}/{len(fmap.glyphs)} broken_tu={fmap.broken_tounicode}"
            )
    return {
        "outputs": outputs,
        "warnings": list(bundle.get("warnings") or []),
        "table_count": int(bundle.get("table_count") or 0),
        "figure_names": list(bundle.get("figure_names") or []),
    }


def _prepare_job_dir(layout: dict, overwrite: bool) -> None:
    job_dir = layout["job_dir"]
    if overwrite and job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    layout["assets_dir"].mkdir(parents=True, exist_ok=True)


def _write_convert_log(src: Path, cfg: dict, purpose: str, layout: dict, bundle: dict) -> Path:
    log_path = layout["job_dir"] / "convert.log"
    lines = [
        f"input: {src}",
        f"purpose: {purpose}",
        f"output: {layout['markdown']}",
        f"overwrite: {bool(cfg.get('overwrite'))}",
        f"table_images: {bool(cfg.get('table_images', True))}",
        f"figure_images: {bool(cfg.get('figure_images', True))}",
        f"persian_digits: {bool(cfg.get('persian_digits'))}",
        f"split_llm: {bool(cfg.get('split_llm'))}",
        f"tables: {bundle.get('table_count', 0)} reconstructed",
        f"table PNGs: {', '.join(bundle.get('table_names') or []) or '-'}",
        f"figure PNGs: {', '.join(bundle.get('figure_names') or []) or '-'}",
        "",
        "warnings:",
    ]
    warnings = bundle.get("warnings") or []
    if warnings:
        lines.extend(f"  - {w}" for w in warnings)
    else:
        lines.append("  (none)")
    maps = bundle.get("maps") or {}
    if maps:
        lines.append("")
        lines.append("fonts:")
        for key, fmap in maps.items():
            named = sum(1 for g in fmap.glyphs.values() if g.unicode)
            lines.append(
                f"  {key}: {fmap.name} method={fmap.method} "
                f"mapped={named}/{len(fmap.glyphs)} broken_tounicode={fmap.broken_tounicode}"
            )
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


if __name__ == "__main__":
    raise SystemExit(main())
