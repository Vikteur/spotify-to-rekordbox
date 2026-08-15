import { useEffect, useRef } from 'react';
import { api } from './api';
import type { LibrarySummary, ScanStatus } from './types';

/**
 * Poll `/api/scan/status` every 500 ms while a scan is running, then stop.
 *
 * The whole interval lifecycle lives here so it can't leak: the poll starts
 * only when a scan is running and no interval is live, clears itself the moment
 * the scan leaves the "scanning" state (handing back the finished library), and
 * is torn down on unmount. `setScan`/`onDone` are assumed stable (plain state
 * setters), so the effect re-runs only when `scan` changes.
 */
export function useScanPolling(
  scan: ScanStatus | null,
  setScan: (status: ScanStatus) => void,
  onDone: (library: LibrarySummary) => void,
): void {
  const polling = useRef<number | null>(null);

  useEffect(() => {
    if (scan?.state === 'scanning' && polling.current == null) {
      polling.current = window.setInterval(async () => {
        try {
          const status = await api.scanStatus();
          setScan(status);
          if (status.state !== 'scanning' && polling.current) {
            window.clearInterval(polling.current);
            polling.current = null;
            if (status.library) onDone(status.library);
          }
        } catch {
          // transient poll failure: keep polling
        }
      }, 500);
    }
  }, [scan, setScan, onDone]);

  useEffect(
    () => () => {
      if (polling.current) window.clearInterval(polling.current);
    },
    [],
  );
}
