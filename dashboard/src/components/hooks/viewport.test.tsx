/**
 * The viewport hook (T-412).
 *
 * Three claims, and the third is the one that needs a hook rather than a function:
 * the class is right on the first render, a resize that crosses a boundary re-renders
 * the caller, and a resize that stays inside a class does not — because §8.3's classes
 * are what the layout acts on, and re-rendering the shell on every pixel of a drag is
 * work nobody asked for.
 */
import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { stubViewport } from '../../test/viewport';
import { currentViewportClass, useViewportClass } from './viewport';

/** A probe that renders the class it was given and counts its own renders. */
const renders = { count: 0 };

function Probe() {
  const viewport = useViewportClass();
  renders.count += 1;
  return <p>class: {viewport}</p>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  renders.count = 0;
});

describe('useViewportClass', () => {
  it('reads the class of the window it is given', () => {
    stubViewport(500);
    render(<Probe />);

    expect(screen.getByText('class: narrow')).toBeInTheDocument();
    expect(currentViewportClass()).toBe('narrow');
  });

  it('falls back to the full console when the environment cannot measure itself', () => {
    // No `matchMedia` at all — jsdom's own state, and the reason the fallback matters:
    // the alternative is a test environment (or a browser) that hides every screen
    // behind a notice because it could not answer a query.
    render(<Probe />);

    expect(screen.getByText('class: wide')).toBeInTheDocument();
  });

  it('re-renders when a boundary is crossed, and stays put while it is not', () => {
    const viewport = stubViewport(1200);
    render(<Probe />);
    expect(screen.getByText('class: medium')).toBeInTheDocument();
    const afterFirstRender = renders.count;

    // Inside the class: 1100 px is still §8.3's 1024–1439 row.
    act(() => {
      viewport.setWidth(1100);
    });
    expect(screen.getByText('class: medium')).toBeInTheDocument();
    expect(renders.count, 'a resize inside the class re-rendered the caller').toBe(
      afterFirstRender,
    );

    // Across a boundary, twice: down into compact, then up into wide.
    act(() => {
      viewport.setWidth(900);
    });
    expect(screen.getByText('class: compact')).toBeInTheDocument();
    act(() => {
      viewport.setWidth(1600);
    });
    expect(screen.getByText('class: wide')).toBeInTheDocument();
  });

  it('stops listening when it unmounts', () => {
    const viewport = stubViewport(500);
    const { unmount } = render(<Probe />);
    unmount();
    const afterUnmount = renders.count;

    act(() => {
      viewport.setWidth(1600);
    });

    expect(renders.count, 'an unmounted probe re-rendered').toBe(afterUnmount);
  });
});
