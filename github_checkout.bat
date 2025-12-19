@echo off
setlocal enabledelayedexpansion

REM This script checks out the provided tag and updates the version number in the installed system to be the tag number

REM Check if tag argument is provided
if "%~1"=="" (
    echo Usage: %~nx0 ^<tag^>
    echo Example: %~nx0 v1.0.0
    exit /b 1
)

set TAG=%~1

REM Check if we're in a git repository
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo Error: Not a git repository
    exit /b 1
)

REM Fetch all tags from remote
echo Fetching tags from remote...
git fetch --tags --force
if errorlevel 1 (
    echo Error: Failed to fetch tags
    exit /b 1
)

REM Check if tag exists
git rev-parse %TAG% >nul 2>&1
if errorlevel 1 (
    echo Error: Tag '%TAG%' not found
    exit /b 1
)

REM Checkout the tag
echo Checking out tag: %TAG%
git checkout %TAG%
if errorlevel 1 (
    echo Error: Failed to checkout tag '%TAG%'
    exit /b 1
)

REM Write tag to file
set TAG_FILE=current_release.py
(
    echo.
    echo.
    echo """
    echo     Stores neurobooth version number.
    echo     GENERATED FILE. DO NOT EDIT MANUALLY
    echo """
    echo.
    echo version = '%TAG%'
) > %TAG_FILE%if errorlevel 1 (
    echo Error: Failed to write tag to file
    exit /b 1
)

echo.
echo Successfully checked out tag: %TAG%
echo Tag written to: %TAG_FILE%
exit /b 0