# Tekne

A systemd-free desktop respin of Devuan Excalibur: herbstluftwm on X11, a gum TUI
installer, built with live-build. This is a spec-driven project, so the docs are
the source of truth.

These instructions are for any coding agent working in this repository (Claude Code
reads them through CLAUDE.md, other agents read this file directly).

## Read first
- [SPEC.md](SPEC.md): what we're building, the phases, and the acceptance criteria.
- [DECISIONS.md](DECISIONS.md): every decision, with a permanent `DEC-nnn` ID, a status (Decided, Proposed, Open, or Superseded), rationale, and history.
- [docs/desktop-stack.md](docs/desktop-stack.md) and [docs/installer.md](docs/installer.md): detailed designs.

`devuan-custom-distro-spec.md` is the original rough draft. It's been superseded by the files above. Don't treat it as current.

## Working rules
- **Keep the docs in sync.** When a decision changes, update DECISIONS.md (edit the entry and add a dated History line) and every doc that references it, in the same commit. Cross-check SPEC.md, docs/*, and DECISIONS.md for consistency.
- **Don't silently change Decided entries.** Propose the change to the maintainer first. Proposed entries are safe defaults to build on, but flag them when they matter. Never renumber or reuse a `DEC-nnn` ID.
- **Reserve a new `DEC-nnn` ID on `master` before writing the decision.** Work happens on more than one machine, so commit a one-line Proposed stub to `master` first, then fill it in on your branch. Two branches that each add the next free ID would otherwise collide, and IDs can't be renumbered.
- **Work phase by phase** (SPEC.md §7). A phase is done only when all its ✅ criteria pass. Prefer small commits per phase step.
- **Before adding any package,** check that it exists in Devuan Excalibur and passes the no-systemd rule (SPEC.md §4).
- **Pin every external build input** by checksum or container digest.
- **Third-party APT repositories** are allowed only under DEC-026: a pinned key, a `.sources` entry shipped in `tekne-apt-sources`, and APT pins limited to specific packages.
- **Don't add loose config to `includes.chroot/`** unless it's live-session-only. Anything an installed system keeps belongs in a `packages/tekne-*` package.
- The maintainer may edit docs directly between sessions. Re-read files rather than relying on memory of earlier sessions.

## Working with the maintainer
- **The maintainer runs root and push steps.** `sudo` needs their password and `git push` needs their SSH passphrase. Prepare the commit or command, give one command per block, and check the result afterwards through files, `git status`, `out/build.log`, `dpkg-query` or `gh`.
- **Commit locally, one commit per phase step,** with the docs updated in the same commit.
- **CI before `master`.** The maintainer pushes a test branch (`git push origin HEAD:refs/heads/phaseNN`), the agent runs `gh workflow run build.yml --ref phaseNN` and fixes what fails, and only then is `master` pushed. Delete the branch afterwards.
- **Iterate locally.** When a QEMU test fails, the maintainer runs `sudo scripts/build.sh` and the agent reruns the single test with `--keep`, so a fix can be tried on the kept VM disk in minutes.
- **Questions about Decided entries** go to the maintainer as numbered questions, each with a recommendation.

## Safety on development machines
- **The development machines run Tekne themselves** and are the maintainer's daily systems. Never run `tekne-install`, partitioning, formatting, or anything else destructive on the host. Test in QEMU with virtual disks (`scripts/test-in-qemu.sh`, `tests/smoke/*`).
- **Update a host only with packages:** `scripts/build.sh --packages-only`, then `apt install ./out/packages/...` (DEC-006, DEC-032).
- **Identify disks by model or serial** (`lsblk -o NAME,MODEL,SERIAL`), never by `nvme0n1`-style names: they can swap between boots, and a machine may hold disks that aren't Tekne's.
- **Terminal output can hold secrets.** Don't read the maintainer's terminals to check steps that handle keys or passphrases, and never print a secret to check it (DEC-040's history records a signing subkey exposed this way). Check through git, files and `gh` instead.
- **Never commit raw kernel logs or network dumps.** They contain hardware serials and Wi-Fi BSSIDs. Summarise the relevant lines instead.
