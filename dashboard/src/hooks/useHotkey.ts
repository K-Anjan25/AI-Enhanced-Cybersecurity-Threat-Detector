import { useEffect } from "react";

/**
 * useHotkey — register a global keydown listener (e.g. ⌘K / Ctrl+K command
 * palette, Escape to close drawers). Combo syntax: `"mod+k"`, `"ctrl+shift+p"`,
 * `"escape"`, `"g"`. "mod" = Ctrl on Windows/Linux, Cmd on macOS. By default
 * shortcuts are ignored while typing in a field, so typing never triggers one.
 */
export function useHotkey(
  combo: string,
  callback: (e: KeyboardEvent) => void,
  options: { ignoreWhenTyping?: boolean } = { ignoreWhenTyping: true }
): void {
  useEffect(() => {
    const parts = combo.toLowerCase().split("+").filter(Boolean);
    const hasMod = parts.includes("mod") || parts.includes("ctrl") || parts.includes("meta");
    const key = parts.find((p) => !["mod", "ctrl", "meta", "shift", "alt"].includes(p));
    if (!key) return;

    const isTypingTarget = (target: EventTarget | null): boolean => {
      const el = target as HTMLElement | null;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };

    const handler = (e: KeyboardEvent) => {
      if (options.ignoreWhenTyping && isTypingTarget(e.target)) return;
      if (e.key.toLowerCase() !== key) return;

      const wantsMod = parts.includes("mod") || parts.includes("ctrl");
      const wantsMeta = parts.includes("meta");
      const wantsShift = parts.includes("shift");
      const wantsAlt = parts.includes("alt");

      if (wantsMod && !e.ctrlKey && !e.metaKey) return;
      if (!wantsMod && (e.ctrlKey || e.metaKey)) return; // no-mod combo pressed with a modifier
      if (wantsMeta && !e.metaKey) return;
      if (wantsShift && !e.shiftKey) return;
      if (!wantsShift && e.shiftKey && !wantsMeta && !wantsMod) return;
      if (wantsAlt && !e.altKey) return;

      e.preventDefault();
      callback(e);
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [combo, callback, options.ignoreWhenTyping]);
}
