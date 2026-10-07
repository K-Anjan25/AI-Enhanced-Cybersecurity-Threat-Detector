/**
 * The accessibility pass (T-413, NFR-09, design.md §9).
 *
 * axe answers "is this markup wrong?" for the rules it has. It does not answer the two
 * questions §9 also asks, and a release cannot claim an accessibility pass on axe
 * alone:
 *
 *   * **Is the document navigable the way a screen reader reads it?** One `h1`, the
 *     landmarks (`header`, `nav`, `main`), a named list for the queue, scoped table
 *     headers, and no `tabindex` above zero — the structure that decides whether a
 *     reader can jump around the page or has to walk every element.
 *   * **Is every action reachable from the keyboard?** §9 claims "every action
 *     reachable and operable by keyboard", which is checkable: press Tab until focus
 *     stops moving and assert the set of controls focus landed on is the set of
 *     controls on the screen. Nothing else proves a control is not mouse-only — a
 *     `div` with a click handler looks fine to axe and cannot be reached at all.
 *
 * The audit reports *findings*, and the caller asserts the list is empty: a failure
 * that names the element and the reason is worth more than a boolean, which is what
 * the two screens' third test after this one exists for.
 */
import { getRoles, within } from '@testing-library/dom';

/** One thing the structure audit found, in the terms a reader would fix it. */
export interface Finding {
  /** Where it is: a CSS-ish path, enough to find the element. */
  readonly where: string;
  /** What is wrong, in one sentence. */
  readonly problem: string;
}

/** A short, stable description of an element for a finding. */
function describe(element: Element): string {
  const id = element.id === '' ? '' : `#${element.id}`;
  const text = (element.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 40);
  return `<${element.tagName.toLowerCase()}${id}>${text === '' ? '' : ` "${text}"`}`;
}

/**
 * Whether an element could hold focus at all: not disabled, and not hidden.
 *
 * jsdom reports layout as zero, so `hidden`, the `hidden` attribute and an
 * `aria-hidden` ancestor are the three kinds of invisibility it can tell us about.
 */
function focusableCandidate(element: HTMLElement): boolean {
  if (element.hasAttribute('disabled')) return false;
  if (element.getAttribute('aria-hidden') === 'true') return false;
  // A hidden control is not a tab stop.
  if (element.closest('[hidden]') !== null) return false;
  return true;
}

/**
 * The tabs a roving-tabindex `tablist` covers.
 *
 * The ARIA tabs pattern is deliberate about the tab order: exactly one tab is a Tab
 * stop and the others are `tabindex="-1"`, reached with the arrow keys instead. The
 * triage screen's evidence panel is built that way, and `EvidencePanel.test.tsx` asserts
 * the arrow keys move the selection — so an audit that called those tabs unreachable
 * would be wrong about a correct pattern, and one that ignored the pattern entirely
 * would miss a tablist whose arrows had been deleted.
 *
 * The rule is therefore narrow: a `-1` tab is covered **only** when it sits inside a
 * `role="tablist"` that has exactly one tab stop of its own. A tablist with no tab stop
 * at all leaves every tab unreachable, and that is reported.
 */
function tabsCoveredByRovingGroup(container: HTMLElement): Set<Element> {
  const covered = new Set<Element>();
  for (const tablist of container.querySelectorAll('[role="tablist"]')) {
    const tabs = [...tablist.querySelectorAll('[role="tab"]')];
    const stops = tabs.filter((tab) => !isOutOfTabOrder(tab as HTMLElement));
    if (stops.length !== 1) continue;
    for (const tab of tabs) {
      if (isOutOfTabOrder(tab as HTMLElement)) covered.add(tab);
    }
  }
  return covered;
}

/**
 * Every control the screen renders: the things an operator is meant to activate.
 *
 * This is the list the keyboard audit walks towards, and it is deliberately *wider*
 * than the tab stops. An audit that started from the tab stops could not notice the
 * defect the keyboard audit exists for — a control taken out of the tab order (by a
 * `tabindex="-1"`, say) is simply not in that list, and the walk would pass while the
 * control became mouse-only. The battery found exactly that: the first version of this
 * function was the tab-stop list, and removing the queue rows from the tab order
 * survived.
 */
