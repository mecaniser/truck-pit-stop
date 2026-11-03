import '@testing-library/jest-dom'

// jsdom has no media-query engine. Supply the browser API so each responsive
// test can override its result, without relying on spyOn creating missing APIs.
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {},
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false },
  }),
})
