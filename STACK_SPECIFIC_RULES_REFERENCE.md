# STACK_SPECIFIC_RULES_REFERENCE.md

Version: 1.0 — 2026-04-24

Status: optional manual appendix. Include only the relevant sections in a custom-instructions preprompt for projects that use these stacks or conventions.

## Using Community Rule Packs
- Use collections such as `awesome-cursorrules` as raw material, not as drop-in global preprompts.
- Import only rules that match the current project stack, are non-obvious, and can be verified through code search, tests, or linters.
- Prefer rules that point to local commands and canonical project files over generic style advice.
- Remove rules already enforced by formatters, linters, typecheckers, or framework defaults.
- Keep imported stack rules in this reference file or project-local instructions, not in the global always-on preprompt.

## TypeScript Defaults
- Prefer explicit types, type guards, and discriminated unions.
- Avoid `any`, unsafe assertions, nested ternaries, and non-trivial inline render callbacks unless required by local conventions.
- Define schemas near related types when parsing external or user-controlled input.
- Use existing project validation utilities before adding new validation logic.

## React Defaults
- Use effects only for true side effects; prefer derived values, event handlers, or state updates for local UI logic.
- Check `window` and `document` availability before DOM access in SSR-capable code.
- Move large render chunks into focused components when it improves readability or testability.
- Name handlers by intent, such as `handleSaveClick`, rather than leaving complex inline callbacks in render paths.

## UI and Styling Defaults
- Search the project UI kit before creating new components.
- Prefer project layout primitives over custom wrappers when equivalent primitives exist.
- Use design tokens or CSS custom properties for spacing, radii, colors, and layout constants.
- Follow the project naming convention for CSS classes and files.
- Avoid inline layout styles unless the project explicitly uses them.

## Internationalization
- Move user-facing strings into the project i18n system when one exists.
- Follow local formatting conventions for labels, messages, dates, numbers, and plurals.
- Import i18n utilities according to local project patterns.

## Tests and E2E
- Add or update tests for changed logic when practical.
- Keep mocks in the project’s dedicated mock locations.
- In E2E suites with page objects or fixtures, expose locators through class methods or helpers rather than duplicating raw selectors.
- Run focused tests first, then broader checks when shared behavior or integration surfaces changed.

## Complex Component Refactors
- For components with multiple modes, prefer a delegator that routes to mode-specific components when it reduces branching.
- Extract shared logic to utilities only when multiple modes actually reuse it.
- Preserve non-layout CSS behavior while migrating layout to UI primitives.
- Avoid repo-wide pattern migrations unless explicitly requested and verified with broad checks.
