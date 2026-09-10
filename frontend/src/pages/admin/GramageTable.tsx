/**
 * Tabuľka gramáže — zdieľa ju admin Prehľad aj kuchyňský prehľad (#486).
 *
 * Celý obsah aj vzhľad riadi `spec` z backendu (`gramage_table_spec.py`), ktorý
 * renderuje aj PDF. Tu sa nič nerozhoduje, len prekladá na značky — preto je
 * komponent read-only zo svojej podstaty a kuchyňa cezeň nemá čo zmeniť.
 */

import React, { useMemo, useState } from 'react';
import { ChevronRight, Pencil } from 'lucide-react';
import { DietColorSwatch } from './DietColorSwatch';
import { Card } from './ui';
import { normalizeForSearch } from '../../lib/searchNormalize';

export interface SpecCell {
  text?: string;
  css?: string;
  colspan?: number;
  count?: string;
  /** Počet porcií pre konkrétnu gramážovú skupinu/menu. */
  corner_count?: string;
  sub?: string;
  meta?: string;
  meta_right?: string;
  note?: string | null;
  label?: string;
  swatch?: { color: string; base_colors: string[] };
  /** "S"/"Z" (10.9.2026, #568 nadväzba) — spolu/zvlášť na diet-component-merge
   * boarde, napr. "S" alebo composite "Z + S + Z". */
  pack_badge?: string;
}

export interface SpecRow {
  kind: string;
  css: string;
  cells: SpecCell[];
  group_id?: string;
  collapsible?: boolean;
  color?: string | null;
  /** Podfarbenie riadku diéty — hlavná/vedľajšia farba kombinovanej diéty (#536). */
  background?: string | null;
  /** Len na riadkoch `kind: "client"` — cieľ odklikávania naloženia (#487). */
  prevadzka_id?: number | null;
}

export interface SpecSection {
  key: string;
  label: string;
  selected: boolean;
}

export interface SpecVydaj {
  key: string;
  name: string;
  selected: boolean;
}

export interface TableSpec {
  total_columns: number;
  sections: SpecSection[];
  /** Výdajné body kuchyne — každý sa dá zobraziť a vytlačiť sám. */
  vydaje: SpecVydaj[];
  header: {
    corner: string;
    /** Nadradený pás hlavičky: Raňajky / Obed / Olovrant. */
    meals?: Array<{ text: string; css: string; colspan: number }>;
    groups: Array<{ text: string; sub: string; css: string; colspan: number }>;
    components: Array<{ text: string; sub: string; css: string }>;
  };
  rows: SpecRow[];
  footer: SpecRow[];
}

const SpecCells: React.FC<{ cells: SpecCell[] }> = ({ cells }) => (
  <>
    {cells.map((cell, index) => (
      <td key={index} className={cell.css || undefined} colSpan={cell.colspan}>
        {cell.corner_count !== undefined && (
          <span className="corner-count">{cell.corner_count}</span>
        )}
        {cell.count !== undefined ? (
          <span className="lbl-line">
            <span title={cell.text}>
              {cell.swatch && (
                <span style={{ display: "inline-flex", marginRight: 8 }}>
                  <DietColorSwatch color={cell.swatch.color} baseColors={cell.swatch.base_colors} size={9} />
                </span>
              )}
              {cell.text}
            </span>
            <span className="count-badge">{cell.count}</span>
            {cell.pack_badge && (
              <span className={`pack-badge${cell.pack_badge.includes("Z") ? " pack-badge--z" : ""}`}>
                {cell.pack_badge}
              </span>
            )}
          </span>
        ) : (
          cell.text
        )}
      </td>
    ))}
  </>
);

