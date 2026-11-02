import { ArrowLeft, ArrowRight } from "lucide-react";

type Props = {
  page: number;
  count: number;
  onChange: (page: number) => void;
};

export function Pager({ page, count, onChange }: Props) {
  return (
    <nav className="lv-pager" aria-label="Pages">
      <button
        className="lv-button"
        type="button"
        aria-label="Previous page"
        disabled={page === 0}
        onClick={() => onChange(page - 1)}
      >
        <ArrowLeft size={18} />
      </button>
      <select
        className="lv-select"
        aria-label="Page"
        value={page}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {Array.from({ length: count }, (_, index) => (
          <option key={index} value={index}>
            Page {index + 1} of {count}
          </option>
        ))}
      </select>
      <button
        className="lv-button"
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
