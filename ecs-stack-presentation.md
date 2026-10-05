---
marp: true
theme: default
paginate: true
size: 16:9
title: ECS stack and TwinCAT library management
style: |
  section {
    font-size: 24px;
    padding: 50px 60px;
  }
  h1 { font-size: 40px; }
  h2 { font-size: 34px; margin-bottom: 0.4em; }
  h3 { font-size: 26px; font-weight: 600; }
  table {
    font-size: 17px;
    width: 100%;
    table-layout: fixed;
  }
  table th, table td {
    padding: 5px 8px;
    word-wrap: break-word;
  }
  table th { background: #f2f2f2; }
  pre, code { font-size: 17px; }
  pre { line-height: 1.32; }
  blockquote {
    font-size: 22px;
    border-left: 4px solid #999;
    padding-left: 0.8em;
    color: #333;
  }
  ul, ol { line-height: 1.45; }
  /* audience tag: the bare `[EXEC]` / `[ENG]` / `[BOTH]` line under each title */
  section > p > code:only-child { font-size: 15px; color: #777; background: none; }
  /* dense tables get their own class */
  section.dense table { font-size: 14px; }
  section.dense { font-size: 21px; }
---

<!--
HOW TO USE THIS FILE

Marp deck.

TO GENERATE SLIDES (no Node needed):
  Install the "Marp for VS Code" extension (marp-team.marp-vscode), then open this file
  and click the Marp icon in the editor title bar for live preview. To export, open the
  command palette (Ctrl+Shift+P) and run "Marp: Export Slide Deck...", choosing PPTX,
  PDF or HTML. PPTX and PDF export uses the Chrome or Edge already on the machine.

  Install from the terminal with:
    code --install-extension marp-team.marp-vscode

ALTERNATIVE (needs Node installed):
  npx @marp-team/marp-cli ecs-stack-presentation.md --preview
  npx @marp-team/marp-cli ecs-stack-presentation.md -o ecs-stack.pptx

NOTE ON PPTX: each slide exports as a full-page image, so the text is not editable in
PowerPoint afterwards. If you need editable slides, export PDF or HTML and present from
those, or rebuild the deck natively in PowerPoint using this file as the script.

Slides marked `<!-- _class: dense -->` use smaller type for tables and code. Remove that
line if a slide looks too small on the projector.

Each slide is tagged [EXEC], [ENG] or [BOTH].
For a 25-minute managerial slot, keep the [EXEC] and [BOTH] slides: "We cannot reliably
rebuild" through "The proposal in one picture", then "The decision table" through "What
we are asking for". Drop the [ENG] slides in between.
For the full review, run everything. Act III and the Q&A are the point of the talk.

Speaker notes live in the `> Speaker notes:` blocks. They carry what is said but not
shown. Marp exports them as presenter notes in PPTX.

The final "Q&A prep" section is presenter material, not a slide. Delete it before
exporting a deck for projection.

Sources: background.txt, stack-management-executive summary.txt, ecs-stack-detailed.txt.
Section numbers in the notes refer to ecs-stack-detailed.txt.
-->

# We cannot reliably rebuild what we commissioned

### ECS stack and TwinCAT library management: a design review

`[EXEC]`

**Ground rule for this talk:** every option on the table costs something, including
doing nothing. We are arguing for the least painful one, not a free one. We want you to
test that claim.

> Speaker notes:
> Open by saying what this meeting is and is not. It is not a request to approve a
> finished thing. It is a design that we think is right and that we want picked apart
> before we build it.
>
> The one sentence to land: take a project we commissioned two years ago, rebuild it
> today on a different machine, and we cannot promise you get the same IOC back. That is
> the problem. Everything else in this deck follows from it.
>
> Say the ground rule out loud. The deck has an entire act about what this design costs
> us. If you go away thinking some piece is not worth its price, say so today, because
> that is cheaper than finding out after we build it.

---

## What we deliver, and why versions matter here

`[EXEC]`

- About 5 core TwinCAT libraries plus several higher level and domain libraries
- Two compiler worlds: legacy 4022/4024, and current 4026
- Systems are commissioned and checked out against specific versions, then run for years
- Moving a commissioned system onto new versions can force re-commissioning, which is
  expensive and operationally disruptive
- Some 4026 features are structural, for example Generics. Source using them cannot be
  parsed by the older compiler at all, so it can never be shared with 4024

> Speaker notes:
> Two facts set up everything else.
>
> First, our delivered systems are long lived and validated against a specific set of
> versions. "Just upgrade it" is not a cheap sentence in this domain. It can mean a
> re-commissioning campaign.
>
> Second, the 4022/4024 and 4026 split is not a preference or a migration we can hurry.
> Generics are a parser-level difference. A file using them does not compile on the old
> toolchain, so there is no version of "be careful" that makes one source file serve both
> worlds.
>
> If someone asks why not simply move everything to 4026: that is the destination, and
> the answer is on "The proposal in one picture". The cost of getting there is
> operational rather than technical.

---

<!-- _class: dense -->

## Where a version actually gets chosen today

`[EXEC]`

| Step | What is versioned | How chosen today | Recorded with the project? |
|---|---|---|---|
| Add direct dependency | a library, e.g. twincat-motion | manually, by the engineer | partially |
| Transitive dependencies | LCLS General, twincat-math, ... | latest on the node | no |
| Build IOC on Windows | pytmc, ads-ioc | node-wide fixed install | no |
| Build on Linux | pytmc | whatever is activated on PATH | **no** |
| Build on Linux | ads-ioc | from the Makefile, via `IOC_TOP` | yes |

Five mechanisms. None of them coordinated with the others.

> Speaker notes:
> This table is the whole diagnosis on one slide. Walk it slowly, it is worth the time.
>
> An engineer opens the project in XAE and sets the direct references by hand. Adding
> twincat-motion also pulls in LCLS General and twincat-math. Unless the engineer expands
> the library manager and sets those too, they resolve to whatever is newest on that node.
>
> Building produces a .tmc. Tools, Configure and build IOC, runs pytmc against it, using
> one node-wide install that every project on that node shares. Then the project moves to
> Linux and make runs. The project Makefile knows nothing about pytmc. It includes the
> ads-ioc Makefile via IOC_TOP, and that invokes whatever pytmc happens to be on PATH.
>
> Read the last column aloud. Almost nothing here is recorded with the project. ads-ioc
> is the one thing we pin, and we pin it in the Makefile.

---

## What goes wrong

`[EXEC]`

**Builds differ by machine and by date.** Transitive libraries resolve to whatever is
newest on the node. Nothing is pinned, so the same project builds differently in two
places. (F1, F2)

**The generator itself is a moving target.** pytmc turns the .tmc into the DB and IOC.
It is under heavy feature development and can break backward compatibility, so the same
.tmc can produce different output depending on which pytmc processes it. On Windows that
is a node-wide install, on Linux it is the activated shell. (F3, F4, F5)

**Nothing protects us from a future break.** pytmc has not broken regeneration of an
existing project so far. We have no mechanism that would stop it if it did. (F6, a risk)

> Speaker notes:
> Three groups, and they are not equally bad.
>
> The first is annoying and already happens. Two engineers, two nodes, two different sets
> of transitive library versions, and nobody can see it happened.
>
> The second is the one that actually threatens delivery. pytmc is the tool whose version
> matters most to the output, it moves fastest, and it is the only tool with no recorded
> version anywhere. ads-ioc is pinned via IOC_TOP. pytmc is pinned nowhere at all, and it
> is chosen by two different mechanisms on the two platforms every project has to cross.
>
> Be precise on the third. Do not oversell it. pytmc has not, to date, broken an existing
> project's regeneration. The honest statement is about posture: iocBoot is generated and
> disposable, so if someone deletes it and regenerates on a machine with a newer pytmc,
> nothing in the project says which pytmc was supposed to run. If a breaking change ever
> lands, we find out by being broken.
>
> If you overstate F6 in this room, someone who knows pytmc will correct you and you lose
> the rest of the argument.

---

## What that looks like in practice

`[EXEC]`

Same project. Same `.tmc`. Two engineers.

1. Engineer A builds on node 1. pytmc 2.20 there. Transitive LCLS General resolves to
   3.4.1, the newest on that node.
2. Engineer B builds the same checkout on node 2, a month later. pytmc 2.22 there, LCLS
   General 3.5.2.
3. Both builds succeed. Neither engineer is warned about anything.
4. The generated DB and IOC differ. Nothing in the repository records which combination
   produced the version we commissioned.

> Speaker notes:
> Make this concrete, and keep the version numbers illustrative rather than claiming
> these are real incidents.
>
> The point is not that the second build is wrong. The point is that we cannot tell which
> one matches the system that was checked out and signed off, because the information was
> never written down.
>
> This is also the slide where someone may say "in practice it has been fine." That is
> largely true, and you should agree. It has been fine because the drift has been small
> and because people are careful. The argument is that we are relying on it staying small,
> with nothing recording what we relied on.

---

## The consequence, and the cost of leaving it alone

`[EXEC]`

- A commissioned system cannot be reliably reproduced today
- Going forward, nothing protects an old project from a future tooling change
- Doing nothing is a real option, and it has a real price:
  - we keep carrying an unbounded risk on systems that run for years
  - when a rebuild does diverge, we debug it with no record of what changed
  - the cost arrives unscheduled, on whichever project happens to hit it first

> Speaker notes:
> This slide exists so the status quo stays on the table as a named option for the rest
> of the talk. Everything in Act II gets compared against it.
>
> The honest framing: doing nothing is not free, it is deferred and unpredictable. The
> proposal converts a silent, unbounded, unscheduled cost into a visible, bounded,
> scheduled one. That is the trade. It is a good trade in my view, and it is a trade, not
> a win.
>
> This is the end of the managerial arc's problem statement. If you are running the short
> version, go from here to "The proposal in one picture", then to the decision table and
> the closing slides.

---

## The proposal in one picture

`[BOTH]`

- **4026 is the destination, 4022/4024 is maintenance.** New capability targets 4026.
  Older targets get bug fixes.
- **Two concerns, kept separate.** Maturity is `master` versus `stable`. Compiler target
  is expressed by version line and metadata. They are never multiplied into branches.
- **One rule protects the graph.** Core building blocks stay target-neutral and never
  adopt 4026-only features.
- **One binding artifact.** Every PLC project pins to a single immutable `ecs-stack`
  release: a flat lockfile of all library versions plus pytmc and ads-ioc.
- **One guarantee, enforced by the machine.** Resolution hard-fails on transitive target
  incoherence, so an incoherent stack cannot be published or built.

> Speaker notes:
> Five points, and the fifth is the one that makes the rest more than a convention.
>
> The lockfile replaces the uncontrolled `Name, *` placeholder resolution with exact
> pins, including the transitive libraries nobody currently sees, and including pytmc,
> which nothing currently records.
>
> What we chose here: pin the complete set, libraries and tools, as one immutable unit.
> What it costs: a release repo, a lockfile per project, and a release-cutting process
> somebody has to own. What the alternatives cost more: pinning only pytmc leaves the
> transitive library drift in place, and recording versions without enforcing them gives
> us a good audit trail of builds we cannot reproduce. The decision table has the full
> comparison.

---

## Why protecting the cores protects everything

`[ENG]`

> Compiler-target compatibility is transitive. A library supports a target only if all
> of its dependencies support that target.

Consequences:

- A core that adopted a 4026-only feature becomes 4026-only, and cascades that to every
  dependent
- A library that depends on the 4026-only chain is itself 4026-only, whether it meant to
  be or not
- Therefore cores may evolve with neutral features and fixes, must never adopt 4026-only
  features, and must never depend on the 4026-only chain

New 4026-only capability goes into a 4026-only library, or a new library that depends on
the core. Never into the core in place.

> Speaker notes:
> This is the invariant the whole model rests on, and it is one line.
>
> The practical consequence is that we only have to defend four libraries. Guard
> neutrality on LCLS General, PMPS, lcls-twincat-math and lcls-twincat-motion, and the
> whole graph below them stays usable by both worlds.
>
> The flip side is a real constraint on developers, and you should say so. If someone
> wants a 4026 feature inside a core, the answer is no, and the work goes somewhere else.
> That is a cost. It is smaller than the alternative, which is that one convenient commit
> in a core quietly makes every consumer 4026-only.
>
> lcls-twincat-he-satt is the live example. It is 4026-only today, not because anyone
> decided that, but because it depends on twincat-motion-abstraction. That is transitivity
> doing its work without asking anybody.

---

<!-- _class: dense -->

## The libraries: single-trunk cases

`[ENG]`

| Library | Category | Target | Branches | CI gate |
|---|---|---|---|---|
| LCLS General | Core | neutral | `master` + `stable` | @ 4022 |
| PMPS | Core | neutral | `master` + `stable` | @ 4022 |
| lcls-twincat-math | Core | neutral | `master` + `stable` | @ 4022 |
| lcls-twincat-motion | Core | neutral | `master` + `stable` | @ 4022 |
| twincat-device-abstraction | 4026-only | tc4026 | `master` + `stable` | @ 4026 |
| twincat-motion-synchronous | 4026-only | tc4026 | `master` + `stable` | @ 4026 |
| twincat-motion-abstraction | 4026-only | tc4026 | `master` + `stable` | @ 4026 |
| lcls-twincat-he-satt | De-facto 4026 | tc4026 | `master` + `stable` | @ 4026 |

Eight of the ten libraries. Two branches each, `stable` created on demand.

> Speaker notes:
> Say clearly that this is a destination, not a description. Today every one of these
> libraries is developed on a single master branch. "How we would adopt this" covers the
> route from here to there.
>
> The shape of the slide is the argument. Eight libraries, one trunk each, nothing
> complicated. The complexity is confined to the two on the next slide.
>
> lcls-twincat-motion is the row worth pausing on. It is deprecated but long-term
> supported, and its successor is twincat-motion-abstraction, which is 4026-only.
> Migrating a consumer to the successor makes that consumer 4026-only. Its end of life is
> tied to the last 4024 consumer, so there is no date. That is an open item later.
>
> lcls-twincat-he-satt is de-facto 4026 rather than by choice. It depends on
> twincat-motion-abstraction, and transitivity did the rest.

---

## The libraries: the two dual-target cases

`[ENG]`

| | lcls-twincat-common-components | twincat-optics |
|---|---|---|
| Category | Dual-target | Dual-target |
| Target | both | both |
| 4024 line | majors `< 4.0.0`, frozen, fixes only | boundary **TBD** |
| 4026 line | majors `>= 4.0.0`, active | needed once it moves to `twincat-motion-abstraction` |
| CI gate | 4024 line @ 4022, 4026 line @ 4026 | same |
| Status | boundary decided | boundary open |

These two carry four branches each. Everything else carries two.

> Speaker notes:
> A note on wording: the source documents call these straddling libraries. This deck says
> dual-target, which is the same category.
>
> common-components has a decided boundary at 4.0.0. Majors below that are the frozen
> 4024 line, fixes only. Majors at and above are active 4026 development.
>
> twincat-optics needs a 4026 line when it switches its dependency from
> lcls-twincat-motion to twincat-motion-abstraction, because that switch makes the line
> 4026-only. Its boundary is genuinely undecided. Do not invent a number in the room.
>
> The open question on optics is not only where the boundary falls. It is whether the
> 4024 line still needs new features at all, or can be development-frozen, which would
> make the boundary question much easier.

---

<!-- _class: dense -->

## How the target propagates

`[ENG]`

```
[neutral cores]  LCLS General · PMPS · lcls-twincat-math · lcls-twincat-motion
        |  (usable by BOTH the 4024 and 4026 worlds)
        |
        v (4026 world only)
twincat-device-abstraction --+
twincat-motion-synchronous --+--> twincat-motion-abstraction (4026-only)
                                     |
              +----------------------+-----------------------+
              v                      v                       v
     lcls-twincat-he-satt   lcls-twincat-common-components   twincat-optics
      (de-facto 4026)        (4026 line = majors >= 4.0.0)   (4026 line, TBD)
```

The 4024 lines of common-components and optics depend on the neutral cores, including
lcls-twincat-motion, and not on the 4026 chain. That is what lets a neutral core and a
4024 line of a dual-target library live together in a 4024 stack while the 4026 chain
cannot.

> Speaker notes:
> The note under the diagram is the crux of the coherence argument, so read it out rather
> than letting people skim it.
>
> Everything in the top box is available to both worlds. Everything below the arrow is
> 4026 only, and anything that depends on it inherits that.
>
> This is also why a tc4024 stack that includes lcls-twincat-he-satt is not a
> configuration mistake we should catch in review. It is arithmetically impossible, and
> the resolver refuses it. "New ways for a build to fail" covers what that refusal looks
> like when it fires.

---

## Branching: two axes, not a matrix

`[ENG]`

**What we chose.** Cores and the 4026-only chain are single trunk: `master` plus
`stable` on demand. Maturity is a pre-release suffix (`2.4.0` versus `2.4.0-preview.1`),
never a branch. `stable` is fixes only, PATCH releases only, no feature backports ever.

**Dual-target libraries are the one exception.** They have to serve 4024 and 4026 both,
so they carry four branches while both targets are alive: one development line and one
fixes line per target, each gated on its own compiler.

| Branch | Line | Purpose | CI gate |
|---|---|---|---|
| `master` | 4022/4024 | existing 4024 development | build @ 4022 |
| `stable/tc4024` | 4022/4024 | 4024 fixes only | build @ 4022 |
| `tc4026` | 4026 | 4026 development | build @ 4026 |
| `stable/tc4026` | 4026 | 4026 fixes only | build @ 4026 |

**What it costs.** Four branches on those libraries, and four places a release could be
cut from the wrong line. **What the alternative costs more.** Four branches per library
across the whole set is roughly 30, which is what we are avoiding everywhere else.

> Speaker notes:
> Expect the challenge here, and welcome it: "you did not remove the complexity, you
> renamed it." That is fair and you should concede it. The claim is about where the
> complexity sits. For most libraries the target lives in metadata and version lines,
> which CI can check. A thirty branch matrix is checkable by human attention, which is
> what we are trying to stop relying on.
>
> Be precise about the dual-target case, because it is the one place the branch count is
> genuinely four. Stable branch names are symmetric and target-explicit on purpose, so
> nobody cuts a release from the wrong one.
>
> What "dual-target" means concretely: the library has to build against 4024 and against
> 4026. It does that through its two lines, not by keeping one source tree that satisfies
> both compilers. Each branch gates on its own target only. That is forced by
> transitivity rather than chosen: once the 4026 line depends on the 4026-only chain, it
> cannot compile under 4024, so asking it to would be asking for the impossible.
>
> The branches and the major version boundary are two halves of one mechanism rather than
> competing options. The branches are where the work happens. The major version is how a
> consumer tells which target a release is for, which is why common-components puts its
> 4026 line at 4.0.0 and above.
>
> Note for anyone reading both documents: the executive summary describes the major
> version boundary and does not carry the four-branch table from section 9.1. The summary
> is incomplete there, not in conflict with it.
>
> Also worth saying plainly: no feature backports to a frozen line, ever, from the
> technical side. If operations wants a feature on a frozen system, that is a migration
> decision they own and pay for. That bright line is what stops maintenance branches from
> sprawling.

---

<!-- _class: dense -->

## The stack: intent and resolution are separate artifacts

`[ENG]`

| | Manifest | Lockfile |
|---|---|---|
| Authored by | a person | the resolver |
| Contains | version *ranges* | *exact* pins |
| Also records | deliberate exclusions | per-library target attestation |
| Mutable | yes | no, immutable |
| Role | intent | the deliverable |

```yaml
ecs_stack_version: 5.4.0
line: tc4026            # tc4022/tc4024 or tc4026
channel: stable         # stable | preview
ioc_build:              # universal to every PLC project
  pytmc:  v2.22.1
  ads_ioc: R2.1.3
libraries:
  LCLS_General: 3.5.2
  twincat-motion-abstraction: 2.4.1
verified_coherent: true
```

> Speaker notes:
> What it costs: two schemas, a release repo, and a release-cut workflow. What the
> alternative costs more: ranges in a lockfile means it is not a lockfile.
>
> The split is deliberate and the schemas enforce it. Manifests accept ranges, lockfiles
> accept exact versions only, so you cannot commit a range into a lockfile or a fixed pin
> mindset into a manifest. One schema or the other rejects it.
>
> The stack is flat and single tier. There is no ecs-motion-stack. pytmc and ads-ioc are
> used by every PLC project regardless of domain, so nothing here is motion specific.
> Domains are groupings for readability inside the lockfile with no semantic meaning.
>
> The resolver is deterministic, which is what makes immutability trustworthy: release
> repo CI re-runs it and asserts the committed lockfile matches, so a hand-edited or stale
> lockfile is caught.

---

## Project binding and the build

`[ENG]`

`ECS_STACK` is the master pin. The committed lockfile is its projection, and it lives
just outside `iocBoot` so it survives iocBoot being deleted and regenerated.

```
1. Determine ECS_STACK
2. Ensure the local lockfile is present and in sync with ECS_STACK
3. Resolve the lockfile -> pytmc version, ads-ioc, library pins
4. ctrlenv-pathmunge pytmc/<version>        # PATH-only, EPICS-safe
5. Set IOC_TOP from the ads-ioc pin
6. Verify .plcproj placeholders match the lockfile -> HARD-FAIL on mismatch
7. Run make (pytmc builds, from its own uv .venv)
8. Emit a build report, on success and on failure
```

The build never re-resolves. Resolution is a release-time concern.

> Speaker notes:
> Three choices on this slide are worth defending explicitly.
>
> The lockfile sits outside iocBoot because iocBoot is pytmc-generated and disposable. If
> the binding lived inside it, deleting iocBoot would delete the record of which stack the
> project was built against. Putting it outside costs us one more file at the project root
> and buys us a binding that survives regeneration.
>
> Step 4 uses ctrlenv-pathmunge rather than pixi activation, and that is not a style
> preference. pathmunge only touches PATH, so it leaves central EPICS alone, and the IOC
> build needs central EPICS. Full pixi activation resets EPICS deliberately, which makes
> it unusable here. We need pytmc as a command, not a whole environment.
>
> Pinning pytmc by version transitively pins that version's entire uv-locked dependency
> graph, because the .venv is frozen inside the published version. So the stack only has
> to record one version string.
>
> pytmc itself stays completely stack-agnostic. tc-release handles every stack concern
> around it. That matters because it means we are not forking or patching pytmc.

---

# What this costs us

### The part of the design we most want you to attack

`[BOTH]`

> Speaker notes:
> Transition slide. Say it directly: everything so far was what the design does. The next
> five slides are what it takes from us. If we have got the balance wrong anywhere, this
> is where it will show.

---

## New artifacts, each of which can rot

`[BOTH]`

- A release repository: manifests, lockfiles, a catalog index
- Two JSON schemas, which have to be maintained as the model evolves
- A committed lockfile in every PLC project
- A build report per build
- A Confluence catalog rendered from the repo

Every one of these is a thing that can drift, go stale, or be wrong in a way that is
only discovered later.

> Speaker notes:
> Be genuinely honest here rather than listing these as features.
>
> The catalog is the clearest risk. It is derived from the repo and rendered, never hand
> maintained, specifically because a hand-maintained parallel copy drifts. That is the
> design intent. If the rendering ever breaks and somebody patches the page by hand, we
> have the drift back.
>
> The build report is the artifact that ties an IOC to its exact stack, and it is emitted
> on failure as well as success. It is also one more thing to store, find and keep.
>
> Nobody should leave this room thinking the lockfile is free. It is a file in every
> project that must be committed, must be regenerated when ECS_STACK changes, and will
> show up in diffs.

---

## New process, and a release everyone has to attend

`[BOTH]`

**Ownership is settled.** ECS owns most of these libraries, so ECS owns the management
repo too. It sits with the code it pins.

**Privileges differ by maintainer**, as they already do across the library repos. Not
everyone needs write access to manifests or the right to cut a release.

**The release itself engages everyone.** A stack release is a statement about every
library in it, so cutting one is a coordination event across all the maintainers, not an
action one person performs alone.

Still to settle: cadence, turnaround when a project needs a pin that no published stack
has yet, and who arbitrates a disagreement between maintainers at release time.

> Speaker notes:
> Correct any impression that this is an unowned orphan process. ECS owns most of the
> libraries and will own the management repo, which puts the repo with the people who
> already maintain what it pins.
>
> The interesting part is the shape of the release, not the ownership of the repo. Because
> a stack release pins every library at once, it cannot be cut quietly by one maintainer.
> Everyone with a library in the stack has to be engaged, because the release is asserting
> that their library at that version is coherent with everything else in the set.
>
> That is a real cost and it is worth naming as one. It is a recurring meeting, or at
> least a recurring round of sign-offs. The counterweight is that this coordination is
> happening implicitly today and badly, in the sense that nobody checks the combination at
> all until something fails to compile.
>
> The differentiated privileges matter practically. Authoring a manifest range is a
> different act from cutting a release, and the repo should reflect that.
>
> Expect the question "does this mean I wait for a release before I can use a new library
> version." We have not defined the turnaround. That is worth deciding in this room.

---

## New ways for a build to fail

`[BOTH]`

Builds that used to succeed can now stop:

- `.plcproj` placeholders do not match the lockfile
- `TARGET_INCOHERENCE`: a library or a transitive dependency is incompatible with the line
- `ECS_STACK` is not an immutable published release
- `VERSION_CONFLICT`, `UNSATISFIABLE_RANGE`, `CHANNEL_VIOLATION`, `MISSING_TRANSITIVE_DEP`

These are failures we want. They are still failures the team has to learn to read, and
they will sometimes arrive at the worst possible moment.

> Speaker notes:
> Give both halves of this honestly.
>
> The good half: today an incoherent target mix compiles for a while and then fails
> somewhere confusing, or worse, produces something that runs and was never validated.
> Failing at resolution time with a named library is strictly better.
>
> The bad half: hard-fail means hard-fail. If somebody is standing at a machine trying to
> get a fix out and the stack refuses, the design as written does not give them an escape
> hatch. Whether it should is a real question and it is in the Q&A section.
>
> What makes this survivable is diagnostics. The resolver has a defined failure taxonomy,
> and TARGET_INCOHERENCE in particular must name the offending library, its target and the
> path that required it. A hard fail with a bad message would be worse than no check.

---

## The parts that are genuinely fiddly

`[BOTH]`

**Binding reconciliation has four cases** (section 21). Lockfile present with a blank
`ECS_STACK` after iocBoot regeneration recovers the binding from the lockfile and writes
it back. Lockfile present and matching is the simple path. Lockfile present and
differing means the user changed `ECS_STACK`, so regenerate. Neither present is a fresh
project and falls back to a default stack, always logged, and hard-failing for deploy.

**The dual-target lifecycle is ongoing work**, not setup. Transitional state, then a
development freeze, then an operations-controlled end of life, then convergence.

**Windows is not built yet.** `win-x86_64` uv venvs and a Windows `ctrlenv-pathmunge`
equivalent do not exist. ads-ioc provisioning is unresolved.

> Speaker notes:
> The reconciliation logic is the subtlest thing in the document and it deserves this
> slide, because it is exactly the sort of thing that is easy to agree to in a meeting and
> painful to debug at three in the morning.
>
> The rule that matters: a blank Makefile after regeneration must never clobber an
> existing lockfile. It recovers from it instead. Get that wrong and deleting iocBoot
> silently rebinds the project to the default stack.
>
> The default stack applies only when there is no lockfile and no ECS_STACK, and it is
> always logged explicitly. Deploy builds hard-fail rather than silently shipping an IOC
> built against a default.
>
> On Windows, the detailed document calls these implementation TODOs rather than design
> blockers. That is the author's judgement and the room is entitled to disagree with it.
> Linux is authoritative and Windows differs only in path resolution, which is the reason
> for the confidence, but the artifacts still have to be produced and a PowerShell or
> git-bash pathmunge equivalent still has to work.

---

<!-- _class: dense -->

## The decision table

`[BOTH]`

| Choice | What it costs | What the alternative costs |
|---|---|---|
| Do nothing | nothing today | unbounded, unscheduled, unrecorded risk on systems that run for years |
| Pin the whole stack | release repo, process, per-project lockfile | pinning only pytmc leaves transitive library drift entirely in place |
| Enforce, do not just record | builds that now hard-fail | a perfect audit trail of builds we still cannot reproduce |
| Release repo | a repo and two schemas to maintain | versions in the build report only: no way to ask for a known-good set up front |
| Four branches only where both targets are live | four branches on two libraries, plus cross-target compatibility to maintain | four branches on every library, roughly 30 |
| `ctrlenv-pathmunge` | a Windows equivalent still to be written | pixi activation clobbers central EPICS, which the IOC build needs |
| Lockfile outside iocBoot | one more file at project root | inside iocBoot, the binding dies whenever iocBoot is regenerated |
| Incremental adoption | a long period of mixed state | a clean cut-over nobody has capacity to execute |

> Speaker notes:
> This is the slide the talk exists for. Spend real time here and invite disagreement row
> by row.
>
> Ask the room directly: which row do you think we got wrong? Is there a row missing? Is
> there an option in the right-hand column that is actually cheaper than we have written?
>
> The row most likely to be challenged is row three, enforce versus record. Recording
> without enforcing is genuinely cheaper and genuinely less disruptive, and it would give
> us most of the diagnostic value. The argument against it is that it does not deliver the
> thing we actually need, which is being able to rebuild the commissioned system, not
> merely knowing that we cannot.
>
> If the room lands on recording first and enforcing later, that is a legitimate outcome
> and it maps cleanly onto the adoption steps on the "How we would adopt this" slide.
>
> If you are running the managerial cut, the engineering slides that set up two of these
> rows were skipped, so give each one a sentence. ctrlenv-pathmunge is how we put the
> pinned pytmc on PATH without disturbing the central EPICS install the IOC build needs.
> iocBoot is a generated directory that gets deleted and rebuilt, which is why the record
> of what we pinned has to live outside it.

---

<!-- _class: dense -->

## Every stated failure has an answer

`[BOTH]`

| Failure | Addressed by |
|---|---|
| F1 blind transitive resolution | the stack pins all libraries including transitive ones, resolved from the lockfile, never "latest" |
| F2 no pinning | `ECS_STACK` names one immutable release, the project commits a lockfile, nothing floats at build time |
| F3 version-sensitive generation | pytmc is pinned in the stack, so a given `.tmc` is always processed by the same pytmc |
| F4 node-determined Windows build | build tools come from the project's stack, not the node-wide install |
| F5 pytmc unrecorded, platforms disagree | pytmc and ads-ioc are pinned and consumed identically on both platforms via `ctrlenv-pathmunge` |
| F6 no protection against future breakage | the pin lives in a committed lockfile outside iocBoot, so a project regenerates with the exact pytmc it was built with |

> Speaker notes:
> This is a completeness check, not a victory lap. Every problem named in the diagnosis
> has a mechanism against it, and the mechanisms are mostly the same two things: pin
> everything, and record the pin where regeneration cannot destroy it.
>
> Keep F6 worded as risk here too. The claim is that a future pytmc change cannot break an
> old project's regeneration, even if iocBoot is deleted, because the lockfile survives
> and names the pytmc version. It is not a claim that anything has broken.

---

## How we would adopt this

`[BOTH]`

Today every library is developed on a single `master`. The branch structure in this deck
does not exist yet, and that is fine, because it is designed to arrive incrementally.

1. **Stand up the stack and reproducibility layer first.** `ecs-stack`, lockfiles, the
   `ECS_STACK` binding, the resolver. This delivers reproducibility and target coherence
   on its own, with no branch changes at all.
2. **Decide the 4024/4026 boundary per dual-target library.** Already done for
   common-components at `4.0.0`. Still open for optics.
3. **Let branches accrue on demand.** A `stable` branch appears when a library first has
   a frozen consumer that needs fixes. We do not erect them up front.

> Speaker notes:
> This is the de-risking slide and it is the strongest practical argument in the deck.
>
> Step 1 is separable. It does not require anyone to change how they branch, it does not
> require the classification table to be agreed in full, and it is where all the
> reproducibility value is. If the room is unsure about the branching model, we can build
> step 1 and keep arguing about the rest.
>
> Step 3 is worth emphasising for anyone worried about process weight. Nobody creates
> thirty branches on a Monday. A branch appears when a real frozen consumer needs it.

---

## What is still open

`[BOTH]`

- **twincat-optics boundary major.** Undecided. Also unresolved: whether the 4024 line
  still needs new features or can be development-frozen.
- **Release cadence and turnaround.** Ownership sits with ECS. How often a stack is cut,
  and how fast a project can get a pin that does not exist yet, is open.
- **Windows tooling.** `win-x86_64` uv venvs and a Windows `ctrlenv-pathmunge` do not
  exist yet. ads-ioc provisioning on Windows is unresolved.
- **lcls-twincat-motion end of life.** Tied to its last 4024 consumer, so there is no
  date and no owner for setting one.
- **Escape hatch for urgent fixes.** The design hard-fails. It does not say what an
  engineer does at 2am.

> Speaker notes:
> The executive summary does not carry the four-branch table from section 9.1. That is a
> gap in the summary rather than a disagreement between the documents, and it is worth
> fixing in the summary so a reader who only sees that page does not think the branches
> are gone.
>
> The last bullet is the one I would most like an answer to today. Everything else can be
> decided later without invalidating the model. That one changes how the enforcement is
> built.

---

## What we are asking for

`[BOTH]`

We are asking for agreement on the **model and design**. The implementation, meaning how
Linux and Windows realise it and how the stack repo is built, is secondary and can evolve
without changing the model.

Questions we want answered in this room:

1. Is the overhead in the decision table worth what it buys, row by row?
2. Should enforcement be hard-fail from day one, or record first and enforce later?
3. What release cadence and turnaround can the maintainers commit to between them?
4. Where does the twincat-optics boundary fall, and can its 4024 line be
   development-frozen?
5. Is there an escape hatch for an urgent field fix, and who authorises it?

> Speaker notes:
> End on the questions rather than a summary. The summary is already in their heads by
> now, and closing on questions is what makes this a review rather than a pitch.
>
> Question 2 is the one with the most room to move. Question 3 is aimed at the room
> collectively rather than at one person, because a stack release engages every
> maintainer whose library is in it.
>
> If the room wants to defer everything, propose step 1 from "How we would adopt this"
> as the thing to agree today, because it is separable and it carries the value.

---

# Appendix

`[ENG]`

> Speaker notes:
> Backup material. Do not present unless asked.

---

## Appendix A: the project lockfile

`[ENG]`

```
# ecs-stack.lock
# Auto-generated projection of an immutable ecs-stack release for THIS project.
# Do not hand-edit version pins. To change the stack, set ECS_STACK and rebuild.
```

Sections it carries:

- the binding, meaning which immutable release this project is pinned to
- IOC build tooling, universal to every PLC project
- resolved TwinCAT library pins, the `*` replacements, grouped by domain for readability
- the placeholder resolution map: what each `PlaceholderReference DefaultResolution
  'Name, *'` must resolve to
- provenance of this projection

> Speaker notes:
> The placeholder resolution map is what step 6 of the build checks against. That is the
> mechanism that stops a .plcproj drifting away from the stack it claims to be pinned to.

---

## Appendix B: resolver failure taxonomy

`[ENG]`

1. `UNSATISFIABLE_RANGE`: no eligible version for a library or tool
2. `CHANNEL_VIOLATION`: only preview releases available but the channel disallows them
3. `MISSING_TRANSITIVE_DEP`: a required dependency is not in the manifest
4. `VERSION_CONFLICT`: the selected version fails a dependency's range
5. `TARGET_INCOHERENCE`: a library or transitive dependency is incompatible with the
   line. Must name the offending library, its target, and the requiring path.

The resolver runs at release cut and in release-repo CI. It does not run at build time.

> Speaker notes:
> Five distinct, actionable errors. The fifth is the central guarantee's failure mode and
> the one whose message quality matters most.
>
> The resolver is deterministic, so CI re-runs it and asserts the committed lockfile
> matches. That is how a hand-tampered or stale lockfile gets caught.

---

## Appendix C: the dual-target lifecycle

`[ENG]`

**Two triggers, different owners.**

1. Development freeze on 4024, controlled by development, and it comes sooner. New
   features target 4026 only. No system is forced to migrate. Most of the simplification
   benefit is realised here.
2. End of life for the 4024 line, controlled by operations, later, possibly per system.
   The 4024 fixes line retires only when no commissioned system needs its fixes.

**Convergence.** When 4024 retires, the 4026 line graduates to `master`, the old 4024
line is frozen and tagged, and the fixes line persists until its last consumer ends.
Steady state returns to `master` plus `stable`, 4026 only.

> Speaker notes:
> The two-trigger split is the operationally honest part. Development gets to stop adding
> features to 4024 without waiting for operations, and operations keeps its fixes line for
> as long as a commissioned system needs it. Neither blocks the other.

---

## Q&A prep

<!--
NOT FOR PROJECTION. This is the last section in the file and it will render as one
oversized slide. That is intended: read it in the markdown or print it, and delete this
section before exporting a deck you will actually put on screen.

Each entry gives the question as it will actually be asked, the honest answer, where it
is grounded in the source documents, and where the design is weak, what we would need to
decide.
-->

### Design challenges

**"Isn't this over-engineering a version problem?"**
Partly yes, and the honest answer is that the enforcement layer is the expensive part,
not the pinning. Pinning is cheap and uncontroversial. Hard-fail resolution, two schemas
and a release repo are what cost. The argument for them is that a pin nobody checks
becomes a pin that is wrong. Grounded in the decision table. If the room disagrees, the
fallback is record-first, enforce-later, which is a legitimate position.

**"Why not just pin pytmc and stop there?"**
That fixes F3, F4, F5 and most of F6 for a fraction of the cost, and it is the single
highest value change in the whole proposal. It does not fix F1 or F2, so transitive
library drift continues and two nodes still produce different builds. Reasonable question
to put back to the room: is library drift actually hurting us, or is pytmc the only real
problem? If it is only pytmc, the proposal is much larger than it needs to be.
*This one does not have a clean answer in the current design and we should be ready for it.*

**"Why a release repo rather than just recording versions in the build report?"**
The build report tells you what a build used, after the fact. It gives you no way to ask
for a known-good coherent set before you start, and no way to say "give me the same thing
that project got." The repo is what makes a stack requestable. Grounded in section 14 and
the decision table.

**"What if two projects need different pins from the same library?"**
They pin different stack releases. That is supported and expected, since each line and
channel is independently pinned. What is not defined is what happens when neither
existing stack has the combination a project needs, and who decides whether to cut a new
one. That is the open turnaround question on "New process, and a release everyone has to
attend".

**"Is 'immutable' absolute? What if a published stack turns out to be wrong?"**
The design says released artifacts are immutable and retained as long as any commissioned
system depends on them. It does not describe a yank or deprecation path. The workable
answer is a new release plus a marker on the bad one, with projects migrating explicitly,
but the design does not currently specify this.
*Gap. Worth raising ourselves rather than waiting for it.*

**"A frozen system's pinned pytmc has a security problem. Now what?"**
Nothing in the model stops you moving that project to a newer stack. The pin is a default
and a record, not a lock on the repository. The cost is the normal one: changing the
stack changes the generated output, so the system needs re-verification. That is the same
trade as any version change on a commissioned system, made visible rather than accidental.

**"Does hard-fail block an urgent field fix?"**
As written, yes. If the placeholders do not match the lockfile or the target is
incoherent, the build stops. There is no documented override.
*This is the weakest point in the design for an operations audience and we should lead
with it rather than be caught by it. Options are an explicit logged override flag, a
warn-only mode for non-deploy builds, or accepting the block. Needs a decision.*

### Cost and ownership

**"Who cuts stack releases and how often?"**
ECS owns the management repo, the same way it owns most of the libraries in it. Section
27 defines the workflow, preconditions and version bump conventions. What is undecided is
cadence, and what the turnaround is when a project needs a pin no published stack has.

**"So one person decides what goes into a stack?"**
No. Privileges differ by maintainer, as they already do across the library repos, but
cutting a release engages everyone with a library in the stack, because the release is
asserting that their library at that version is coherent with the rest of the set. That
coordination is a real recurring cost and should be presented as one. It is also
happening implicitly today, badly, in that nobody checks the combination until something
fails to compile.

**"What does this cost an engineer day to day?"**
Once it is running, less than today: they stop setting library placeholders by hand,
because the build resolves them from the lockfile. During adoption it costs more, because
they have to learn a new failure mode and a new file. Grounded in section 17, where the
stated goal is that the developer does not manually set placeholders.

**"How long until step 1 is usable?"**
Not estimated in the source material. Do not invent a number in the room. What can be
said is that step 1 is separable and does not depend on any branching change.

**"What is the migration cost for existing commissioned projects?"**
Not addressed in the source material. A commissioned system that is never rebuilt needs
nothing. A system that will be rebuilt needs a lockfile that reflects what it was
actually built with, and for older systems that information may no longer exist.
*Gap worth naming.*

### Model questions

**"Did the branch matrix really go away, or just move?"**
For most libraries it moved, into version lines and release metadata, which CI can check.
For dual-target libraries it did not go away at all: those carry four branches while both
targets are live. The claim is that four branches on two libraries is different from four
branches on ten. Concede the point rather than arguing it.

**"What if a core genuinely needs a 4026-only feature?"**
The answer is no, and the capability goes into a 4026-only library or a new library that
depends on the core. Never into the core in place. This is a real constraint on
developers and it is the price of the transitivity guarantee. Section 5.

**"What does dual-target actually require of the library?"**
That it builds against 4024 and against 4026. It meets that through its two lines rather
than through one source tree that satisfies both compilers, and each branch gates on its
own target only. The 4026 line depends on the 4026-only chain, so by transitivity it
cannot compile under 4024 and is never asked to.

**"Then what stops the two lines drifting apart?"**
Nothing mechanical, and that is deliberate rather than an oversight. They are separate
lines precisely because the code diverges once one side takes a 4026-only dependency.
Convergence is handled by the lifecycle in Appendix C, where the 4026 line eventually
graduates to `master`, not by holding the two in sync along the way.

**"Who decides a dual-target library's boundary major, and what if we choose wrong?"**
Choosing wrong is awkward rather than fatal, since the boundary is a major version
number, but it is disruptive to move once consumers have pinned across it.
common-components is already decided at 4.0.0. optics is open.

**"Is lcls-twincat-motion LTS an open-ended commitment?"**
Effectively yes. Its end of life is tied to the last 4024 consumer, which is an
operations-controlled date that does not exist yet. Being honest that this could be a
long time is better than implying it is temporary.

### Implementation

**"How much of Part II is speculative?"**
The Linux path builds on tools that exist: tc-release, pytmc, ctrlenv-pathmunge, uv and
pixi. What is expanded is tc-release gaining stack resolution at the head of its build
step. The Windows path is the speculative part.

**"What is the Windows risk?"**
Real but bounded. The claim is that Windows and Linux differ only in path resolution and
never in tool or library versions, and that Windows does not need central EPICS handling,
which simplifies it. The work not yet done is producing win-x86_64 uv venvs with
launchers and a Windows-runnable pathmunge, either reusing the bash function under
git-bash or msys, or porting it.

**"What if ctrlenv-pathmunge is not viable on Windows?"**
Not answered in the source material. The requirement is narrow, since it only needs to
put a directory on PATH and resolve the right architecture, so a PowerShell or batch port
is plausible. Saying "we would port it" is honest. Saying "it will definitely work" is
not.
