# Resolves one or more tools (same spec `ads-deploy pathmunge` takes) and
# prepends their executable directories to PATH -- for your CURRENT shell.
#
# Usage (note the leading ". " -- this MUST be dot-sourced):
#     . pathmunge-activate.ps1 pytmc make
#     . pathmunge-activate.ps1 pytmc/v2.22.1
#
# IMPORTANT: a plain .exe (like ads-deploy itself) can never modify its
# parent shell's environment -- that's an OS-level constraint, not a design
# choice. A normally-invoked script (`.\pathmunge-activate.ps1 ...`) runs in
# its OWN scope and any $env:PATH change it makes is discarded when it
# returns. Dot-sourcing (". .\pathmunge-activate.ps1 ...") runs the script
# in the CALLING shell's scope instead, so the PATH change persists --
# exactly the same convention Python venvs' Activate.ps1 uses.
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $ToolSpecs
)

# Deliberately NOT merging stderr (2>&1) here: ads-deploy logs its
# human-readable status lines (e.g. "using latest installed version: ...")
# to stderr, and merging streams would contaminate $resolved -- the PATH
# fragment -- with that log text. Capturing stdout alone keeps $resolved
# exactly the one line pathmunge prints; stderr still reaches the console
# directly for the user to see.
$resolved = & ads-deploy pathmunge @ToolSpecs
if ($LASTEXITCODE -ne 0) {
    return
}

$env:PATH = "$resolved;$env:PATH"
