/**
 * Hunt console — `/hunt` (design.md §4.6, FR-51).
 *
 * A structured search over the alert read model, and the screen the rest of Explore
 * is built on. Three properties hold it together:
 *
 *   * **A hunt is a question, not a stream.** Nothing polls and nothing runs on a
 *     keystroke: the analyst writes a query, presses Run, and gets the window they
 *     asked for. The window is snapshotted at the moment it runs, so the sentence on
 *     an empty result — "searched … between …" — stays true while it is being read.
 *   * **What is searched is always on screen.** The echo above the table names the
 *     executed query and the window, including the parts the analyst did not type —
 *     the ordering and the row cap — and the empty state repeats both, because an
 *     empty table is the one place an analyst cannot tell a quiet network from a typo
 *     (design.md §4.6).
 *   * **What cannot be done is said, not omitted.** §4.6 asks for fields this build
 *     has no read model for (`src_ip`, `dst_port`, `template_id`) and for a "create
 *     alert from this filter" action. The console names the first as unsearchable
 *     terms with their reasons (T-418, T-419) and the second as unavailable with the
 *     reason there is no such write API: alerts are produced by the detection
 *     pipeline. A control that is absent with a reason beats one that looks as if it
 *     worked.
 */
import { useMemo, useState, type ReactNode } from 'react';

import { Button, EmptyState, ErrorState, Panel, Skeleton, useToast } from '../../../components/ui';
import { ApiError } from '../../../api/client';
import { sessionToken } from '../../../api/session';
import { QueryInput } from '../components/QueryInput';
import { ResultsTable } from '../components/ResultsTable';
import { SavedHunts } from '../components/SavedHunts';
import { exportRefusalMessage, useHuntExport, useHuntSearch } from '../hooks';
import {
  buildHuntParams,
  describeHunt,
  huntWindow,
  parseHuntQuery,
  spanOf,
  HUNT_SPANS,
  type HuntParse,
  type HuntSpan,
  type HuntWindow,
} from '../query';
import {
  rememberHunt,
  removeHunt,
  saveHunt,
  savedHunts,
  recentHunts,
  huntStoreSubject,
} from '../saved';
import { buildHuntView } from '../view';

/** One hunt that has been run: the parse, and the window it ran in. */
interface Run {
  parse: HuntParse;
  window: HuntWindow;
  spanKey: HuntSpan['key'];
}

