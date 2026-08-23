"""Quality-control pipeline for the egocentric factory corpus.

One file serves both entry points: ``python pipeline.py <episodes>`` runs the
checks in-process for the dev loop, and ``hflow up --pipeline
examples/egocentric/pipeline.py:app`` runs the identical App under Airflow.
"""

import sys
from pathlib import Path

import hflow

# Imported as functions, not reached as ``hflow.checks.x`` attributes: a step's
# version content-hashes the functions it NAMES (and, transitively, the hflow
# code they call), while a module contributes only its name. Aliased because
# the wrapper below takes the built-in's name.
from hflow.checks import timestamp_regularity as measure_timestamp_regularity
from hflow.ffmpeg import frame_stats

# Inside the runtime's containers the data root is always mounted at
# /opt/airflow/data; on the host the corpus lives where prepare.py wrote it.
# Both vantage points name the same directory, so local runs and Airflow runs
# share one catalog.
CONTAINER_DATA_ROOT = Path("/opt/airflow/data")
DATA_ROOT = CONTAINER_DATA_ROOT if CONTAINER_DATA_ROOT.is_dir() else Path("data/egocentric")

app = hflow.App("egocentric", data_root=DATA_ROOT)


@app.check()
def timestamp_regularity(episode: hflow.Episode) -> hflow.CheckResult:
    return measure_timestamp_regularity(episode, expected_hz={episode.cameras[0]: 10.0})


@app.check(critical=True)
def camera_health(episode: hflow.Episode) -> hflow.CheckResult:
    stats = frame_stats(episode.video())
    camera_start_ns = int(episode.channel(episode.cameras[0]).timestamps[0])
    freeze_intervals = [
        hflow.Interval(
            start_ns=camera_start_ns + round(freeze_start_s * 1_000_000_000),
            end_ns=camera_start_ns + round(freeze_end_s * 1_000_000_000),
            label="camera_freeze",
        )
        for freeze_start_s, freeze_end_s in stats.freeze_intervals
    ]
    return hflow.CheckResult(
        measurements={
            "black_frame_pct": stats.black_frame_pct,
            "freeze_total_s": stats.freeze_total_s,
            "luma_avg_mean": stats.luma_avg_mean,
            "frame_count": stats.frame_count,
        },
        intervals=freeze_intervals,
        verdict=stats.black_frame_pct < 5.0 and stats.freeze_total_s < 2.0,
    )


@app.enrich()
def contact_sheet(episode: hflow.Episode) -> hflow.EnrichmentResult:
    artifact_path = DATA_ROOT / "artifacts" / f"{episode.path.stem}-contact-sheet.jpg"
    sheet = hflow.ffmpeg.contact_sheet(
        episode.frames(fps=1.0),
        artifact_path,
        columns=5,
        max_tiles=20,
    )
    return hflow.EnrichmentResult(
        labels={"contact_sheet_frame_count": sheet.frames_sampled_from},
        artifacts={"contact_sheet": sheet.path},
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <episode.mcap> [episode.mcap ...]")
    for episode_path in map(Path, sys.argv[1:]):
        app.test(episode_path, record=True)


if __name__ == "__main__":
    main()
