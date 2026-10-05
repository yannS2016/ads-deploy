"""
`ads-deploy build` generates IOC boot directories for a TwinCAT solution and
builds each one with `make`. Replaces the old `build_ioc.cmd` +
`create_iocboot.cmd` + `build.sh` chain, called directly as a Visual Studio
External Tool (Command=ads-deploy, Arguments=
"build $(SolutionDir)$(SolutionFileName)") with no `.cmd`/bash wrapper
needed.

The old chain shelled out to `bash.exe` purely to: enumerate `ioc-*`
directories (`find`), patch a Makefile `IOC_TOP=` line that command-line
`make` variables already override (dead code -- the old script's own comment
said as much), and export PATH. All three are plain Python here:
`pathlib.Path.glob`, no patch needed at all, and `vstools.tool_env` for PATH.
`make.exe` (pixi/conda-forge-provisioned) is a native Windows console
executable -- launching it never needed bash. It still needs a POSIX shell
for its own `$(shell ...)` calls and recipe execution though (confirmed
directly: `process_begin: CreateProcess(NULL, pwd, ...) failed` without
one). GNU Make does NOT pick this up from an inherited environment `SHELL`
variable (deliberate, for build reproducibility); it only honors a
`SHELL=...` *command-line* variable assignment (confirmed directly: setting
`env["SHELL"]` alone had no effect), so `vstools.find_shell()`'s result is
passed as a `make` argument here, the same way `IOC_TOP`/`TEMPLATE_PATH`
already are -- replacing what used to happen implicitly by running `make`
as bash's child.
"""

import argparse
import logging
import pathlib
import shutil
import subprocess

from . import iocboot, util, vstools

DESCRIPTION = __doc__
logger = logging.getLogger(__name__)


def build_arg_parser(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser()

    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawTextHelpFormatter

    parser.add_argument(
        "solution",
        type=str,
        help="Full solution path, e.g. $(SolutionDir)$(SolutionFileName)",
    )

    return parser


def _build_one_ioc(
    ioc_dir: pathlib.Path, ads_ioc_location: pathlib.Path, env: dict, shell: str
) -> bool:
    """Build a single generated IOC directory. Returns True on success."""
    if not (ioc_dir / "Makefile").exists():
        return True

    logger.info("* Building %s", ioc_dir.name)

    build_dir = ioc_dir / ".pytmc_build"
    if build_dir.exists():
        logger.info("* Cleaning old build directory...")
        shutil.rmtree(build_dir)

    args = [
        vstools.resolve_executable("make", env),
        f"IOC_TOP={ads_ioc_location}/",
        f"TEMPLATE_PATH={ads_ioc_location}/iocBoot/templates",
    ]
    if shell:
        args.append(f"SHELL={shell}")
    args += ["build", "clean"]

    result = subprocess.run(args, cwd=ioc_dir, env=env)
    return result.returncode == 0


def main(solution: str) -> None:
    solution = vstools.resolve_solution(solution)
    iocboot_dir = solution.parent / "iocBoot"

    logger.info("Creating IOC boot directories and Makefiles")
    with open(solution, "rt", encoding="utf-8") as project_file:
        iocboot.main(
            project=project_file, ioc_template_path=None, destination=str(iocboot_dir)
        )

    logger.info("Attempting to build the IOC")
    ads_ioc_location = util.get_latest_ads_ioc()
    env = vstools.tool_env("pytmc", "make")
    shell = vstools.find_shell(env)

    # ads-ioc's own Makefile.base calls `python3 -c "import distutils.version; ..."`
    # for its pytmc version check (an external repo ads-deploy doesn't
    # control). install.py installs setuptools alongside pytmc specifically
    # so its vendored distutils can serve this import instead of the
    # (deprecated, eventually-removed) stdlib one -- confirmed directly,
    # works even on a Python with zero stdlib distutils. SETUPTOOLS_USE_DISTUTILS
    # is what actually makes `import distutils` resolve to that vendored
    # copy rather than failing/using stdlib.
    env["SETUPTOOLS_USE_DISTUTILS"] = "local"

    # setuptools' own vendored distutils.version module still warns that
    # LooseVersion itself is deprecated ("Use packaging.version instead.")
    # -- confirmed directly. ads-ioc's Makefile.base is the one calling
    # LooseVersion, not us, so this is permanent and expected; not a sign
    # of a problem. Scoped to just this one subprocess's environment, not
    # global to ads-deploy or any other Python process. Not module-restricted
    # (e.g. ":distutils"): these warnings use stacklevel=2, which attributes
    # them to the CALLER's module (here, __main__/"<string>", matching the
    # "<string>:N: DeprecationWarning: ..." seen in real build logs) rather
    # than to "distutils" itself, so a module-scoped filter would silently
    # fail to match.
    env["PYTHONWARNINGS"] = "ignore::DeprecationWarning"

    failed = False
    for ioc_dir in sorted(iocboot_dir.glob("ioc-*")):
        if not _build_one_ioc(ioc_dir, ads_ioc_location, env, shell):
            failed = True

    if failed:
        logger.error("** FAILED - see error messages above **")
        raise SystemExit(1)
