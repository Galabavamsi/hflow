"""Built-in checks, shipped in the same shape users write (evidence, not
verdicts; thresholds user-owned). Wrap them to register::

    @app.check()
    def timestamps(ep: hflow.Episode) -> hflow.CheckResult:
        return hflow.checks.timestamp_regularity(ep, tolerance_s=0.010)
"""

import hashlib
from collections.abc import Sequence

import numpy as np

from hflow.episode import Episode
from hflow.ffmpeg import frame_stats
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


def camera_frame_stats(
    episode: Episode,
    *,
    cameras: Sequence[str] | None = None,
    expected_hz: dict[str, float] | None = None,
    black_frame_amount_pct: int = 98,
    black_pixel_threshold: int = 32,
    freeze_noise_db: float = -60.0,
    freeze_min_duration_s: float = 2.0,
) -> CheckResult:
    """Camera blackout, freeze, exposure, and frame-count evidence per camera.

    Wraps the single-decode ffmpeg instrument (``hflow.ffmpeg.frame_stats``:
    blackframe + freezedetect + signalstats in one filter graph, one shared
    frame denominator) over each camera's lossless MP4 remux, and compares
    the stored frame count against the rate the stream claims (declared
    ``expected_hz`` when given, else the stream's median delta) -- the
    LeRobot-style frame-count-vs-rate question. Freeze spans become labeled
    ``freeze:<topic>`` intervals in log time. Requires a canonical episode
    (``Episode.video`` remuxes in-band H.264 only).

    Evidence only, as always: blackout/exposure thresholds and any verdict
    stay user-owned.
    """
    selected_cameras = list(cameras) if cameras is not None else episode.cameras
    measurements: dict[str, float | int | str | bool] = {}
    intervals: list[Interval] = []
    for topic in selected_cameras:
        stamps_ns = episode.channel(topic).timestamps
        message_count = len(stamps_ns)
        measurements[f"{topic}/message_count"] = message_count
        if message_count >= 2:
            deltas_s = np.diff(stamps_ns) / 1e9
            declared_hz = (expected_hz or {}).get(topic)
            expected_period_s = 1.0 / declared_hz if declared_hz else float(np.median(deltas_s))
            span_s = float((stamps_ns[-1] - stamps_ns[0]) / 1e9)
            expected_frame_count = round(span_s / expected_period_s) + 1
            measurements[f"{topic}/expected_frame_count"] = expected_frame_count
            measurements[f"{topic}/frame_deficit_pct"] = float(
                100.0 * (expected_frame_count - message_count) / expected_frame_count
            )

        stats = frame_stats(
            episode.video(topic),
            black_frame_amount_pct=black_frame_amount_pct,
            black_pixel_threshold=black_pixel_threshold,
            freeze_noise_db=freeze_noise_db,
            freeze_min_duration_s=freeze_min_duration_s,
        )
        measurements[f"{topic}/decoded_frame_count"] = stats.frame_count
        measurements[f"{topic}/black_frame_pct"] = stats.black_frame_pct
        measurements[f"{topic}/freeze_total_s"] = stats.freeze_total_s
        measurements[f"{topic}/luma_avg_mean"] = stats.luma_avg_mean
        measurements[f"{topic}/luma_avg_min"] = stats.luma_avg_min
        measurements[f"{topic}/luma_avg_max"] = stats.luma_avg_max
        if message_count:
            # Instrument times are seconds from the MP4 start, which is the
            # camera's first message; map freezes back onto the log clock.
            stream_start_ns = int(stamps_ns[0])
            intervals.extend(
                Interval(
                    start_ns=stream_start_ns + int(freeze_start_s * 1e9),
                    end_ns=stream_start_ns + int(freeze_end_s * 1e9),
                    label=f"freeze:{topic}",
                )
                for freeze_start_s, freeze_end_s in stats.freeze_intervals
            )
    return CheckResult(measurements=measurements, intervals=intervals)


