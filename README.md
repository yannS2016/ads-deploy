ads-deploy
==========

ads-deploy bridges the gap between your PLC project in TwinCAT XAE + Visual
Studio and the Python/EPICS tools we use for development and deployment
([PyTMC](https://github.com/slaclab/pytmc), [ads-ioc](https://github.com/pcdshub/ads-ioc)),
invoked directly from Windows via the Visual Studio "External Tools" menu.

ads-deploy itself is packaged and versioned with [uv](https://docs.astral.sh/uv/).
The tools it *manages for you* (pytmc, make) are provisioned with
[pixi](https://pixi.sh/), since pixi can resolve both PyPI and conda-forge
packages -- pip/uv alone can only ever reach PyPI, which doesn't cover
non-Python tools like `make`. Docker and conda (the environment-manager) are
no longer used or required. See [DESIGN.md](DESIGN.md) for the full
rationale behind these choices and a file-by-file summary of the redesign.

Features
========

* pytmc pragma linting / verification
* Build ads-based EPICS IOCs directly from Windows
* Generate IOC boot directories and Makefiles from a TwinCAT solution
* Generate Sphinx-compatible documentation from pytmc pragmas
* Install and pin isolated, immutable versions of any registered tool --
  pytmc (PyPI), make (conda-forge) -- and expose them on `PATH` without any
  environment activation (`ads-deploy install` / `ads-deploy pathmunge`)
* Fetch/update the `ads-ioc` common IOC module (`ads-deploy fetch-ads-ioc`)
* Regenerate the Visual Studio external tools settings for your own install
  location (`ads-deploy vssettings`)

Installation
============

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/),
   [pixi](https://pixi.sh/latest/installation/), and
   [Git for Windows](https://git-scm.com/download/win) (for `git`, and for
   the `sh.exe` GNU Make's Windows port looks for to run Makefile recipes).
2. Clone this repository (e.g. to `C:\Repos\ads-deploy`).
3. Set `PYTMC_VERSION` and `MAKE_VERSION` and run `bootstrap.cmd` from the
   repo root:
   - Command Prompt (`cmd.exe`):
     `set PYTMC_VERSION=v2.22.2 && set MAKE_VERSION=4.4.1 && bootstrap.cmd`
   - PowerShell:
     `$env:PYTMC_VERSION = "v2.22.2"; $env:MAKE_VERSION = "4.4.1"; .\bootstrap.cmd`

   This will:
   - Install `ads-deploy` and `pre-commit` as uv tools (available globally,
     no activation needed).
   - Install the pinned pytmc (from PyPI) and make (from conda-forge), each
     into its own isolated pixi environment.
   - Fetch the `ads-ioc` common module.
   - Regenerate `external-tools.vssettings` to point at this install location.
4. In Visual Studio: **Tools > Import and Export Settings... > Import** and
   select the generated `external-tools.vssettings`. This adds the "External
   Tools" menu entries used against any open TwinCAT solution.

Visual Studio's External Tools settings are per-user (confirmed: there's no
"install once for every account" option), so step 4 is a per-user action
regardless of how ads-deploy itself was installed. `external-tools.vssettings`
also bakes in `ads-deploy`'s *resolved path* at generation time (Visual
Studio's Command field does not do a PATH search the way `cmd.exe` does).
For a standalone, per-machine install this means regenerating it
(`ads-deploy vssettings`) on each machine rather than copying one machine's
generated file to another -- but for a *shared* install (see below), the
one file generated against that shared location is exactly what should be
copied/distributed to every other user on that same machine.

### Installing for all users on a shared machine

By default, step 3 installs `ads-deploy` (and the pinned pytmc/make, plus
`pre-commit`) under the *current user's own profile* (`uv tool install`'s
own default) -- other accounts on the same machine won't see it. For a
shared install, set `ADS_DEPLOY_SHARED_DIR` before running `bootstrap.cmd`,
as an Administrator:
```
set ADS_DEPLOY_SHARED_DIR=C:\ProgramData\ads-deploy
```
Use a location under `C:\ProgramData`, not an ordinary user-writable
directory: its default ACLs give regular accounts read+execute but not
write, which is what keeps a curious or novice user from corrupting the
shared install -- this is deliberate, not incidental, since settings files
have been fiddled with by accident before.

**The actual zero-command outcome for other users is the generated
`external-tools.vssettings` file, not PATH.** `bootstrap.cmd` regenerates it
at the end of a shared-install run with `Command` baked in as the *shared*
`ads-deploy`'s resolved path. Importing a `.vssettings` file copies its
contents into Visual Studio's own per-user settings store -- it does not
stay linked to the file it came from -- so this one generated file can be
handed to every other user on the machine (checked into the repo, dropped
on a network share, emailed, whatever) to import as-is. They do not run
`bootstrap.cmd`, `ads-deploy vssettings`, or anything else themselves; they
only do the one unavoidable GUI step everyone does regardless of install
mode (step 4 below -- VS External Tools settings are confirmed per-user,
with no all-users import option).

`bootstrap.cmd` also sets `ADS_DEPLOY_TOOLENV_ROOT` **system-wide** via
`setx /M` when `ADS_DEPLOY_SHARED_DIR` is set -- unlike `PATH`, this is a
single short, standalone string (nowhere near `setx`'s 1024-character
truncation limit), so scripting it is safe. This one *is* required, not
optional: it's what every other user's VS-launched `ads-deploy build`/
`lint`/etc. calls use to find the shared pytmc/make pixi environments
(`ads_deploy/toolenv.py`'s `toolenv_root()`, per-user `%LOCALAPPDATA%` by
default) -- without it, those calls would silently fall back to each user's
own, empty, per-user location and fail. Like any system environment
variable change, it only takes effect for other users at their *next*
login, not retroactively in an already-open session.

Extending the system `PATH` is a **separate, optional** step, only needed
for people who also want `ads-deploy`/`pytmc`/`make`/`pre-commit` available
from a plain terminal outside of Visual Studio -- the VS External Tools
workflow above never depends on PATH, since `Command` is already a resolved
absolute path. `bootstrap.cmd` deliberately does not script this itself --
`setx /M PATH ...` has a hard 1024-character limit and silently *truncates*
longer values, which can corrupt the whole machine's PATH -- and instead
prints the one PowerShell command for an admin to review and run themselves
if they want it, once.

A user who wants to experiment with a different tool/version independently
of the shared install can simply run their own **per-user** `bootstrap.cmd`
(leave `ADS_DEPLOY_SHARED_DIR` unset) and their own `ads-deploy vssettings`
-- this produces a fully separate, personal install and settings file with
no effect on, or coordination with, the shared one.

VS "External Tools" workflow
=============================

Each menu entry calls `ads-deploy` directly (`Command` is `ads-deploy`'s
resolved path, baked in by `ads-deploy vssettings` at generation time --
Visual Studio doesn't search `PATH` for this field) with a subcommand and
the full solution path as **one** argument -- there is no `.cmd` wrapper
script and no bash involved anywhere in this chain. The two
macros are concatenated with no space (`$(SolutionDir)$(SolutionFileName)`,
not `$(SolutionDir) $(SolutionFileName)`) deliberately: `$(SolutionDir)`
always ends in a backslash, and a quoted Windows argument ending in `\"` has
its closing quote escaped by standard argv parsing, merging it with whatever
argument follows (confirmed directly). A full path ending in `.sln` can't
trigger that.

| Menu entry | Command |
| --- | --- |
| Lint pragmas | `ads-deploy lint $(SolutionDir)$(SolutionFileName)` |
| Configure and build IOC(s) | `ads-deploy build $(SolutionDir)$(SolutionFileName)` |
| Record debugging | `ads-deploy debug $(SolutionDir)$(SolutionFileName)` |
| Project summary | `ads-deploy summary $(SolutionDir)$(SolutionFileName)` |
| Qt Designer | `designer` (not pytmc-specific, called directly) |

From a terminal, pass the full `.sln` path as one argument, e.g.
`ads-deploy build "C:\...\cc_test\cc_test.sln"` -- not a separate directory
and filename.

`ads-deploy build` is the one that used to need `bash.exe` (`build_ioc.cmd` →
`create_iocboot.cmd` → `build.sh`) purely to enumerate `ioc-*` directories,
patch a Makefile line that's dead code once `make`'s own command-line
variables already override it, and export `PATH`. All of that is now plain
Python (`pathlib.Path.glob`, `vstools.tool_env`) -- `make.exe` itself is a
native Windows console executable and never needed bash to run.

Managing tool versions
=======================

Provisioning and PATH exposure are two separate steps, matching how
`ctrlenv-pathmunge` works on Linux (it only resolves and exposes a version
already built elsewhere -- it doesn't build anything itself):

* `ads-deploy install <tool>/<version>` provisions (once, immutably) an
  isolated [pixi](https://pixi.sh/) environment for a pinned version of a
  registered tool. Installing the same `tool/version` again is a no-op
  *unless* ads-deploy would now generate a different `pixi.toml` for it
  (e.g. a newer ads-deploy version changed a dependency pin) -- that's
  detected automatically and rebuilt without needing `--force`. Run
  `ads-deploy install` with **no** arguments to install every entry in a
  `pathmunge.toml`'s `[tool-versions]` table at once (found by walking up
  from the current directory) -- the same file that pins what a project
  resolves also doubles as its install manifest, so there's only one file
  to maintain.
* `ads-deploy pathmunge <tool>/<version> [<tool2>/<version2> ...]` resolves
  one or more *already-installed* tool/versions and prints a single `PATH`
  fragment (all their executable directories joined together) to prepend --
  without activating any environment. It fails (and tells you to run
  `install`) if a requested version isn't provisioned yet. `ads-deploy
  build`/`lint`/`debug`/`summary` call the same resolution logic
  **in-process** (`vstools.tool_env`) rather than shelling out to this
  command -- no subprocess boundary, no shell quoting involved at all for
  the actual "External Tools" workflow.

Which registry a tool's package comes from is a one-line, declarative entry
in [`ads_deploy/tool_registry.py`](ads_deploy/tool_registry.py) -- adding a
future tool that's conda-forge-only (a compiler, a library, anything
non-Python) is just a new entry there, never new install logic:

```python
REGISTRY = {
    "pytmc": ToolSource(ecosystem="pypi", package="pytmc"),
    "make": ToolSource(ecosystem="conda", package="make"),
}
```

```
$ ads-deploy install pytmc/v2.22.2
$ ads-deploy install make/4.4.1
$ ads-deploy pathmunge pytmc/v2.22.2 make/4.4.1
C:\...\toolenvs\pytmc\v2.22.2\.pixi\envs\default\Scripts;C:\...\toolenvs\make\4.4.1\.pixi\envs\default\Library\bin

$ ads-deploy versions pytmc
v2.22.2
```

`ads-deploy pathmunge <tool>` (no version) resolves one in order: a
`pathmunge.toml` pin (see below), then the highest version of `<tool>`
already installed locally, then fails with a pointer to `install` only if
nothing is installed at all. So a project with nothing pinned just uses
whatever you last installed -- no `pathmunge.toml` is required for the
common case.

A project can pin its own version explicitly by placing a `pathmunge.toml`
next to its `.sln`:

```toml
[tool-versions]
pytmc = "v2.22.2"
make = "4.4.1"
```

```
$ ads-deploy install
INFO:ads_deploy.install:Installing every tool pinned in .\pathmunge.toml
```

### Using pinned tools directly from a terminal (outside TwinCAT/VS)

`ads-deploy pathmunge` only *prints* the resolved PATH fragment -- it can't
modify your current shell's `PATH` itself (a child process can never reach
back and mutate its parent shell's environment; that's an OS-level
constraint, not a design choice -- the same reason `conda activate` is a
shell function/script, not a plain executable). `bootstrap.cmd` installs two
small wrapper scripts next to `ads-deploy` itself for exactly this case:

```
C:\> pathmunge-activate pytmc make
C:\> pytmc --version

PS C:\> . pathmunge-activate.ps1 pytmc make
PS C:\> pytmc --version
```

The `cmd.exe` version must be invoked directly by name (never via
`cmd /c pathmunge-activate ...`); the PowerShell version must be
dot-sourced (the leading `. `) -- both are required so the PATH change runs
in your current shell's scope rather than a throwaway child process.
