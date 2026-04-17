# neurobooth-terra change for db-coordinated file registration

This change belongs in the **neurobooth-terra** repo (not this repo) but is
required for the db-coordinated file registration work in neurobooth-os to
produce clean results. Apply it when deploying that change.

## File

`neurobooth_terra/dataflow.py`

## Function

`copy_files` (the only `log_sensor_file` lookup call site; other scripts that
query `log_sensor_file` are unaffected)

## Change

Around line 208, change the per-file lookup from:

```python
# query log_sensor_file table for this specific file
df = sensor_file_table.query(
    where=f"sensor_file_path @> ARRAY['{fname}']").reset_index()

# TODO: If query returns empty, check the log_task table for txt/csv file

if len(df.log_sensor_file_id) > 0:
    log_sensor_file_id = df.log_sensor_file_id[0]
else:
    # files with these extensions are not tracked yet
    untracked_extensions = ['xdf', 'txt', 'csv', 'jittered', 'asc', 'log']
    if not any(ext in fname for ext in untracked_extensions):
        print(f'log_sensor_file_id not found for {fname}')
    continue
```

to:

```python
# Query log_sensor_file joined with log_task.
# Incomplete tasks (cancelled or crashed before _perform_task completed)
# have log_sensor_file rows (written by ACQ at device-start time) but
# log_task.task_id is NULL. Filter those out so we don't transfer their
# orphaned files.
cursor = sensor_file_table.conn.cursor()
cursor.execute(
    """
    SELECT lsf.log_sensor_file_id
    FROM log_sensor_file lsf
    JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
    WHERE lsf.sensor_file_path @> ARRAY[%s]
      AND lt.task_id IS NOT NULL
    """,
    (fname,),
)
rows = cursor.fetchall()

if rows:
    log_sensor_file_id = rows[0][0]
else:
    # files with these extensions are not tracked yet
    untracked_extensions = ['xdf', 'txt', 'csv', 'jittered', 'asc', 'log']
    if not any(ext in fname for ext in untracked_extensions):
        print(f'log_sensor_file_id not found for {fname}')
    continue
```

## Effect

| Scenario | log_task.task_id | log_sensor_file | Copy action |
|---|---|---|---|
| Normal completion | set | yes, timing filled | transfer |
| User abort ('q') | set | yes, timing filled | transfer |
| Cancel before `_perform_task` | NULL | yes, no timing | **skip** |
| Crash before `_perform_task` | NULL | yes, no timing | **skip** |
| Bug: entry never created | -- | missing | **warn** (canary) |

The "log_sensor_file_id not found" canary is preserved — it only fires when
neither ACQ's early write nor XDF post-processing wrote a row, which means a
real bug (not a cancelled task).
