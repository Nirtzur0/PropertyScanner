import { useCallback, useDeferredValue, useMemo, useReducer } from "react";
import type { WorkbenchFilters } from "../types";

type FilterState = {
  search: string;
  country: string;
  city: string;
  listingType: string;
  minPrice: string;
  maxPrice: string;
  minSupport: string;
  sourceStatus: string;
};

type FilterAction =
  | { type: "set"; field: keyof FilterState; value: string }
  | { type: "clear" };

const initialState: FilterState = {
  search: "",
  country: "",
  city: "",
  listingType: "",
  minPrice: "",
  maxPrice: "",
  minSupport: "",
  sourceStatus: "",
};

function reducer(state: FilterState, action: FilterAction): FilterState {
  if (action.type === "clear") return { ...initialState, search: state.search };
  return { ...state, [action.field]: action.value };
}

export function useExploreFilters() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const deferredSearch = useDeferredValue(state.search);

  const filters: WorkbenchFilters = useMemo(
    () => ({
      search: deferredSearch || undefined,
      country: state.country || undefined,
      city: state.city || undefined,
      listing_type: state.listingType || undefined,
      min_price: state.minPrice ? Number(state.minPrice) : undefined,
      max_price: state.maxPrice ? Number(state.maxPrice) : undefined,
      min_support: state.minSupport ? Number(state.minSupport) : undefined,
      source_status: state.sourceStatus || undefined,
      sort: "deal_score_desc",
      limit: 200,
    }),
    [deferredSearch, state.country, state.city, state.listingType, state.minPrice, state.maxPrice, state.minSupport, state.sourceStatus],
  );

  const hasActiveFilters =
    Boolean(state.country) ||
    Boolean(state.city) ||
    Boolean(state.listingType) ||
    Boolean(state.minPrice) ||
    Boolean(state.maxPrice) ||
    Boolean(state.minSupport) ||
    Boolean(state.sourceStatus);

  const clearFilters = useCallback(() => dispatch({ type: "clear" }), []);

  const setSearch = useCallback((v: string) => dispatch({ type: "set", field: "search", value: v }), []);
  const setCountry = useCallback((v: string) => dispatch({ type: "set", field: "country", value: v }), []);
  const setCity = useCallback((v: string) => dispatch({ type: "set", field: "city", value: v }), []);
  const setListingType = useCallback((v: string) => dispatch({ type: "set", field: "listingType", value: v }), []);
  const setMinPrice = useCallback((v: string) => dispatch({ type: "set", field: "minPrice", value: v }), []);
  const setMaxPrice = useCallback((v: string) => dispatch({ type: "set", field: "maxPrice", value: v }), []);
  const setMinSupport = useCallback((v: string) => dispatch({ type: "set", field: "minSupport", value: v }), []);
  const setSourceStatus = useCallback((v: string) => dispatch({ type: "set", field: "sourceStatus", value: v }), []);

  return {
    search: state.search, setSearch,
    country: state.country, setCountry,
    city: state.city, setCity,
    listingType: state.listingType, setListingType,
    minPrice: state.minPrice, setMinPrice,
    maxPrice: state.maxPrice, setMaxPrice,
    minSupport: state.minSupport, setMinSupport,
    sourceStatus: state.sourceStatus, setSourceStatus,
    filters,
    hasActiveFilters,
    clearFilters,
  };
}
