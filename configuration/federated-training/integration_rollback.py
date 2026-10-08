import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "configuration" / "federated-training" / ".local"
BACKUP = LOCAL / "integration-rollback"
MANIFEST = BACKUP / "manifest.json"
EXTRAS = (
    "go/pkg/training/training.go", "go/pkg/training/training_test.go",
    "go/cmd/api-gateway/training.go", "go/cmd/api-gateway/training_test.go",
    "go/cmd/orchestrator/training.go", "go/cmd/orchestrator/training_test.go",
    "go/cmd/agent/training.go", "go/cmd/agent/training_test.go",
    "python/federated-training/integration.py", "python/federated-training/test_integration.py",
    "charts/federated-training/templates/_helpers.tpl", "charts/federated-training/templates/dynamos.yaml",
    "configuration/federated-training/Dockerfile.go",
    "configuration/federated-training/test_integrated.py",
    "configuration/federated-training/integration_rollback.py",
    "docs/development_guide/dynamos_training_integration.md",
)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    if MANIFEST.exists():
        raise RuntimeError("Integration rollback snapshot already exists")
    entries = []
    with tarfile.open(LOCAL / "integration-before.tar.gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("Unsafe archive entry")
            current = ROOT / relative
            previous = archive.extractfile(member).read()
            if current.is_file() and current.read_bytes() != previous:
                original = BACKUP / "originals" / relative
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(previous)
                entries.append({"path": relative.as_posix(), "action": "restore", "expected": checksum(current),
                                "original": checksum(original)})
    with tarfile.open(LOCAL / "integration-sidecar-before.tar.gz") as archive:
        for relative in ("go/cmd/sidecar/main.go", "go/cmd/sidecar/rabbit_send.go", "go/cmd/sidecar/rabbit_ms_chain.go"):
            previous = archive.extractfile(relative).read()
            current = ROOT / relative
            if current.read_bytes() != previous:
                original = BACKUP / "originals" / relative
                original.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(previous)
                entries.append({"path": relative, "action": "restore", "expected": checksum(current), "original": checksum(original)})
    relative = "go/pkg/api/http.go"
    original = BACKUP / "originals" / relative
    original.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LOCAL / "integration-api-http.go", original)
    entries.append({"path": relative, "action": "restore", "expected": checksum(ROOT / relative), "original": checksum(original)})
    for relative in EXTRAS:
        if (ROOT / relative).is_file():
            entries.append({"path": relative, "action": "remove", "expected": checksum(ROOT / relative)})
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(entries, indent=2))
    print(f"Integration rollback recorded for {len(entries)} files")


def restore_infrastructure():
    from manage import DOCKER, tools, CONTEXT
    image = "dynamos-federated-training:standalone-restored"
    subprocess.run([DOCKER, "build", "-t", image, str(ROOT / "python" / "federated-training")], check=True)
    tools("kind", "load", "docker-image", image, "--name", "dynamos-training")
    tools("helm", "upgrade", "federated-training", "/workspace/charts/federated-training",
          "--kube-context", CONTEXT, "--namespace", "training-system", "--reuse-values",
          "--set", f"image={image}", "--force-conflicts", "--wait", "--timeout", "300s")
    access_path = LOCAL / "access.json"
    access = json.loads(access_path.read_text())
    access["url"] = "http://127.0.0.1:8095"
    access.pop("integration", None)
    access_path.write_text(json.dumps(access))
    print("Standalone sandbox restored; original DYNAMOS cluster was not modified.")


def rollback(apply, restore_cluster=False):
    entries = json.loads(MANIFEST.read_text())
    for entry in entries:
        current = ROOT / entry["path"]
        if not current.is_file() or checksum(current) != entry["expected"]:
            raise RuntimeError(f"Later edit detected; nothing changed: {entry['path']}")
        if entry["action"] == "restore" and checksum(BACKUP / "originals" / entry["path"]) != entry["original"]:
            raise RuntimeError("Original backup failed verification")
    for entry in entries:
        print(f"{entry['action']}: {entry['path']}")
    if not apply:
        print("Preview only. Stop frontend/forward before using --apply. Cluster and data are not modified.")
        return
    for entry in entries:
        path = ROOT / entry["path"]
        if entry["action"] == "restore":
            shutil.copy2(BACKUP / "originals" / entry["path"], path)
        else:
            path.unlink()
    print("Code restored to the standalone prototype; cluster and datasets were NOT deleted.")
    if restore_cluster:
        restore_infrastructure()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Undo only the DYNAMOS integration, preserving the previous prototype")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore-cluster", action="store_true")
    arguments = parser.parse_args()
    if arguments.snapshot:
        snapshot()
    else:
        rollback(arguments.apply, arguments.restore_cluster)