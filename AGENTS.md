# Agent Guidelines

- Keep the codebase minimal and readable; prefer straightforward functions over complex abstractions.
- Include concise comments explaining each function's intent and any non-obvious logic.
- Favor small, testable increments and ensure new functionality is covered by automated tests when feasible.
- Use Python 3 standard tooling; dependencies should be lightweight and justified.
- When adding CLI entry points, provide clear default paths that work with the existing `dummy_data` folder.
- Prefer CSV for lightweight outputs unless a stronger need arises.
- Documentation in code should be bilingual-friendly where possible (English comments are acceptable).
