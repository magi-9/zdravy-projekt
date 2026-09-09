import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Check, AlertTriangle, X, Upload, Smartphone } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useToast } from "../../context/ToastContext";
import { logger } from "../../lib/logger";
import { AdminDateNav, PageHead, Card } from "./ui";
import { dashboardDefaultDate, dashboardMaxDate } from "../../lib/businessDay";
import { useScrollToHashRow } from "../../lib/scrollToHashRow";

const API = import.meta.env.VITE_API_URL || "/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface OverviewCounts {
  breakfast: number;
  lunch: number;
  olovrant: number;
  total: number;
  standard_total: number;
  diet_counts: Record<string, number>;
}

interface OverviewRow {
  prevadzka_id: number;
  nazov: string;
  celok: string;
  delivered: boolean;
  delivery_status?: "missing" | "manual_zero" | "auto" | "manual";
  counts: OverviewCounts;
  flags: {
    attention: string[];
    config_notes: string[];
    unmapped_diets?: string[];
    uncertain_diets?: string[];
  };
  attention_dismissed: boolean;
  has_warning: boolean;
  pack_separately_enabled: boolean;
  adults_pack_separately_enabled: boolean;
  olovrant_s_obedom: boolean;
}

interface OverviewResponse {
  date: string;
  edupage: OverviewRow[];
  app: OverviewRow[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// ── Row ───────────────────────────────────────────────────────────────────────

// Hover popover pre riadky s `has_warning` — nahrádza pôvodný natívny
// browser `title` tooltip. `attention` sa dá po jednom dni odkliknúť ako
// vybavené ("OK, vybavené"): ostatné flagy (config_notes/unmapped/uncertain)
// sa dajú vyriešiť len opravou dát, dismiss tlačidlo teda dostane len
// `attention`. Odkliknutie platí len pre TENTO deň (`DailyOrder` je per
// prevádzka+deň) — nasledujúci deň má vlastný riadok, takže flag sa
// prirodzene znova ukáže, ak pretrváva.
const AttentionPopover: React.FC<{
  row: OverviewRow;
  date: string;
  onDismissed: () => void;
}> = ({ row, date, onDismissed }) => {
  const { apiFetch } = useAuth();
  const { error: toastError } = useToast();
  const [open, setOpen] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  const unmapped = (row.flags.unmapped_diets ?? []).map(
    (d) => `neznáma diéta z EduPage: ${d} — založ ju v appke`,
  );
  const uncertain = (row.flags.uncertain_diets ?? []).map(
    (d) => `neistá zhoda diéty z EduPage: ${d} — over, či je správne priradená`,
  );
  const canDismiss = row.flags.attention.length > 0 && !row.attention_dismissed;

  const handleDismiss = useCallback(async () => {
    setDismissing(true);
    try {
      const res = await apiFetch(`${API}/admin/summary/dismiss-attention/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prevadzka_id: row.prevadzka_id, date }),
      });
      if (!res.ok) throw new Error("dismiss failed");
      setOpen(false);
      onDismissed();
    } catch (e) {
      logger.error(e);
      toastError("Nepodarilo sa odkliknúť upozornenie.");
    } finally {
      setDismissing(false);
    }
  }, [apiFetch, date, onDismissed, row.prevadzka_id, toastError]);

  return (
    <span
      className="zpa-attnpop"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <span className="zpa-statusdot warn">
        <AlertTriangle />
      </span>
      {open && (
        <div className="zpa-attnpop-card" role="tooltip">
          <div className="zpa-attnpop-title">Dodané, ale skontroluj</div>
          <ul>
            {row.flags.config_notes.map((n) => (
              <li key={`c:${n}`}>{n}</li>
            ))}
            {row.flags.attention.map((n) => (
              <li key={`a:${n}`}>
                {n}
                {row.attention_dismissed && <span className="zpa-attnpop-done"> — vybavené</span>}
              </li>
            ))}
            {[...unmapped, ...uncertain].map((n) => (
              <li key={`u:${n}`}>{n}</li>
            ))}
          </ul>
          {canDismiss && (
            <button
              type="button"
              className="zpa-attnpop-btn"
              disabled={dismissing}
              onClick={handleDismiss}
            >
              <Check /> OK, vybavené
            </button>
          )}
        </div>
      )}
    </span>
  );
};

const StatusDot: React.FC<{
  row: OverviewRow;
  source: "edupage" | "app";
  date: string;
  onDismissed: () => void;
}> = ({ row, source, date, onDismissed }) => {
  if (source === "app") {
    if (row.delivery_status === "manual_zero") {
      return (
        <span className="zpa-statusdot zero" title="Manuálne odoslaná nulová objednávka">
          0
        </span>
      );
    }
    if (row.delivery_status === "auto") {
      return (
        <span className="zpa-statusdot warn" title="Automaticky skopírované z predchádzajúceho dňa">
          <AlertTriangle />
        </span>
      );
    }
    if (row.delivery_status === "manual") {
      return (
        <span className="zpa-statusdot ok" title="Manuálne zadané">
          <Check />
        </span>
      );
    }
  }

  if (!row.delivered) {
    return (
      <span className="zpa-statusdot err" title="Zatiaľ nedošlo nič">
        <X />
      </span>
    );
  }
  if (row.has_warning) {
    return <AttentionPopover row={row} date={date} onDismissed={onDismissed} />;
  }
  return (
    <span className="zpa-statusdot ok" title="Podklady dodané">
      <Check />
    </span>
  );
};

const MealCount: React.FC<{ label: string; value: number; strong?: boolean }> = ({ label, value, strong }) => (
  <div className="zpa-mealcount">
    <span className="k">{label}</span>
    <span className={`v${value > 0 || strong ? " on" : ""}${strong ? " strong" : ""}`}>{value}</span>
  </div>
);

const FacilityFlags: React.FC<{ row: OverviewRow; source: "edupage" | "app" }> = ({ row, source }) => {
  const automaticAdults = source === "edupage";
  const separatePackingEnabled = automaticAdults
    ? row.adults_pack_separately_enabled
    : row.pack_separately_enabled;
  const zvLabel = automaticAdults
    ? `EduPage: dospelí automaticky zvlášť — ${separatePackingEnabled ? "zapnuté" : "vypnuté"}`
    : `App: zabaliť zvlášť — ${separatePackingEnabled ? "zapnuté" : "vypnuté"}`;

  return (
    <div className={`zpa-ovflags${row.olovrant_s_obedom ? " zpa-ovflags--stacked" : ""}`}>
      <span className={`zpa-ovflag zv ${separatePackingEnabled ? "on" : "off"}`} aria-label={zvLabel} title={zvLabel}>ZV</span>
      {row.olovrant_s_obedom && (
        <span className="zpa-ovflag ol" aria-label="Olovrant sa vozí s obedom" title="Olovrant sa vozí s obedom">OL</span>
      )}
    </div>
  );
};

const OverviewRowItem: React.FC<{
  row: OverviewRow;
  source: "edupage" | "app";
  date: string;
  onDismissed: () => void;
}> = ({ row, source, date, onDismissed }) => {
  const showCelok = row.celok && row.celok !== row.nazov;
  const dietWarnings = [
    ...(row.flags.unmapped_diets ?? []),
    ...(row.flags.uncertain_diets ?? []),
  ];
  const dietEntries = Object.entries(row.counts.diet_counts ?? {}).filter(([, count]) => count > 0);
  return (
    <div className="zpa-ovrow" id={`prevadzka-row-${row.prevadzka_id}`}>
      <StatusDot row={row} source={source} date={date} onDismissed={onDismissed} />
      <FacilityFlags row={row} source={source} />
      <div style={{ minWidth: 0, flex: 1 }}>
        <Link to={`/admin/facilities/${row.prevadzka_id}`} className="zpa-ovrow-link" title="Otvoriť detail prevádzky">
          <div className="nm">{row.nazov}</div>
        </Link>
        {showCelok && <div className="sub">{row.celok}</div>}
        {/* Klasik hore, diéty pod tým — súčet vrátane detí s diétou ostáva
            v „Spolu" napravo (reálny počet na rozvoz), toto je len rozpis. */}
        {row.delivered && dietEntries.length > 0 && (
          <div className="sub">
            {`klasik ${row.counts.standard_total}, `}
            {dietEntries.map(([name, count]) => `${name} ${count}`).join(", ")}
          </div>
        )}
        {dietWarnings.length > 0 && (
          <div className="sub" style={{ color: "var(--mustard-700)" }}>
            {dietWarnings.join(", ")}
          </div>
        )}
      </div>
      <div className="zpa-ovcounts">
        <MealCount label="R" value={row.counts.breakfast} />
        <MealCount label="Ob" value={row.counts.lunch} />
        <MealCount label="Ol" value={row.counts.olovrant} />
        <div className="sep" />
        <MealCount label="Spolu" value={row.counts.total} strong />
      </div>
    </div>
  );
};

// ── Category card ─────────────────────────────────────────────────────────────

const CategoryCard: React.FC<{
  title: string;
  icon: React.ReactNode;
  rows: OverviewRow[];
  source: "edupage" | "app";
  date: string;
  onDismissed: () => void;
}> = ({ title, icon, rows, source, date, onDismissed }) => {
  const delivered = rows.filter((r) => r.delivered).length;
  const warnings = rows.filter((r) => r.delivered && (r.has_warning || r.delivery_status === "auto")).length;
  return (
    <Card style={{ overflow: "hidden" }}>
      <div className="zpa-card-head" style={{ padding: "16px 20px", borderBottom: "1px solid var(--line-soft)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ color: "var(--green-600)", display: "inline-flex" }}>{icon}</span>
          <h3>{title}</h3>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
          <span style={{ color: "var(--ink-3)" }}>{delivered}/{rows.length} dodané</span>
          {warnings > 0 && <span style={{ color: "var(--mustard-700)", fontWeight: 700 }}>{warnings} na kontrolu</span>}
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="zpa-empty" style={{ padding: "28px 20px" }}>Žiadne prevádzky.</div>
      ) : (
        <div>
          {rows.map((row) => (
            <OverviewRowItem
              key={row.prevadzka_id}
              row={row}
              source={source}
              date={date}
              onDismissed={onDismissed}
            />
          ))}
        </div>
      )}
    </Card>
  );
};

// ── Main component ────────────────────────────────────────────────────────────

const PrevadzkaOverview: React.FC = () => {
  const { apiFetch } = useAuth();
  const { error: toastError } = useToast();
  // "Termín dodania podkladov" nesmie pripadnúť na víkend — pri otvorení cez
  // víkend zobrazí stav za posledný predchádzajúci pracovný deň (piatok),
  // keďže cez víkend sa nič nedodáva a nasledujúci pondelok by ešte nemal dáta.
  // Rovnaké pravidlo ako gramážny dashboard (`dashboardDefaultDate`): od 21:00
  // (po večernom scrapi) sa predvolený pohľad sám preklopí na zajtrajšok,
  // pokiaľ ten sám nie je voľno (user 2.9.2026).
  const [date, setDate] = useState(() => dashboardDefaultDate());
  // Rovnaký cap ako gramážny dashboard (`AdminDashboard.tsx`) — dnes + 2
  // pracovné dni, zosúladené s hodinovým EduPage priebežným náhľadom, ktorý
  // dáta na toto okno priebežne dopĺňa.
  const maxDate = useMemo(() => dashboardMaxDate(), []);
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API}/admin/summary/prevadzka-overview/?date=${date}`);
      if (res.ok) {
        setData(await res.json());
      } else {
        toastError("Nepodarilo sa načítať prehľad prevádzok.");
      }
    } catch (e) {
      logger.error(e);
      toastError("Nepodarilo sa načítať prehľad prevádzok.");
    } finally {
      setLoading(false);
    }
  }, [apiFetch, date, toastError]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  useScrollToHashRow(!loading && data != null);

  return (
    <>
      <PageHead
        eyebrow="Prevádzky"
        title="Kontrola objednávok"
        desc="Prehľad, ktoré prevádzky za daný deň dodali objednávky."
        actions={<AdminDateNav date={date} onChange={setDate} maxDate={maxDate} compact />}
      />

      {loading ? (
        <div className="zpa-empty">Načítavam…</div>
      ) : (
        <div className="zpa-grid-2">
          <CategoryCard
            title="EduPage prevádzky"
            icon={<Upload />}
            rows={data?.edupage ?? []}
            source="edupage"
            date={date}
            onDismissed={fetchData}
          />
          <CategoryCard
            title="App prevádzky"
            icon={<Smartphone />}
            rows={data?.app ?? []}
            source="app"
            date={date}
            onDismissed={fetchData}
          />
        </div>
      )}
    </>
  );
};

export default PrevadzkaOverview;
