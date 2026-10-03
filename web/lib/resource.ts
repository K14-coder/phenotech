// A tiny keyed cache for lazily fetched data, readable from React without setState-in-effect.
// ensure(key, load) starts a load once per key; useResource subscribes and (optionally) triggers it.
import { useEffect, useSyncExternalStore } from "react";

export interface Resource<T> {
  status: "loading" | "ready" | "error";
  data?: T;
  error?: string;
}

const entries = new Map<string, Resource<unknown>>();
const listeners = new Set<() => void>();
const LOADING: Resource<never> = { status: "loading" };

function emit() {
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/**
 * Starts loading `key` unless it has been requested already (errors stick until retry(key), so a
 * missing file is fetched once, not in a loop). Safe to call from event handlers.
 */
export function ensure<T>(key: string, load: () => Promise<T>): Resource<T> {
  const hit = entries.get(key) as Resource<T> | undefined;
  if (hit) return hit;
  const pending: Resource<T> = { status: "loading" };
  entries.set(key, pending);
  // let subscribers show a loading state (ensure runs in handlers and effects, never during render)
  queueMicrotask(emit);
  load().then(
    (data) => {
      entries.set(key, { status: "ready", data });
      emit();
    },
    (err: unknown) => {
      entries.set(key, { status: "error", error: err instanceof Error ? err.message : String(err) });
      emit();
    },
  );
  return pending;
}

/** Forgets a failed (or any) entry so the next ensure() fetches again. */
export function retry<T>(key: string, load: () => Promise<T>): void {
  entries.delete(key);
  ensure(key, load);
  emit();
}

/** Subscribes to `key` without starting a load (null until something calls ensure). */
export function useResourceValue<T>(key: string | null): Resource<T> | null {
  return useSyncExternalStore(
    subscribe,
    () => (key ? ((entries.get(key) as Resource<T> | undefined) ?? null) : null),
    () => null,
  );
}

/** Subscribes to `key` and loads it after mount. */
export function useResource<T>(key: string | null, load: () => Promise<T>): Resource<T> | null {
  const value = useResourceValue<T>(key);
  useEffect(() => {
    if (key) ensure(key, load);
  }, [key, load]);
  return key ? (value ?? LOADING) : null;
}
