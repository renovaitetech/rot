# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Tasks

Project tasks are stored in `.claude/tasks/` as Markdown files.
Each file is named by ticket ID (e.g. `ROT-13.md`) and contains
the task description, steps, and current status.

Before starting work, read the relevant task file to understand
the scope and track progress by updating the checkboxes.

## Commit Rules

- Use Conventional Commits format: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`
- Include scope in parentheses for the module: `feat(parsons-gym): add adaptive hints`
- **NEVER add Co-Authored-By lines** — strictly prohibited. No co-authorship, no attribution lines, no Signed-off-by. Commit messages must contain only the description and summary.
- **Never push** — commits stay local until the user explicitly requests a push.
