"use client";

import { useSyncExternalStore } from "react";

/**
 * One value persisted in this browser's `localStorage`, readable from React.
 *
 * `use()` returns `null` during server render and before the browser value is
 * known, and `undefined` once it is known that nothing is saved. Callers must
 * treat `null` as "don't know yet", never as "empty". Storage can throw or be
 * cleared (private windows, blocked site data), so every read and write is
 * guarded and the page still works without it; a failed write is remembered
 * for this page view only.
 */
export interface LocalStore<T> {
  use(): T | undefined | null;
  save(value: T | null): void;
}

/**
 * @param key The `localStorage` key.
 * @param parse Validates what was stored; returns `undefined` for anything malformed.
 */
export function createLocalStore<T>(key: string, parse: (raw: unknown) => T | undefined): LocalStore<T> {
  const listeners = new Set<() => void>();
  let loaded = false;
  let memo: T | undefined;

  function read(): T | undefined {
    if (!loaded) {
      loaded = true;
      try {
        const raw = window.localStorage.getItem(key);
        memo = raw === null ? undefined : parse(JSON.parse(raw));
      } catch {
        memo = undefined;
      }
    }
    return memo;
  }

  function subscribe(listener: () => void): () => void {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== key && event.key !== null) return;
      loaded = false;
      listener();
    };
    listeners.add(listener);
    window.addEventListener("storage", onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener("storage", onStorage);
    };
  }

  return {
    use() {
      return useSyncExternalStore(subscribe, read, () => null);
    },
    save(value) {
      loaded = true;
      memo = value ?? undefined;
      try {
        if (value === null) window.localStorage.removeItem(key);
        else window.localStorage.setItem(key, JSON.stringify(value));
      } catch {
        // Remembered for this page view only.
      }
      listeners.forEach((listener) => listener());
    },
  };
}
