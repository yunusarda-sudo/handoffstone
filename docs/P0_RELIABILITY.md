# P0 reliability contract

This patch hardens the existing stdlib/JSONL library. It does not add a memory
service, MCP, SQLite, a Codex integration, live evidence verification, or a real
agent benchmark. Valid canonical JSON and compact wire v2 retain their shape.

## Verification is an explicit attestation

A canonical record with `status=VERIFIED` must carry at least one evidence
reference with `verified=True` (a real boolean), a non-blank id and locator, and
one of the existing kinds: file, commit, test, URL, conversation, or memory.
An empty or redacted locator cannot attest a claim. Use `USER_ASSERTED`,
`AGENT_INFERRED`, or `UNVERIFIED` when the source has not been checked.

```python
evidence = EvidenceReference(
    id="acceptance-run-42", kind="test", locator="results/acceptance-42.json",
    verified=True,
)
decision = capture_decision(
    "project-A", "codex", "Keep JSONL", "Keep local JSONL", "No service needed",
    evidence_refs=[evidence], status=VerificationStatus.VERIFIED,
)
```

The caller is responsible for having checked that reference. The library does
not open arbitrary files/URLs, run tests, authenticate the caller, or infer that
the referenced result is current. A fabricated locator plus an attestation can
still be false. Compact history entries carry inherited historical status;
they are not independent canonical evidence records.

Checks run at construction, record/package import, serialization and persistence.
Mutable records and evidence are rechecked at export/save; changing an object
after construction cannot bypass those boundaries. Raw nested canonical records
in snapshots/handoffs are checked too.

## Sensitive content: reject rather than silently rewrite

Recognized secrets/PII and nonempty sensitive metadata keys are rejected with
`UnsafeContentError`, including nested metadata, snapshot/handoff bodies, dictionary
keys, evidence fields, package questions and uncertainty. JSON, wire and Markdown
exports share this policy. Direct dataclass construction, public capture helpers,
manual input and consumer-import records cannot bypass it.

Existing `sanitize_for_transfer()` remains an explicit redaction helper. Consumer
export extraction already uses it. Inspect sanitized data before capturing it;
`[REDACTED]` and location-only metadata such as `secret_path` are accepted.
Never put a real credential in an evidence locator.

Detection uses patterns and known field names. It is not a universal secret
detector: unknown credential forms or arbitrary passwords in ordinary prose may
escape it, and ordinary text that resembles credentials can be rejected. Encoded
or obfuscated content is not decoded. The Python object is not a sandbox; code
that bypasses the library and writes files itself is outside this boundary.

## Scope and file access

`validate_scope()` accepts `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`. Empty scopes, separators,
absolute/parent paths, leading dots and other characters raise `InvalidScopeError`
before filesystem access. `save_record(record, scope=...)` requires an exact match
with `record.project_scope`. Loading a foreign-scope record is corruption.

Normal scope filenames stay unchanged. Names containing spaces, Unicode or `:`
that older versions accepted now require an explicit caller-side remapping;
there is no automatic rename/migration or global empty-scope query.

Store files must be regular files. Opens use no-follow and nonblocking flags;
symlinks and FIFOs are refused. New store directories/files request modes 0700/0600.
The configured store root is trusted, and this is not protection against an
attacker with control of the process or its parent directories. On systems
without `O_NOFOLLOW`, protected persistence fails explicitly rather than silently
using a weaker open. macOS is tested; Windows/Linux execution is not certified
by these tests.

## Writes: return True or raise

`save_record()` keeps its successful `True` return. I/O, flush or fsync failures
raise `StoreWriteError`. Capture/checkpoint/handoff helpers propagate this error;
returning a newly allocated object is not a substitute for persistence success.

The implementation flushes and fsyncs an individual append. A failed write/sync
may already have left bytes on disk. Failure means persistence is unconfirmed,
not that a rollback occurred; do not retry blindly. Multi-record supersession is
not transactional, concurrent updates are not resolved, deduplication is not
implemented, and sudden power loss recovery is not certified. Directory entries
are not fsynced as a separate transaction.

## Reads: empty, corrupt, unavailable are distinct

| Condition | Public result |
| --- | --- |
| Missing file or healthy empty/whitespace-only file | `[]` |
| Healthy store | Existing list/latest-version-per-id behavior |
| Malformed/unsafe JSON, unsupported record, unbacked VERIFIED or foreign scope | `StoreCorruptionError` with `line_number` |
| Open/read failure or non-regular file | `StoreUnavailableError` |
| Invalid requested scope | `InvalidScopeError` |

Corrupt records are not silently skipped, even when filtering for another kind.
No successful partial list is returned. `get_latest_record()` propagates these
errors; it only returns `None` for a genuinely empty valid selection. Invalid
UTF-8 is corruption; its reported line is the current decoding position, which
can be approximate because Python buffers text reads. Existing files are not
repaired, rewritten or deleted on read.

Old unsafe stores will now fail closed. Back up and inspect them deliberately
before repair; do not drop lines or relabel all records as verified to get past
the exception. Error messages omit payload values. The errors distinguish store
state without claiming recovery has been implemented.

## Verification and compatibility

```sh
python3 -B test_handoffstone.py
python3 -B test_bench_handoffstone.py
python3 -B -m unittest -v test_reliability
python3 -B handoffstone.py
python3 -B bench_handoffstone.py --json --out ''
python3 -B bench_handoffstone.py --profile --json --out ''
```

The original core tests retain their assertions; previously unbacked VERIFIED
fixtures now supply explicit synthetic attestations. Benchmark constraints and
smoke examples without evidence are `USER_ASSERTED`. Benchmark negative controls
are unchanged. An additional acceptance check constructs full/wire/JSONL fixtures
with the untouched pre-P0 module and consumes them through the new public APIs;
the test suite also reads a real checkpoint from a fresh Python process.

These are local library checks, not proof of real-agent task completion,
production readiness, crash resilience, or superiority to Basic Memory. The
next bounded experiment is specified in [the adapter design](REAL_AGENT_ADAPTER_DESIGN.md).
