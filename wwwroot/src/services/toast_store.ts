// The toasts of the app: small messages at the top right that outlive the page that raised them.
import { useSyncExternalStore } from 'react';

export type ToastKind = 'progress' | 'success' | 'error';

export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

/** A finished toast goes away by itself after this long; a failure stays until the Learner closes it. */
export const SUCCESS_TOAST_MILLISECONDS = 6000;

type Listener = () => void;

let toasts: readonly Toast[] = [];
let nextId = 1;
const listeners = new Set<Listener>();

const publish = (next: readonly Toast[]): void => {
  toasts = next;
  listeners.forEach((listener) => listener());
};

export const dismissToast = (id: number): void => publish(toasts.filter((toast) => toast.id !== id));

/** Shows a toast and returns its id, so the same toast can later change. */
export const showToast = (kind: ToastKind, text: string): number => {
  const id = nextId;
  nextId += 1;
  publish([...toasts, { id, kind, text }]);

  return id;
};

/** Changes a toast that is still shown, for example from progress to its result. */
export const changeToast = (id: number, kind: ToastKind, text: string): void => {
  publish(toasts.map((toast) => (toast.id === id ? { ...toast, kind, text } : toast)));

  if (kind === 'success') {
    setTimeout(() => dismissToast(id), SUCCESS_TOAST_MILLISECONDS);
  }
};

/** Removes every toast. For tests. */
export const clearToasts = (): void => publish([]);

const subscribe = (listener: Listener): (() => void) => {
  listeners.add(listener);

  return () => listeners.delete(listener);
};

export const useToasts = (): readonly Toast[] => useSyncExternalStore(subscribe, () => toasts);
