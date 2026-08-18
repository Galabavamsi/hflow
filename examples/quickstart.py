"""The vertical slice in one file: one episode in, measurements out, zero
infrastructure.

Run it on your own recording (any standard MCAP, e.g. a rosbag2 file with
compressed images), or with no argument to generate a synthetic sample::

    uv run python examples/quickstart.py [episode.mcap]

The canonical episode it writes under ./data/test-runs/ opens directly in
Foxglove and Rerun.
"""

import sys
from pathlib import Path

import numpy as np

import hflow


def check_joint_smoothness(joints: np.ndarray, rate_hz: float) -> dict[str, float]:
    velocities = np.abs(np.diff(joints, axis=0)) * rate_hz
    return {
        "max_velocity_rad_s": float(velocities.max()),
        "mean_velocity_rad_s": float(velocities.mean()),
    }


app = hflow.App("kitchen-pipeline", data_root="./data")


@app.check()
def joint_smoothness(ep: hflow.Episode) -> hflow.CheckResult:
    joints = ep.channel("/joint_states").to_numpy()
    measurements = check_joint_smoothness(joints, rate_hz=100)
    return hflow.CheckResult(measurements=dict(measurements))


@app.check()
def timestamps(ep: hflow.Episode) -> hflow.CheckResult:
    return hflow.checks.timestamp_regularity(ep, tolerance_s=0.005)


@app.check(critical=True)
def camera_blackout(ep: hflow.Episode) -> hflow.CheckResult:
    stats = hflow.ffmpeg.frame_stats(ep.video("wrist_cam"))
    return hflow.CheckResult(
        measurements={"black_pct": stats.black_frame_pct},
        verdict=stats.black_frame_pct < 50.0,
    )


def main() -> None:
    if len(sys.argv) > 1:
        episode_path = Path(sys.argv[1])
    else:
        episode_path = Path("./data/sample/episode_0001.mcap")
        if not episode_path.is_file():
            print(f"synthesizing a sample episode at {episode_path} ...")
            hflow.testing.synthesize_episode(episode_path)

    app.test(episode_path)


if __name__ == "__main__":
    main()
