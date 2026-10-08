# Federated Training Sandbox: UVA, VU and TUDelft

This is an opt-in, local prototype using synthetic data only. The current setup
integrates the original DYNAMOS API Gateway, policy-enforcer, orchestrator,
agents, sidecars, RabbitMQ and etcd in the separate training cluster. The
coordinator handles federated rounds after DYNAMOS approves the request.
The original cluster and SQL deployment are not upgraded. The Horus `/training`
page uses the DYNAMOS API; its other pages remain demonstrations.
See [DYNAMOS integration](dynamos_training_integration.md) for the current flow,
tests and integration-specific undo instructions.

## What Was Added

- A separate kind cluster named `dynamos-training` with Cilium enforcing
  NetworkPolicies. The original `dynamos` cluster is not modified.
- Namespaces `uva`, `vu` and `tudelft`, each with an independent dataset PVC,
  DYNAMOS agent/sidecar and local state PVC. Each dataset has 240 synthetic records
  with the same four-feature schema, but different random seeds and contents.
- A coordinator in `training-system` with a persistent state/model volume.
- One approved algorithm: scikit-learn logistic regression with local SGD
  and sample-count-weighted FedAvg. All organizations use the same feature
  order, class definitions and hyperparameters.
- A separately gated regular DYNAMOS TUDelft agent in the existing Helm charts.
  `tudelftEnabled` defaults to false. This agent is NOT deployed in the original
  cluster by the sandbox setup. SQL agreements/DSP provisioning for TUDelft
  are not added by this prototype.

The first run uses three rounds and two local epochs. Each round creates one
trainer Job per selected organization. The global weights are sent to each
organization, training reads only that organization's dataset, and parameter
updates return to the coordinator. It produces one final global model.
Metrics shown in the UI are validation scores of the local models before
aggregation, NOT an evaluation of the final global model on an independent
global test dataset.

## First Test, One Step At A Time

Keep Docker Desktop and `dynamos-dev` running. Run commands from the repository
root on the Mac. The management script uses the Docker Desktop binary directly,
so a shell alias from `docker` to Podman does not interfere.

1. Set up the independent cluster (already done during implementation):

   ```bash
   python3 configuration/federated-training/manage.py setup
   ```

  This builds native trainer and Go service images, installs Cilium and DYNAMOS,
  seeds the three
   local datasets, and tests isolation before enabling training. The script uses
   Helm 4 from the dev container and restores your previous kubectl context.
   It does not upload any image to Docker Hub. Re-running it preserves datasets;
   seed Jobs do not overwrite existing files. Do not delete/re-run seed Jobs
   against populated PVCs. A failed isolation check leaves training disabled.

2. Open the API in one terminal and leave it running:

   ```bash
   python3 configuration/federated-training/manage.py forward
   ```

3. Start Horus in another terminal:

   ```bash
   npm --prefix horus-sandbox-frontend install
   npm --prefix horus-sandbox-frontend run dev -- --host 127.0.0.1 --port 5174 --strictPort
   ```

4. Open <http://127.0.0.1:5174/training>. Select UVA, VU and TUDelft. Keep
   logistic regression, three rounds and two local epochs. Click **Start
   training**. The dataset dropdown references a fixed local dataset ID; the
   client cannot supply a filesystem path, image or arbitrary Python script.

5. Watch actual Pods and Jobs from another terminal:

   ```bash
   /Applications/Docker.app/Contents/Resources/bin/docker exec -it dynamos-dev \
     kubectl --context kind-dynamos-training get pods,jobs -A -l app=federated-training --watch
   ```

   Jobs named `training-...-r1`, `r2`, and `r3` appear in each selected namespace.
  Each training Pod has a trainer and a DYNAMOS sidecar. Jobs are cleaned up
  600 seconds after completion. The agents and coordinator
   remain running. Each trainer has a read-only `/data` mount, no mounted
   Kubernetes service-account token, a read-only root filesystem and no elevated
   capabilities. The final artifact persists after trainer Pods disappear.

6. Wait for **completed** and click **Download final model**. The downloaded
   JSON contains the model coefficients/intercept, feature order, classes and
   execution metadata. There is no raw data, prediction-by-record export or
   download endpoint for organization-local models. The JSON is a portable
   logistic-regression model, not a pickle/joblib archive. Keep its feature
   order when applying it to new data.

7. Optionally run the reproducible end-to-end test while port-forward is active:

   ```bash
  python3 configuration/federated-training/test_integrated.py
   ```

   Do not run it concurrently with an active UI training run. It checks
   authentication, rejection of unknown algorithms, download denial before
   completion, three-round training and the final artifact's allowed fields.

## Observe And Recheck Isolation

