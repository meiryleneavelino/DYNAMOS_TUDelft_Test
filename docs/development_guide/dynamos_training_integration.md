# Training Integrated With DYNAMOS

## Architecture

```text
Horus -> DYNAMOS API Gateway -> sidecar/RabbitMQ -> policy-enforcer
                                               -> orchestrator
                                               -> organization agents
         -> approved federated coordinator -> organization agents
         -> local trainer + DYNAMOS sidecar -> RabbitMQ -> agent
         -> coordinator aggregation -> final model -> authorized API download
```

The API uses `/api/v1/ml/`. The coordinator is not directly exposed to the
browser. A sandbox bearer token maps to `sandbox-researcher` on the server;
the browser cannot supply a different identity. The existing approval RPCs
carry `mlTrainingRequest` and its validated parameters. The policy-enforcer
requires explicit request-type, dataset, algorithm and computeToData permission
for every selected organization. Partial approval does not start training.

The original orchestrator resolves online agents in etcd, chooses computeToData
for this request type and sends composition messages through its sidecar.
Agents persist compositions in etcd. The API persists the approved plan and
issues an expiring HMAC capability bound to researcher, run ID and parameters.
The coordinator verifies this capability and rechecks permission through the
same DYNAMOS approval path before each round and before exporting the model.

Each original Go agent creates a local Job with two containers: `trainer` and
`sidecar`. Only the trainer mounts its organization's dataset, read-only.
The trainer sends a strictly typed model update over localhost gRPC to the
sidecar; RabbitMQ delivers it to that organization's permanent DYNAMOS agent.
The agent checks a one-use round result capability and validates output fields.
The coordinator collects updates and applies sample-weighted FedAvg.
The API rechecks policy before allowing the final model download.

## Run Calmly

Keep Docker Desktop and the `dynamos-dev` container running. From the repository
root on the Mac, use a separate terminal for each long-running command.

1. Deploy/update only the training cluster:

   ```bash
   python3 configuration/federated-training/manage.py setup
   ```

   This does not deploy into `kind-dynamos`, overwrite datasets, push images or
   replace the existing SQL deployment. Wait for installation and isolation
   checks to finish before opening the API. Setup is not needed every day.

2. Open the DYNAMOS API Gateway on localhost:

   ```bash
   python3 configuration/federated-training/manage.py forward
   ```

3. Start the Horus interface:

   ```bash
   npm --prefix horus-sandbox-frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
   ```

4. Open <http://127.0.0.1:5174/training>, select UVA/VU/TUDelft, keep three
   rounds and two local epochs, and start training. Download appears only for
   completed runs. Historical standalone runs are retained on disk but are
   not shown by the integrated API because they have no DYNAMOS approval.

5. Observe Pods:

   ```bash
   /Applications/Docker.app/Contents/Resources/bin/docker exec -it dynamos-dev \
     kubectl --context kind-dynamos-training get pods,jobs -A --watch
   ```

   In `training-system`, API Gateway, policy-enforcer and orchestrator each have
   a DYNAMOS sidecar; the Python coordinator is a separate Pod. In `uva`, `vu`
   and `tudelft`, each permanent Go agent has a sidecar, and each training round
   has a trainer/sidecar Job. `core` contains RabbitMQ and three application
   etcd members. Kubernetes's own etcd remains separate in `kube-system`.

## Verify Integration, Not Just Training

With port-forward active and no UI run in progress:

```bash
python3 configuration/federated-training/test_integrated.py
```

This temporarily changes TUDELFT's synthetic agreement in etcd and restores
it in `finally` blocks. It tests denial before Job creation, a three-party
three-round run, trainer/sidecar Pod composition, final artifact fields,
download denial after revocation, rejection at a subsequent round/final
policy revalidation, and logs proving RabbitMQ results reached a Go agent.
If the process is forcibly killed during this test, inspect and restore the
synthetic agreement before using the UI; do not treat a stale test state as
the intended policy. The operator can rerun setup to reseed static agreements.

An agreement change is enforced at authorization/revalidation boundaries;
it does not guarantee immediate preemption of a currently running trainer.
Cancellation deletes tracked Jobs. Do not claim immediate syscall-level
enforcement, complete revocation atomicity or exactly-once delivery.

Local isolation can be checked separately with `manage.py verify`. No raw
dataset download endpoint is added. The trainer's outbound network access
includes RabbitMQ as required by the DYNAMOS architecture. See the sandbox
guide for the exact network/RBAC checks and privacy limitations.

## Scope And Limits

This reuses original DYNAMOS services and communication, not merely similar
Python services. It does not install the entire original monitoring/DSP stack
or move training into the original cluster. Existing SQL code paths remain
unchanged unless the new ML type/feature flag is used; the sandbox provides
ML fixtures, not a full SQL dataset deployment. OpenCensus propagation is
reused, but a tracing collector/dashboard is not installed by this chart.

This is still a synthetic single-node local sandbox: no OIDC, secure
aggregation, differential privacy, Cosign, Kata/gVisor or production TLS is
implemented. Broker normal_user credentials and application etcd trust remain
shared; network policies do not prove broker queue isolation or protection
against cluster administrators. A reviewed production deployment must address
these boundaries before using real organization data.

## Undo Only This Integration

Stop frontend and port-forward first. Preview changes:

```bash
python3 configuration/federated-training/integration_rollback.py
```

Then apply code restoration when ready:

```bash
python3 configuration/federated-training/integration_rollback.py --apply
```

This refuses to overwrite files changed after its recorded snapshot, preserves
the previous standalone prototype and does not delete either cluster or data.
To additionally restore the previous standalone sandbox services, use this
instead of the code-only command:

```bash
python3 configuration/federated-training/integration_rollback.py --apply --restore-cluster
```

This rebuilds the original trainer image from restored sources and applies the
restored chart to `kind-dynamos-training` only. It removes integrated-only
services and their core state, but keeps the organization datasets, training
history and model volume. Download any models needed before undoing. This
infrastructure reversal was not executed against the live sandbox during
implementation because it would undo the integration being delivered.
The earlier prototype rollback can be used after integration code is undone.