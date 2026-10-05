"""
Shared helpers for the `ads-deploy lint`/`build`/`debug`/`summary` commands
that back Visual Studio's "External Tools" menu entries directly (no `.cmd`
wrapper, no bash) -- see DESIGN.md for why.
"""

import logging
import os
import pathlib
import shutil
import sys

from . import pathmunge

logger = logging.getLogger(__name__)


def resolve_solution(solution: str) -> pathlib.Path:
    """
    Resolve the full solution path, passed as ONE argument.

    Deliberately a single argument rather than separate $(SolutionDir) and
    $(SolutionFileName) macros: $(SolutionDir) always ends in a backslash,
    and a quoted Windows argument ending in `\\"` has its closing quote
    escaped by standard argv parsing (confirmed directly: two quoted args
    `"...cc_test\\"` + `"cc_test.sln"` merge into one garbled argv entry).
    A full path ending in `.sln` can't trigger that, so VS's Arguments
    field concatenates the macros with no space:
    `$(SolutionDir)$(SolutionFileName)`.
    """
    return pathlib.Path(solution)


def tool_env(*tool_specs: str) -> dict:
    """
    Resolve one or more tool specs (same syntax as `ads-deploy pathmunge`)
    **in-process** and return an ``os.environ``-based copy with their
    directories prepended to PATH, for use as ``subprocess.run(..., env=...)``.

    Calling `pathmunge.resolve_tool_spec` directly -- rather than shelling
    out to `ads-deploy pathmunge` and reparsing its stdout -- is the whole
    point: it removes an entire class of cmd.exe/bash quoting and
    PATH-separator bugs that only exist at a subprocess boundary.
    """
    all_dirs = []
    for spec in tool_specs:
        all_dirs.extend(pathmunge.resolve_tool_spec(spec))

    sep = ";" if sys.platform == "win32" else ":"
    prepend = sep.join(str(d) for d in all_dirs)

    env = os.environ.copy()
    existing = env.get("PATH", "")
    env["PATH"] = f"{prepend}{sep}{existing}" if existing else prepend
    return env


def resolve_executable(name: str, env: dict) -> str:
    """
    Resolve ``name`` to an absolute path using ``env``'s ``PATH``, rather
    than passing the bare name to ``subprocess.run`` and letting Windows
    search for it itself.

    Confirmed directly against a real failure: when ``subprocess.run`` is
    given a bare command name (no path separators) together with a custom
    ``env=``, Windows' ``CreateProcess`` does NOT use that env's ``PATH`` to
    locate the executable -- the implicit search it performs uses the
    *calling* process's own current ``PATH``, since the custom environment
    only takes effect once the child process has actually started, not
    during the search for what to launch. `tool_env()`'s whole point is
    resolving pinned tool directories into a ``PATH`` that is NOT the
    calling process's real one (that's what makes an un-PATH-extended
    terminal able to call pinned tools at all) -- so a bare name resolved
    only through that custom ``PATH`` must be turned into an absolute path
    here first. Same underlying reason `ads_deploy/vssettings.py` resolves
    `ads-deploy` via `shutil.which()` rather than relying on Visual Studio
    to search PATH for it.
    """
    resolved = shutil.which(name, path=env.get("PATH"))
    if resolved is None:
        logger.warning(
            "Could not resolve %r via the resolved tool PATH -- the "
            "subprocess call below will likely fail to find it.",
            name,
        )
        return name
    return resolved


