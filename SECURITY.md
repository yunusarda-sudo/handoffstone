# Security Policy

## Supported versions

| Version   | Supported |
| --------- | --------- |
| 0.1.x-alpha | Yes     |

`handoffstone` is pre-release. Security fixes land on `main` and ship in the
next alpha tag.

## What this project stores

The library is local-first and dependency-free. By default it writes JSONL under
`~/.handoffstone` (override with `HANDOFFSTONE_HOME`). Do not put secrets, API
keys, tokens, or passwords into records. Prefer recording *where* a secret lives,
not the secret itself.

## Scope and store hardening

- A project `scope` is a single filename component. Empty names, `.`, `..`, path
  separators, and NUL are rejected.
- Context store paths that are symlinks are refused.
- New store files are created with mode `0600` on POSIX.

Concurrent replacement of a store file and multi-writer transaction safety are
out of scope for the current alpha. Do not point `HANDOFFSTONE_HOME` at a shared
or untrusted directory.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Email the maintainer through the address on the GitHub profile for
[yunusarda-sudo](https://github.com/yunusarda-sudo), and include:

1. A short description of the issue and impact.
2. Steps to reproduce, or a minimal script against the current `main`.
3. Affected version or commit SHA if known.

You should hear back within a few days. After a fix ships, we will credit you in
the changelog if you want that.