export function HuntPage() {
  const [text, setText] = useState('');
  const [spanKey, setSpanKey] = useState<HuntSpan['key']>('24h');
  const [run, setRun] = useState<Run | null>(null);
  const subject = huntStoreSubject(sessionToken());
  const [saved, setSaved] = useState(() => savedHunts(subject));
  const [recent, setRecent] = useState(() => recentHunts(subject));

  // Two parses, and the difference matters: the live one drives the input's own error
  // list and the Run button, while the *run* parse is what the table, the echo and the
  // export describe. Editing the box after a run must not change what is on screen —
  // otherwise the table would be answering a question the analyst has already started
  // rewriting.
  const liveParse = useMemo(() => parseHuntQuery(text), [text]);
  const params = useMemo(
    () => (run === null ? null : buildHuntParams(run.parse, run.window)),
    [run],
  );
  const query = useHuntSearch(params, run !== null);
  const view = useMemo(
    () =>
      buildHuntView({
        page: query.data,
        parse: run?.parse ?? null,
        window: run?.window ?? null,
        failed: query.isError,
      }),
    [query.data, query.isError, run],
  );

  const exportation = useHuntExport();
  const huntError = query.error;
  const toast = useToast();
  const refusal = exportRefusalMessage(exportation.error);

  const start = (parse: HuntParse, key: HuntSpan['key']): void => {
    setRun({ parse, window: huntWindow(key, Date.now()), spanKey: key });
    if (parse.errors.length === 0) {
      // Recent hunts record the *canonical* echo, so re-running one from the dropdown
      // is the query that actually executed rather than the keystrokes that led to it.
      setRecent(rememberHunt(subject, describeHunt(parse), new Date()));
    }
  };

  const runHunt = (): void => {
    if (liveParse.errors.length > 0) return;
    start(liveParse, spanKey);
  };

  // Changing the window while a hunt is on screen re-runs it: the window control is
  // what the table is about, and a result set that disagreed with the selector above
  // it would be the screen lying about what was searched.
  const changeSpan = (key: HuntSpan['key']): void => {
    setSpanKey(key);
    if (run !== null) start(run.parse, key);
  };

  const download = (csv: string): void => {
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'aegis-hunt.csv';
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const span = spanOf(spanKey);
  const summary: string =
    view.state === 'rows' || view.state === 'empty'
      ? view.truncated
        ? `Showing the newest ${String(view.rowCount)} of a longer result — this read stops at the row cap. Narrow the window or the filters, or export the query.`
        : `${String(view.rowCount)} row${view.rowCount === 1 ? '' : 's'} in ${view.windowLabel ?? span.label}.`
      : '';

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-h1">Hunt</h1>
        <p className="text-body-sm text-muted">
          Search alerts by severity, status, family, entity and score over a window you choose.
          Every run is a bounded read: the newest rows of the window, up to the row cap.
        </p>
      </header>

      <Panel title="Query">
        <div className="flex flex-col gap-4">
          <QueryInput
            value={text}
            onChange={setText}
            onRun={runHunt}
            errors={liveParse.errors}
            disabled={query.isFetching}
          />

          <div className="flex flex-wrap items-end gap-4">
            <div className="flex items-center gap-2">
              <label className="text-caption text-muted" htmlFor="hunt-span">
                Window
              </label>
              <select
                id="hunt-span"
                value={spanKey}
                onChange={(event) => {
                  changeSpan(event.target.value as HuntSpan['key']);
                }}
                className="h-8 rounded-input border border-line bg-surface px-2 text-body-sm text-ink"
              >
                {HUNT_SPANS.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <Button onClick={runHunt} disabled={liveParse.errors.length > 0 || query.isFetching}>
              {query.isFetching ? 'Searching…' : 'Run hunt'}
            </Button>

            <Button
              variant="secondary"
              disabled={params === null || exportation.isPending}
              onClick={() => {
                if (params === null) return;
                exportation.mutate(params, {
                  onSuccess: (result) => {
                    download(result.csv);
                    toast(
                      'success',
                      `Exported ${String(result.rows)} rows as CSV. The export is recorded in the audit trail.`,
                    );
                  },
                });
              }}
            >
              {exportation.isPending ? 'Exporting…' : 'Export CSV'}
            </Button>
          </div>

          <SavedHunts
            saved={saved}
            recent={recent}
            onLoad={(stored) => {
              setText(stored);
              start(parseHuntQuery(stored), spanKey);
            }}
            onSave={(name) => {
              setSaved(saveHunt(subject, name, text, new Date()));
            }}
            onForget={(name) => {
              setSaved(removeHunt(subject, name));
            }}
          />

          <p className="text-caption text-muted">
            Saving a hunt keeps the text in this browser; the export is the only part of this screen
            the server records. Creating an alert from a filter is not available in this build:
            alerts are written by the detection pipeline, and there is no API that creates one by
            hand.
          </p>

          {refusal === null ? null : (
            <p role="alert" className="text-caption text-severityText-critical">
              {refusal}
            </p>
          )}
        </div>
      </Panel>

      <Panel
        title="Results"
        actions={
          view.executed === null ? null : (
            <p className="text-caption text-muted" data-testid="hunt-echo">
              {`Searched ${view.executed} · ${view.windowLabel ?? ''}`}
            </p>
          )
        }
      >
        {resultBody()}
      </Panel>
    </div>
  );

  function resultBody(): ReactNode {
    if (view.state === 'idle') {
      return (
        <p className="text-body-sm text-muted">
          Nothing has been searched yet. Write a query and run it: the executed query and the window
          are shown here, so an empty result never has to be guessed at.
        </p>
      );
    }
    if (view.state === 'loading') return <Skeleton lines={6} label="Hunt results" />;
    if (view.state === 'error') {
      return (
        <ErrorState
          message="The hunt could not be read"
          detail={
            huntError instanceof ApiError && huntError.status === 400
              ? 'The API refused the query — the window or a filter is outside what it accepts. Nothing was searched.'
              : 'The read failed, so nothing is shown rather than a stale page.'
          }
          action={<Button onClick={() => void query.refetch()}>Retry</Button>}
        />
      );
    }
    return (
      <>
        <ResultsTable
          rows={view.rows}
          empty={
            <EmptyState
              title="No alert matched"
              description={view.emptyReason ?? 'The window is quiet for this query.'}
            />
          }
        />
        <p className="mt-2 text-caption text-muted">{summary}</p>
      </>
    );
  }
}
