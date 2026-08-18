"""The Docker Compose runtime: provision and talk to a local Airflow.

``hflow up`` renders a bundle (see ``_bundle``) and starts it with plain
``docker compose``; observability is Airflow's own UI on localhost. The SDK
never imports Airflow -- it renders files and speaks the REST API.
"""

from hflow.runtime._bundle import (
    DEFAULT_AIRFLOW_IMAGE,
    BundlePaths,
    RuntimeConfig,
    bundle_dag_ids,
    infer_hflow_source,
    load_bundle,
    render_bundle,
    sub_dag_id_for_stage,
)
from hflow.runtime._client import (
    AirflowClient,
    AirflowClientError,
    AirflowHealth,
)
from hflow.runtime._compose import (
    ComposeError,
    compose_down,
    compose_logs,
    compose_ps,
    compose_up_detached,
)
from hflow.runtime._deploy import (
    DeployConfig,
    DeployPaths,
    render_deploy_bundle,
    validate_data_root_uri,
)
from hflow.runtime._lifecycle import (
    client_for_bundle,
    describe_runtime_status,
    start_runtime,
    started_summary,
)

__all__ = [
    "DEFAULT_AIRFLOW_IMAGE",
    "AirflowClient",
    "AirflowClientError",
    "AirflowHealth",
    "BundlePaths",
    "ComposeError",
    "DeployConfig",
    "DeployPaths",
    "RuntimeConfig",
    "bundle_dag_ids",
    "client_for_bundle",
    "compose_down",
    "compose_logs",
    "compose_ps",
    "compose_up_detached",
    "describe_runtime_status",
    "infer_hflow_source",
    "load_bundle",
    "render_bundle",
    "render_deploy_bundle",
    "start_runtime",
    "started_summary",
    "sub_dag_id_for_stage",
    "validate_data_root_uri",
]
