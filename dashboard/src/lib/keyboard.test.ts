import { afterEach, describe, expect, it } from 'vitest';

import {
  FILTER_ATTRIBUTE,
  FILTER_MARK,
  FILTER_SELECTOR,
  filterIntent,
  firstFilterField,
  helpIntent,
  isMacPlatform,
  isTypingTarget,
  listStepIntent,
  paletteIntent,
  paletteKeyLabel,
  PALETTE_KEY_SHORTCUTS,
} from './keyboard';

/** A real keydown, dispatched so `target` is whatever it landed on. */
function press(init: KeyboardEventInit, target: EventTarget = window): KeyboardEvent {
  const event = new KeyboardEvent('keydown', init);
  target.dispatchEvent(event);
  return event;
}

/** A field to dispatch into, so "the field owns the keystroke" is a real target. */
function field(): HTMLInputElement {
  const input = document.createElement('input');
  document.body.append(input);
  return input;
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('the typing rule', () => {
  it('treats a keystroke in a control as the control’s', () => {
    const input = field();
    const textarea = document.createElement('textarea');
    document.body.append(textarea);

    expect(isTypingTarget(press({ key: 'j' }, input).target)).toBe(true);
    expect(isTypingTarget(press({ key: 'j' }, textarea).target)).toBe(true);
  });

  it('treats a keystroke elsewhere on the page as the app’s', () => {
    const button = document.createElement('button');
    document.body.append(button);

    expect(isTypingTarget(press({ key: 'j' }, button).target)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});

describe('the palette key', () => {
  it('opens on the command key and the control key', () => {
    expect(paletteIntent(press({ key: 'k', metaKey: true }))).toBe(true);
    expect(paletteIntent(press({ key: 'k', ctrlKey: true }))).toBe(true);
    expect(paletteIntent(press({ key: 'K', metaKey: true }))).toBe(true);
  });

  it('refuses a modified or unmodified k', () => {
    // Ctrl+Shift+K is Firefox's console: a shortcut that fights the browser loses.
    expect(paletteIntent(press({ key: 'k', ctrlKey: true, shiftKey: true }))).toBe(false);
    expect(paletteIntent(press({ key: 'k', metaKey: true, altKey: true }))).toBe(false);
    expect(paletteIntent(press({ key: 'k' }))).toBe(false);
  });

  it('prints the key the operator has', () => {
    expect(paletteKeyLabel(true)).toBe('\u2318K');
    expect(paletteKeyLabel(false)).toBe('Ctrl+K');
    expect(PALETTE_KEY_SHORTCUTS).toBe('Meta+K Control+K');
    expect(isMacPlatform('MacIntel')).toBe(true);
    expect(isMacPlatform('iPhone')).toBe(true);
    expect(isMacPlatform('Win32')).toBe(false);
    expect(isMacPlatform('Linux x86_64')).toBe(false);
  });
});

describe('the help key', () => {
  it('opens the reference on ?', () => {
    expect(helpIntent(press({ key: '?', shiftKey: true }))).toBe(true);
  });

  it('leaves ? to a field, and to a modified keystroke', () => {
    expect(helpIntent(press({ key: '?' }, field()))).toBe(false);
    expect(helpIntent(press({ key: '?', metaKey: true }))).toBe(false);
  });
});

describe('the filter key', () => {
  it('jumps on /', () => {
    expect(filterIntent(press({ key: '/' }))).toBe(true);
  });

  it('leaves / to a field, where it is text', () => {
    expect(filterIntent(press({ key: '/' }, field()))).toBe(false);
    expect(filterIntent(press({ key: '/', ctrlKey: true }))).toBe(false);
  });
});

describe('the list step', () => {
  it('is j forward and k back', () => {
    expect(listStepIntent(press({ key: 'j' }))).toBe(1);
    expect(listStepIntent(press({ key: 'k' }))).toBe(-1);
    expect(listStepIntent(press({ key: 'x' }))).toBe(0);
  });

  it('ignores a repeat, a modifier and a field', () => {
    // Holding j would otherwise walk the whole queue, one route change per frame.
    expect(listStepIntent(press({ key: 'j', repeat: true }))).toBe(0);
    expect(listStepIntent(press({ key: 'j', ctrlKey: true }))).toBe(0);
    expect(listStepIntent(press({ key: 'j' }, field()))).toBe(0);
  });
});

describe('the filter mark', () => {
  it('is one spelling of the attribute and its selector', () => {
    expect(FILTER_MARK).toEqual({ [FILTER_ATTRIBUTE]: 'filter' });
    expect(FILTER_SELECTOR).toBe(`[${FILTER_ATTRIBUTE}="filter"]`);
  });

  it('finds the first marked field, and nothing when a screen marks none', () => {
    expect(firstFilterField()).toBeNull();

    // `FILTER_MARK` is a JSX spread: React turns a `data-` key into the attribute.
    // A DOM element set up by hand needs `setAttribute`, which is why the two are
    // pinned together here rather than assumed equal.
    const marked = document.createElement('input');
    marked.setAttribute(FILTER_ATTRIBUTE, 'filter');
    const other = document.createElement('input');
    document.body.append(other, marked);

    expect(marked.matches(FILTER_SELECTOR)).toBe(true);
    expect(firstFilterField()).toBe(marked);
  });
});
