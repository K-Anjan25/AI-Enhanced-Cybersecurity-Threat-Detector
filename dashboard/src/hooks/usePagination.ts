import { useState, ChangeEvent, MouseEvent } from "react";

export interface UsePaginationReturn {
  page: number;
  itemsPerPage: number;
  handleChangePage: (
    event: MouseEvent<HTMLButtonElement> | null,
    newPage: number
  ) => void;
  handleChangeItemsPerPage: (
    event: ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => void;
  setPage: React.Dispatch<React.SetStateAction<number>>;
}

export default function usePagination(
  initialPage: number = 0,
  initialItemsPerPage: number = 10
): UsePaginationReturn {
  const [page, setPage] = useState<number>(initialPage);
  const [itemsPerPage, setItemsPerPage] = useState<number>(initialItemsPerPage);

  const handleChangePage = (
    _event: MouseEvent<HTMLButtonElement> | null,
    newPage: number
  ): void => {
    setPage(newPage);
  };

  const handleChangeItemsPerPage = (
    event: ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ): void => {
    setItemsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  return {
    page,
    itemsPerPage,
    handleChangePage,
    handleChangeItemsPerPage,
    setPage,
  };
}