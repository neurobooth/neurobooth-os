"""Investigate sessions that exited without logging a critical error.

A server's main() logs `critical("An uncaught exception occurred. Exiting...")`
on any caught exception, so a MISSING critical row means the exit bypassed that
path: a hard crash (faulthandler->neurobooth_crash.log only), the logging
blackout (PostgreSQLHandler.emit swallows DB errors -> stdout), or an external
kill/power-loss/force-restart after a hang.

Restart markers (logged right after make_db_logger() at process launch):
  CTR  -> "Starting GUI"     (gui.py)
  STM  -> "Starting STM"     (server_stm.py)
  ACQ  -> "Starting ACQ ..." (server_acq.py)

Stage 1 (no args): discovery -- per day, count restart markers and list the
days/sessions with repeated restarts.
Stage 2 (--date YYYY-MM-DD): deep dive on that day -- per restart marker, show
the tail of log activity (all servers) immediately before it, the time gap, and
whether a critical/error preceded it.
"""
import argparse
import sys

import pandas as pd
from _db import get_conn

RESTART_LIKE = (
    "message LIKE 'Starting GUI%%' "
    "OR message LIKE 'Starting STM%%' "
    "OR message LIKE 'Starting ACQ%%'"
)


def discover(conn, days: int) -> None:
    print(f"=== Restart markers in the last {days} days ===\n")
    q = f"""
    SELECT server_time::date AS day,
           server_type,
           server_id,
           count(*) AS restarts
    FROM log_application
    WHERE server_time >= (now() - interval '%s days')
      AND ({RESTART_LIKE})
    GROUP BY day, server_type, server_id
    ORDER BY day DESC, server_type, server_id
    """
    df = pd.read_sql_query(q, conn, params=(days,))
    if df.empty:
        print("No restart markers found in window.")
        return
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(df.to_string(index=False))

    # Days where any single process restarted 3+ times -> candidates
    hot = df[df["restarts"] >= 3]
    print("\n=== Days with a process restarted 3+ times (candidates) ===")
    if hot.empty:
        print("(none at >=3; showing per-day totals instead)")
        tot = df.groupby("day")["restarts"].sum().reset_index().sort_values("day", ascending=False)
        print(tot.to_string(index=False))
    else:
        print(hot.to_string(index=False))

    # Sessions active on the hottest day
    print("\n=== Distinct sessions per candidate day ===")
    for day in sorted(df[df["restarts"] >= 3]["day"].unique(), reverse=True):
        sq = """
        SELECT DISTINCT session_id
        FROM log_application
        WHERE server_time::date = %s AND session_id <> ''
        ORDER BY session_id
        """
        s = pd.read_sql_query(sq, conn, params=(str(day),))
        print(f"  {day}: {', '.join(s['session_id'].tolist()) or '(none)'}")


# The 23:00 nightly re-split backlog spams hundreds of identical error rows
# that have nothing to do with live sessions. Exclude from the error scan.
NOISE_FUNCS = ("postprocess_xdf_split",)


