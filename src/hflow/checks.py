"""Built-in checks, shipped in the same shape users write (evidence, not
verdicts; thresholds user-owned). Wrap them to register::

    @app.check()
    def timestamps(ep: hflow.Episode) -> hflow.CheckResult:
        return hflow.checks.timestamp_regularity(ep, tolerance_s=0.010)
"""

from collections.abc import Sequence

import numpy as np

from hflow.episode import Episode
from hflow.steps import CheckResult, Interval


def timestamp_regularity(
    episode: Episode,
    *,
    topics: Sequence[str] | None = None,
    expected_hz: dict[str, float] | None = None,
    tolerance_s: float = 0.010,
    gap_factor: float = 3.0,
) -> CheckResult:
    """Intra-stream timestamp regularity plus cross-stream sync offsets.

    Per topic: message deltas against the expected period (``1/expected_hz``
    when declared, else the stream's median delta -- LeRobot validates the
    same way post-hoc with a far tighter default tolerance; raw multi-sensor
    capture needs the looser default here). Deltas beyond ``gap_factor``
    periods become labeled gap intervals. Cross-stream: start/end offsets of
    every camera stream against the densest non-camera stream.
    """
    infos = episode.topics
    selected = (
        list(topics)
        if topics is not None
        else sorted(topic for topic, info in infos.items() if info.message_count >= 2)
    )
    measurements: dict[str, float | int | str | bool] = {}
    intervals: list[Interval] = []

    for topic in selected:
        stamps_ns = episode.channel(topic).timestamps
        if len(stamps_ns) < 2:
            measurements[f"{topic}/message_count"] = len(stamps_ns)
            continue
        deltas_s = np.diff(stamps_ns) / 1e9
        declared_hz = (expected_hz or {}).get(topic)
        expected_period_s = 1.0 / declared_hz if declared_hz else float(np.median(deltas_s))
        violation_mask = np.abs(deltas_s - expected_period_s) > tolerance_s
        measurements[f"{topic}/median_dt_s"] = float(np.median(deltas_s))
        measurements[f"{topic}/violation_pct"] = float(np.mean(violation_mask) * 100.0)
        measurements[f"{topic}/max_gap_s"] = float(np.max(deltas_s))
        gap_indices: list[int] = np.flatnonzero(deltas_s > gap_factor * expected_period_s).tolist()
        intervals.extend(
            Interval(
                start_ns=int(stamps_ns[index]),
                end_ns=int(stamps_ns[index + 1]),
                label=f"gap:{topic}",
            )
            for index in gap_indices
        )

    camera_topics = [topic for topic in episode.cameras if topic in selected]
    state_topics = [
        topic
        for topic in selected
        if topic not in episode.cameras and infos[topic].message_count >= 2
    ]
    if camera_topics and state_topics:
        reference = max(state_topics, key=lambda topic: infos[topic].message_count)
        reference_stamps = episode.channel(reference).timestamps
        for camera in camera_topics:
            camera_stamps = episode.channel(camera).timestamps
            measurements[f"sync/{camera}~{reference}/start_offset_s"] = float(
                (camera_stamps[0] - reference_stamps[0]) / 1e9
            )
            measurements[f"sync/{camera}~{reference}/end_offset_s"] = float(
                (camera_stamps[-1] - reference_stamps[-1]) / 1e9
            )

    return CheckResult(measurements=measurements, intervals=intervals)


def joint_discontinuity(
    episode: Episode,
    *,
    topic: str = "/joint_states",
    field: str = "position",
    velocity_limit: float = 3.0,
) -> CheckResult:
    """Finite-difference joint velocities against a configurable limit.

    Flags Dyna's "choppy joint states". Ships as measurements and intervals
    only -- never a default reject rule: motion-smoothness heuristics are
    known to invert on real defects (the Voxel51 result), so the threshold
    and any verdict stay user-owned.
    """
    channel = episode.channel(topic)
    positions = channel.to_numpy(field)
    if positions.ndim == 1:
        positions = positions[:, np.newaxis]
    stamps_ns = channel.timestamps
    if len(stamps_ns) < 2:
        return CheckResult(measurements={f"{topic}/message_count": len(stamps_ns)})

    deltas_s = np.diff(stamps_ns) / 1e9
    nonpositive_dt_count = int(np.sum(deltas_s <= 0))
    safe_deltas_s = np.where(deltas_s > 0, deltas_s, np.nan)
    velocities = np.abs(np.diff(positions, axis=0)) / safe_deltas_s[:, np.newaxis]
    per_step_max = np.nanmax(velocities, axis=1)
    violation_mask = per_step_max > velocity_limit

    intervals: list[Interval] = []
    run_start: int | None = None
    for index, violating in enumerate(violation_mask):
        if violating and run_start is None:
            run_start = index
        elif not violating and run_start is not None:
            intervals.append(
                Interval(
                    start_ns=int(stamps_ns[run_start]),
                    end_ns=int(stamps_ns[index]),
                    label=f"joint_discontinuity:{topic}",
                )
            )
            run_start = None
    if run_start is not None:
        intervals.append(
            Interval(
                start_ns=int(stamps_ns[run_start]),
                end_ns=int(stamps_ns[-1]),
                label=f"joint_discontinuity:{topic}",
            )
        )

    return CheckResult(
        measurements={
            f"{topic}/max_abs_velocity": float(np.nanmax(per_step_max)),
            f"{topic}/velocity_limit": velocity_limit,
            f"{topic}/violation_count": int(np.sum(violation_mask)),
            f"{topic}/violation_pct": float(np.mean(violation_mask) * 100.0),
            f"{topic}/nonpositive_dt_count": nonpositive_dt_count,
        },
        intervals=intervals,
    )