export function interactiveControls(container: HTMLElement): HTMLElement[] {
  return [
    ...container.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="switch"], [role="tab"]',
    ),
  ].filter(focusableCandidate);
}

/**
 * Everything a keyboard can put focus on, whether or not it is a control.
 *
 * Deliberately wider than `interactiveControls`: the structure audit's question is
 * "can focus land somewhere that does nothing?", and a `<p tabindex="0">` is exactly
 * that — it is not in `interactiveControls`, so a check built on that list would walk
 * straight past it. The battery caught this: making a live-region paragraph focusable
 * survived until this function existed.
 */
export function focusableElements(container: HTMLElement): HTMLElement[] {
  return [
    ...container.querySelectorAll<HTMLElement>(
      'a[href], button, input, select, textarea, iframe, [tabindex]',
    ),
  ].filter(focusableCandidate);
}

/**
 * The focusable elements that are a tab stop: what `Tab` can land on, and therefore
 * what the structure audit holds to the rule that focus must be able to do something.
 */
export function keyboardReachable(container: HTMLElement): HTMLElement[] {
  return focusableElements(container).filter((element) => !isOutOfTabOrder(element));
}

/** Whether the element is a control that tabbing will never land on. */
function isOutOfTabOrder(element: HTMLElement): boolean {
  if (element.getAttribute('tabindex') === '-1') return true;
  // `inert` removes a subtree from the tab order as well as from the accessible tree,
  // and jsdom does not compute it, so it is read from the ancestor chain.
  return element.closest('[inert]') !== null;
}

/**
 * The landmarks a screen-reader user navigates by (design.md §9: "semantic landmarks").
 *
 * Separate from `auditStructure` because it is a property of the *shell* rather than of
 * a page: a page rendered on its own in a test has no `<main>`, and asserting otherwise
 * would be asserting that a component mounts a landmark its parent owns. The app-level
 * test is where the three core screens are audited through the shell.
 */
export function auditLandmarks(container: HTMLElement): Finding[] {
  const findings: Finding[] = [];

  const mains = [...container.querySelectorAll('main')];
  if (mains.length !== 1) {
    findings.push({
      where: 'document',
      problem: `expected exactly one <main>, found ${String(mains.length)}`,
    });
  }

  const landmarks = Object.keys(getRoles(container));
  for (const role of ['banner', 'navigation', 'main']) {
    if (!landmarks.includes(role)) {
      findings.push({ where: 'document', problem: `no ${role} landmark` });
    }
  }

  return findings;
}

/**
 * Everything else the structure audit checks, one finding per problem.
 *
 * It is deliberately a list rather than an assertion: a test that fails with "expected
 * 0, got 1" tells the next person nothing about *which* element is wrong.
 */
export function auditStructure(container: HTMLElement): Finding[] {
  const findings: Finding[] = [];

  const headings = [...container.querySelectorAll('h1')];
  if (headings.length !== 1) {
    findings.push({
      where: 'document',
      problem: `expected exactly one h1, found ${String(headings.length)}`,
    });
  }

  for (const table of container.querySelectorAll('table')) {
    const headers = [...table.querySelectorAll('th')];
    if (headers.length === 0) continue;
    const unscoped = headers.filter((header) => !header.hasAttribute('scope'));
    if (unscoped.length > 0) {
      findings.push({
        where: describe(table),
        problem: `${String(unscoped.length)} of ${String(headers.length)} headers have no scope`,
      });
    }
  }

  for (const element of container.querySelectorAll<HTMLElement>('[tabindex]')) {
    const value = Number.parseInt(element.getAttribute('tabindex') ?? '0', 10);
    if (value > 0) {
      findings.push({
        where: describe(element),
        problem: `positive tabindex ${String(value)} takes the element out of document order`,
      });
    }
  }

  // A control that is focusable but not natively operable is the mouse-only control in
  // disguise: a `div` with `tabindex="0"` and a click handler gets focus and does
  // nothing on Enter.
  for (const element of keyboardReachable(container)) {
    const tag = element.tagName.toLowerCase();
    const role = element.getAttribute('role');
    const native = ['a', 'button', 'input', 'select', 'textarea'].includes(tag);
    // Roles that carry their own keyboard interaction: an SVG node with `role="button"`
    // and a `role="slider"` handle are both operable without being native controls.
    const operable =
      role !== null &&
      ['button', 'link', 'checkbox', 'radio', 'switch', 'tab', 'slider'].includes(role);
    if (!native && !operable) {
      findings.push({
        where: describe(element),
        problem: 'focusable but neither a native control nor an operable role',
      });
    }
  }

  return findings;
}

