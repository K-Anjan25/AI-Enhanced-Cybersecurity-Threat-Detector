import { useState, useMemo } from "react";

export interface FilterableItem {
  severity?: string;
  [key: string]: unknown;
}

export interface UseTableFilterReturn<T extends FilterableItem> {
  searchQuery: string;
  setSearchQuery: React.Dispatch<React.SetStateAction<string>>;
  severityFilter: string;
  setSeverityFilter: React.Dispatch<React.SetStateAction<string>>;
  filteredData: T[];
}

export default function useTableFilter<T extends FilterableItem>(
  data: T[] = [],
  searchKeys: (keyof T)[] = ["ipAddress", "threatType"] as (keyof T)[]
): UseTableFilterReturn<T> {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");

  const filteredData = useMemo<T[]>(() => {
    return data.filter((item) => {
      const matchesSearch = searchKeys.some((key) => {
        const val = item[key];
        return String(val ?? "").toLowerCase().includes(searchQuery.toLowerCase());
      });

      const matchesSeverity =
        severityFilter === "ALL" || item.severity === severityFilter;

      return matchesSearch && matchesSeverity;
    });
  }, [data, searchQuery, severityFilter, searchKeys]);

  return {
    searchQuery,
    setSearchQuery,
    severityFilter,
    setSeverityFilter,
    filteredData,
  };
}