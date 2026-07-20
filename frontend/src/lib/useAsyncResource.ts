import { useCallback, useEffect, useRef, useState } from "react";

export type UseAsyncResourceOptions = {
  enabled?: boolean;
  deps?: unknown[];
  errorMessage?: string;
};

export function useAsyncResource<T>(
  fetcher: () => Promise<T>,
  initialValue: T,
  options: UseAsyncResourceOptions = {}
) {
  const { enabled = true, deps = [], errorMessage = "No se pudo cargar la informacion." } = options;
  const [data, setData] = useState<T>(initialValue);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await fetcherRef.current();
      setData(result);
    } catch {
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
    // errorMessage is a stable literal at each call site; fetcher is read via ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [errorMessage]);

  useEffect(() => {
    if (!enabled) return;
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, reload, ...deps]);

  return { data, setData, loading, error, setError, reload };
}
