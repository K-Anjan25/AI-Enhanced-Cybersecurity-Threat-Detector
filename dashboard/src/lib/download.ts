/**
 * Handing a file to the browser (T-408, T-415).
 *
 * A download is an anchor click on an object URL rather than a navigation: the
 * document was fetched with the session's bearer token in a header, and letting the
 * browser navigate to it would either send no credential or put one in a URL.
 * `revokeObjectURL` runs immediately after the click -- the browser has already
 * taken its reference, and a blob held for the life of the tab is a leak.
 *
 * This lives in `lib` because two features hand files out (the hunt console's CSV
 * and the queue's CSV/PDF) and because jsdom needs it in one place to be stubbed in
 * one place: `URL.createObjectURL` is not implemented there.
 */

export interface DownloadFile {
  /** The document, as text or as bytes. */
  content: string | Blob;
  /** What the file is called. From the server's `Content-Disposition` when it said. */
  filename: string;
  /** The media type, used when `content` is text. */
  mediaType?: string;
}

/** Save one document to the operator's disk. */
export function saveFile(file: DownloadFile): void {
  // `typeof` rather than `instanceof Blob`: the blob a `Response` hands back is not
  // necessarily an instance of the environment's own `Blob` constructor (it is not in
  // jsdom, where the two come from different realms), and a misclassified blob would
  // be re-wrapped here -- silently losing the server's media type.
  const blob =
    typeof file.content === 'string'
      ? new Blob([file.content], { type: file.mediaType ?? 'text/plain;charset=utf-8' })
      : file.content;
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = file.filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
