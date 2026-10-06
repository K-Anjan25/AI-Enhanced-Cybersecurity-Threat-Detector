/**
 * The command surface's own barrel (T-411).
 *
 * `CommandPalette` and `ShortcutReference` are §6 components, but they are not in
 * `components/ui`: the primitives barrel is the list a *screen* composes from, and
 * this is a pair of dialogs the shell mounts once with commands handed in. Keeping
 * them in their own directory — the way the severity ramp has its own `charts/` —
 * keeps the primitive list from growing a second kind of thing.
 *
 * What is exported here is the palette, the reference, the command model and the
 * shortcut table. The wiring (where commands come from, which key opens what) lives
 * in `features/command`, because that is the layer allowed to know the app.
 */
export { CommandPalette } from './CommandPalette';
export type { CommandPaletteProps } from './CommandPalette';
export { ShortcutReference } from './ShortcutReference';
export type { ShortcutReferenceProps } from './ShortcutReference';
export { commandDomId, filterCommands, GROUP_ORDER, groupCommands, moveSelection } from './model';
export type { Command, CommandGroup, CommandGrouping } from './model';
export { shortcutTable } from './shortcuts';
export type { Shortcut } from './shortcuts';
