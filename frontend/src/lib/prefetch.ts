/** Start a slow request early (e.g. while the Auto Demo shows another screen) and hand the same promise to the
 *  screen that needs it, so the result is on screen the moment it opens. Each prefetched result is used once. */
const inflight = new Map<string, Promise<any>>();

export function prefetch<T>(key: string, run: () => Promise<T>): void {
  if (inflight.has(key)) return;
  inflight.set(key, run().catch((e) => { inflight.delete(key); throw e; }));
  inflight.get(key)!.catch(() => {});
}

export function take<T>(key: string, run: () => Promise<T>): Promise<T> {
  const p = inflight.get(key);
  inflight.delete(key);
  return p ?? run();
}