def find_shell(env: dict) -> str:
    """
    Locate a directory holding the *full* Git for Windows coreutils set
    (`pwd.exe`, `mkdir.exe`, `sh.exe`, etc.) and make sure it's on ``env``'s
    PATH, mutating ``env`` in place. Returns the `sh.exe` path found there,
    or ``None`` if no such directory can be located.

    Two distinct fixes are needed here, confirmed directly against real
    build failures -- neither one alone is sufficient:

    1. GNU Make's Windows port runs some `$(shell ...)` calls (e.g.
       `$(shell pwd)`, used by ads-ioc's Makefile.base) via *direct*
       `CreateProcess`, bypassing any shell entirely, when it decides the
       command has no shell metacharacters -- this is what
       `process_begin: CreateProcess(NULL, pwd, ...) failed.` means. `pwd`
       itself is a shell *builtin* with no standalone executable in most
       places, but Git for Windows' coreutils ship a real standalone
       `pwd.exe` -- CreateProcess can find and run that, so its directory
       must be on PATH.
    2. For recipe lines that DO need a real shell, GNU Make does NOT use an
       inherited environment `SHELL` variable (deliberate, for build
       reproducibility -- see the GNU Make manual); it only honors a
       `SHELL=...` *command-line* variable assignment, which the caller
       must pass as a `make` argument -- confirmed directly: setting
       `env["SHELL"]` alone had no effect.

    Previously both worked implicitly because the old build chain ran
    `make` as a *child* of `bash.exe`; calling `make` directly from Python
    has no such parent to inherit a shell-aware PATH/setup from.

    Where this actually lives is NOT reliably "next to bash.exe": Git for
    Windows' installer-registered `<GitRoot>\\bin` can hold `bash.exe` *and*
    `sh.exe` as minimal shims without the full coreutils set at all --
    `pwd.exe`/`mkdir.exe`/etc. only exist in the sibling `<GitRoot>\\usr\\bin`
    (confirmed directly: assuming "same directory as bash.exe" found a
    valid `sh.exe` but not `pwd.exe`, and the CreateProcess failure
    persisted even with that wrong directory added to PATH). So every
    plausible layout is checked and verified by actually finding `pwd.exe`
    there, rather than assumed.
    """
    if sys.platform != "win32":
        return None

    bash = shutil.which("bash", path=env.get("PATH"))
    if bash is None:
        # Confirmed directly: Visual Studio (devenv.exe), when launched
        # before Git for Windows was installed or before its PATH entry was
        # registered, keeps running with its OWN stale, already-loaded
        # environment -- Windows never pushes PATH updates into an already
        # running process. A CLI session opened fresh picks up the current
        # PATH fine; a long-running VS instance silently doesn't, with no
        # indication to the user beyond this warning. Rather than give up
        # entirely, fall back to Git for Windows' well-known install
        # locations (same kind of on-disk fallback toolenv.py already uses
        # for the shared install, rather than relying purely on PATH/env
        # state that may be stale) before telling the user to install it.
        for root_var in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(root_var)
            if root:
                candidate = pathlib.Path(root) / "Git" / "bin" / "bash.exe"
                if candidate.is_file():
                    bash = str(candidate)
                    break
        local_app_data = os.environ.get("LOCALAPPDATA")
        if bash is None and local_app_data:
            candidate = (
                pathlib.Path(local_app_data) / "Programs" / "Git" / "bin" / "bash.exe"
            )
            if candidate.is_file():
                bash = str(candidate)

    if bash is None:
        logger.warning(
            "No bash found on PATH or Git for Windows' well-known install "
            "locations -- make's Makefile recipes may fail. If Git for "
            "Windows IS installed, this process (e.g. Visual Studio) may "
            "have been started before its PATH entry was registered -- "
            "try fully closing and reopening it. Otherwise, install Git "
            "for Windows: https://git-scm.com/download/win"
        )
        return None

    bash_dir = pathlib.Path(bash).parent
    candidates = [
        bash_dir,  # bash.exe already in usr/bin
        bash_dir.parent / "usr" / "bin",  # bash.exe in <root>/bin or /cmd
        bash_dir.parent.parent / "usr" / "bin",
    ]

    for candidate in candidates:
        if (candidate / "pwd.exe").is_file():
            logger.info("Using Git for Windows coreutils at %s", candidate)
            # Appended, not prepended: this directory exists only to supply
            # pwd/sh/mkdir as a fallback. It must never outrank the pinned
            # pytmc/make directories tool_env() already put on PATH -- if it
            # happened to contain its own "python3" or similar, prepending
            # it would silently shadow the pinned, version-checked pytmc.
            env["PATH"] = f"{env.get('PATH', '')};{candidate}"
            sh = candidate / "sh.exe"
            return str(sh) if sh.is_file() else None

    logger.warning(
        "Found bash at %s but no pwd.exe in any of: %s -- "
        "make's $(shell ...) calls may fail.",
        bash,
        ", ".join(str(c) for c in candidates),
    )
    return None
