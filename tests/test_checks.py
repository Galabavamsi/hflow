"""Direct unit tests for the built-in checks (paths e2e only grazes)."""

from pathlib import Path

import pytest

import hflow
from hflow.checks import joint_discontinuity, timestamp_regularity
from hflow.testing import SyntheticEpisodeSpec, synthesize_episode


@pytest.fixture(scope="module")
def jittery_episode(tmp_path_factory: pytest.TempPathFactory) -> hflow.Episode:
    """State-only episode with the +3ms timestamp-offset segment enabled...

    on the camera -- so use a camera-bearing spec but a short one; the offset
    segment lives on camera 0 per the fixture contract.
    """
    path = synthesize_episode(
        tmp_path_factory.mktemp("checks") / "episode.mcap",
        SyntheticEpisodeSpec(
            duration_s=4.0,
            timestamp_offset_segment=(2.0, 3.0),
            joint_jump_at_s=1.5,
        ),
    )
    return hflow.Episode(path)


def test_declared_rate_beats_median_inference(jittery_episode: hflow.Episode) -> None:
    # With a deliberately wrong declared rate, every delta violates.
    result = timestamp_regularity(
        jittery_episode,
        topics=["/joint_states"],
        expected_hz={"/joint_states": 50.0},  # actual: 100 Hz
        tolerance_s=0.001,
    )
    violation_pct = result.measurements["/joint_states/violation_pct"]
    assert isinstance(violation_pct, float)
    assert violation_pct == 100.0


def test_offset_segment_is_flagged_at_tight_tolerance(jittery_episode: hflow.Episode) -> None:
    camera_topic = "/wrist_cam/compressed"
    result = timestamp_regularity(jittery_episode, topics=[camera_topic], tolerance_s=0.001)
    violation_pct = result.measurements[f"{camera_topic}/violation_pct"]
    assert isinstance(violation_pct, float)
    # The +3ms offset produces exactly two anomalous deltas (entry and exit).
    assert violation_pct > 0.0


def test_gap_intervals_are_labeled(tmp_path: Path) -> None:
    # A source with a genuine gap: build via the writer-level fixture trick --
    # simplest is a synthetic episode read back and re-checked with a small
    # gap_factor so the offset deltas register as gaps.
    path = synthesize_episode(
        tmp_path / "episode.mcap",
        SyntheticEpisodeSpec(duration_s=2.0, timestamp_offset_segment=(1.0, 1.5)),
    )
    with hflow.Episode(path) as episode:
        result = timestamp_regularity(episode, topics=["/wrist_cam/compressed"], gap_factor=1.02)
    assert result.intervals, "offset entry delta must exceed 1.02x the period"
    assert all(interval.label == "gap:/wrist_cam/compressed" for interval in result.intervals)


def test_cross_stream_sync_measurements_exist(jittery_episode: hflow.Episode) -> None:
    result = timestamp_regularity(jittery_episode)
    sync_keys = [key for key in result.measurements if key.startswith("sync/")]
    # Two cameras, each measured against the densest state topic, two bounds.
    assert len(sync_keys) == 4
    for key in sync_keys:
        assert "~/joint_states/" in key


def test_joint_discontinuity_finds_the_injected_jump(jittery_episode: hflow.Episode) -> None:
    result = joint_discontinuity(jittery_episode, velocity_limit=3.0)
    violation_count = result.measurements["/joint_states/violation_count"]
    assert isinstance(violation_count, int)
    assert violation_count >= 1
    assert result.intervals
    assert result.verdict is None  # evidence, not verdicts


def test_joint_discontinuity_high_limit_is_quiet(jittery_episode: hflow.Episode) -> None:
    result = joint_discontinuity(jittery_episode, velocity_limit=1e6)
    assert result.measurements["/joint_states/violation_count"] == 0
    assert result.intervals == []
