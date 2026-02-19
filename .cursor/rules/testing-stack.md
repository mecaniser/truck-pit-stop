# Testing Stack & Conventions

alwaysApply: true

## Backend (Python — FastAPI)

- **Runner**: pytest + pytest-asyncio
- **Test location**: `backend/tests/test_*.py`
- **Fixtures**: `backend/tests/conftest.py`
- **DB in tests**: in-memory SQLite via `aiosqlite` with `StaticPool` — never touch the real Postgres
- **Mocking**: `monkeypatch` for function/module patching, `FakeRedis` class in conftest for Redis, mock external services (Stripe, Twilio, Resend, Cloudinary) — never make real HTTP calls in tests
- **Integration tests**: `httpx.AsyncClient` with `httpx.ASGITransport(app=app)` against the FastAPI app, override `get_db` dependency
- **Coverage**: `pytest-cov`
- **Run**: `cd backend && python -m pytest`
- **Run with coverage**: `cd backend && python -m pytest --cov=app --cov-report=term-missing`

### Naming

- Test files: `test_<module_or_feature>.py`
- Test functions: `test_<what_it_does>` — describe behavior, not implementation
- Fixtures: descriptive nouns (`fake_redis`, `client`, `auth_headers`)

### Patterns

- Use `@pytest.mark.asyncio` for all async tests
- Use `pytest.importorskip("aiosqlite")` when test needs SQLite async engine
- Prefer `monkeypatch.setattr` over `unittest.mock.patch`
- Each integration test gets a fresh in-memory DB via fixture

## Frontend (TypeScript — React + Vite)

- **Runner**: Vitest (configured in `vite.config.ts`)
- **Environment**: jsdom
- **Component testing**: @testing-library/react + @testing-library/jest-dom + @testing-library/user-event
- **API mocking**: MSW (Mock Service Worker) v2
- **Coverage**: @vitest/coverage-v8
- **Run**: `cd frontend && npm test`
- **Run with coverage**: `cd frontend && npm run test:coverage`

### File locations

- Utility tests: `src/__tests__/<util>.test.ts`
- Component tests: colocated `src/features/<feature>/__tests__/<Component>.test.tsx`
- MSW handlers: `src/__tests__/mocks/handlers.ts`
- MSW server setup: `src/__tests__/mocks/server.ts`

### Naming

- Test files: `<module>.test.ts` or `<Component>.test.tsx`
- Test blocks: `describe('<function or component>')` + `it('does specific behavior')`

### Patterns

- Test user-visible behavior, not implementation details
- Use `screen.getByRole`, `screen.getByText` over `getByTestId`
- Use `userEvent` over `fireEvent`
- Setup MSW handlers for API-dependent component tests
- Reset Zustand stores between tests

## E2E (Playwright)

- **Location**: `e2e/`
- **Config**: `e2e/playwright.config.ts`
- **Test files**: `e2e/tests/*.spec.ts`
- **Run**: `cd e2e && npx playwright test`
- **Target**: `http://localhost:5173` with `webServer` auto-start in config
- **Browser**: Chromium only for speed (expand later)
