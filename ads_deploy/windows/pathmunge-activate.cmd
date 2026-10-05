@echo off
REM Resolves one or more tools (same spec `ads-deploy pathmunge` takes) and
REM prepends their executable directories to PATH -- for your CURRENT shell.
REM
REM Usage:
REM     pathmunge-activate pytmc make
REM     pathmunge-activate pytmc/v2.22.1
REM
REM IMPORTANT: a plain .exe (like ads-deploy itself) can never modify its
REM parent shell's environment -- that's an OS-level constraint, not a
REM design choice (the same reason `conda activate` is a shell
REM function/script, not a plain executable). This file MUST be invoked
REM directly by name (just type `pathmunge-activate ...`), never via
REM `cmd /c pathmunge-activate ...` -- a .cmd file typed directly at a
REM cmd.exe prompt runs IN that same process, so its SET PATH persists
REM after it returns; `cmd /c` spawns a new child cmd.exe whose env changes
REM are discarded when it exits, same limitation as calling ads-deploy.exe
REM directly.
SET "_PathmungeOut=%TEMP%\ads-deploy-pathmunge-%RANDOM%.txt"
ads-deploy pathmunge %* > "%_PathmungeOut%" 2>&1
IF ERRORLEVEL 1 (
    type "%_PathmungeOut%"
    IF EXIST "%_PathmungeOut%" del "%_PathmungeOut%"
    EXIT /B 1
)
FOR /F "usebackq delims=" %%P in ("%_PathmungeOut%") DO SET "PATH=%%P;%PATH%"
IF EXIST "%_PathmungeOut%" del "%_PathmungeOut%"