def deep_dive(conn, day: str, tail: int, before_s: int) -> None:
    print(f"=== Deep dive on {day} ===\n")

    # GUI (control) restarts are the true "system restarted" signal: the STM
    # machine logs 2 markers/launch, so only count control.
    rq = """
    SELECT server_time, server_id, session_id, message
    FROM log_application
    WHERE server_time::date = %s AND server_type = 'control'
      AND message LIKE 'Starting GUI%%'
    ORDER BY server_time
    """
    restarts = pd.read_sql_query(rq, conn, params=(day,))
    restarts["gap_since_prev_min"] = (
        restarts["server_time"].diff().dt.total_seconds() / 60).round(1)
    print(f"{len(restarts)} GUI (full-system) restart(s) on {day}:")
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(restarts[["server_time", "gap_since_prev_min", "session_id"]].to_string(index=False))

    # Full day timeline
    tq = """
    SELECT server_time, server_type, server_id, session_id, log_level,
           filename, function, line_no, message, traceback
    FROM log_application
    WHERE server_time::date = %s
    ORDER BY server_time
    """
    allrows = pd.read_sql_query(tq, conn, params=(day,))
    print(f"\nTotal rows that day: {len(allrows)}")
    print("Level counts:", allrows["log_level"].value_counts().to_dict())

    # Error/critical, EXCLUDING the nightly re-split backlog noise
    bad = allrows[allrows["log_level"].isin(["error", "critical"])
                  & ~allrows["function"].isin(NOISE_FUNCS)]
    n_noise = ((allrows["log_level"] == "error")
               & allrows["function"].isin(NOISE_FUNCS)).sum()
    print(f"\n=== {len(bad)} error/critical rows (excl. {n_noise} postprocess-backlog) ===")
    with pd.option_context("display.width", 220, "display.max_colwidth", 110, "display.max_rows", 300):
        if not bad.empty:
            print(bad[["server_time", "server_type", "server_id", "log_level",
                       "function", "message"]].to_string(index=False))
    n_crit = (allrows["log_level"] == "critical").sum()
    print(f"\n*** critical rows the entire day: {n_crit} ***")

    # For each GUI restart, merged cross-server timeline in the window before it
    print(f"\n\n=== Cross-server activity in the {before_s}s before each GUI restart ===")
    for _, r in restarts.iterrows():
        t0 = r["server_time"]
        win = allrows[(allrows["server_time"] < t0)
                      & (allrows["server_time"] >= t0 - pd.Timedelta(seconds=before_s))]
        # Last event from EACH server before the restart (who went silent, when)
        print(f"\n--- GUI restart at {t0} (gap {r['gap_since_prev_min']} min) ---")
        for st in ("control", "presentation", "acquisition"):
            prior_st = allrows[(allrows["server_type"] == st) & (allrows["server_time"] < t0)]
            if prior_st.empty:
                print(f"    {st:13s}: (no prior rows)")
                continue
            last = prior_st.iloc[-1]
            silence = (t0 - last["server_time"]).total_seconds()
            print(f"    {st:13s}: last at {last['server_time']} "
                  f"({silence:6.1f}s before restart) [{last['log_level']}] "
                  f"{last['function']}: {last['message'][:80]}")
        if win.empty:
            print(f"  (no rows in the {before_s}s window)")
            continue
        disp = win.tail(tail).copy()
        disp["t"] = disp["server_time"].dt.strftime("%H:%M:%S")
        disp["src"] = disp["server_type"].str[:4]
        with pd.option_context("display.width", 220, "display.max_colwidth", 95, "display.max_rows", 80):
            print(disp[["t", "src", "log_level", "function", "message"]].to_string(index=False))


CLEAN_CLOSE = "Closing app log db connection"


def audit_shutdowns(conn, days: int) -> None:
    """Flag every GUI/ACQ relaunch NOT preceded by a clean log-handler close.

    Clean exits log '%s' last (logging.shutdown -> handler.close). If the row
    immediately before a 'Starting' marker (same server_id) is anything else,
    the process died without running shutdown: external kill, hang+forcequit,
    power loss, segfault, or a logging blackout that swallowed the final
    critical. Those are the true 'exited without a critical' events.
    """ % CLEAN_CLOSE
    print(f"=== Shutdown audit over last {days} days ===")
    print("Pairing each (re)start with the preceding row from the same machine.\n")

    # Only the unambiguous single-process machines: control(GUI) and acq(index0).
    targets = [
        ("control", "Starting GUI%"),
        ("acquisition", "Starting ACQ (index=0)%"),
    ]
    for server_type, like in targets:
        q = """
        SELECT server_time, server_id, log_level, function, message
        FROM log_application
        WHERE server_type = %s
          AND server_time >= (now() - interval '%s days')
        ORDER BY server_id, server_time
        """
        df = pd.read_sql_query(q, conn, params=(server_type, days))
        if df.empty:
            print(f"--- {server_type}: no rows ---\n")
            continue
        starts = df[df["message"].str.startswith(like.rstrip("%"))]
        print(f"--- {server_type}: {len(starts)} (re)starts ---")
        rows = []
        for idx in starts.index:
            t0 = df.at[idx, "server_time"]
            sid = df.at[idx, "server_id"]
            # previous row from same server_id
            prev = df[(df["server_id"] == sid) & (df["server_time"] < t0)]
            if prev.empty:
                cls, prevmsg, gap = "FIRST_SEEN", "(none)", None
            else:
                p = prev.iloc[-1]
                gap = (t0 - p["server_time"]).total_seconds()
                if p["message"] == CLEAN_CLOSE:
                    cls = "clean"
                elif gap > 3600:
                    cls = "GAP>1h (likely overnight boot)"
                else:
                    cls = "*** UNCLEAN ***"
                prevmsg = f"[{p['log_level']}] {p['function']}: {p['message'][:70]}"
            rows.append({"restart_at": t0, "class": cls,
                         "gap_s": None if gap is None else round(gap, 1),
                         "prev_row": prevmsg})
        out = pd.DataFrame(rows)
        with pd.option_context("display.width", 240, "display.max_colwidth", 90, "display.max_rows", 200):
            print(out.to_string(index=False))
        n_unclean = out["class"].str.contains("UNCLEAN").sum()
        print(f"  >> {n_unclean} UNCLEAN (silent-exit) of {len(out)} restarts\n")


