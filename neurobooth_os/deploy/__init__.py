"""One-command, blue-green deployment of a booth environment.

Run on an environment's CTR machine::

    nb_deploy                    # staging: deploy each repo's default branch
    nb_deploy --os-ref BRANCH    # any branch, tag or commit
    nb_deploy rollback           # undo the last deploy

See docs/deployment.md.

Everything in this package except ``orchestrator`` and ``__main__`` must stay
standard-library only: ``agent`` and its helpers are copied to STM/ACQ and run
there with a bare interpreter, outside the booth venv they are rebuilding.
"""