interface GramageTableProps {
  spec: TableSpec;
  className?: string;
  /**
   * Voliteľná akcia vpravo v riadku prevádzky. Admin Prehľad ju neposiela a
   * vyzerá presne ako predtým; kuchyňa cez ňu vešia odklikávanie naloženia.
   */
  renderClientAction?: (prevadzkaId: number) => React.ReactNode;
  /**
   * Voliteľný klik na názov prevádzky — otvorí jej detail (#527). Kuchyňa
   * ju neposiela, tam názov zostáva iba text.
   */
  onClientNameClick?: (prevadzkaId: number) => void;
  /**
   * Namiesto vlastného výškového stropu (`max-height: 100vh - ...`) sa tabuľka
   * roztiahne na celú výšku rodiča a roluje sa iba ona — okolie (dátum, filter)
   * tak zostáva stále na očiach. Admin Prehľad ju posiela, kuchyňa nie (#548).
   */
  fill?: boolean;
  /**
   * Voliteľné vyhľadávanie podľa mena prevádzky (#573) — Admin Prehľad ho
   * posiela z vlastného vyhľadávacieho poľa, kuchyňa nie. Bez neho sa
   * nefiltruje vôbec (prázdny reťazec má rovnaký efekt).
   */
  searchTerm?: string;
  /**
   * Voliteľná ceruzka pri mene prevádzky na úpravu jej internej poznámky
   * (#573) — otvorí editor v Admin Prehľade, samotný text nesie ClientRow z
   * dashboardu, nie táto (read-only) tabuľka. Kuchyňa ju neposiela.
   */
  onEditNote?: (prevadzkaId: number) => void;
  /**
   * "Zobraziť všetko rozbalené" (Nastavenia tabuľky, 2.9.2026) — vynúti
   * zobrazenie sub-riadkov/medzisúčtov pre KAŽDÉHO klienta, nezávisle od
   * lokálneho stavu rozbaleného/zbaleného (ktorý inak defaultne zbaľuje
   * úplne všetkých). Bez tohto by `include_summary_rows=false` poslané
   * backendu zmenilo len spec (zmizli by "Súčet bez diét" riadky), ale
   * sub-riadky by ostali skryté, kým ich admin sám nerozklikne — presne
   * opak "formátu ako v PDF" sľúbeného v popisku prepínača.
   */
  alwaysExpanded?: boolean;
}

