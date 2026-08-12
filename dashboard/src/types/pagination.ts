export interface PaginationState {
  page: number;
  itemsPerPage: number;
  totalItems?: number;
  totalPages?: number;
}

export interface PaginatedResponse<T = unknown> {
  data: T[];
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}