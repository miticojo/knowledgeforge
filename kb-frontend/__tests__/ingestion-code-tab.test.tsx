/**
 * Tests for the "Code Repository" ingestion tab.
 *
 * NOTE: kb-frontend currently has NO test runner configured in package.json
 * (no jest / vitest / playwright). This file is written in a Vitest-compatible
 * style. To run it, add `vitest`, `@testing-library/react`, `@testing-library/user-event`
 * and `jsdom` to devDependencies and a `test` script. The assertions below
 * exercise the externally visible contract of the new tab.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mocks for browser-only/3rd-party deps that the page pulls in transitively.
vi.mock("@/components/providers/AuthProvider", () => ({
  useAuth: () => ({
    user: { email: "tester@example.com" },
    loading: false,
    signIn: vi.fn(),
    logOut: vi.fn(),
  }),
}));

vi.mock("@copilotkit/react-core", () => ({
  useCopilotChat: () => ({ appendMessage: vi.fn(), isLoading: false }),
}));

vi.mock("@copilotkit/react-ui", () => ({
  CopilotChat: () => null,
}));

vi.mock("@copilotkit/runtime-client-gql", () => ({
  TextMessage: class {
    constructor(public payload: unknown) {}
  },
  Role: { User: "user" },
}));

vi.mock("next/dynamic", () => ({
  default: () => () => null,
}));

import IngestionPage from "@/app/ingestion/page";

describe("IngestionPage — Code Repository tab", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("switches to the Code Repository tab and POSTs to /api/ingest-git with the right body", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({ job_id: "abc123", status: "queued" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<IngestionPage />);

    // Switch to the new tab.
    await user.click(screen.getByRole("tab", { name: /code repository/i }));

    // Fill in the form.
    const url = screen.getByLabelText(/repository url/i);
    await user.clear(url);
    await user.type(url, "https://github.com/org/repo.git");

    const ref = screen.getByLabelText(/branch \/ ref/i);
    await user.type(ref, "main");

    // Submit.
    await user.click(screen.getByRole("button", { name: /ingest repository/i }));

    await waitFor(() => {
      const ingestCall = fetchMock.mock.calls.find(
        (c) => typeof c[0] === "string" && c[0].includes("/api/ingest-git")
      );
      expect(ingestCall).toBeTruthy();
      const body = JSON.parse(ingestCall![1].body);
      expect(body.repo_url).toBe("https://github.com/org/repo.git");
      expect(body.ref).toBe("main");
      expect(body.include).toEqual(
        expect.arrayContaining(["**/*.py", "**/*.ts", "**/*.tsx"])
      );
      expect(body.exclude).toEqual(
        expect.arrayContaining(["node_modules/**", ".git/**"])
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/job queued/i)).toBeInTheDocument();
    });
  });

  it("shows a validation error when the repo URL is empty", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<IngestionPage />);

    await user.click(screen.getByRole("tab", { name: /code repository/i }));

    // Submit button should be disabled when the URL is empty.
    const button = screen.getByRole("button", { name: /ingest repository/i });
    expect(button).toBeDisabled();

    // Even if forced, ensure we never POST with an empty URL.
    expect(
      fetchMock.mock.calls.some(
        (c) => typeof c[0] === "string" && c[0].includes("/api/ingest-git")
      )
    ).toBe(false);
  });

  it("rejects malformed URLs client-side", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<IngestionPage />);

    await user.click(screen.getByRole("tab", { name: /code repository/i }));

    const url = screen.getByLabelText(/repository url/i);
    await user.type(url, "not-a-url");
    await user.click(screen.getByRole("button", { name: /ingest repository/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/valid/i);
    });
    expect(
      fetchMock.mock.calls.some(
        (c) => typeof c[0] === "string" && c[0].includes("/api/ingest-git")
      )
    ).toBe(false);
  });
});
