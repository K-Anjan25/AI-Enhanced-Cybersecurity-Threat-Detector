import React, { ChangeEvent } from "react";

export interface CategoryItem {
  id?: string | number;
  name: string;
}

export type Category = string | CategoryItem;

export interface SearchBarProps {
  searchValue?: string;
  onChangeSearchValue?: (value: string) => void;
  filter?: string;
  onChangeFilter?: (filter: string) => void;
  sortBy?: string;
  onChangeSortBy?: (sortBy: string) => void;
  categories?: Category[];
}

const SearchBar: React.FC<SearchBarProps> = ({
  searchValue = "",
  onChangeSearchValue,
  filter = "",
  onChangeFilter,
  sortBy = "",
  onChangeSortBy,
  categories = [],
}) => {
  return (
    <div className="flex flex-col sm:flex-row items-center gap-3 w-full bg-app-surface p-3 rounded-xl border border-line-subtle shadow-sm">
      {/* Search Input */}
      <div className="relative flex-1 w-full">
        <span className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-content-tertiary text-sm">
          🔍
        </span>
        <input
          type="text"
          value={searchValue}
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            onChangeSearchValue?.(e.target.value)
          }
          placeholder="Search threats, IPs, hashes..."
          className="w-full bg-app-bg text-sm text-content-primary pl-9 pr-4 py-2 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition placeholder-content-tertiary"
        />
      </div>

      {/* Sort By Dropdown */}
      <div className="w-full sm:w-44">
        <select
          value={sortBy}
          onChange={(e: ChangeEvent<HTMLSelectElement>) =>
            onChangeSortBy?.(e.target.value)
          }
          className="w-full bg-app-bg text-sm text-content-primary px-3 py-2 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition cursor-pointer"
        >
          <option value="">Sort By</option>
          <option value="DATE_DESC">Date (Newest)</option>
          <option value="DATE_ASC">Date (Oldest)</option>
          <option value="SEVERITY_DESC">Severity (High to Low)</option>
          <option value="SEVERITY_ASC">Severity (Low to High)</option>
        </select>
      </div>

      {/* Filter / Category Dropdown */}
      <div className="w-full sm:w-48">
        <select
          value={filter}
          onChange={(e: ChangeEvent<HTMLSelectElement>) =>
            onChangeFilter?.(e.target.value)
          }
          className="w-full bg-app-bg text-sm text-content-primary px-3 py-2 rounded-lg border border-line-subtle focus:outline-none focus:border-accent-primary transition cursor-pointer"
        >
          <option value="">All Categories</option>
          {categories.map((cat: Category, idx: number) => {
            const name = typeof cat === "string" ? cat : cat.name;
            const key = typeof cat === "object" && cat.id ? cat.id : idx;
            return (
              <option key={key} value={name}>
                {name}
              </option>
            );
          })}
        </select>
      </div>
    </div>
  );
};

export default SearchBar;