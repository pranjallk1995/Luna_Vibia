import { Search } from "lucide-react";

type Props = {
  label: string;
  value: string;
  /** How many tracks match, once they have loaded. */
  count?: number;
  onChange: (value: string) => void;
};

export function SearchBox({ label, value, count, onChange }: Props) {
  return (
    <label className="lv-search">
      <Search size={17} aria-hidden="true" />
      <input
        type="search"
        aria-label={label}
        placeholder="Search by filename or tag"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {count !== undefined && (
        <span className="lv-search-count">
          {count} {count === 1 ? "track" : "tracks"}
        </span>
      )}
    </label>
  );
}
