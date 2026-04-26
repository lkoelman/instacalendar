
# Rules

## Test-Driven Development (TDD) Workflow

**Strong preference for TDD**; Agent should guide this workflow proactively.

### TDD Steps

1. **Write failing test first** (before any implementation)
   - Add test case to appropriate test file in package
   - Run pytest to confirm test fails with expected error
   - Commit the failing test (optional but recommended for clarity)

2. **Implement minimal code to pass test**
   - Write only enough code to make the test pass
   - Avoid over-engineering or extra features

3. **Run tests again**
   - pytest should now pass
   - If not, iterate on implementation

4. **Refactor if needed**
   - Keep tests passing while improving code
   - Run pytest after each refactor

5. **Repeat for next behavior**

**When TDD is impractical:**
- Document why (e.g., characterization test requires understanding existing behavior first)
- Use characterization tests: write tests that capture current behavior, then refactor safely
- Still aim for test coverage of new/changed code

**Test coverage expectations:**
- New behavior: must have tests
- Bug fixes: add regression test that would have caught the bug
- Refactors: existing tests must still pass; add tests if coverage gaps exist


## Editing and Change Discipline

### Hard Rules

1. **Read before writing**: NEVER propose changes to code you haven't read. Use Read tool first.
2. **No surprise changes**: Only make changes directly requested or clearly necessary for the task.
3. **Smallest scope first**: Build/test single modules or packages before workspace-wide operations.
4. **Preserve documentation comments**: Keep existing documentation comments when editing code. If a comment becomes inaccurate, rewrite it to match the new behavior; do not remove documentation comments without replacing them with accurate documentation.

### What NOT to do (unless explicitly requested)

- Add features beyond what was asked
- Refactor surrounding code "while you're there"
- Add docstrings, comments, or type annotations to unchanged code
- Add error handling for scenarios that can't happen
- Create helpers/utilities for one-time operations
- Design for hypothetical future requirements
- Add backwards-compatibility hacks (e.g., renaming unused `_vars`, re-exporting types, `// removed` comments)
- Delete unused code without confirming it's truly unused

### Keep it simple

- Three similar lines of code > premature abstraction
- Only validate at system boundaries (user input, external APIs), not internal code
- Trust framework guarantees
- Don't use feature flags or backwards-compatibility shims when you can just change the code

### Read Documentation

Before making changes, read ARCHITECTURE.md and README.md files for the components you are working on.

## Git Conventions

**Commit workflow:**
- Agent proposes commit messages; user retains final edit/approval
- **NEVER commit, push, or run destructive git commands without explicit user permission**
- **NEVER update git config without explicit user permission**
- **NEVER run force push, hard reset, or other destructive git operations without explicit user approval**
- **NEVER skip hooks** (--no-verify, --no-gpg-sign) unless explicitly requested


## Documentation Maintenance

**Docs must stay in sync with code changes.**

When modifying code, check if these docs need updates:
- README.md - Overview, getting started, installation
- Component-specific documentation (e.g., `<component>/**/{README.md,ARCHITECTURE.md}`)

**When to update docs:**
- New features: add how-to guide or update relevant README
- API changes: update module README and architecture docs
- Build/test changes: update this AGENTS.md or module-specific docs
- Deprecations: mark as deprecated in docs, add migration guide if needed

**Writing docstrings**
Only write docstrings for non-trivial components.
Be concise, specific, and value dense. Write so that a new developer can understand the code and easily tie it back to the system architecture, i.e. to its role in the larger system context.
Docstrings should expres intent, role in system context, and side effects.
Class docstrings should document fields and their intent.

**Before committing**, ask: "Did I update the docs?"

# MEMORY

(This section is agent managed)

- [2026-04-26] Optional config additions should preserve non-interactive `auth` flows; add CLI regression coverage before introducing new prompts.
- [2026-04-26] Configured OpenRouter model IDs such as `openai/gpt-4o-mini` are OpenRouter catalog IDs; LiteLLM calls should prefix them as `openrouter/...` unless they already start with `openrouter/`.

## Memory Management

- Remember the # MEMORY section of this file before taking actions to avoid repeating past mistakes.
- After completing a task, if you encounter a non-obvious codebase quirk or a problem that took more than one attempt to fix, immediately update the # MEMORY section with a concise lesson.
- Always prefix memories with [YYYY-MM-DD]
- Self-Pruning: If a memory entry is no longer accurate due to code changes, remove or update it.
- Compaction: Keep the # MEMORY section under 50 lines to manage context efficiency. If memories become redundant or have repetitions that can be generalized, compact the memories by merging similar lessons into a single rule.

**After finishing a task**, ask: "Did I update # MEMORY?"

## Python Development

- use `uv` for package and dependency managenent, and for running python code