/**
 * The reading order, as a list of what a screen reader would announce for one region.
 *
 * Used by the audit's report rather than by an assertion: it is the closest thing to a
 * transcript this environment can produce, and it is what makes a human check of the
 * order possible without a screen reader installed.
 */
export function readingOrder(container: HTMLElement): string[] {
  const roles = getRoles(container);
  const lines: string[] = [];
  for (const [role, elements] of Object.entries(roles)) {
    for (const element of elements) {
      const text = (element.textContent ?? '').trim().replace(/\s+/g, ' ');
      lines.push(`${role}: ${text.slice(0, 60)}`);
    }
  }
  return lines;
}

/**
 * Walk the screen with Tab, and report the controls focus never reached.
 *
 * §9's claim is "every action reachable and operable by keyboard", and this is the
 * only check that tests it as a whole: axe cannot see a control that is focusable but
 * skipped by the tab order, and no per-control test notices the control nobody wrote a
 * test for.
 *
 * The walk stops when focus returns to something it has already visited, so a screen
 * whose first control traps focus does not spin: what is reported is what was missed,
 * which is the finding either way.
 */
export async function auditKeyboard(
  container: HTMLElement,
  user: { tab: (options?: { shift?: boolean }) => Promise<void> },
): Promise<Finding[]> {
  const expected = interactiveControls(container);
  if (expected.length === 0) return [];

  // A control no tab stop can land on is unreachable by definition, and it is reported
  // separately from the walk below so the finding names the cause. The exception is the
  // roving-tabindex tablist, which is a pattern rather than an omission.
  const roving = tabsCoveredByRovingGroup(container);
  const findings: Finding[] = expected
    .filter((element) => isOutOfTabOrder(element) && !roving.has(element))
    .map((element) => ({
      where: describe(element),
      problem: 'a control that is not a tab stop, so the keyboard cannot reach it',
    }));
  // The walk follows tab stops only: a tab covered by its tablist's arrows is reached by
  // those arrows, which the panel's own test asserts, and no amount of tabbing reaches it.
  const walkable = expected.filter((element) => !isOutOfTabOrder(element));
  if (walkable.length === 0) return findings;

  // Start from a neutral position, the way an operator arriving at the screen does:
  // a control that is only reachable *because* something else already had focus is not
  // reachable by keyboard navigation. In a test the focused element is usually left
  // over from an earlier click, so this is also what makes the walk independent of
  // what the test did before it.
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur();

  const visited = new Set<Element>();
  const reached = (): number => walkable.filter((element) => visited.has(element)).length;
  // Two passes over the screen and a little slack: one pass is enough when focus starts
  // at the top, and the second covers the wrap a browser performs at the end of the
  // document. A trap that stops focus moving simply reports the rest as unreachable.
  const limit = walkable.length * 2 + 10;
  for (let step = 0; step < limit && reached() < walkable.length; step += 1) {
    await user.tab();
    const active = document.activeElement;
    if (active === null || active === document.body) continue;
    visited.add(active);
  }

  return [
    ...findings,
    ...walkable
      .filter((element) => !visited.has(element))
      .map((element) => ({
        where: describe(element),
        problem: 'not reachable by tabbing from the start of the screen',
      })),
  ];
}

/** The named list, for callers that want to assert a specific region exists. */
export function namedList(container: HTMLElement, name: string): HTMLElement {
  return within(container).getByRole('list', { name });
}
