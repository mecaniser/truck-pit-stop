import '@testing-library/jest-dom'

// jsdom has no layout engine; anchored workspace menus still subscribe to element size.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}
