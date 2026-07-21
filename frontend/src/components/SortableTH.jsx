import { ChevronUp, ChevronDown, ArrowUpDown } from "lucide-react";

/**
 * Clickable, sortable <th> — matches the pattern already established in
 * HR.jsx's EmployeeTable. Click toggles asc/desc; an ArrowUpDown icon shows
 * on hover for unsorted columns, a filled chevron for the active column.
 */
export function SortableTH({ label, field, sortBy, sortDir, onSort, align = "left", className = "", ...rest }) {
  const active = sortBy === field;
  return (
    <th
      onClick={() => onSort(field)}
      className={`px-3 py-2.5 text-xs font-semibold uppercase tracking-wider whitespace-nowrap cursor-pointer select-none group ${className}`}
      style={{ color: active ? "#a5b4fc" : "#6b7280", textAlign: align }}
      {...rest}
    >
      <span className={`inline-flex items-center gap-1 ${align === "center" ? "justify-center" : ""}`}>
        {label}
        <span className={`transition-opacity ${active ? "opacity-100" : "opacity-0 group-hover:opacity-50"}`}>
          {active
            ? (sortDir === "asc" ? <ChevronUp size={11} className="text-indigo-400" /> : <ChevronDown size={11} className="text-indigo-400" />)
            : <ArrowUpDown size={10} />}
        </span>
      </span>
    </th>
  );
}

/** Toggle helper: same field click flips direction, new field resets to asc. */
export function toggleSort(sortBy, sortDir, field) {
  return sortBy === field
    ? { sortBy: field, sortDir: sortDir === "asc" ? "desc" : "asc" }
    : { sortBy: field, sortDir: "asc" };
}

/** Generic client-side sort — pass the keys that hold numeric values. */
export function sortRows(rows, sortBy, sortDir, numericFields = []) {
  if (!sortBy) return rows;
  const numeric = numericFields.includes(sortBy);
  const mul = sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (numeric) return ((Number(a[sortBy]) || 0) - (Number(b[sortBy]) || 0)) * mul;
    const av = (a[sortBy] ?? "").toString().toLowerCase();
    const bv = (b[sortBy] ?? "").toString().toLowerCase();
    return av.localeCompare(bv) * mul;
  });
}
