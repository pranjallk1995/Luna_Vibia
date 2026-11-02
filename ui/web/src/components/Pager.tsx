import { ArrowLeft, ArrowRight } from "lucide-react";

import { pageSlots } from "../lib";

type Props = {
  page: number;
  count: number;
  onChange: (page: number) => void;
};

/** Numbered pages to click directly; a single page needs no pager. */
export function Pager({ page, count, onChange }: Props) {
  if (count <= 1) return null;
  return (
    <nav className="lv-pager" aria-label="Pages">
      <button
        className="lv-pager-item lv-pager-step"
        type="button"
        aria-label="Previous page"
        disabled={page === 0}
        onClick={() => onChange(page - 1)}
      >
        <ArrowLeft size={18} />
      </button>
      {pageSlots(page, count).map((slot, index) =>
        slot === null ? (
          <span className="lv-pager-gap" key={`gap-${index}`} aria-hidden="true">
            …
          </span>
        ) : (
          <button
            className={slot === page ? "lv-pager-item lv-pager-current" : "lv-pager-item"}
            type="button"
            key={slot}
            aria-label={`Page ${slot + 1}`}
            aria-current={slot === page ? "page" : undefined}
            onClick={() => onChange(slot)}
          >
            {slot + 1}
          </button>
        ),
      )}
      <button
        className="lv-pager-item lv-pager-step"
        type="button"
        aria-label="Next page"
        disabled={page === count - 1}
        onClick={() => onChange(page + 1)}
      >
        <ArrowRight size={18} />
      </button>
    </nav>
  );
}
