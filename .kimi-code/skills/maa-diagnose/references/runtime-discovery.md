# Diagnostic runtime discovery and compatibility

The diagnostic runtime is an external project that is not vendored, installed, or updated by Everything Maa. This skill only discovers and drives whatever the user already has.

## Supported runtime

| Field | Value |
| --- | --- |
| Upstream | [Windsland52/MaaEvidenceKit](https://github.com/Windsland52/MaaEvidenceKit), renamed from `MaaDiagnosticExpert` |
| npm package | `maa-evidence-kit` |
| Executable | `maa-evidence` |
| Verified version | `0.3.2` |
| Supported range | `>=0.3.0 <0.4.0` verified; `0.2.x` and `0.1.x` are legacy and must be re-discovered before use |
| Host requirement | Node.js 24 or later |
| Structured schema ids | `maa-evidence/v1`, `maa-evidence-batch/v1`, `maa-evidence-profile/v1` |
| Local MCP server | none shipped at `0.3.x` |

The rename is the reason discovery is mandatory. The command names quoted in older Everything Maa planning notes, `describe-runtime` and `run-diagnostic-pipeline`, do not exist in `0.3.x`. Their responsibilities map onto the surface below.

## Authoritative Skill handoff

Before using the table below, run the locator in `scripts/find-maa-evidence-skill.mjs` and follow its result:

- `found`: read `skillPath` and the references it requires for the current diagnosis completely;
- `package-without-skill`: read the upstream Skill at the release matching `packageVersion`;
- `not-found`: read the latest formal upstream Release, falling back to the default branch only with an unpinned-guidance warning.

Standalone installed skills take precedence over package copies, and package copies take precedence over GitHub. This instruction precedence is separate from the runtime-surface precedence below. If the authoritative Skill cannot be loaded, do not compose commands from this reference alone.

## Discovery sequence

Run these before composing any analysis command, and treat their output as the authoritative catalog:

```bash
maa-evidence --version
maa-evidence --help
```

Record, as evidence:

- the reported package version;
- the subcommand list actually printed by help;
- the flags the intended subcommand accepts;
- the `schema` id of the first structured result.

If a subcommand or flag named below is absent from the discovered help output, it does not exist in the installed build. Use what help reports, not this table.

| Responsibility | Surface verified at `0.3.2` |
| --- | --- |
| Describe the runtime | `--version` and `--help` |
| Cross-tool diagnostic pipeline | `inspect PATH` |
| Log-only adapter (MaaLogAnalyzer) | `mla inspect PATH` |
| Static project adapter (maa-support-extension packages) | `mse inspect PATH`, `mse resolve PATH` |
| Local corpus inventory | `repo-docs PATH` |
| Evidence lookup on a saved result | `view`, `window`, `search`, `batch` |
| Structured output | `--format json` with `--output FILE` |
| Bounded run window | `--from` and `--to` on `mla inspect` |
| Scoped static expansion | `--task`, `--controller`, `--resource`, `--depth`, `--no-referencers` |
| Optional local timing sidecar | `--profile FILE` |
| Upload-capable commands to avoid | `feedback`, `telemetry enable` |

`--profile FILE` at `0.3.x` writes a local stage-timing sidecar. It is not a diagnostic profile selector. Only treat an option as a diagnostic profile when discovery proves the installed build defines one.

## Precedence and fallback policy

Apply exactly one policy, in this order, and record which surface was used:

1. **Local MCP surface.** Use it only when the installed runtime advertises an MCP server and the harness already has that server configured. `0.3.x` ships none, so this step normally falls through.
2. **Packaged CLI on `PATH`.** Resolve `maa-evidence` and confirm it with `--version`.
3. **User-supplied local checkout.** Use the built entry point the user pointed at, for example `node dist/cli/main.js`, only when the user named that checkout.

Do not mix surfaces inside one diagnosis, and do not fall back to a surface the user did not authorize. Never install, build, or upgrade the runtime to reach a later step.

## Failing safely

| Condition | Result |
| --- | --- |
| No surface resolves | `status: error`, `failure_owner: user`, `stop_reason: diagnostic-runtime-unavailable` |
| Version below the supported range | `status: warning`, report the discovered version, and either stop or continue only with commands the discovered help confirms |
| Version above the supported range | `status: warning`, continue from discovered help only, and record the untested version in `findings` |
| Discovered schema id is unknown | `status: error`, `failure_owner: user`, `stop_reason: diagnostic-contract-unsupported`; do not guess field meanings |
| Host Node.js is too old | `status: error`, `failure_owner: user`, `stop_reason: diagnostic-runtime-host-unsupported` |
| Command exits non-zero | Treat as a tool failure, keep stderr as evidence, and do not present it as a project defect |

In every failing case, report what would unblock the diagnosis as a `next_actions` entry for the user, and keep the original failure that triggered the request unresolved rather than guessing an owner.

## When the contract changes

The upstream contract is expected to move. Handle a change without editing this skill first:

- Re-run discovery every session; never cache a command catalog across sessions.
- Prefer the envelope's own `schema` id over the package version when deciding whether output is readable.
- If a field this skill relies on is missing, degrade to what is present, mark the gap in `findings`, and lower `status` to `warning`.
- If the structured envelope cannot be parsed at all, stop with `stop_reason: diagnostic-contract-unsupported` rather than falling back to the human-readable renderer.
- Raise a repository change only after discovery confirms a stable new surface, and update the verified version in this table together with `integrations/catalog.json` and `THIRD_PARTY_NOTICES.md`.

## Side effects to suppress

The runtime has opt-out behavior that would otherwise mutate the environment or leave the machine:

- Set `MAA_EVIDENCE_AUTO_UPDATE=0` for every invocation. Self-update installs packages, which this skill is not allowed to do.
- Check `telemetry status` before a first run and report it. Do not enable telemetry, and do not disable a setting the user chose.
- Never run `feedback`; it uploads material and requires interactive confirmation.
- Write `--output` results to a scratch path outside the target project, and report the path in `artifacts`.
