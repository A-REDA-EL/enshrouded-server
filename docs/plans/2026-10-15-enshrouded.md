# Enshrouded Server Implementation Plan

**Goal:** A repeatable Docker Compose deployment for a private Enshrouded server.

**Architecture:** Pinned community Proton runtime, persistent bind mount, an
isolated download service and host-side locked maintenance commands. No Docker
socket is mounted into containers.

**Tech Stack:** Docker Engine, Compose v2, Python 3.10+, systemd on Linux x86-64.

1. Write behavior tests for private configuration, query readiness, backup
   preservation, archive rejection, restart-on-backup-error and update failure.
   Run them and confirm failure before implementation.
2. Add Compose, example environment, query probe and management command. Run
   the behavior tests and resolve failures.
3. Add daily backup units and a runbook with researched primary sources.
4. Validate Compose using the installed Docker CLI, run the test suite, exercise
   setup/backup/restore in temporary directories and inspect the final files.

Execute in this session. The workspace is empty and is not a Git repository;
there is no existing branch to isolate or commit.