```bash
python3 configuration/federated-training/manage.py verify
```

Do this only when no training is active; it restarts the coordinator to change
the training gate. Afterwards restart the `forward` command if its connection
closed. The checks are active probes, not hard-coded UI success indicators:

- Each worker reads its own dataset; writing to its dataset volume fails.
- Each worker has no Kubernetes API token and cannot reach the API server.
- Each worker can reach its local agent but cannot connect to another
  organization's agent.
- A reachable control sink outside the permitted destination is denied to all
  workers. An unrestricted control Job first verifies that the sink is alive.
- Organization agents cannot read secrets or another namespace's PVCs through
  their Kubernetes RBAC permissions.
- Dataset hashes differ between UVA, VU and TUDelft; no dataset contents leave
  the organization during this check.

The report is saved in
`configuration/federated-training/.local/isolation-report.json`, which is ignored
by Git. Operator credentials and test artifacts are also in this ignored,
owner-only local directory. Never publish it. `networkVerified` is an operator
gate reflecting the last test, NOT cryptographic attestation. Re-run checks
after changing images, policies or workloads. Do not manually bypass the gate.

## Security Boundaries And Limitations

- All organizations share one local cluster/node in this simulation. This is
  not physical separation, and it does not protect against cluster/node admins.
- No raw records are transferred by the provided trainer. Model updates and
  aggregated metrics DO leave the organizations. Models/updates can leak
  information: no differential privacy or secure aggregation is implemented.
- The trusted trainer image and local agents are part of the trust boundary.
  The agent has namespace-local Job creation permissions. This is not an
  execution sandbox for untrusted algorithms. DNS is allowed to cluster DNS;
  this prototype does not claim covert-channel prevention or audit completeness.
- No Cosign admission, Kata/gVisor, eBPF runtime monitoring or DSP negotiation
  is added. Cilium applies network policy; it does not inspect ML semantics.
- The API maps a local sandbox bearer token to one configured researcher,
  then evaluates that researcher's agreements through DYNAMOS. This is not
  production OIDC or multi-user identity. Signed training capabilities bind
  parameters and participants; agents scope RabbitMQ results to one-use round
  capabilities. Trainers never receive the shared API secret or signing key.
- DYNAMOS's RabbitMQ normal_user credentials are shared in this trusted-code
  sandbox. Namespace network isolation does not imply per-organization queue
  isolation. Production needs scoped broker credentials/vhosts, TLS and tighter
  etcd permissions; these are not claimed by this prototype.
- Vite proxies authentication server-side. The secret is not embedded in the
  browser bundle. Both frontend and port-forward bind to localhost. This is a
  development-only proxy, not a production gateway; the built static frontend
  requires a proper authenticated backend/reverse proxy to function.
- Health checks are unauthenticated and return no data. No dataset-serving
  endpoint is implemented. Browser downloading was verified by the button's
  HTTP 200 response, attachment header and model contents; the integrated VS
  Code browser does not expose a normal Playwright download event. Use a regular
  browser for the actual save dialog.
- Training supports one active run at a time. Cancellation stops tracked Jobs
  and disables model download. A coordinator restart marks unfinished runs
  interrupted; do not expect automatic resumption or exactly-once delivery.
- Use only synthetic data until independent security and privacy review.

## Stop Or Undo

Stop the frontend and API port-forward with Ctrl+C in their respective terminals.
This does not delete models, datasets or either cluster.

Before undoing code, preview the exact restoration:

```bash
python3 configuration/federated-training/integration_rollback.py
```

To apply that restoration:

```bash
python3 configuration/federated-training/integration_rollback.py --apply
```

This restores code to the preceding standalone prototype. See the integration
guide for infrastructure reversal as well. After reversing the integration,
the earlier `rollback.py` can separately undo the initial prototype.
Original integration files are backed up under `.local/integration-rollback`.
The script restores only changed files and removes only recorded additions.
It refuses to change anything if a recorded file has been edited since the
snapshot. It does not use `git reset`, delete the original Horus folder, discard
your previous manifest changes or remove cluster data. Keep the local backup
until you are satisfied with the prototype. Afterwards run `npm install` in
Horus if you restored its original dependency files.
The retained local directory also has its own ignore file so credentials and
saved models remain ignored after restoring the repository's original ignore rules.

The separate cluster can later be deleted explicitly, but doing so destroys
its local datasets, run history and models. Download any model you need first:

```bash
/Applications/Docker.app/Contents/Resources/bin/docker exec dynamos-dev \
  kind delete cluster --name dynamos-training
```

Never substitute `dynamos` for `dynamos-training` in that command. Cluster
deletion is not performed automatically by rollback.