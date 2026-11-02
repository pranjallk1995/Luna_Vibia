import { Search } from "lucide-react";

type Props = {
  label: string;
  value: string;
  onChange: (value: string) => void;
};

export function SearchBox({ label, value, onChange }: Props) {
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
    </label>
  );
}
