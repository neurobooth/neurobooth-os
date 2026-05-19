"""Unit tests for extras/perf/timing_session_metrics.py.

Only the pure transform layer is exercised (the live DB path needs the SSH
tunnel + production Postgres). The Tier-2 scaffold must stay inert: it has to
raise rather than silently return a fabricated number.
"""

import pandas as pd
import pytest

import timing_session_metrics as sm


def _df():
    rows = []

    def add(sid, date, task, dev, t0, t1):
        rows.append(
            dict(
                device_id=dev,
                log_session_id=sid,
                session_date=date,
                task_id=task,
                task_start=pd.Timestamp(t0),
                task_end=pd.Timestamp(t1),
            )
        )

    # baseline session 1, task A: marker@00.000, Intel +0.5s, FLIR +1.2s
    add(
        1, "2026-01-10", "A", "Marker", "2026-01-10 10:00:00.000", "2026-01-10 10:01:00"
    )
    add(1, "2026-01-10", "A", "Intel", "2026-01-10 10:00:00.500", "2026-01-10 10:01:00")
    add(1, "2026-01-10", "A", "FLIR", "2026-01-10 10:00:01.200", "2026-01-10 10:01:00")
    # baseline session 2, task A: skew 0.4s, marker latency 0.1s
    add(
        2, "2026-02-01", "A", "Marker", "2026-02-01 09:00:00.000", "2026-02-01 09:01:00"
    )
    add(2, "2026-02-01", "A", "Intel", "2026-02-01 09:00:00.100", "2026-02-01 09:01:00")
    add(2, "2026-02-01", "A", "FLIR", "2026-02-01 09:00:00.400", "2026-02-01 09:01:00")
    # pilot session 3, task A: skew 2.0s, marker latency 0.3s
    add(
        3, "2026-04-05", "A", "Marker", "2026-04-05 11:00:00.000", "2026-04-05 11:01:30"
    )
    add(3, "2026-04-05", "A", "Intel", "2026-04-05 11:00:00.300", "2026-04-05 11:01:30")
    add(3, "2026-04-05", "A", "FLIR", "2026-04-05 11:00:02.000", "2026-04-05 11:01:30")
    # session 4 in the gap -> must be excluded by assign_period
    add(4, "2026-03-10", "A", "Marker", "2026-03-10 11:00:00", "2026-03-10 11:01:00")
    add(4, "2026-03-10", "A", "Intel", "2026-03-10 11:00:05", "2026-03-10 11:01:00")
    return pd.DataFrame(rows)


BASELINE = ("2026-01-01", "2026-03-03")
PILOT = ("2026-03-20", "2026-05-15")


def test_assign_period_buckets_and_excludes_gap():
    tagged = sm.assign_period(_df(), BASELINE, PILOT)
    by_session = tagged.groupby("log_session_id")["period"].first().to_dict()
    assert by_session[1] == "baseline"
    assert by_session[2] == "baseline"
    assert by_session[3] == "pilot"
    assert by_session[4] is None  # in the deliberate gap


def test_start_skew_values():
    tagged = sm.assign_period(_df(), BASELINE, PILOT)
    skew = sm.start_skew(tagged[tagged["period"].notna()])
    by_session = skew.set_index("log_session_id")["skew_sec"].to_dict()
    assert by_session[1] == pytest.approx(1.2)
    assert by_session[2] == pytest.approx(0.4)
    assert by_session[3] == pytest.approx(2.0)
    assert set(skew["n_devices"]) == {3}


def test_marker_first_sample_latency_values():
    tagged = sm.assign_period(_df(), BASELINE, PILOT)
    lat = sm.marker_first_sample_latency(tagged[tagged["period"].notna()])
    by_session = lat.set_index("log_session_id")["marker_latency_sec"].to_dict()
    assert by_session[1] == pytest.approx(0.5)
    assert by_session[2] == pytest.approx(0.1)
    assert by_session[3] == pytest.approx(0.3)


def test_marker_latency_empty_without_marker_rows():
    df = _df()
    df = df[df["device_id"] != "Marker"]
    lat = sm.marker_first_sample_latency(df)
    assert lat.empty


def test_device_span():
    spans = sm.device_span(_df())
    s1 = spans[(spans["log_session_id"] == 1) & (spans["device_id"] == "Marker")]
    assert s1["span_sec"].iloc[0] == pytest.approx(60.0)


def test_summarize_empty_and_nonempty():
    empty = sm.summarize(pd.Series([], dtype=float))
    assert empty["n"] == 0 and empty["mean"] is None and empty["p95"] is None

    s = sm.summarize(pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert s["n"] == 4
    assert s["mean"] == pytest.approx(2.5)
    assert s["median"] == pytest.approx(2.5)
    assert s["sd"] == pytest.approx(pd.Series([1.0, 2, 3, 4]).std(ddof=0))


def test_ab_summary_delta_sign():
    df = pd.DataFrame(
        {
            "period": ["baseline", "baseline", "pilot", "pilot"],
            "v": [1.0, 3.0, 10.0, 12.0],
        }
    )
    out = sm.ab_summary(df, "v")
    assert out["baseline"]["mean"] == pytest.approx(2.0)
    assert out["pilot"]["mean"] == pytest.approx(11.0)
    assert out["delta"]["mean"] == pytest.approx(9.0)


def test_ab_summary_delta_none_when_one_side_empty():
    df = pd.DataFrame({"period": ["baseline", "baseline"], "v": [1.0, 2.0]})
    out = sm.ab_summary(df, "v")
    assert out["pilot"]["n"] == 0
    assert out["delta"]["mean"] is None


def test_compute_metrics_end_to_end():
    metrics = sm.compute_metrics(_df(), BASELINE, PILOT)
    assert metrics["session_counts"] == {"baseline": 2, "pilot": 1}

    skew = metrics["cross_device_start_skew_sec"]
    assert skew["baseline"]["mean"] == pytest.approx(0.8)  # mean(1.2, 0.4)
    assert skew["pilot"]["mean"] == pytest.approx(2.0)
    assert skew["delta"]["mean"] == pytest.approx(1.2)

    lat = metrics["marker_to_first_sample_latency_sec"]
    assert lat["baseline"]["mean"] == pytest.approx(0.3)  # mean(0.5, 0.1)

    # Tier-2 must be an explicit deferred sentinel, never a number.
    sl = metrics["sample_level"]
    assert sl["status"] == "deferred"
    assert "HDF5" in sl["data_source"]
    assert sl["metrics_pending"]


def test_compute_metrics_marker_note_when_no_marker():
    df = _df()
    df = df[df["device_id"] != "Marker"]
    metrics = sm.compute_metrics(df, BASELINE, PILOT)
    blk = metrics["marker_to_first_sample_latency_sec"]
    assert blk["note"] == "no Marker device rows in range"
    assert blk["delta"]["mean"] is None


@pytest.mark.parametrize(
    "fn",
    [
        sm.frame_interval_jitter_from_hdf5,
        sm.native_vs_lsl_drift_ppm_from_hdf5,
        sm.dropped_duplicated_frames_from_hdf5,
    ],
)
def test_tier2_scaffolds_raise_not_implemented(fn):
    with pytest.raises(NotImplementedError) as exc:
        fn("anything")
    assert "methodology review" in str(exc.value)
