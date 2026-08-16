/**
 * The autosave queue behind the guest flow's "Saved" chip.
 *
 * Every mutation becomes a keyed job; scheduling the same key again replaces
 * the older payload, so rapid edits collapse into one write of the latest
 * state. Jobs run one at a time in FIFO order (writes are idempotent PUTs, so
 * a retry after a flaky phone connection can never duplicate a song), failures
 * retry with backoff forever, and a closing tab flushes whatever is left —
 * debounced edits included — with `keepalive` fetches, so nothing is lost
 * mid-answer.
 */

export type SaveState = 'saved' | 'saving' | 'retrying';

type Job = (keepalive: boolean) => Promise<void>;

const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 10000];

export class Saver {
  private queue = new Map<string, Job>();
  private waiting = new Map<string, { timer: number; job: Job }>();
  private pumping = false;
  private failures = 0;
  private onState: (state: SaveState) => void;

  constructor(onState: (state: SaveState) => void) {
    this.onState = onState;
  }

  /** Queue (or replace) a write. `delayMs` debounces text-ish edits. */
  schedule(key: string, job: Job, delayMs = 0): void {
    this.clearWaiting(key);
    this.onState(this.failures > 0 ? 'retrying' : 'saving');
    if (delayMs <= 0) {
      this.queue.set(key, job);
      void this.pump();
      return;
    }
    const timer = window.setTimeout(() => {
      this.waiting.delete(key);
      this.queue.set(key, job);
      void this.pump();
    }, delayMs);
    this.waiting.set(key, { timer, job });
  }

  /** Drop a pending write (e.g. the save of an entry that was just deleted). */
  cancel(key: string): void {
    this.clearWaiting(key);
    this.queue.delete(key);
    if (!this.hasPending()) this.onState('saved');
  }

  hasPending(): boolean {
    return this.queue.size > 0 || this.waiting.size > 0 || this.pumping;
  }

  /** Is a newer write for this key still waiting to go out? */
  isPending(key: string): boolean {
    return this.queue.has(key) || this.waiting.has(key);
  }

  /** Tab is closing: fire everything still pending as keepalive requests. */
  flushKeepalive(): void {
    for (const [key, pending] of this.waiting) {
      window.clearTimeout(pending.timer);
      this.queue.set(key, pending.job);
    }
    this.waiting.clear();
    for (const job of this.queue.values()) {
      job(true).catch(() => undefined);
    }
    this.queue.clear();
    // The requests are on their way with keepalive; if the user stays after
    // all, the next edit re-opens the queue anyway.
    this.onState('saved');
  }

  private clearWaiting(key: string): void {
    const pending = this.waiting.get(key);
    if (pending !== undefined) {
      window.clearTimeout(pending.timer);
      this.waiting.delete(key);
    }
  }

  private async pump(): Promise<void> {
    if (this.pumping) return;
    this.pumping = true;
    try {
      while (this.queue.size > 0) {
        const [key, job] = this.queue.entries().next().value as [string, Job];
        this.queue.delete(key);
        try {
          await job(false);
          this.failures = 0;
        } catch {
          // Put it back at the front (unless a newer payload replaced it while
          // in flight) and try again after a pause — autosave never gives up.
          if (!this.queue.has(key)) {
            this.queue = new Map([[key, job], ...this.queue]);
          }
          this.failures += 1;
          this.onState('retrying');
          const delay =
            RETRY_DELAYS_MS[Math.min(this.failures - 1, RETRY_DELAYS_MS.length - 1)];
          await new Promise((resolve) => window.setTimeout(resolve, delay));
        }
      }
    } finally {
      this.pumping = false;
      if (this.queue.size > 0) {
        void this.pump(); // scheduled while we were finishing
      } else if (this.waiting.size === 0) {
        this.onState(this.failures > 0 ? 'retrying' : 'saved');
      }
    }
  }
}
