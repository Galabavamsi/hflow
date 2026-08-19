<p align="center">
  <a href="https://hebbianrobotics.com">
    <img src="docs/assets/hebbian-logo-on-black.svg" alt="Hebbian Robotics" width="128">
  </a>
</p>

# HFlow

**An open-source, modular data pipeline for turning physical-AI data into
quality-checked, queryable datasets for training robotics models.**

HFlow is reusable infrastructure for processing multimodal physical-AI data:
human egocentric recordings, robot teleoperation demonstrations, autonomous
policy rollouts, and other sensor-rich episodes. The goal: anyone who
needs to process this data should be able to plug their existing transformation,
quality-checking, labeling, and enrichment code into one pipeline instead of
rebuilding orchestration, artifact storage, versioning, observability, and
curation infrastructure for every project.

It replaces one-off processing scripts and manually assembled file lists with
versioned episodes, observable pipeline runs, queryable quality evidence, and
reproducible Parquet manifests. The processing logic remains ordinary Python
owned by the user; HFlow supplies the reusable infrastructure around it.

The design is an open source implementation of Dyna Robotics'
["Training Dyna-2 at million-hour scale, repeatably"](https://www.dyna.co/research/dyna-2-infrastructure) article,
published August 2026. Dyna-2 was trained on more than one million hours of
egocentric video data, and the post describes the reusable infrastructure that
made processing and experimenting with that data repeatable. You can think of
HFlow as an independent, open-source implementation of those public ideas,
adapted for people who need the same foundation without Dyna's million-hour
production stack. It is not Dyna's private source code or an undisclosed
wire-compatible production system.

MCAP is HFlow's v1 input and output boundary because it efficiently stores
and serves synchronized video, state, action, and other time-series streams.
That format requirement does not define where the data comes from: human-worn
cameras, teleoperated robots, autonomous policies, and other collection systems
can all feed the pipeline once their data is represented as a supported MCAP
episode.

> **Status: pre-v1, core lifecycle implemented end to end.** Working today: canonical MCAP writing (topic-group chunking, in-band H.264), episode accessors, user/built-in checks and enrichments, `app.test()` (see the [runnable examples](./examples/README.md)), the Parquet catalog + DuckDB curation (`hflow curate`), the conformance doctor, `app.run()`/`hflow up` for a local Docker Compose Airflow 3 runtime, and `hflow deploy` for an existing Airflow 3 deployment. The local runtime's ingest DAG is integration-tested end to end: trigger via REST, process in an isolated task venv, and record rows in the catalog. See [what is different from Dyna](./docs/ARCHITECTURE.md#what-is-different-from-dyna) for the explicit implemented/simplified/deferred/out-of-scope boundary. Remaining pre-v1 work and scale paths are tracked in [issues](https://github.com/Hebbian-Robotics/hflow/issues).

## What you get

Human and robot data move through the same four-stage lifecycle Dyna describes:

```
collection --> ingestion ---------------> curation ------> delivery
(landing       (transform -> QC gate ->  (SQL over        (curated MCAP +
 bucket)        enrich, as an             episode          manifest; convert
                Airflow DAG)              catalog)         for training)
```

<p align="center">
  <img src="docs/assets/hflow-readme.gif" alt="HFlow pipeline demo" width="960">
</p>

- **Your processing code stays yours.** Transformations, quality checks, labels, and enrichments are plain Python functions in your own environment. Existing code plugs in through small adapters instead of being rewritten for a proprietary framework.
- **Episodes are MCAP**, the container that ROS 2 records natively and [Foxglove](https://foxglove.dev/)/[Rerun](https://rerun.io/) open directly, written with the two tuning ideas from Dyna's post: in-band H.264 with GOP length matched to how the data will be read, and **topic-group chunking** (camera streams and state streams never share a chunk, so a training sample costs one read per group instead of one per topic).
- **Quality checks produce reusable evidence.** Accessors extract the inputs existing processing code expects (numpy arrays, MP4 paths, JPEG frames), and results land as queryable measurements rather than hardcoded verdicts. Different datasets can apply different thresholds without processing the media again.
- **Curation is a SQL query.** Every episode's measurements, tags, and version stamps live in a Parquet catalog; [DuckDB](https://duckdb.org/) queries it into a training manifest. Two experiments cut the same corpus with two queries; nothing is reprocessed and nothing is deleted.
- **No new UIs, no obfuscation.** Episodes open in Foxglove and Rerun. Runs are watched in Airflow's own UI. The catalog is Parquet any tool can read. Every surface is a standard format or an existing open-source tool.

## How it differs from Dyna

HFlow preserves the workflow and standard-format boundaries from Dyna's
post, but deliberately leaves out infrastructure whose value appears only at
million-hour scale. In particular:

- collection hardware and training-batch loading are outside this repository;
- input is currently MCAP-only, and ingestion is explicitly triggered rather
  than started by a bucket watcher;
- replay is stage-level, and resource declarations do not yet route individual
  steps across heterogeneous worker pools; and
- the Parquet/DuckDB catalog replaces Dyna's database, CDC, and analytical
  warehouse stack; distributed corpus caches and training-fleet orchestration
  are out of scope.

The [implementation-differences matrix](./docs/ARCHITECTURE.md#what-is-different-from-dyna)
labels each area as implemented, simplified, deferred, or out of scope and
explains the boundary in detail.

## Hosting and scale

The open-source deployment is built to be easy to own: run one single-tenant
workspace with the included Docker Compose runtime, or deploy its generated DAG
bundle into an Airflow 3 environment you already operate. It has no user
accounts, RBAC, or multi-tenant control plane.

The data plane is kept separate from account and control-plane concerns so the
same engine can be scaled as multiple isolated workspaces (for example, one
per team or customer) behind an external control plane. That is the intended
path to a future hosted version, but the hosted control plane is not
implemented in this repository and is not a pre-v1 release commitment.

## Community and hosted interest

<!-- Add the Google Form and Discord invite links to the two entries below once they are live. -->

- **Hosted version interest:** Google Form coming soon.
- **Community Discord:** invite link coming soon.

Until then, use [GitHub issues](https://github.com/Hebbian-Robotics/hflow/issues)
for reproducible bugs and scoped feature requests.

## Install and try it

HFlow is not published to PyPI yet. Run the pre-v1 package from a source
checkout with [uv](https://docs.astral.sh/uv/):

```bash
git clone https://github.com/Hebbian-Robotics/hflow.git
cd hflow
uv sync --locked --all-extras
uv run python examples/quickstart.py
```

The quickstart synthesizes a small multimodal episode with camera and state
streams when no input file is given, runs the pipeline in-process, and writes
its outputs under the gitignored `data/` directory. It needs no Docker or
Airflow. To use your own recording:

```bash
uv run python examples/quickstart.py path/to/episode.mcap
```

Use `uv run hflow --help` to see the CLI. When you are ready to schedule the
same pipeline, continue with the [runtime guide](./docs/RUNTIME.md). Developers
and contributors should start with [CONTRIBUTING.md](./CONTRIBUTING.md). Browse
the [examples catalog](./examples/README.md) for the egocentric-corpus and
OpenAI vision paths.

## What it looks like

Get started in six lines of code. This fuller example uses a robot
teleoperation episode, but the same step interface applies to egocentric video
and other physical-AI recordings.

```python
import hflow
from your_existing_qc import check_joint_smoothness  # use your existing checks

app = hflow.App("kitchen-pipeline", data_root="./data")


@app.check()
def joint_smoothness(ep: hflow.Episode) -> hflow.CheckResult:
    joints = ep.channel("/joint_states").to_numpy()  # our line: extract
    result = check_joint_smoothness(joints, rate_hz=100)  # your line: unchanged
    return hflow.CheckResult(measurements=result)  # our line: record


@app.check(critical=True)
def camera_blackout(ep: hflow.Episode) -> hflow.CheckResult:
    stats = hflow.ffmpeg.frame_stats(ep.video("wrist_cam"))  # one decode pass
    return hflow.CheckResult(
        measurements={"black_pct": stats.black_frame_pct},
        verdict=stats.black_frame_pct < 0.5,  # your threshold
    )


if __name__ == "__main__":
    app.test("episode_0001.mcap")  # whole pipeline, in-process, no infra
    # Or call app.run() here to start the Compose runtime, then use `hflow ingest`.
```

Curation comes afterwards, via `hflow.curate(data_root / "catalog", sql, output="manifest.parquet")`
or `hflow curate "<sql>"` on the command line, either way reporting coverage
denominators alongside the manifest:

```sql
SELECT episode_id, uri FROM episodes
WHERE task = 'fold_napkin'
  AND status != 'quarantined'
  AND black_pct < 1.0                      -- percent, user-owned threshold
  AND pipeline_version = 'a41c9f27b3d8'    -- pin one reprocessing generation
```

## Design tenets

1. **Democratize the architecture, defer the optimizations.** Preserve the useful workflow and standard interfaces at small scale, and label each production-scale mechanism honestly as implemented, simplified, deferred, or out of scope.
2. **Evidence, not verdicts.** Checks record measurements with coverage; pass/fail policy belongs to the consumer, at curation time. Quality tags route episodes; they never delete data.
3. **Standard formats at every boundary.** MCAP episodes, Parquet catalogs, Airflow DAGs. Our code exists only where the format forces bridging or a pitfall is genuinely non-obvious.
4. **Your code stays your code.** Existing transforms, checks, and enrichments plug in through small adapters instead of being rewritten.
5. **Transparent provenance.** The docs mark every design element as *Dyna says* (from the blog) or *HFlow chooses* (our engineering judgment, with the evidence behind it).

## Non-goals

- **Training.** The pipeline ends at curated, quality-tagged, version-stamped episodes and a manifest. Many users filter data to deliver or sell it, not to train on it. (Converters to training formats such as [LeRobot](https://github.com/huggingface/lerobot) are planned as a separate, standalone package.)
- **Maximum flexibility.** Robotics/physical-AI data is the narrative and the constraint budget: one canonical episode format, coarse-grained steps, and opinionated defaults are features.
- **Million-hour throughput.** The [benchmark report](./docs/BENCHMARKS.md) documents honestly what the simple version achieves and where it falls over.

## Requirements

- Python ≥ 3.11
- Docker (for the pipeline runtime; `app.test()` needs none), or bring your own Airflow deployment (Astronomer, MWAA, Cloud Composer, self-managed)
- The first `hflow up` downloads ~2 GB of container images and builds the task venv (one-time; `app.test()` needs none of this)
- Native `s3://`, `gs://`, and Azure data roots use the optional bucket backend (`uv sync --extra bucket`); local paths do not import it
- On Linux x86_64/aarch64, the first video operation downloads a checksum-verified, pinned ffmpeg/ffprobe build into the user cache. Set `HFLOW_FFMPEG` and `HFLOW_FFPROBE` to use binaries you manage instead.
- Windows is supported via WSL2 (Airflow does not run natively on Windows)

## Documentation

- [Documentation home](./docs/README.md): start by task, then choose a tutorial, how-to guide, reference, or explanation
- [Runnable examples](./examples/README.md): exact commands, prerequisites, expected output, and links to the relevant guides
- [Architecture and differences from Dyna](./docs/ARCHITECTURE.md): the implemented, simplified, deferred, and out-of-scope matrix
- [Call OpenAI vision from a step](./docs/how-to/call-openai-vision.md): a focused guide linked to a complete executable pipeline
- [Contributing](./CONTRIBUTING.md): development setup, validation commands, test gates, and pull-request expectations
- [Security policy](./SECURITY.md): supported versions and private vulnerability reporting

## References

Primary source:

- Dyna Robotics, [Training Dyna-2 at million-hour scale, repeatably](https://www.dyna.co/research/dyna-2-infrastructure) (Aug 2026)

Formats and tooling this project builds on:

- [MCAP specification](https://mcap.dev/spec) and [Python libraries](https://mcap.dev/docs/python) (Foxglove)
- [foxglove.CompressedVideo schema](https://docs.foxglove.dev/docs/sdk/schemas/compressed-video): in-band H.264/H.265/VP9/AV1 video in MCAP
- [Apache Airflow 3](https://airflow.apache.org/): ingestion DAG orchestration
- [DuckDB](https://duckdb.org/): curation queries over the Parquet catalog
- [Foxglove](https://foxglove.dev/) and [Rerun](https://rerun.io/): episode inspection
- [FFmpeg](https://ffmpeg.org/): video processing and the deterministic frame instrument

Parts of the durability and measurement design draw on production experience from [Pareto](https://github.com/Hebbian-Robotics/pareto), Hebbian Robotics' robotics data curation platform.

## License

[Apache-2.0](./LICENSE)
