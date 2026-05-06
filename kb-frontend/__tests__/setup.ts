import "@testing-library/jest-dom/vitest";

// Polyfills for jsdom required by Radix UI primitives.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverPolyfill {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
    ResizeObserverPolyfill;
}

if (typeof (globalThis as { EventSource?: unknown }).EventSource === "undefined") {
  // jsdom doesn't ship EventSource. Provide an inert stub so components that
  // open SSE connections during mount don't blow up the suite.
  class EventSourceStub {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    readonly CONNECTING = 0;
    readonly OPEN = 1;
    readonly CLOSED = 2;
    readyState = 0;
    url = "";
    withCredentials = false;
    onopen: ((ev: Event) => void) | null = null;
    onmessage: ((ev: MessageEvent) => void) | null = null;
    onerror: ((ev: Event) => void) | null = null;
    constructor(url: string) {
      this.url = url;
    }
    addEventListener() {}
    removeEventListener() {}
    dispatchEvent() {
      return true;
    }
    close() {
      this.readyState = 2;
    }
  }
  (globalThis as unknown as { EventSource: unknown }).EventSource = EventSourceStub;
}

if (typeof window !== "undefined" && !window.HTMLElement.prototype.hasPointerCapture) {
  // Radix uses pointer capture APIs that jsdom does not implement.
  const proto = window.HTMLElement.prototype as unknown as Record<string, unknown>;
  proto.hasPointerCapture = () => false;
  proto.releasePointerCapture = () => {};
  proto.setPointerCapture = () => {};
  proto.scrollIntoView = () => {};
}