def idle_fraction(
    episode: Episode,
    *,
    topic: str = "/joint_states",
    field: str | None = None,
    velocity_epsilon: float = 0.05,
    min_interval_s: float = 1.0,
) -> CheckResult:
    """Time-weighted fraction of the episode spent with no joint moving.

    A step is idle when every joint's finite-difference speed is below
    ``velocity_epsilon``; the fraction weights each step by its own duration,
    so irregular sampling does not skew it. Idle runs at least
    ``min_interval_s`` long become labeled ``idle:<topic>`` intervals.
    Evidence for curation cuts over mostly-stationary demonstrations -- the
    keep/drop policy (and any verdict) stays user-owned.
    """
    channel = episode.channel(topic)
    positions = channel.to_numpy(field)
    if positions.ndim == 1:
        positions = positions[:, np.newaxis]
    stamps_ns = channel.timestamps
    if len(stamps_ns) < 2:
        return CheckResult(measurements={f"{topic}/message_count": len(stamps_ns)})

    deltas_s = np.diff(stamps_ns) / 1e9
    safe_deltas_s = np.where(deltas_s > 0, deltas_s, np.nan)
    velocities = np.abs(np.diff(positions, axis=0)) / safe_deltas_s[:, np.newaxis]
    per_step_max = np.nanmax(velocities, axis=1)
    idle_mask = per_step_max < velocity_epsilon
    positive_deltas_s = np.where(deltas_s > 0, deltas_s, 0.0)
    total_span_s = float(np.sum(positive_deltas_s))
    idle_total_s = float(np.sum(positive_deltas_s[idle_mask]))

    intervals: list[Interval] = []
    run_start: int | None = None
    for index, is_idle in enumerate(idle_mask):
        if is_idle and run_start is None:
            run_start = index
        elif not is_idle and run_start is not None:
            if (stamps_ns[index] - stamps_ns[run_start]) / 1e9 >= min_interval_s:
                intervals.append(
                    Interval(
                        start_ns=int(stamps_ns[run_start]),
                        end_ns=int(stamps_ns[index]),
                        label=f"idle:{topic}",
                    )
                )
            run_start = None
    if run_start is not None and (stamps_ns[-1] - stamps_ns[run_start]) / 1e9 >= min_interval_s:
        intervals.append(
            Interval(
                start_ns=int(stamps_ns[run_start]),
                end_ns=int(stamps_ns[-1]),
                label=f"idle:{topic}",
            )
        )

    return CheckResult(
        measurements={
            f"{topic}/idle_fraction": idle_total_s / total_span_s if total_span_s else 0.0,
            f"{topic}/idle_total_s": idle_total_s,
            f"{topic}/velocity_epsilon": velocity_epsilon,
        },
        intervals=intervals,
    )


def episode_duration(episode: Episode, *, topics: Sequence[str] | None = None) -> CheckResult:
    """Episode span and message volume, recorded for curation-side outlier cuts.

    An outlier is a corpus-relative judgment, so it cannot be decided inside
    a per-episode check without baking a threshold into the corpus; this
    check records the evidence and the cut is a curation query, e.g.::

        SELECT episode_id FROM episodes
        WHERE duration_s < 2 OR duration_s > 300
    """
    infos = episode.topics
    selected = (
        list(topics)
        if topics is not None
        else sorted(topic for topic, info in infos.items() if info.message_count >= 1)
    )
    start_candidates_ns: list[int] = []
    end_candidates_ns: list[int] = []
    message_count_total = 0
    for topic in selected:
        stamps_ns = episode.channel(topic).timestamps
        if len(stamps_ns) == 0:
            continue
        message_count_total += len(stamps_ns)
        start_candidates_ns.append(int(stamps_ns[0]))
        end_candidates_ns.append(int(stamps_ns[-1]))
    duration_s = (
        (max(end_candidates_ns) - min(start_candidates_ns)) / 1e9 if start_candidates_ns else 0.0
    )
    return CheckResult(
        measurements={
            "duration_s": duration_s,
            "message_count_total": message_count_total,
            "topic_count": len(selected),
        }
    )


def content_digest(episode: Episode) -> CheckResult:
    """A stable digest of the episode's message content, for duplicate hunts.

    SHA-256 over every channel's log times and raw payloads (channels in
    (topic, channel_id) order), so it identifies the recorded *content*
    independent of container layout: two files that differ only in chunking,
    compression, or metadata records digest the same. Exact-duplicate
    detection is then a curation query::

        SELECT value_text AS digest, count(*) AS copies
        FROM measurements WHERE key = 'content_digest'
        GROUP BY digest HAVING count(*) > 1

    Note ``episode_id`` already content-addresses the canonical *file*, which
    dedupes byte-identical re-ingests on its own; this digest additionally
    catches the same recording landed under different names or provenance.
    """
    digest = hashlib.sha256()
    ordered_channels = sorted(
        episode.channels.values(), key=lambda info: (info.topic, info.channel_id)
    )
    for info in ordered_channels:
        channel = episode.channel(info.channel_id)
        digest.update(info.topic.encode())
        digest.update(len(channel.raw).to_bytes(8, "big"))
        for log_time_ns, payload in zip(channel.timestamps, channel.raw, strict=True):
            digest.update(int(log_time_ns).to_bytes(8, "big", signed=True))
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return CheckResult(measurements={"content_digest": digest.hexdigest()})
