@echo off
:: Deploy neurobooth-os + configs to every machine of this environment.
:: Run on the environment's CTR machine. See docs\deployment.md.
::
::   nb_deploy                                  staging: default branches
::   nb_deploy --os-ref v1.2.3 --config-ref v1.2.3
::   nb_deploy rollback
::   nb_deploy status
::
:: Runs outside the booth venv (uv run --no-project) because a deploy rebuilds
:: venvs, and from the user's home so no shell holds a handle inside the install.
::
:: Everything after setup is one parenthesized block: cmd.exe re-reads a .bat
:: from disk as it goes, and this file lives in the install a deploy re-points.
:: A block is parsed in full before it runs.
setlocal EnableDelayedExpansion
set "PYTHONPATH=%~dp0"
pushd "%USERPROFILE%"
(
    uv run --no-project --with "pyyaml>=6.0" --with "pydantic>=2.5.2" python -m neurobooth_os.deploy %*
    set "NB_DEPLOY_EXIT=!ERRORLEVEL!"
    popd
    exit /b !NB_DEPLOY_EXIT!
)
