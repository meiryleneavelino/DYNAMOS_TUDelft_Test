import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLUSTER = "dynamos-training"
CONTEXT = f"kind-{CLUSTER}"
IMAGE = "dynamos-federated-training:local"
DYNAMOS_IMAGE = "dynamos-integrated-services:local"
LOCAL = ROOT / "configuration" / "federated-training" / ".local"
DESKTOP_DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
DOCKER = os.getenv("DOCKER_BIN", DESKTOP_DOCKER if Path(DESKTOP_DOCKER).exists() else shutil.which("docker"))


def tools(*arguments, capture=False, input_data=None, check=True):
    result = subprocess.run([DOCKER, "exec", "-i", "dynamos-dev", *arguments],
                            text=True, input=input_data, capture_output=capture, check=check)
    return result.stdout.strip() if capture else result


def kubectl(*arguments, capture=False, input_data=None, check=True):
    return tools("kubectl", "--context", CONTEXT, *arguments, capture=capture,
                 input_data=input_data, check=check)


def prepare_access():
    LOCAL.mkdir(mode=0o700, parents=True, exist_ok=True)
    access = LOCAL / "access.json"
    if not access.exists():
        descriptor = os.open(access, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as target:
            json.dump({"token": secrets.token_urlsafe(32), "url": "http://127.0.0.1:8095"}, target)
    settings = json.loads(access.read_text())
    token_path = LOCAL / "api-token"
    descriptor = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as target:
        target.write(settings["token"])
    integrated = LOCAL / "integrated-values.json"
    if not integrated.exists():
        descriptor = os.open(integrated, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as target:
            json.dump({"integrated": {"enabled": True, "image": DYNAMOS_IMAGE,
                                      "signingKey": secrets.token_urlsafe(48),
                                      "rabbitPassword": secrets.token_urlsafe(32), "user": "sandbox-researcher"}}, target)
    settings["url"] = "http://127.0.0.1:8095/api/v1/ml"
    settings["integration"] = "dynamos"
    access.write_text(json.dumps(settings))


def set_gate(verified):
        tools("helm", "upgrade", "federated-training", "/workspace/charts/federated-training",
                    "--kube-context", CONTEXT, "--namespace", "training-system", "--reuse-values",
                    "--set", f"networkVerified={'true' if verified else 'false'}", "--force-conflicts",
                    "--wait", "--timeout", "180s")


def setup(skip_build):
    prepare_access()
    if not skip_build:
        subprocess.run([DOCKER, "build", "-f", str(ROOT / "python" / "federated-training" / "Dockerfile"),
                        "-t", IMAGE, str(ROOT)], check=True)
        subprocess.run([DOCKER, "build", "-f", str(ROOT / "configuration" / "federated-training" / "Dockerfile.go"),
                        "-t", DYNAMOS_IMAGE, str(ROOT)], check=True)
    previous_context = tools("kubectl", "config", "current-context", capture=True)
    try:
        clusters = tools("kind", "get", "clusters", capture=True).splitlines()
        if CLUSTER not in clusters:
            tools("kind", "create", "cluster", "--name", CLUSTER,
                "--config", "/workspace/configuration/federated-training/kind.yaml")
        tools("kind", "load", "docker-image", IMAGE, "--name", CLUSTER)
        tools("kind", "load", "docker-image", DYNAMOS_IMAGE, "--name", CLUSTER)
        tools("helm", "repo", "add", "cilium", "https://helm.cilium.io", "--force-update")
        tools("helm", "upgrade", "--install", "cilium", "cilium/cilium", "--version", "1.18.3",
              "--namespace", "kube-system", "--kube-context", CONTEXT,
              "--set", "ipam.mode=kubernetes", "--set", "operator.replicas=1",
              "--set", "kubeProxyReplacement=false", "--wait", "--timeout", "5m")
        kubectl("wait", "--for=condition=Ready", "nodes", "--all", "--timeout=180s")
        tools("helm", "upgrade", "--install", "federated-training", "/workspace/charts/federated-training",
              "--kube-context", CONTEXT, "--namespace", "training-system", "--create-namespace",
              "--set-file", "apiToken=/workspace/configuration/federated-training/.local/api-token",
              "-f", "/workspace/configuration/federated-training/.local/integrated-values.json",
              "--force-conflicts", "--wait", "--timeout", "300s")
        for namespace in ("uva", "vu", "tudelft"):
            kubectl("wait", "--for=condition=complete", "job/training-seed", "-n", namespace, "--timeout=180s")
            kubectl("rollout", "restart", "deployment/training-agent", "-n", namespace)
            kubectl("rollout", "status", "deployment/training-agent", "-n", namespace, "--timeout=120s")
        for service in ("api-gateway", "orchestrator", "policy-enforcer"):
            kubectl("rollout", "restart", f"deployment/{service}", "-n", "training-system")
            kubectl("rollout", "status", f"deployment/{service}", "-n", "training-system", "--timeout=120s")
        from verify import verify
        verify()
    finally:
        if previous_context:
            tools("kubectl", "config", "use-context", previous_context)


def main():
    parser = argparse.ArgumentParser(description="Manage the separate synthetic federated training cluster")
    parser.add_argument("action", choices=("setup", "verify", "forward", "status"))
    parser.add_argument("--skip-build", action="store_true")
    arguments = parser.parse_args()
    if not DOCKER:
        parser.error("Docker Desktop is required")
    if arguments.action == "setup":
        setup(arguments.skip_build)
    elif arguments.action == "verify":
        from verify import verify
        verify()
    elif arguments.action == "forward":
        kubectl("port-forward", "--address", "127.0.0.1", "-n", "training-system",
            "svc/api-gateway", "8095:8080")
    else:
        kubectl("get", "pods,jobs,pvc", "-A", "-l", "app=federated-training")


if __name__ == "__main__":
    main()