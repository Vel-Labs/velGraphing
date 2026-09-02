# VelGraphing Agent Guide

## Mission

Improve repository navigation while keeping source authoritative.

## Start Here

1. Read `README.md` and `docs/INDEX.md`.
2. Read the nearest relevant skill under `plugins/graph-engineering/skills/`.
3. Keep changes inside this repository unless the user grants more scope.

## Rules

- Prefer the smallest source-bound implementation.
- Keep generated runtime files aligned with canonical source.
- Do not treat graph output as proof of correctness or authority.
- Keep direct source fallback for incomplete or high-risk evidence.
- Do not add a database, daemon, hook, crawler, scheduler, provider, or
  cross-project write without explicit authority.
- Do not publish, deploy, or change a consumer repository without explicit
  authority.
- Test changed behavior and package parity before completion.
- Report files changed, validation, and remaining risks.
