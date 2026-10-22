# Manual accessibility pass (D-087, NFR-09)

Automated checks do not cover everything. This page is the script for the part that
needs a person with assistive technology. It is not done yet. Results go in the table at
the bottom, one row per page and per tool. Until those rows are filled in by a tester,
NFR-09's screen-reader and keyboard criteria remain **not verified**.

What the automated pass already covers, in real Chromium (`scripts/browser/`):

- axe-core with the WCAG 2.0 and 2.1 A and AA rules, on the landing page, the sign-in
  page, and the six signed-in routes (overview, triage, traffic, models, hunt, admin).
  Zero violations on all eight at the time of writing.
- Colour contrast, measured on the rendered pixels behind each text element. The
  median background passes AA everywhere. The worst single pixel does not, on the
  landing headline and its nav. The animated wireframe that caused it has since been removed (see the resolved note below).
  See the open item below.
- A keyboard Tab walk: every stop had a visible focus indicator, and no trap was found.

## What a tester must check

Use NVDA with Firefox on Windows, and VoiceOver with Safari on macOS. Test each page
in the table, signed in where the page requires it.

1. **Names and roles.** Every control announces a name and a role. Icon-only buttons
   announce what they do, not their glyph.
2. **Headings.** The heading outline reads as the page is laid out, with one `h1`.
3. **Landmarks.** Navigation, main, and any side panels are reachable by landmark.
4. **Forms.** Sign-in announces the email and password labels and any error text, and
   errors are announced when they appear.
5. **Live regions.** New alerts and status changes (the connection banner, the live
   counts) are announced once, not repeatedly and not never.
6. **Charts.** Each chart has a text alternative that gives the same information: the
   values, not only "chart".
7. **Keyboard only.** Every action works without a mouse, including the triage verdict
   buttons and the command palette. Focus is never lost after a dialog closes.
8. **Zoom.** The layout holds at 200% zoom without horizontal scrolling of text.
9. **Reduced motion.** With the OS reduced-motion setting on, the landing animation
   stops or is replaced.

## Resolved: landing headline over the animated wireframe

The animated 3D field has been removed from the landing hero, so no moving lines cross the
text. The hero is now a solid Vanilla Cloud ground with Stream Blue text (6.09:1), and every
text and control pair on the public pages uses the two brand colours and passes WCAG AA. The
pairs are listed in memory.md D-098. A screen-reader pass is still needed (item 4 below).

## Results

| Page     | Tool               | Tester | Date | Pass / fail | Notes |
| -------- | ------------------ | ------ | ---- | ----------- | ----- |
| Landing  | NVDA + Firefox     |        |      |             |       |
| Landing  | VoiceOver + Safari |        |      |             |       |
| Sign-in  | NVDA + Firefox     |        |      |             |       |
| Overview | NVDA + Firefox     |        |      |             |       |
| Triage   | NVDA + Firefox     |        |      |             |       |
| Traffic  | NVDA + Firefox     |        |      |             |       |
| Models   | NVDA + Firefox     |        |      |             |       |
| Hunt     | NVDA + Firefox     |        |      |             |       |
| Admin    | NVDA + Firefox     |        |      |             |       |
