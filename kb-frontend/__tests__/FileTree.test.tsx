import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import FileTree, { FileTreeRow } from "@/components/ingestion/FileTree";

function makeRows(): FileTreeRow[] {
  return [
    { file: "a/one.py", parser: "python-ast", status: "done", entities_added: 3, edges_added: 2 },
    { file: "a/two.ts", parser: "tree-sitter-ts", status: "done", entities_added: 4, edges_added: 1 },
    { file: "a/three.md", parser: "gemini-markdown", status: "parsing", entities_added: 0, edges_added: 0 },
    { file: "a/four.go", parser: "tree-sitter-go", status: "routed", entities_added: 0, edges_added: 0 },
    { file: "a/five.sql", parser: "sqlglot", status: "failed", entities_added: 0, edges_added: 0 },
  ];
}

describe("FileTree", () => {
  it("calls onSelect with row 3's path and marks active", async () => {
    const rows = makeRows();
    const onSelect = vi.fn();
    const { rerender } = render(
      <FileTree files={rows} selected={null} onSelect={onSelect} />
    );

    const options = screen.getAllByRole("option");
    expect(options).toHaveLength(5);

    // Row index 2 = third row.
    await userEvent.click(options[2]);
    expect(onSelect).toHaveBeenCalledWith("a/three.md");

    rerender(<FileTree files={rows} selected="a/three.md" onSelect={onSelect} />);
    const refreshed = screen.getAllByRole("option");
    expect(refreshed[2]).toHaveAttribute("data-active", "true");
    expect(refreshed[2]).toHaveAttribute("aria-selected", "true");
  });
});
