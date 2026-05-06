import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DemoModeBanner } from "@/components/DemoModeBanner";

function mockFetchOnce(body: any, ok = true) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    json: async () => body,
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("DemoModeBanner", () => {
  beforeEach(() => {
    sessionStorage.clear();
    delete (process.env as any).NEXT_PUBLIC_DEMO_MODE;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders banner when /api/health returns demo_mode true", async () => {
    mockFetchOnce({ demo_mode: true });
    render(<DemoModeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId("demo-mode-banner")).toBeInTheDocument();
    });
    expect(screen.getByText(/Demo mode/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /demo guide/i })).toHaveAttribute(
      "href",
      "https://github.com/miticojo-labs/knowledgeforge/blob/main/demo/README.md"
    );
  });

  it("renders nothing when demo_mode is false", async () => {
    mockFetchOnce({ demo_mode: false });
    const { container } = render(<DemoModeBanner />);
    // wait a tick for the effect microtask
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId("demo-mode-banner")).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when fetch fails", async () => {
    const fn = vi.fn().mockRejectedValue(new Error("nope"));
    vi.stubGlobal("fetch", fn);
    render(<DemoModeBanner />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId("demo-mode-banner")).toBeNull();
  });

  it("can be dismissed and persists in sessionStorage", async () => {
    mockFetchOnce({ demo_mode: true });
    const user = userEvent.setup();
    render(<DemoModeBanner />);
    const banner = await screen.findByTestId("demo-mode-banner");
    expect(banner).toBeInTheDocument();

    const dismissBtn = screen.getByRole("button", { name: /dismiss/i });
    await user.click(dismissBtn);

    expect(screen.queryByTestId("demo-mode-banner")).toBeNull();
    expect(sessionStorage.getItem("kf-demo-banner-dismissed")).toBe("1");
  });

  it("does not re-render banner when previously dismissed in session", async () => {
    sessionStorage.setItem("kf-demo-banner-dismissed", "1");
    mockFetchOnce({ demo_mode: true });
    render(<DemoModeBanner />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByTestId("demo-mode-banner")).toBeNull();
  });
});
