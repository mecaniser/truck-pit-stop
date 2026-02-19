# Test-Driven Development (TDD)

alwaysApply: true

## Iron Law

NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.

Code written before its test? Delete it. Start over. No exceptions.

- Don't keep it as "reference"
- Don't "adapt" it while writing tests
- Delete means delete

## RED-GREEN-REFACTOR Cycle

Every change follows this cycle. No shortcuts.

### RED — Write One Failing Test

- One behavior per test
- Clear name describing the behavior
- Use real code paths (mocks only when unavoidable — external APIs, time, randomness)
- Run the test. Confirm it **fails** for the expected reason (missing feature, not a typo or import error)

### GREEN — Minimal Code to Pass

- Write the simplest code that makes the test pass
- Don't add features beyond what the test requires
- Don't refactor yet
- Run all tests. Confirm **all green**, output pristine (no warnings, no errors)

### REFACTOR — Clean Up

- Only after green
- Remove duplication, improve names, extract helpers
- Keep tests green throughout
- Don't add new behavior during refactor

### Repeat

Next failing test for the next behavior.

## Bug Fixes

Every bug fix starts with a failing test that reproduces the bug. No exceptions.

## Red Flags — Stop and Restart

If any of these happen, delete the code and start over with TDD:

- Production code written before its test
- Test passes immediately on first run (you're testing existing behavior, not new)
- Can't explain why the test failed
- Rationalizing "too simple to test", "I'll test after", "just this once"
- "I already manually tested it"
- "Keep as reference and write tests around it"

## Good Tests

- **Minimal**: One assertion per behavior. "and" in the name? Split it.
- **Clear**: Name describes what should happen, not implementation details.
- **Real**: Test real behavior through public APIs, not internal implementation.
- **Independent**: No test depends on another test's state or execution order.

## When Stuck

| Problem | Solution |
|---------|----------|
| Don't know how to test it | Write the API you wish existed. Write the assertion first. |
| Test too complicated | Design too complicated. Simplify the interface. |
| Must mock everything | Code too coupled. Use dependency injection. |
| Test setup is huge | Extract fixtures/helpers. Still complex? Simplify design. |
