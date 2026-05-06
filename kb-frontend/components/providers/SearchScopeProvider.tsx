"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

type SearchScope = "all" | "mine" | "shared";

interface SearchScopeContextValue {
  scope: SearchScope;
  setScope: (scope: SearchScope) => void;
  datasets: string[];
  setDatasets: (datasets: string[]) => void;
  toggleDataset: (dataset: string) => void;
}

const SearchScopeContext = createContext<SearchScopeContextValue>({
  scope: "all",
  setScope: () => {},
  datasets: ["archisurance", "hotpotqa"],
  setDatasets: () => {},
  toggleDataset: () => {},
});

export function SearchScopeProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<SearchScope>("all");
  const [datasets, setDatasets] = useState<string[]>(["archisurance", "hotpotqa"]);

  const toggleDataset = useCallback((dataset: string) => {
    setDatasets((prev) => {
      if (prev.includes(dataset)) {
        if (prev.length <= 1) return prev;
        return prev.filter((d) => d !== dataset);
      }
      return [...prev, dataset];
    });
  }, []);

  return (
    <SearchScopeContext.Provider value={{ scope, setScope, datasets, setDatasets, toggleDataset }}>
      {children}
    </SearchScopeContext.Provider>
  );
}

export function useSearchScope() {
  return useContext(SearchScopeContext);
}
