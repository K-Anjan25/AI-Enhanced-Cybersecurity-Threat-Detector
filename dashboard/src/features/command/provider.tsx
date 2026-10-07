/**
 * The command palette's wiring (T-411): where its commands come from, which keys
 * open it, and the state that says which dialog is up.
 *
 * It is the composition root of this feature, and that placement is the design: the
 * palette itself is presentational and knows nothing about routes, and the *sources*
 * of commands are three different layers — the shell's IA, the hunt console's saved
 * queries, and the app's own actions — which no single feature may reach. A feature
 * may not import another feature (rules.md §7), so the one component that may read
 * both the nav model and the hunt store is the app shell, and it hands the result in
 * as a prop.
 *
 * **Below 768 px the palette offers the triage loop and the actions** (T-412). A
 * command that navigates to a screen the viewport refuses would be a command that
 * navigates to a notice, so the destination list is filtered by the same viewport
 * answer the shell and the routes use.
 *
 * **The saved hunts are read when the palette opens**, not when the provider mounts:
 * an operator who saves a hunt and immediately presses `⌘K` must find it, and a list
 * read once at start-up would offer the hunts of a previous session.
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import {
  CommandPalette,
  ShortcutReference,
  shortcutTable,
  type Command,
} from '../../components/command';
import { navDestinations } from '../../components/layout/nav';
import { useViewportClass } from '../../components/hooks/viewport';
import { ALERTS_PATH } from '../../lib/routes';
import { isMacPlatform } from '../../lib/keyboard';
import { huntHref } from '../../lib/routes';
import { useTheme } from '../../theme/ThemeProvider';
import { useGlobalShortcuts } from './hooks';

/** The part of a saved hunt the palette needs. The store's own row is wider. */
export interface SavedHuntRef {
  readonly name: string;
  readonly text: string;
}

export interface CommandProviderProps {
  /**
   * The saved hunts to offer, read each time the palette opens.
   *
   * A function rather than an array for exactly that reason, and optional so a test
   * or a future build without saved hunts renders a palette with navigation and
   * actions instead of no palette at all.
   */
  listSavedHunts?: (() => readonly SavedHuntRef[]) | undefined;
  children: ReactNode;
}

export interface CommandsValue {
  /** Open the palette, or close it when it is already open. */
  openPalette: () => void;
  /** Open the shortcut reference. */
  openShortcuts: () => void;
}

const CommandsContext = createContext<CommandsValue | null>(null);

/** The shell's handle on the palette. Throws rather than silently doing nothing. */
export function useCommands(): CommandsValue {
  const value = useContext(CommandsContext);
  if (value === null) {
    throw new Error('useCommands must be called inside <CommandProvider>');
  }
  return value;
}

type Dialog = 'palette' | 'shortcuts' | null;

export function CommandProvider({ listSavedHunts, children }: CommandProviderProps) {
  const [dialog, setDialog] = useState<Dialog>(null);
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const viewport = useViewportClass();
  const mac = useMemo(() => isMacPlatform(), []);

  const openPalette = useCallback(() => {
    setDialog((current) => (current === 'palette' ? null : 'palette'));
  }, []);
  const openShortcuts = useCallback(() => setDialog('shortcuts'), []);
  const close = useCallback(() => setDialog(null), []);

  useGlobalShortcuts({ onPalette: openPalette, onShortcuts: openShortcuts });

  // Read on the open edge: `savedHunts` is a synchronous `localStorage` read, and
  // doing it here is what makes a hunt saved a second ago appear.
  const saved = useMemo(
    () => (dialog === 'palette' ? (listSavedHunts?.() ?? []) : []),
    [dialog, listSavedHunts],
  );

  const commands = useMemo<Command[]>(() => {
    // §8.3's last row: the queue is what a narrow window offers. `/alerts` is the only
    // destination whose screen is not wrapped in `Offered` (App.tsx), and it is also
    // the only one §8.3 names, so the filter is written as the path rather than as a
    // class test that would have to be kept in step with the route table.
    const destinations =
      viewport === 'narrow'
        ? navDestinations().filter((destination) => destination.to === ALERTS_PATH)
        : navDestinations();

    const navigation: Command[] = destinations.map((destination) => ({
      id: `nav:${destination.to}`,
      label: destination.label,
      hint: destination.to,
      group: 'Navigation',
      keywords: destination.keywords,
      run: () => navigate(destination.to),
    }));

    const hunts: Command[] = (viewport === 'narrow' ? [] : saved).map((hunt) => ({
      id: `hunt:${hunt.name}`,
      label: hunt.name,
      hint: hunt.text,
      group: 'Saved hunts',
      keywords: ['hunt', 'query'],
      run: () => navigate(huntHref(hunt.text)),
    }));

    const actions: Command[] = [
      {
        id: 'action:shortcuts',
        label: 'Keyboard shortcuts',
        hint: '?',
        group: 'Actions',
        run: openShortcuts,
      },
      {
        id: 'action:theme',
        label: `Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`,
        // The same control as the top bar's, for the same reason: it is an action
        // with no screen, and a palette is where actions live.
        hint: 'Theme',
        group: 'Actions',
        run: toggleTheme,
      },
    ];

    return [...navigation, ...hunts, ...actions];
  }, [navigate, openShortcuts, saved, theme, toggleTheme, viewport]);

  const value = useMemo<CommandsValue>(
    () => ({ openPalette, openShortcuts }),
    [openPalette, openShortcuts],
  );

  return (
    <CommandsContext.Provider value={value}>
      {children}
      <CommandPalette open={dialog === 'palette'} commands={commands} onClose={close} />
      <ShortcutReference
        open={dialog === 'shortcuts'}
        shortcuts={shortcutTable(mac)}
        onClose={close}
      />
    </CommandsContext.Provider>
  );
}
