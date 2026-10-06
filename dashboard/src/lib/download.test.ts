/**
 * Handing a file to the browser (T-415).
 *
 * `saveFile` is three lines of browser API and one discriminator, and the
 * discriminator is the part worth a test: a `Response`'s blob is not always an
 * instance of the page's own `Blob` (the test environment is one place where it is
 * not), and a document that gets re-wrapped loses the media type the server chose.
 * The rest of the file is asserted through the object URL and the anchor, because
 * those are what the browser actually reads.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { saveFile } from './download';

const URL_STUB = 'blob:aegis';

/** The two APIs jsdom does not implement, plus the click that would navigate. */
function stubBrowser() {
  const created: Blob[] = [];
  const revoked: string[] = [];
  const anchors: HTMLAnchorElement[] = [];
  const click = vi.fn(function (this: HTMLAnchorElement) {
    anchors.push(this);
  });
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: (blob: Blob) => {
      created.push(blob);
      return URL_STUB;
    },
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: (url: string) => {
      revoked.push(url);
    },
  });
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(click);
  return { created, revoked, anchors, click };
}

let browser: ReturnType<typeof stubBrowser>;

beforeEach(() => {
  browser = stubBrowser();
});

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(URL, 'createObjectURL');
  Reflect.deleteProperty(URL, 'revokeObjectURL');
});

describe('saveFile', () => {
  it('wraps text in a blob that carries the media type it was given', () => {
    saveFile({
      content: 'id,created_at\r\n1,2026-10-06T10:00:00+00:00\r\n',
      filename: 'a.csv',
      mediaType: 'text/csv',
    });

    expect(browser.created).toHaveLength(1);
    expect(browser.created[0]?.type).toBe('text/csv');
  });

  it('hands a blob over as it stands, rather than re-wrapping it', async () => {
    // The document the API returned, byte for byte, and from the realm the API
    // returns it in: `postExport` keeps the `Response`'s blob, which is *not* an
    // instance of this environment's `Blob` (`instanceof` across the two realms is
    // false), so an `instanceof` discriminator re-wraps it and replaces the
    // server's media type with this module's default.
    const document = await new Response('%PDF-1.4', {
      headers: { 'content-type': 'application/pdf' },
    }).blob();

    saveFile({ content: document, filename: 'aegis-alerts.pdf' });

    expect(browser.created[0]).toBe(document);
    expect(browser.created[0]?.type).toBe('application/pdf');
  });

  it('names the file what the server named it, and cleans the object URL up', () => {
    saveFile({ content: 'x', filename: 'aegis-alerts-2026-10-06.csv' });

    expect(browser.click).toHaveBeenCalledTimes(1);
    expect(browser.anchors[0]?.download).toBe('aegis-alerts-2026-10-06.csv');
    expect(browser.anchors[0]?.href).toContain(URL_STUB);
    expect(browser.revoked).toEqual([URL_STUB]);
    // The anchor is not left in the document: a link to a revoked blob URL would be
    // a dead control the next time anything looked for one.
    expect(document.querySelector('a')).toBeNull();
  });
});
