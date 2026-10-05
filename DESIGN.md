# ads-deploy: uv + pixi redesign

This document records the design decisions behind moving ads-deploy off
conda/Docker, and is a how-to guide for using the result. See
`ecs-stack-presentation.md` for the broader multi-repo context this fits
into.

ads-deploy itself is packaged with [uv](https://docs.astral.sh/uv/). The
tools it *manages for you* (pytmc, make) are provisioned with
[pixi](https://pixi.sh/) -- see "Why pixi for tool provisioning" below for
why these are two different tools doing two different jobs.

## Context

ads-deploy bridges TwinCAT XAE (Visual Studio) projects to the EPICS/pytmc
build toolchain on Windows, invoked via VS "External Tools" menu entries. It
was previously packaged as a conda environment with a parallel, largely-unused
Docker mode (`setup.py` + `versioneer` + `conda-recipe`), with pytmc/ads-ioc
versions pinned inconsistently across five different files, and
`epics-base`/`happi`/Docker dependencies that nothing in the codebase actually
used.

A sibling design effort (`ecs-stack-presentation.md`) is moving the broader
TwinCAT/EPICS toolchain toward `uv`-based, per-tool pinned installs exposed
via a PATH-only "pathmunge" mechanism, and explicitly calls out that the
Windows side of this (uv venvs, a Windows pathmunge equivalent, ads-ioc
version provisioning) doesn't exist yet. This redesign rebuilds ads-deploy on
`uv` to fill that gap.

## Decision: uv for packaging ads-deploy itself

ads-deploy is Windows-only, so the concern that rules pixi out elsewhere in
the ecs-stack effort — full pixi activation resetting a shared, central EPICS
environment other tooling depends on — doesn't apply here directly. ads-deploy
is a plain Python CLI with no non-Python dependencies of its own, so `uv tool
install` is the simplest way to distribute it (a global shim, no activation
needed to run `ads-deploy`), matching the direction already adopted elsewhere
in the org's TwinCAT/EPICS stack (tc-release).

## Why pixi for tool provisioning (not uv)

`ads-deploy install`/`pathmunge` originally drove plain `uv venv` + `uv pip
install`, same as the packaging choice above — reasonable at the time, since
every dependency actually in play (pytmc, jinja2, lxml, etc.) was confirmed to
be a real PyPI wheel with no system/native-library requirement.

That assumption broke once `build_ioc.cmd`'s actual IOC-build step needed
`make`: GNU Make is not a Python package and will never be on PyPI. The old
conda setup got it from conda-forge (`conda_env_windows_extras.yml`'s `make`
entry) — conda-forge's `make` feedstock is the best-governed source for a
Windows Make binary (actively maintained, CI-built, reproducible), far better
than scraping an old GnuWin32/sourceforge binary.

The tempting fix — special-case `make` with its own conda-forge installer
code path inside `install.py` — was rejected as exactly the kind of patch
that doesn't scale: the next dev who needs a different non-Python or
conda-only dependency (a compiler, Qt, anything) would have to add *another*
special case. Instead, `ads-deploy install` now generates a small
per-(tool, version) **pixi project** and runs `pixi install` — pixi natively
resolves both conda-forge (`[dependencies]`) and PyPI (`[pypi-dependencies]`,
resolved internally via `uv`) packages in one environment/lockfile. Which
ecosystem a tool's package lives in is a one-line declarative entry in
`ads_deploy/tool_registry.py`:

```python
REGISTRY = {
    "pytmc": ToolSource(ecosystem="pypi", package="pytmc"),
    "make": ToolSource(ecosystem="conda", package="make"),
}
```

Adding a future conda-forge-only tool is one line there — never new install
logic. `install.py`/`pathmunge.py`/`toolenv.py` have no per-tool branching at
all; they only know "pixi project" and "scan the resulting environment for
executable directories."

Verified end-to-end with real pixi installs (not just reasoning from docs):
`pytmc/v2.22.1` (PyPI) lands its console script in
`.pixi/envs/default/Scripts`; `make/4.4.1` (conda-forge) lands `make.exe` in
`.pixi/envs/default/Library/bin`; both are directly runnable once their
resolved directories are on `PATH`. `toolenv.bin_dirs()` checks every known
conda-env executable location (`Scripts`, `Library/bin`,
`Library/usr/bin`, `Library/mingw-w64/bin`, the prefix root) and returns
whichever ones actually exist, so this generalizes to any future tool without
per-tool knowledge of where its binaries land.

### Other architectures considered (revisited and re-confirmed)

This two-tool split was revisited explicitly after review feedback that it
would draw PR questions. Rejected alternatives, with reasons:

- **Backend per tool** (uv for pytmc, pixi only for make): doesn't reduce the
  project's actual dependency footprint — pixi is still required either way,
  since make has no other source. Only adds a second install code path for
  zero reduction in tools-to-explain. Concretely: `tool_registry.py`'s
  `ecosystem` field ("pypi" vs "conda") only changes which `pixi.toml`
  section a package lands in (`[pypi-dependencies]` vs `[dependencies]`);
  `install.py`/`toolenv.py`'s environment creation, drift detection, and
  PATH resolution never branch on ecosystem at all — splitting pytmc onto
  its own `uv venv` would force exactly that branching back in. It would
  also lose side-by-side version isolation for pytmc specifically: a pixi
  project per `(tool, version)` lets two pytmc versions stay installed
  simultaneously and immutably, where `uv tool install` is built around one
  active version per tool name and would need extra naming hacks to match.
- **One shared pixi environment bundling everything** (closest 1:1 port of
  the old `conda_env_base.yml`, with ads-deploy itself installed into that
  same environment): rejected because it reintroduces "ads-deploy is not
  just always on PATH, you first activate/select an environment," and loses
  independent per-project tool-version pinning without manually juggling
  multiple named environments — exactly what the per-tool-per-version model
  was built to solve.
- **A "stack" abstraction** bundling tool versions as one named, independently
  pinnable unit (closer to the ecs-stack doc's own language): rejected
  because that concept is the separate `ecs-stack` effort's job to own;
  building a competing/overlapping "stack" inside ads-deploy would duplicate
  that project's scope.
- **Drop pixi entirely**: the only way to get a true single-tool (uv-only)
  story, at the cost of dropping automatic `make` provisioning and going back
  to "install make yourself via choco/MSYS2/Git SDK" — the exact friction
  pixi was introduced to remove.

## Command surface

| Command | Role |
| --- | --- |
| `ads-deploy install <tool>/<version>` | Provisions (once, immutably) an isolated pixi environment for a pinned tool version, e.g. `pytmc/v2.22.2` or `make/4.4.1`. Re-running the same spec is a no-op; `--force` rebuilds it. |
| `ads-deploy pathmunge <tool>[/<version>] [<tool2>[/<version2>] ...]` | Resolves one or more *already-installed* tool/versions and prints a single `PATH` fragment (all their executable directories joined) — no activation, no other env var touched. Fails with a pointer to `install` if a requested version isn't provisioned yet. A tool with no version given resolves one from a project-local `pathmunge.toml`, falling back to the latest installed version. |
| `ads-deploy versions <tool>` | Lists every version of a tool installed locally. |
| `ads-deploy fetch-ads-ioc` | Clones/updates the `ads-ioc` common IOC module and its latest release tag (replaces the old self-mutating `post_install.sh`). |
| `ads-deploy vssettings` | Regenerates `external-tools.vssettings` from a template, pointed at wherever this install actually lives (replaces the old hardcoded `C:\Repos\ads-deploy` assumption). |

`install` and `pathmunge` are deliberately separate commands, mirroring how
`ctrlenv-pathmunge` works on Linux: there it only resolves and exposes a tool
version already built elsewhere (by tc-release); it never builds anything
itself. `ads-deploy pathmunge` follows the same contract on Windows — pure
resolve-and-print. `ads-deploy install` is the Windows-side provisioning step
the ecs-stack doc calls out as not yet existing.

### Usage

```
$ ads-deploy install pytmc/v2.22.2
$ ads-deploy install make/4.4.1
$ ads-deploy pathmunge pytmc/v2.22.2 make/4.4.1
C:\...\toolenvs\pytmc\v2.22.2\.pixi\envs\default\Scripts;C:\...\toolenvs\make\4.4.1\.pixi\envs\default\Library\bin

$ ads-deploy versions pytmc
v2.22.2

$ ads-deploy pathmunge pytmc/v9.9.9      # not installed
RuntimeError: pytmc/v9.9.9 is not installed. Run:
    ads-deploy install pytmc/v9.9.9
```

A project can pin its own versions by placing a `pathmunge.toml` next to its
`.sln`, so a bare `ads-deploy pathmunge pytmc make` (no versions) resolves
each:

```toml
[tool-versions]
pytmc = "v2.22.2"
make = "4.4.1"
```

`config.cmd` (used by every VS "External Tools" entry) calls
`ads-deploy pathmunge pytmc make` **in one call** and prepends the returned
PATH fragment — PATH-only, no environment activation, no mutation of
`VIRTUAL_ENV`/`PYTHONHOME`/`CONDA_PREFIX`. The "one call for multiple tools"
shape is deliberate, not cosmetic: looping over several separate `pathmunge`
calls in a `.cmd` file and accumulating `PATH` across iterations would hit
the same cmd.exe same-block-variable-expansion gotcha described below (a
loop body is also one parenthesized block) — so the join happens once, in
Python, instead.

## ads-ioc: still a separate mechanism

`ads-ioc` is a private git repository, not a package on PyPI or conda-forge —
pixi wouldn't help here regardless of ecosystem. It's handled by the separate
`fetch-ads-ioc` command (git clone + release-tag lookup), never by
`install`/`pathmunge`.

## Scope cuts

- **GUI/screen tooling removed entirely.** `typhos_gui.py`, `caproto_ioc.py`,
  and their `typhos`/`pydm`/`ophyd`/`pcdsdevices` dependencies are deleted,
  not kept as an optional extra — Windows only builds the IOC; the UI runs on
  Linux, so ads-deploy has no reason to carry screen-generation tooling at
  all.
- **Docker dropped entirely**, including the "Run IOC(s)" VS Tools-menu
  entry, which only ever worked by spawning a Docker container
  (`make_scripts.py`) — there was no native-Windows equivalent to fall back
  to, so it's gone rather than reimplemented.
- **conda dropped entirely** (env files, `conda-recipe/`, `conda activate`
  chains, `versioneer`), replaced by a single `pyproject.toml` (hatchling +
  hatch-vcs).
- Kept as-is: `config`, `iocboot`, `tsproj`, `docs` — the core pytmc-adjacent
  build-path commands, unchanged in behavior.
- External Tools menu entries went from 10 to 5 (+ Qt Designer): Lint
  pragmas, Configure and build IOC(s), Record debugging, Project summary, Qt
  Designer.

## Bug fixed along the way

`ads_deploy/util.py` used `distutils.version.LooseVersion`, which doesn't
exist on Python 3.12+ (distutils was removed from the standard library).
This silently broke `config`/`iocboot`/`tsproj`/`docs` on any modern Python.
Replaced with plain tuple-based version parsing.

## How to set up a machine

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/),
   [pixi](https://pixi.sh/latest/installation/), and
   [Git for Windows](https://git-scm.com/download/win) (for `bash.exe` and
   `git`, needed by the Makefile-based IOC build step and ads-ioc cloning).
2. Clone this repository (e.g. to `C:\Repos\ads-deploy`).
3. Set `PYTMC_VERSION` and `MAKE_VERSION` and run `bootstrap.cmd` from the
   repo root:
   - Command Prompt (`cmd.exe`):
     `set PYTMC_VERSION=v2.22.2 && set MAKE_VERSION=4.4.1 && bootstrap.cmd`
   - PowerShell:
     `$env:PYTMC_VERSION = "v2.22.2"; $env:MAKE_VERSION = "4.4.1"; .\bootstrap.cmd`

   This installs `ads-deploy` as a uv tool, installs the pinned pytmc and
   make (each its own pixi environment), fetches `ads-ioc`, and regenerates
   `external-tools.vssettings`. Every step checks its exit code and stops
   immediately on failure.
4. In Visual Studio: **Tools > Import and Export Settings... > Import**, and
   select the generated `external-tools.vssettings`.

## What changed on disk

**Deleted:** `Dockerfile`, `Makefile` (Docker build), `MANIFEST.in`,
`setup.py`, `setup.cfg`, `versioneer.py`, `ads_deploy/_version.py`,
`requirements.txt`, `dev-requirements.txt`, `conda-recipe/`,
`conda_env_base.yml`, `conda_env_windows_extras.yml`,
`setup_conda_on_windows.cmd`, `setup_conda_on_linux.sh`, `switch_to_docker.cmd`,
`switch_to_conda.cmd`, `ads_deploy/typhos_gui.py`, `ads_deploy/caproto_ioc.py`,
`ads_deploy/windows/{conda_config.cmd,conda_config.sh,post_install.sh,
docker_ioc.cmd,select_conda_or_docker.cmd,make_scripts.cmd,make_scripts.py,
run_ioc.cmd,motor_screens.cmd,other_screens.cmd}`.

**Added:** `pyproject.toml`, `bootstrap.cmd`, `ads_deploy/toolenv.py`,
`ads_deploy/install.py`, `ads_deploy/pathmunge.py`, `ads_deploy/versions.py`,
`ads_deploy/tool_registry.py`, `ads_deploy/fetch_ads_ioc.py`,
`ads_deploy/vssettings.py`,
`ads_deploy/templates/external-tools.vssettings.jinja2`.

**Modified:** `ads_deploy/__init__.py` (version via `importlib.metadata`
instead of versioneer), `ads_deploy/__main__.py` (new `MODULES` entries),
`ads_deploy/util.py` (dropped `distutils`; extracted `parse_version_tag()`,
shared with `fetch_ads_ioc.py`'s numeric tag sort), `ads_deploy/config.py`
(stale Docker-only help text removed), remaining `ads_deploy/windows/*.cmd`/
`.sh` scripts (Docker branching removed, conda activation replaced with
`ads-deploy pathmunge pytmc make`; `config.cmd`'s `SolutionDir`/
`SolutionFullPath` handling and same-block-variable-expansion bugs fixed —
see commit history on `mnt_new_design` for the specifics), `bootstrap.cmd`
(checks for `pixi`, installs `make` alongside `pytmc`),
`external-tools.vssettings` (regenerated, 5 entries + Qt Designer),
`README.md`.

---

# Phase 2: eliminate mixed cmd.exe/bash scripting

The migration above replaced conda/Docker, but the VS "External Tools" chain
still ran through `ads_deploy/windows/*.cmd` wrapper scripts, and "Configure
and build IOC(s)" additionally shelled out to `bash.exe` (`build_ioc.cmd` →
`build.sh`) to enumerate `ioc-*` directories and invoke `make`. Essentially
every bug chased down in this project came from that same root cause: two
different shell languages, each with their own quoting/escaping/expansion
rules, calling into each other across process boundaries -- a
trailing-backslash-before-quote bug, a same-parenthesized-block variable
expansion bug (twice, independently), `%VAR:\=/%` corrupting on an
empty/unset variable, a `;` vs `:` PATH-separator mismatch between cmd.exe
and bash, and a "terminal resets mid-build" mystery that turned out to be
exactly this kind of fragility.

## Decision: move the VS Tools-menu chain into direct Python CLI commands

Visual Studio's External Tools "Command" field can point directly at an
executable -- confirmed against the real dialog, whose file-browse filter
(`*.exe;*.com;*.pif;*.bat;*.cmd`) treats `.exe` as first-class, not a
fallback. Pointing `Command` straight at `ads-deploy` (a real `ads-deploy.exe`
via `uv tool install`, resolved through `PATH` the same way `git`/`uv`/`pixi`
already are) with `Arguments` set to the solution path macros eliminates
every `.cmd` file in this chain: no `%1`/`%~1` quote-stripping, no
`%SolutionDir:~1,-1%` substring slicing, no `%VAR:\=/%` conversions, no
same-block variable expansion risk at all -- argparse and pathlib handle
this natively.

Tool-version resolution now happens **in-process**: `ads_deploy/vstools.py`'s
`tool_env()` calls `pathmunge.resolve_tool_spec()` directly and builds a
modified `env` dict for `subprocess.run(...)`, rather than shelling out to
`ads-deploy pathmunge`, capturing its stdout through a temp file, and
reparsing it through cmd.exe's substitution engine -- the exact mechanism
that produced several of the bugs above. Verified directly (fake pytmc/make
stubs installed under a throwaway toolenv root): `vstools.resolve_solution`
joins VS's macros correctly with no quote handling needed, and `tool_env`'s
resulting `PATH` correctly resolves both tools via `subprocess.run`.

`build_ioc.cmd`'s only real uses of bash were: enumerating `ioc-*`
directories (`find`), a `sed` patch to a Makefile `IOC_TOP=` line that
command-line `make` variables already override (the old script's own comment
said as much -- dead code), and exporting `PATH`. All three are trivial in
Python (`pathlib.Path.glob("ioc-*")`, dropping the dead sed entirely,
`env=` on `subprocess.run`). `make.exe` (pixi/conda-forge-provisioned) is a
native Windows console executable -- launching it never needed bash.

**Caveat that does NOT go away:** GNU Make's Windows port executes Makefile
*recipes* via `$(SHELL)`, typically resolving to an `sh.exe` on `PATH`
(normally satisfied by Git for Windows). Dropping bash from ads-deploy's own
orchestration does not remove Git for Windows as a prerequisite -- `git`
(cloning ads-ioc) and `sh.exe` (make's own recipe execution, independent of
anything ads-deploy does) are both still needed.

## New command surface

| Command | Replaces |
| --- | --- |
| `ads-deploy lint <dir> <file>` | `lint_pragmas.cmd` |
| `ads-deploy build <dir> <file>` | `build_ioc.cmd` + `create_iocboot.cmd` + `build.sh` |
| `ads-deploy debug <dir> <file>` | `debug_records.cmd` |
| `ads-deploy summary <dir> <file>` | `summary.cmd` |

Each takes VS's `$(SolutionDir)`/`$(SolutionFileName)` as two plain argv
strings (`ads_deploy/vstools.py`'s `resolve_solution()` joins them) -- no
batch quote-stripping convention to replicate. Qt Designer is not
pytmc-specific at all; the VS entry calls `designer` directly, no wrapper.

`ads-deploy build` resolves the latest local `ads-ioc` checkout via
`util.get_latest_ads_ioc()` -- the same mechanism `ads-deploy iocboot`
already used -- instead of depending on a cached `ADS_IOC_LOCATION`
environment variable that `config.cmd` used to re-source defensively. This
removes that whole caching/re-sourcing mechanism, not just its `.cmd` form:
`fetch-ads-ioc` no longer has a `--write-config` flag, since nothing reads
such a file any more.

`ads_deploy/vssettings.py`'s `TOOLS` list carries `command` + `arguments`
directly, instead of `script=...cmd` + `scripts_dir` templating. `command`
is `ads-deploy`'s (or `designer`'s) *resolved absolute path* via
`shutil.which()`, computed fresh each time `ads-deploy vssettings` runs --
**not** the bare string `"ads-deploy"`. Confirmed directly: Visual Studio's
External Tools "Command" field does not do a `PATH` search the way
`cmd.exe` does (a bare `ads-deploy` is rejected with "The command is not a
valid executable"), so the file still needs regenerating per-machine, same
as the old hardcoded-`C:\Repos\ads-deploy` file did -- just via one command
(`ads-deploy vssettings`) instead of hand-editing XML.

## What was deleted this phase

`ads_deploy/windows/{build.sh,build_ioc.cmd,create_iocboot.cmd,
lint_pragmas.cmd,debug_records.cmd,summary.cmd,config.cmd,qt_designer.cmd}`.

**Kept** (legitimately scripts, not part of this chain): `bootstrap.cmd`
(one-time setup, pure cmd.exe, never called bash); `pathmunge-activate.cmd`/
`.ps1` (must stay shell-native -- a child process can never mutate its
parent shell's environment, which is the whole reason these exist).

## Small fix folded into this phase: `pre-commit`

`pre-commit` (this repo's own `.pre-commit-config.yaml` hooks -- unrelated to
building TwinCAT IOCs) used to come for free via the old shared conda
environment: the conda env was shared and `PATH`-resolved, so any
contributor on the machine could just invoke `pre-commit` with no install
step of their own. That "zero personal setup" property is worth preserving,
not just the package availability -- so `pre-commit` is installed the same
way as `ads-deploy` itself in `bootstrap.cmd`, via `uv tool install
pre-commit` into the same `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` (shared, when
`ADS_DEPLOY_SHARED_DIR` is set). It's also kept in `pyproject.toml`'s
`[dependency-groups] dev` list alongside `pytest`/`flake8`/`coverage`, for
anyone managing their own isolated dev venv -- but the shared `uv tool
install` is the primary path for "just works for everyone on this machine."

## Shared install: vssettings distribution, PATH, and permissions

Three related decisions from reasoning through "how does an admin install
this once for everyone" (see git history on `mnt_new_design` around the
`ADS_DEPLOY_SHARED_DIR` introduction):

1. **The vssettings file, not PATH, is what makes VS usage zero-command for
   other users.** `ads_deploy/vssettings.py` bakes `Command` in as a static,
   already-resolved absolute path (`shutil.which()` at generation time) --
   Visual Studio's External Tools never re-resolves it via PATH, at import
   time or at run time, and importing a `.vssettings` file copies its
   contents into VS's own per-user settings store rather than keeping a live
   link to the source file. So one file generated against the shared
   install location can be handed to every other user to import as-is.
   Don't "fix" this by having each user run `ads-deploy vssettings`
   themselves -- that reintroduces exactly the per-person command this is
   trying to eliminate, and would additionally require PATH to already be
   extended for that user just so `ads-deploy` itself resolves.
2. **System `PATH` mutation stays a manual, printed instruction, never
   scripted -- but `ADS_DEPLOY_TOOLENV_ROOT` IS scripted via `setx /M`.**
   These look similar (both are "make the shared location visible to other
   users") but have opposite risk profiles. `setx /M PATH ...` has a hard
   1024-character limit and silently truncates longer values, risking
   corruption of the whole machine's PATH -- and it's no longer even
   necessary for the VS workflow per (1), only for people who also want
   these tools from a plain terminal, so it's left manual. `setx /M
   ADS_DEPLOY_TOOLENV_ROOT ...` is one short, standalone path string, nowhere
   near that limit -- and unlike PATH, it's not optional: every other user's
   VS-launched `ads-deploy build`/`lint`/etc. calls read it (via
   `ads_deploy/toolenv.py`'s `toolenv_root()`) to find the shared pytmc/make
   pixi environments; without it they'd silently fall back to each user's
   own, empty, per-user `%LOCALAPPDATA%` location and fail. (As with any
   system environment variable, this only takes effect for other users at
   their next login -- not retroactively, nothing scriptable can change
   that.) This whole distinction is also a deliberate break from the conda
   mental model: conda's `activate` bundles "where files live" and "what's
   on PATH" into one action with no durable state to manage at all, while
   uv's tool-shim model keeps "where files live" (`UV_TOOL_DIR`/
   `UV_TOOL_BIN_DIR`, `ADS_DEPLOY_TOOLENV_ROOT` -- safe, scriptable) separate
   from "what's on PATH" (durable Windows system state, deliberately left to
   one manual, reviewable admin action).
3. **Protect the shared install with NTFS permissions, not a generation-time
   gate.** The asset worth protecting from an accidental edit by a novice
   user isn't the distributed `.vssettings` file (importing copies it in,
   so one user's copy can't affect anyone else) -- it's the shared install
   directory itself (the `ads-deploy`/pytmc/make/pre-commit binaries and the
   canonical vssettings file regenerated from it). `ADS_DEPLOY_SHARED_DIR`
   should point under `C:\ProgramData`, whose default ACLs give ordinary
   users read+execute but not write -- not a generic user-writable path like
   `C:\Repos\...`. `ads-deploy vssettings` intentionally stays an ungated,
   normal subcommand throughout: a power user who wants to experiment with
   a different tool/version can always run their own per-user
   `bootstrap.cmd` (unset `ADS_DEPLOY_SHARED_DIR`) and their own `ads-deploy
   vssettings`, fully independent of the shared install.