const GramageTable: React.FC<GramageTableProps> = ({
  spec,
  className,
  renderClientAction,
  onClientNameClick,
  fill,
  searchTerm,
  onEditNote,
  alwaysExpanded,
}) => {
  const [expandedClients, setExpandedClients] = useState<string[]>([]);

  const toggleClient = (key: string) => {
    setExpandedClients((current) =>
      current.includes(key)
        ? current.filter((id) => id !== key)
        : [...current, key],
    );
  };

  // Riadok si nesie triedy aj farbu zo spec-u — tu sa už nič nerozhoduje,
  // len prekladá na značky (viď backend/api/exporters/gramage_table_spec.py).
  const renderRow = (row: SpecRow, index: number) => {
    const style =
      row.color || row.background
        ? { color: row.color ?? undefined, backgroundColor: row.background ?? undefined }
        : undefined;

    if (row.kind === "client") {
      const cell = row.cells[0];
      // #513 — poznámka prevádzky (ak je nastavená) ide rovno za názov na
      // tomto (vždy viditeľnom) riadku, nie len do collapsible note-admin
      // sub-riadku nižšie.
      const isExpanded = alwaysExpanded || expandedClients.includes(row.group_id ?? "");
      const action =
        renderClientAction && row.prevadzka_id != null
          ? renderClientAction(row.prevadzka_id)
          : null;
      const nameClickable = onClientNameClick && row.prevadzka_id != null;
      return (
        <tr key={index} id={row.prevadzka_id != null ? `prevadzka-row-${row.prevadzka_id}` : undefined} className={row.css}>
          <td colSpan={cell.colspan}>
            <div className="client-line">
              <button
                type="button"
                className="client-toggle"
                onClick={() => { if (!alwaysExpanded) toggleClient(row.group_id ?? ""); }}
              >
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span className={`chev${isExpanded ? " open" : ""}`}><ChevronRight size={15} /></span>
                  {nameClickable ? (
                    <span
                      className="client-name-link"
                      role="link"
                      tabIndex={0}
                      title="Otvoriť detail prevádzky"
                      onClick={(e) => {
                        e.stopPropagation();
                        onClientNameClick!(row.prevadzka_id!);
                      }}
                      onKeyDown={(e) => {
                        if (e.key !== "Enter" && e.key !== " ") return;
                        e.preventDefault();
                        e.stopPropagation();
                        onClientNameClick!(row.prevadzka_id!);
                      }}
                    >
                      {cell.text}
                    </span>
                  ) : (
                    cell.text
                  )}
                  <span className="meta">{cell.meta}</span>
                </span>
                {cell.note && <span className="client-note-inline">{cell.note}</span>}
                <span className="meta">{cell.meta_right}</span>
              </button>
              {onEditNote && row.prevadzka_id != null && (
                <button
                  type="button"
                  className="client-note-edit"
                  title="Upraviť poznámku pre prevádzku"
                  aria-label={`Upraviť poznámku pre ${cell.text}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onEditNote(row.prevadzka_id!);
                  }}
                >
                  <Pencil size={14} />
                </button>
              )}
              {action}
            </div>
          </td>
        </tr>
      );
    }

    if (row.kind === "route") {
      const cell = row.cells[0];
      return (
        <tr key={index} className={row.css}>
          <td colSpan={cell.colspan}>
            <span className="route-pill">
              <span title={cell.text}>{cell.text}</span>
              {cell.sub && <small>{cell.sub}</small>}
            </span>
          </td>
        </tr>
      );
    }

    if (
      row.kind === "note-admin" ||
      row.kind === "note-delivery" ||
      row.kind === "total-ms-porcie" ||
      row.kind === "cluster-ms-row"
    ) {
      const cell = row.cells[0];
      return (
        <tr key={index} className={row.css}>
          <td colSpan={cell.colspan}>
            <strong>{cell.label}</strong>{" "}
            <span style={{ whiteSpace: "pre-wrap" }}>{cell.text}</span>
          </td>
        </tr>
      );
    }

    return (
      <tr key={index} className={row.css} style={style}>
        <SpecCells cells={row.cells} />
      </tr>
    );
  };

  const mealBands = spec.header.meals ?? [];

  // Vyhľadávanie podľa mena prevádzky (#573) — filtruje klientske riadky a
  // všetko, čo pod nimi visí (group_id), plus trasy, pod ktorými by inak
  // nezostal ani jeden zhodný klient (prázdna trasa by pôsobila ako chyba).
  const term = searchTerm ? normalizeForSearch(searchTerm) : "";
  const searchedRows = useMemo(() => {
    if (!term) return spec.rows;
    const keptGroupIds = new Set(
      spec.rows
        .filter((row) => row.kind === "client" && normalizeForSearch(row.cells[0]?.text ?? "").includes(term))
        .map((row) => row.group_id ?? ""),
    );
    const keepRow = (row: SpecRow): boolean => {
      if (row.kind === "client") return keptGroupIds.has(row.group_id ?? "");
      if (row.group_id) return keptGroupIds.has(row.group_id);
      return row.kind !== "route";
    };
    const result: SpecRow[] = [];
    let pendingRoute: SpecRow | null = null;
    for (const row of spec.rows) {
      if (row.kind === "route") {
        pendingRoute = row;
        continue;
      }
      if (!keepRow(row)) continue;
      if (pendingRoute) {
        result.push(pendingRoute);
        pendingRoute = null;
      }
      result.push(row);
    }
    return result;
  }, [spec.rows, term]);

  // Podriadky, poznámky a medzisúčty klienta sa ukazujú až po rozbalení —
  // `alwaysExpanded` ("Zobraziť všetko rozbalené") to obchádza pre všetkých.
  const visibleRows = searchedRows.filter(
    (row) => !row.collapsible || alwaysExpanded || expandedClients.includes(row.group_id ?? ""),
  );

  return (
    <Card style={{ overflow: "hidden" }} className={fill ? "zpa-card--fill" : undefined}>
      <div className={`zpa-table-wrap zpa-gram-wrap${fill ? ' zpa-gram-wrap--fill' : ''}${className ? ` ${className}` : ''}`}>
        <table className="zpa-gram">
          <thead>
            {mealBands.length > 0 && (
              <tr>
                <th className="corner" rowSpan={3}>{spec.header.corner}</th>
                {mealBands.map((band, index) => (
                  <th key={index} className={band.css} colSpan={band.colspan}>
                    {band.text}
                  </th>
                ))}
              </tr>
            )}
            <tr>
              {mealBands.length === 0 && (
                <th className="corner" rowSpan={2}>{spec.header.corner}</th>
              )}
              {spec.header.groups.map((group, index) => (
                <th key={index} className={group.css} colSpan={group.colspan}>
                  {group.text}<small title={group.sub || undefined}>{group.sub}</small>
                </th>
              ))}
            </tr>
            <tr>
              {spec.header.components.map((component, index) => (
                <th key={index} className={component.css}>
                  {component.text}<small>{component.sub}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>{visibleRows.map(renderRow)}</tbody>
          <tfoot>{spec.footer.map(renderRow)}</tfoot>
        </table>
      </div>
    </Card>
  );
};

export default GramageTable;
