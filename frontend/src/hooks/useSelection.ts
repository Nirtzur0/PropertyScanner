import { useCallback, useMemo, useState } from "react";

export function useSelection() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const selectOnly = useCallback((id: string) => {
    setSelectedIds([id]);
  }, []);

  const clear = useCallback(() => {
    setSelectedIds([]);
  }, []);

  const isSelected = (id: string) => selectedSet.has(id);

  return { selectedIds, setSelectedIds, toggle, selectOnly, clear, isSelected, count: selectedIds.length };
}
