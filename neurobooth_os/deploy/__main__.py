"""``nb_deploy`` command line. Run on an environment's CTR machine.

Usage::

    nb_deploy [deploy] [--os-ref REF] [--config-ref REF] [--env NAME] [--dry-run]
    nb_deploy rollback [--dry-run]
    nb_deploy status
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

import neurobooth_os.config as cfg
from neurobooth_os.deploy import gitops
from neurobooth_os.deploy.orchestrator import (
    DeployError,
    Orchestrator,
    machines_from_config,
)
from neurobooth_os.deploy.slots import MachineLayout, SlotError


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="nb_deploy", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="deploy", choices=["deploy", "rollback", "status"])
    parser.add_argument("--os-ref", help="neurobooth-os branch, tag or commit "
                        "(default: the repo's default branch; staging only)")
    parser.add_argument("--config-ref", help="configs branch, tag or commit "
                        "(default: the repo's default branch; staging only)")
    parser.add_argument("--env", help="folder under configs/environments/ "
                        "(default: the 'environment' field of the active config)")
    parser.add_argument("--config", type=Path, help="neurobooth_os_config.yaml to read machines from "
                        "(default: the one in NB_CONFIG)")
    parser.add_argument("--dry-run", action="store_true", help="show what would change; change nothing")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        cfg.load_neurobooth_config(str(args.config) if args.config else None)
        config = cfg.neurobooth_config
        orchestrator = Orchestrator(
            environment=args.env or config.environment,
            targets=machines_from_config(config),
            ctr_layout=MachineLayout(Path.home()),
        )
        if args.command == "rollback":
            return orchestrator.rollback(dry_run=args.dry_run)
        if args.command == "status":
            return orchestrator.status()
        return orchestrator.deploy(args.os_ref, args.config_ref, dry_run=args.dry_run)
    except (DeployError, SlotError, gitops.GitError, cfg.ConfigException) as error:
        print(f"nb_deploy: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
