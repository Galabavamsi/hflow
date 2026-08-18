# Airflow 3.x facts for the Compose runtime

Our synthesis of the official docs, not a mirrored document; verify against
the cited sources when it matters. Researched 2026-08-18T08:20Z against
Airflow **3.3.1** (latest stable, released 2026-08-12).

## Image and services

- Image `apache/airflow:3.3.1` (ships Python 3.13.14, measured 2026-08-18;
  the docs' "default 3.12" is stale. `slim-3.3.1` = 275 MB compressed pull vs
  661 MB, but per the #40 spike it lacks psycopg2, asyncpg, and the fab
  provider, and swapping it into a bundle's .env fails SILENTLY: airflow-init
  exits 0 without migrating). <https://airflow.apache.org/docs/docker-stack/index.html>
- Reference compose (<https://airflow.apache.org/docs/apache-airflow/3.3.1/docker-compose.yaml>)
  services: `postgres` (postgres:16), `redis`, **`airflow-apiserver`** (command
  `api-server`, port 8080; note the YAML key has no hyphen in "apiserver"),
  `airflow-scheduler`, `airflow-dag-processor`, `airflow-worker` (celery),
  `airflow-triggerer`, `airflow-init`, optional `airflow-cli`/`flower`.
- Reference uses CeleryExecutor + FabAuthManager (`AIRFLOW__CORE__AUTH_MANAGER:
  airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager`) with an
  `airflow`/`airflow` admin user created by `airflow-init`, plus
  `AIRFLOW__API_AUTH__JWT_SECRET`/`JWT_ISSUER` shared across services.
- **LocalExecutor is viable single-machine**: spawns processes on the
  scheduler node, `[core] parallelism` (default 32); drop redis, the celery
  worker, and flower.
  <https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/executor/local.html>
- All components need `AIRFLOW__CORE__EXECUTION_API_SERVER_URL:
  'http://airflow-apiserver:8080/execution/'` (tasks speak to the Task
  Execution API through it).

## DAG bundles

`AIRFLOW__DAG_PROCESSOR__DAG_BUNDLE_CONFIG_LIST` = JSON list:

```json
[{"name": "dags-folder",
  "classpath": "airflow.dag_processing.bundles.local.LocalDagBundle",
  "kwargs": {"path": "/opt/airflow/dags"}}]
```

`LocalDagBundle` is unversioned (tasks always run latest on-disk code); never
put credentials in `kwargs` (exposed via the Config API).
<https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/dag-bundles.html>

## REST API v2

- Base `/api/v2`; every request needs `Authorization: Bearer <JWT>`.
- Token: `POST {url}/auth/token` with `{"username": ..., "password": ...}` →
  `{"access_token": "..."}`. SimpleAuthManager is the core default (users via
  `[core] simple_auth_manager_users`, auto-generated passwords land in
  `$AIRFLOW_HOME/simple_auth_manager_passwords.json.generated`); the reference
  compose uses FabAuthManager instead.
  <https://airflow.apache.org/docs/apache-airflow/stable/security/api.html>
- Trigger: `POST /api/v2/dags/{dag_id}/dagRuns` with
  `{"logical_date": null, "conf": {...}}` (`logical_date` is required but may
  be explicitly null; optional `dag_run_id`, `note`).
- Health: `GET /api/v2/monitor/health`, the official compose's own
  healthcheck. **HTTP status is always 200; parse the body**:
  `{"metadatabase": {"status": "healthy"}, "scheduler": {...},
  "triggerer": {...}, "dag_processor": {...}}` with
  `healthy`/`unhealthy`/null.
  <https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/check-health.html>

## Config traps we pre-set

- `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: 'false'` (trap: default pauses
  new DAGs), `AIRFLOW__CORE__LOAD_EXAMPLES: 'false'`.
- Object-storage XCom: `AIRFLOW__CORE__XCOM_BACKEND:
  airflow.providers.common.io.xcom.backend.XComObjectStorageBackend` +
  `AIRFLOW__COMMON_IO__XCOM_OBJECTSTORAGE_PATH` (e.g. `file:///...` or
  `s3://conn@bucket/key`), `..._THRESHOLD` (bytes),
  `..._COMPRESSION`.
  <https://airflow.apache.org/docs/apache-airflow-providers-common-io/stable/xcom_backend.html>

## External-python (two-venv worker isolation)

`@task.external_python` / `ExternalPythonOperator` (in
`apache-airflow-providers-standard`): `python` points at the venv's binary;
the function body is extracted to a temp file so **all imports go inside the
function** and data passes via `op_args`/`op_kwargs`; `virtualenv` should be
preinstalled in the target venv; `dill` (if used) must match the main env's
version (`cloudpickle` recommended); Airflow context objects don't serialize
(installing the same Airflow version in the venv recovers most context vars;
`pendulum` + `lazy_object_proxy` suffice for the datetime ones). Measured at
providers-standard 1.17.0 (2026-08-18): with `expect_airflow=False` the ONLY
venv probe is `import pendulum`; `lazy_object_proxy` is never imported in the
venv (context proxies resolve host-side before pickling), so a venv that
passes no Airflow context needs pendulum alone; pin it to the image's
constraint (3.3.1 pins `pendulum==3.2.0`).
<https://airflow.apache.org/docs/apache-airflow-providers-standard/stable/operators/python.html>
