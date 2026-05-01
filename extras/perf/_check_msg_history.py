"""Check when each of the log_application message types we depend on first appeared."""
import pandas as pd
from _db import get_conn


def main():
    conn, tunnel = get_conn()
    try:
        for label, like in [
            ("STARTING TASK", "STARTING TASK:%"),
            ("FINISHED TASK", "FINISHED TASK:%"),
            ("End-to-end transition", "End-to-end transition:%"),
            ("Inter-task gap (STM idle)", "Inter-task gap (STM idle):%"),
            ("stop_acq took", "stop_acq took:%"),
            ("Total task WAIT took", "Total task WAIT took:%"),
            ("Transition: device stop", "Transition: device stop took%"),
            ("Transition: device start", "Transition: device start took%"),
        ]:
            q = """
            SELECT MIN(server_time) AS first_seen, MAX(server_time) AS last_seen,
                   COUNT(*) AS n
            FROM log_application
            WHERE message LIKE %s
            """
            r = pd.read_sql_query(q, conn, params=(like,))
            print(f"  {label:30s}  first={r.first_seen.iloc[0]}  last={r.last_seen.iloc[0]}  n={int(r.n.iloc[0])}")
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()


if __name__ == "__main__":
    main()
