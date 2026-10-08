"""Stand-in for ``uv`` in the simulated booth.

``sync`` creates ``.venv`` in the working directory and records how it was
called; ``pip install`` records the install. A commit containing a file named
``FAIL_SYNC`` makes ``sync`` fail, so tests can push a broken commit.
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    arguments = sys.argv[1:]
    cwd = Path.cwd()
    venv = cwd / ".venv"
    record = {"arguments": arguments, "cwd": str(cwd), "nb_install": os.environ.get("NB_INSTALL"),
              "virtual_env": os.environ.get("VIRTUAL_ENV")}
    if arguments[:1] == ["sync"]:
        if (cwd / "FAIL_SYNC").exists():
            print("fake uv: sync failed (FAIL_SYNC present)", file=sys.stderr)
            return 1
        venv.mkdir(exist_ok=True)
        lock = cwd / "uv.lock"
        record["lock"] = lock.read_text(encoding="utf-8") if lock.exists() else None
        (venv / "sync.json").write_text(json.dumps(record), encoding="utf-8")
        return 0
    if arguments[:2] == ["pip", "install"]:
        venv.mkdir(exist_ok=True)
        (venv / "pip_install.json").write_text(json.dumps(record), encoding="utf-8")
        return 0
    print(f"fake uv: unsupported arguments {arguments}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
