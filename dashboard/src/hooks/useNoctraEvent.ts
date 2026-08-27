import { useEffect } from "react";
import { emit, on, type NoctraEvent } from "../lib/events";

/**
 * useNoctraEvent — the React binding for the NOCTRA event bus (WordPress-hook
 * analog). `emit` dispatches a namespaced event; `on` subscribes with priority.
 *
 *   // Dispatch (e.g. Navbar → drawer):
 *   useNoctraEvent().emit(EVENTS.OPEN_PENDING_DRAWER);
 *
 *   // Listen (e.g. drawer mounts its own handler):
 *   useNoctraEvent(EVENTS.OPEN_PENDING_DRAWER, () => setOpen(true));
 */
export function useNoctraEvent(event?: NoctraEvent, handler?: (...args: unknown[]) => void, priority = 10) {
  useEffect(() => {
    if (!event || !handler) return;
    return on(event, handler, priority);
  }, [event, handler, priority]);

  return { emit, on };
}

export default useNoctraEvent;
