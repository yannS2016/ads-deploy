@echo off
REM Bootstraps ads-deploy on a Windows TwinCAT XAE machine:
REM   1. Verify uv, pixi, and bash are installed.
REM   2. Install ads-deploy itself as a uv tool (global shim, no activation
REM      needed to run `ads-deploy`).
REM      Also installs the pathmunge-activate helper scripts alongside it,
REM      for ad hoc CLI use of pinned tools outside of TwinCAT/VS.
REM   3. Install the pinned pytmc and make versions, each into their own
REM      isolated pixi environment (pytmc from PyPI, make from conda-forge
REM      -- see ads_deploy/tool_registry.py).
REM   4. Fetch ads-ioc (its latest version is auto-discovered at build time
REM      by `ads-deploy build`, no cached location file needed).
REM   5. Regenerate external-tools.vssettings (Command=ads-deploy, resolved
REM      via PATH -- no per-machine install-location path to template).
REM
REM Every step below checks ERRORLEVEL and stops the script on failure --
REM a failed step must never be silently followed by later steps.

where uv >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo uv was not found on PATH.
    echo Install it first: https://docs.astral.sh/uv/getting-started/installation/
    EXIT /B 1
)

where pixi >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo pixi was not found on PATH ^(ads-deploy install needs it to
    echo provision tools from PyPI and conda-forge^).
    echo Install it first: https://pixi.sh/latest/installation/
    EXIT /B 1
)

REM Git for Windows provides both `git` (needed to fetch ads-ioc) and the
REM `sh.exe`/`bash.exe` that GNU Make's Windows port looks for to run
REM Makefile recipes -- ads-deploy's own code no longer invokes bash for
REM orchestration (see DESIGN.md), but make's own recipe execution can still
REM depend on it, so Git for Windows stays a prerequisite either way.
where git >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
    echo git was not found on PATH ^(needed to fetch ads-ioc, and make's own
    echo recipe execution typically needs the sh.exe Git for Windows provides^).
    echo Install Git for Windows: https://git-scm.com/download/win
    EXIT /B 1
)

REM %~dp0 always ends in a backslash; a trailing backslash right before a
REM closing quote escapes the quote on Windows, so strip it before quoting.
SET "RepoRoot=%~dp0"
SET "RepoRoot=%RepoRoot:~0,-1%"

IF "%PYTMC_VERSION%"=="" (
    echo Set PYTMC_VERSION to the pytmc version you want to pin, e.g.:
    echo     cmd.exe:     set PYTMC_VERSION=v2.22.2 ^&^& bootstrap.cmd
    echo     PowerShell:  $env:PYTMC_VERSION = "v2.22.2"; .\bootstrap.cmd
    EXIT /B 1
)

IF "%MAKE_VERSION%"=="" (
    echo Set MAKE_VERSION to the GNU Make version to pin ^(from conda-forge^),
    echo e.g. 4.4.1:
    echo     cmd.exe:     set MAKE_VERSION=4.4.1 ^&^& bootstrap.cmd
    echo     PowerShell:  $env:MAKE_VERSION = "4.4.1"; .\bootstrap.cmd
    EXIT /B 1
)

echo Installing ads-deploy as a uv tool from %RepoRoot% ...
uv tool install --force "%RepoRoot%"
IF %ERRORLEVEL% NEQ 0 (
    echo ** FAILED: could not install ads-deploy. **
    EXIT /B 1
)

REM Drop the pathmunge-activate helper scripts next to the ads-deploy shim
REM itself (uv's own tool-shim bin dir, already on PATH) so they're
REM immediately callable from any shell with no extra PATH setup. These
REM exist for ad hoc CLI use outside of TwinCAT/VS -- `ads-deploy pathmunge`
REM alone can only ever PRINT the resolved PATH fragment (a plain .exe can
REM never modify its parent shell's environment), so these wrap the same
REM capture-and-prepend config.cmd already does, for direct interactive use.
FOR /F "usebackq delims=" %%B in (`uv tool dir --bin`) DO SET "UvToolBin=%%B"
copy /Y "%RepoRoot%\ads_deploy\windows\pathmunge-activate.cmd" "%UvToolBin%\pathmunge-activate.cmd" >nul
copy /Y "%RepoRoot%\ads_deploy\windows\pathmunge-activate.ps1" "%UvToolBin%\pathmunge-activate.ps1" >nul
IF %ERRORLEVEL% NEQ 0 (
    echo ** FAILED: could not install pathmunge-activate helper scripts. **
    EXIT /B 1
)

echo.
echo Installing pytmc %PYTMC_VERSION% into its own isolated environment ...
ads-deploy install pytmc/%PYTMC_VERSION%
IF %ERRORLEVEL% NEQ 0 (
    echo ** FAILED: could not install pytmc/%PYTMC_VERSION%. **
    echo Check that this is a real pytmc release tag/version.
    EXIT /B 1
)

echo.
echo Installing make %MAKE_VERSION% into its own isolated environment ...
ads-deploy install make/%MAKE_VERSION%
IF %ERRORLEVEL% NEQ 0 (
    echo ** FAILED: could not install make/%MAKE_VERSION%. **
    echo Check that this is a real conda-forge make version.
    EXIT /B 1
)

echo.
echo Fetching ads-ioc ...
ads-deploy fetch-ads-ioc
IF %ERRORLEVEL% NEQ 0 (
    echo ** FAILED: could not fetch ads-ioc. **
    EXIT /B 1
)

echo.
echo Regenerating external-tools.vssettings ...
ads-deploy vssettings --output "%RepoRoot%\external-tools.vssettings"
IF %ERRORLEVEL% NEQ 0 (
    echo ** FAILED: could not regenerate external-tools.vssettings. **
    EXIT /B 1
)

echo.
echo Done. Import external-tools.vssettings into Visual Studio
echo (Tools ^> Import and Export Settings...).