def xcheck(conn, day: str) -> None:
    """Crash-vs-blackout discriminator for ACQ silent exits on `day`.

    SystemResourceLogger runs IN the ACQ process but on its OWN db connection.
    For each ACQ silent exit (app-log stops without a clean close), compare the
    last app-log time to the last log_system_resource sample from the same
    machine in that window:
      both stop together  -> process DIED (crash/external kill) -> no critical
      sysres keeps going   -> process ALIVE, app-logger blacked out (DB hiccup)
    """
    print(f"=== ACQ crash-vs-blackout cross-check on {day} ===\n")

    # machine names present in log_system_resource (find the ACQ one)
    mn = pd.read_sql_query(
        "SELECT DISTINCT machine_name FROM log_system_resource "
        "WHERE created_at::date = %s", conn, params=(day,))
    print("system_resource machines that day:", mn["machine_name"].tolist())
    acq_machine = next((m for m in mn["machine_name"] if "ACQ" in m.upper()), None)
    if acq_machine is None:
        print("No ACQ machine in log_system_resource; cannot cross-check.")
        return
    print(f"Using ACQ machine_name = {acq_machine!r}\n")

    # ACQ app-log rows + ACQ restart markers
    app = pd.read_sql_query("""
        SELECT server_time, message FROM log_application
        WHERE server_type='acquisition' AND server_time::date = %s
        ORDER BY server_time
    """, conn, params=(day,))
    starts = app[app["message"].str.startswith("Starting ACQ (index=0)")]

    res = pd.read_sql_query("""
        SELECT created_at FROM log_system_resource
        WHERE machine_name = %s AND created_at::date = %s
        ORDER BY created_at
    """, conn, params=(acq_machine, day))
    print(f"{len(res)} ACQ system_resource samples; "
          f"{len(starts)} ACQ (index=0) restarts.\n")

    for idx in starts.index:
        t0 = app.at[idx, "server_time"]
        prior_app = app[app["server_time"] < t0]
        if prior_app.empty:
            continue
        last_app = prior_app["server_time"].iloc[-1]
        last_msg = prior_app["message"].iloc[-1][:60]
        # system_resource around the silent-exit point
        sr_before = res[res["created_at"] <= last_app + pd.Timedelta(seconds=5)]
        sr_after_gap = res[(res["created_at"] > last_app)
                           & (res["created_at"] < t0)]
        last_sr = sr_before["created_at"].iloc[-1] if not sr_before.empty else None
        sr_lag = None if last_sr is None else (last_app - last_sr).total_seconds()
        verdict = ("PROC DIED (sysres stops with app-log)"
                   if len(sr_after_gap) == 0 else
                   f"BLACKOUT? {len(sr_after_gap)} sysres samples AFTER app-log went silent")
        print(f"restart {t0}  app-log last {last_app} ({last_msg!r})")
        print(f"    last ACQ sysres sample {last_sr} (lag {sr_lag}s) | "
              f"sysres samples in the silent window: {len(sr_after_gap)} -> {verdict}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=10, help="discovery window (days)")
    ap.add_argument("--audit", action="store_true", help="run the shutdown audit")
    ap.add_argument("--xcheck", type=str, default=None, help="crash-vs-blackout xcheck for YYYY-MM-DD")
    ap.add_argument("--date", type=str, default=None, help="deep-dive day YYYY-MM-DD")
    ap.add_argument("--tail", type=int, default=25, help="rows of tail per restart")
    ap.add_argument("--before", type=int, default=180, help="seconds before restart to show")
    args = ap.parse_args()

    conn, tunnel = get_conn()
    try:
        if args.xcheck:
            xcheck(conn, args.xcheck)
        elif args.audit:
            audit_shutdowns(conn, args.days)
        elif args.date:
            deep_dive(conn, args.date, args.tail, args.before)
        else:
            discover(conn, args.days)
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()


if __name__ == "__main__":
    main()
