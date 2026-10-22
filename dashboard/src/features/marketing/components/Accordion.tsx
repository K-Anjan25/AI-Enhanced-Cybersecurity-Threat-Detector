import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import type { FaqItem } from '../content';

/**
 * Accordion with one panel open at a time. Each button carries aria-expanded and
 * aria-controls, and each panel is a labelled region, so keyboard and screen-reader
 * users get the same structure as a mouse user.
 */
export function Accordion({ items }: { items: readonly FaqItem[] }) {
  const [open, setOpen] = useState<number | null>(0);
  const prefix = useId();

  return (
    <div className="grid gap-3">
      {items.map((item, index) => {
        const expanded = open === index;
        const buttonId = `${prefix}-button-${index}`;
        const panelId = `${prefix}-panel-${index}`;
        return (
          <div key={item.q} className="overflow-hidden rounded-card border border-line bg-surface">
            <h3 className="m-0">
              <button
                id={buttonId}
                type="button"
                aria-expanded={expanded}
                aria-controls={panelId}
                onClick={() => setOpen(expanded ? null : index)}
                className="flex w-full items-center justify-between gap-4 px-6 py-4 text-left text-h2 font-semibold text-ink hover:text-accent focus-visible:ring-2"
              >
                <span>{item.q}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={`size-icon-md shrink-0 text-accent transition-transform duration-panel ${expanded ? 'rotate-180' : ''}`}
                />
              </button>
            </h3>
            <div
              id={panelId}
              role="region"
              aria-labelledby={buttonId}
              hidden={!expanded}
              className="px-6 pb-6"
            >
              <p className="m-0 text-body text-muted">{item.a}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
