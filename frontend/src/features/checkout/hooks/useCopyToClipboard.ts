import { useEffect, useRef, useState } from "react";

export type CopyState = "copied" | "failed";

export type CopyStatus = {
  key: string;
  state: CopyState;
};

const RESET_AFTER_MS = 2500;

/**
 * Copy-to-clipboard with a per-field result the UI can show.
 *
 * The failure state is not decoration: the clipboard API rejects on insecure
 * contexts and denied permissions, and a customer who believes they copied a
 * CBU will paste whatever was there before into their banking app. Silence
 * would be the dangerous outcome, so failures are surfaced too.
 */
export function useCopyToClipboard(resetAfterMs: number = RESET_AFTER_MS) {
  const [status, setStatus] = useState<CopyStatus | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  function scheduleReset() {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => setStatus(null), resetAfterMs);
  }

  async function copy(key: string, value: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(value);
      setStatus({ key, state: "copied" });
    } catch {
      setStatus({ key, state: "failed" });
    }
    scheduleReset();
  }

  function stateFor(key: string): CopyState | null {
    return status?.key === key ? status.state : null;
  }

  return { copy, stateFor };
}
