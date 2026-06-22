import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  CaseInfo,
  CASE_CHANGED_EVENT,
  CASE_STORAGE_KEY,
  emitCaseChanged,
  persistSelectedCaseId,
  resolveSelectedCaseId,
} from "../api";

export function useEffectiveCase() {
  const [cases, setCases] = useState<CaseInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(
    () => Number(localStorage.getItem(CASE_STORAGE_KEY)) || null
  );

  const refreshCases = useCallback(async (preferredId?: number | null) => {
    setLoading(true);
    try {
      const data = await api.listCases();
      setCases(data.items);
      const nextId = resolveSelectedCaseId(data.items, preferredId);
      setSelectedCaseId(nextId);
      persistSelectedCaseId(nextId);
      return { items: data.items, effectiveCaseId: nextId };
    } catch {
      setCases([]);
      setSelectedCaseId(null);
      return { items: [] as CaseInfo[], effectiveCaseId: null };
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshCases();
  }, [refreshCases]);

  useEffect(() => {
    const onCaseChanged = (event: Event) => {
      const nextCaseId = (event as CustomEvent<{ caseId?: number | null }>).detail?.caseId ?? null;
      void refreshCases(nextCaseId);
    };
    window.addEventListener(CASE_CHANGED_EVENT, onCaseChanged);
    return () => window.removeEventListener(CASE_CHANGED_EVENT, onCaseChanged);
  }, [refreshCases]);

  const effectiveCaseId = useMemo(
    () => resolveSelectedCaseId(cases, selectedCaseId),
    [cases, selectedCaseId]
  );

  const selectedCase = useMemo(
    () => cases.find((item) => item.case_id === effectiveCaseId) ?? null,
    [cases, effectiveCaseId]
  );

  const selectCase = useCallback((caseId: number) => {
    setSelectedCaseId(caseId);
    persistSelectedCaseId(caseId);
    emitCaseChanged(caseId);
  }, []);

  return {
    cases,
    loading,
    effectiveCaseId,
    selectedCase,
    refreshCases,
    selectCase,
  };
}
