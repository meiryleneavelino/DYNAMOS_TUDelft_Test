import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKUP = ROOT / "configuration" / "federated-training" / ".local" / "rollback"
MANIFEST = BACKUP / "manifest.json"
ORIGINALS = {
    ".gitignore": ".gitignore",
    "charts/agents/values.yaml": "charts/agents/values.yaml",
    "charts/namespaces/values.yaml": "charts/namespaces/values.yaml",
    "horus-sandbox-frontend/src/App.tsx": "App.tsx",
    "horus-sandbox-frontend/src/components/Sidebar.tsx": "Sidebar.tsx",
    "horus-sandbox-frontend/vite.config.ts": "vite.config.ts",
    "horus-sandbox-frontend/package.json": "package.json",
    "horus-sandbox-frontend/package-lock.json": "package-lock.json",
}
ADDITIONS = (
    "charts/agents/templates/tudelft.yaml",
    "charts/namespaces/templates/tudelft.yaml",
    "horus-sandbox-frontend/src/pages/FederatedTraining.tsx",
    "docs/development_guide/federated_training.md",
)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(source):
    if MANIFEST.exists():
        raise RuntimeError("Rollback snapshot already exists; refusing to replace it")
    manifest = []
    for relative, original in ORIGINALS.items():
        target = BACKUP / "originals" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / original, target)
        manifest.append({"path": relative, "action": "restore", "expected": checksum(ROOT / relative),
                         "original_checksum": checksum(target)})
    additions = set(ADDITIONS)
    for relative in ("python/federated-training", "charts/federated-training", "configuration/federated-training"):
        for path in (ROOT / relative).rglob("*"):
            if path.is_file() and ".local" not in path.parts and "__pycache__" not in path.parts:
                additions.add(path.relative_to(ROOT).as_posix())
    for relative in sorted(additions):
        manifest.append({"path": relative, "action": "remove", "expected": checksum(ROOT / relative)})
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved reversible snapshot for {len(manifest)} files. Your previous changes are preserved.")


def rollback(apply):
    if not MANIFEST.exists():
        raise RuntimeError("Rollback snapshot is missing")
    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest:
        path = ROOT / entry["path"]
        if not path.is_file() or checksum(path) != entry["expected"]:
            raise RuntimeError(f"File changed after snapshot; nothing was modified: {entry['path']}")
        if entry["action"] == "restore":
            original = BACKUP / "originals" / entry["path"]
            if not original.is_file() or checksum(original) != entry["original_checksum"]:
                raise RuntimeError(f"Original backup is invalid: {entry['path']}")
    for entry in manifest:
        print(f"{entry['action']}: {entry['path']}")
    if not apply:
        print("Preview only. Use --apply after stopping the frontend and port-forward.")
        return
    for entry in manifest:
        path = ROOT / entry["path"]
        if entry["action"] == "restore":
            shutil.copy2(BACKUP / "originals" / entry["path"], path)
        else:
            path.unlink()
    print("Code restored. Cluster, models and datasets were NOT deleted.")


def main():
    parser = argparse.ArgumentParser(description="Undo only this prototype; refuse if files changed afterwards")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    arguments = parser.parse_args()
    if arguments.snapshot:
        snapshot(arguments.snapshot)
    else:
        rollback(arguments.apply)


if __name__ == "__main__":
    main()