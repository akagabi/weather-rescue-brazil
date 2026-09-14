"""Publish the dataset and the model to the Hugging Face Hub.

    python scripts/g4_publish.py --what both --dry-run     # show the payload
    python scripts/g4_publish.py --what dataset
    python scripts/g4_publish.py --what model --with-mlx

Stages the two repositories the Hub expects and uploads them:

    akagabi/weather-rescue-brazil            dataset
      README.md            the dataset card (from DATASET_CARD.md)
      LICENSE
      weather-rescue-brazil.jsonl
      profiles/*.json      the layout declarations, so the provenance travels

    akagabi/weather-rescue-brazil-reader     model
      README.md            the model card (from MODEL_CARD.md)
      gen3/  smoke4/  smoke2/            LoRA adapters
      mlx-q8/              packaged 8-bit model, --with-mlx

`gen3` is the adapter that produced the published dataset and it lives under
`runs/`, which git ignores - so it is copied from there, not from `models/`.
Shipping `models/` alone would ship the two adapters that did NOT make the
data, which is the kind of thing a model card is supposed to prevent.

The data file lands at the repository ROOT on the Hub (the Hub reads the front
matter of README.md for the config), so the card's `data_files` path is
rewritten for the upload and stays as the repo path locally.

Nothing is uploaded without `--yes`: creating a public repository is
outward-facing and effectively permanent.
"""

from __future__ import annotations

import argparse, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORG = "akagabi"
DATASET_REPO = f"{ORG}/weather-rescue-brazil"
MODEL_REPO = f"{ORG}/weather-rescue-brazil-reader"

ADAPTERS = {
    # name under models/ or runs/g4/  ->  path in the HF repo
    "gen3": ROOT / "runs" / "g4" / "gen3" / "epoch2",
    "smoke4": ROOT / "models" / "g4" / "qwen35-lora-smoke4-epoch2",
    "smoke2": ROOT / "models" / "g4" / "qwen35-lora-smoke2-epoch2",
}
MLX = ROOT / "runs" / "g4" / "mlx-smoke4-q8"

# Files worth carrying, and worth NOT carrying: raw page images stay out (the
# collection asks for attribution, not redistribution of its scans), as does
# anything under runs/ except the adapter and the packaged model.
DATASET_FILES = ["LICENSE", "data/dataset/weather-rescue-brazil.jsonl"]
DATASET_DIRS = ["profiles"]


def _card_with_hub_paths(card: Path, data_file: str) -> str:
    """The Hub reads data_files from the card's front matter, and the file sits
    at the repository root there - not at the path it has in this repo."""
    text = card.read_text()
    return text.replace("data_files: data/dataset/weather-rescue-brazil.jsonl",
                        f"data_files: {data_file}")


def stage_dataset(stage: Path) -> list[Path]:
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "README.md").write_text(
        _card_with_hub_paths(ROOT / "DATASET_CARD.md", "weather-rescue-brazil.jsonl"))
    for rel in DATASET_FILES:
        src = ROOT / rel
        dst = stage / Path(rel).name
        shutil.copy2(src, dst)
    for d in DATASET_DIRS:
        shutil.copytree(ROOT / d, stage / d, dirs_exist_ok=True)
    return sorted(p for p in stage.rglob("*") if p.is_file())


def stage_model(stage: Path, with_mlx: bool) -> list[Path]:
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "README.md").write_text((ROOT / "MODEL_CARD.md").read_text())
    (stage / "LICENSE").write_text((ROOT / "LICENSE").read_text())
    for name, src in ADAPTERS.items():
        if not src.exists():
            print(f"  !! adapter {name} missing at {src.relative_to(ROOT)} - skipped")
            continue
        dst = stage / name
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and f.suffix in (".safetensors", ".json"):
                shutil.copy2(f, dst / f.name)
    if with_mlx:
        if MLX.exists():
            shutil.copytree(MLX, stage / "mlx-q8", dirs_exist_ok=True)
        else:
            print("  !! --with-mlx asked for but no packaged model at runs/g4/mlx-smoke4-q8")
    return sorted(p for p in stage.rglob("*") if p.is_file())


def report(files: list[Path], stage: Path, label: str) -> int:
    total = sum(f.stat().st_size for f in files)
    print(f"\n{label}: {len(files)} files, {total / 1e6:.1f} MB")
    for f in files[:20]:
        print(f"   {str(f.relative_to(stage)):52s} {f.stat().st_size / 1e6:8.2f} MB")
    if len(files) > 20:
        print(f"   ... and {len(files) - 20} more")
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", choices=("dataset", "model", "both"), default="both")
    ap.add_argument("--with-mlx", action="store_true", help="include the 2.5 GB quantised model")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="actually upload; without it nothing leaves the machine")
    args = ap.parse_args()

    stage_root = ROOT / ".publish"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    planned = []
    if args.what in ("dataset", "both"):
        planned.append(("dataset", DATASET_REPO, stage_root / "dataset", stage_dataset(stage_root / "dataset")))
    if args.what in ("model", "both"):
        planned.append(("model", MODEL_REPO, stage_root / "model", stage_model(stage_root / "model", args.with_mlx)))

    for label, repo, stage, files in planned:
        report(files, stage, f"{label} -> {repo}")

    if args.dry_run or not args.yes:
        print("\nDRY RUN - nothing uploaded. Re-run with --yes to publish.")
        return

    from huggingface_hub import HfApi
    api = HfApi()
    who = api.whoami()
    print(f"\nlogged in as {who['name']}")
    anonymous = [r for _, r, _, _ in planned if not r.startswith(who["name"] + "/")]
    if anonymous and who["name"] != ORG:
        print(f"WARNING: {anonymous} are not under your namespace ({who['name']}) - "
              f"they will be created under {ORG} only if you have access")
    for label, repo, stage, _ in planned:
        api.create_repo(repo_id=repo, repo_type=("dataset" if label == "dataset" else "model"),
                        exist_ok=True)
        api.upload_folder(repo_id=repo, folder_path=str(stage),
                          repo_type=("dataset" if label == "dataset" else "model"),
                          commit_message=f"Publish {label} v0.1")
        print(f"uploaded {label}: https://huggingface.co/{'datasets/' if label == 'dataset' else ''}{repo}")


if __name__ == "__main__":
    main()
