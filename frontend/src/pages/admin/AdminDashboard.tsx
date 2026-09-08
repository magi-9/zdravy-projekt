import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, FileText, Loader2, Inbox, LockKeyhole, LockKeyholeOpen, RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useToast } from "../../context/ToastContext";
import { logger } from '../../lib/logger';
import { useScrollToHashRow, scrollToRowAndHighlight } from "../../lib/scrollToHashRow";
import { normalizeForSearch } from "../../lib/searchNormalize";
import ConfirmationModal from "../client/components/ui/ConfirmationModal";
import { AdminDateNav, Button, Card, Empty, Modal, Toggle, Checkbox, Textarea } from "./ui";
import GramageTable, { type TableSpec, type SpecSection, type SpecVydaj } from "./GramageTable";
import { dashboardMaxDate, dashboardDefaultDate } from "../../lib/businessDay";

const API = import.meta.env.VITE_API_URL || "/api";

// "Nastavenia tabuľky" (2.9.2026) — uložené per prehliadač, nech admin po
// kliknutí na škôlku (odchod z tejto stránky) a návrate späť nepríde o svoj
// výber sekcií/výdajov/diétnych klastrov. Nie je to zdieľané nastavenie
// prevádzky ani celku, len osobná preferencia toho, kto tabuľku pozerá —
// preto localStorage, nie backend.
const TABLE_PREFS_KEY = "zpa-gramage-table-prefs";
// Raňajky/obed/olovrant majú vlastné, na sebe nezávislé trasy aj tabuľky
// (#dashboard-per-meal-routes) — `mealType` si pamätá posledný otvorený tab.
type MealType = "breakfast" | "lunch" | "olovrant";
const MEAL_TYPES: { key: MealType; label: string }[] = [
  { key: "breakfast", label: "Raňajky" },
  { key: "lunch", label: "Obed" },
  { key: "olovrant", label: "Olovrant" },
];
interface TablePrefs {
  mealType: MealType;
  sections: string[];
  selectedVydaje: string[];
  showEmpty: boolean;
  clusterSummary: boolean;
  dietClusters: string[];
  expanded: boolean;
  mergeDiets: boolean;
}
function loadTablePrefs(): Partial<TablePrefs> {
  try {
    const raw = localStorage.getItem(TABLE_PREFS_KEY);
    return raw ? (JSON.parse(raw) as Partial<TablePrefs>) : {};
  } catch {
    return {};
  }
}
function saveTablePrefs(prefs: TablePrefs): void {
  try {
    localStorage.setItem(TABLE_PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // Súkromné okno / plné úložisko — preferencia sa proste nezapamätá.
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface Component {
  label: string;
  base_grams: string | null;
  unit?: string;
  is_exception?: boolean;
}

interface ColGroup {
  key: string;
  label: string;
  meal: string;
  variant: string;
  diet_name?: string | null;
  diet_color?: string;
  template_name: string;
  components: Component[];
}

interface SubRow {
  type: "standard" | "diet";
  meal: string;
  variant?: string;
  label: string;
  diet_color?: string;
  diet_base_colors?: string[];
  count: number;
  col_grams: string[][];
}

interface DietSummaryRow {
  name: string;
  color?: string;
  base_colors?: string[];
  count: number;
  col_grams: string[][];
}

interface ClientRow {
  client: string;
  client_id: number;
  row_key?: string;
  prevadzka_id?: number | null;
  delivery_note?: string;
  total_count: number;
  standard_total_count: number;
  standard_col_grams: string[][];
  diet_summary_rows: DietSummaryRow[];
  admin_order_note?: string;
  sub_rows: SubRow[];
}

interface CountStandardRow {
  name: string;
  count: number;
}

interface CountDietRow {
  label: string;
  count: number;
}

interface CountSection {
  meal: string;
  variant: string;
  diet_name?: string | null;
  label: string;
  standard: CountStandardRow[];
  diets: CountDietRow[];
}

interface DeliveryRouteGroup {
  id: number;
  name: string;
  driver?: string;
  departure_time?: string | null;
  note?: string;
  rows: ClientRow[];
}

interface DeliveryBlockGroup {
  id: number;
  name: string;
  routes: DeliveryRouteGroup[];
}

// Hotový popis tabuľky z backendu. Obrazovka aj PDF ho renderujú z rovnakého
// spec-u, takže sa nemajú ako rozísť — všetky rozhodnutia o poradí riadkov,
// textoch, číslach a triedach padli v gramage_table_spec.py.

interface GramageDashboard {
  date: string;
  meal_plan_id: number | null;
  col_groups: ColGroup[];
  rows: ClientRow[];
  blocks?: DeliveryBlockGroup[];
  unassigned_rows?: ClientRow[];
  totals: string[][];
  count_summary: CountSection[];
  diet_colors?: Record<string, string>;
  diet_base_colors?: Record<string, string[]>;
  spec: TableSpec;
}

type OrderMealKey = "breakfast" | "lunch" | "olovrant";

interface OrderMealSummary {
  menus?: Record<string, number>;
  diets?: Record<string, number>;
  categories?: Array<{
    name: string;
    menus: Record<string, number>;
    diets: Record<string, number>;
    total: number;
  }>;
  total: number;
}

interface OrderReportRow {
  // Riadok je na objednávku, nie na používateľa — EduPage prevádzky zdieľajú
  // jeden systémový login, takže `user_id` nie je unikátne.
  order_id: number;
  user_id: number;
  name: string;
  email: string;
  breakfast: OrderMealSummary;
  lunch: OrderMealSummary;
  olovrant: OrderMealSummary;
  total: number;
}

interface OrderReport {
  date: string;
  rows: OrderReportRow[];
  totals: Record<OrderMealKey, OrderMealSummary> & { grand: number };
}

interface ClosedDayResponse {
  date: string;
  is_closed: boolean;
}

// ── Date helpers ──────────────────────────────────────────────────────────────

// ── Main component ────────────────────────────────────────────────────────────

const AdminDashboard: React.FC = () => {
  const { apiFetch } = useAuth();
  const { error: toastError, success: toastSuccess } = useToast();
  const navigate = useNavigate();
  // Od 12:00 sa odomkne aj zajtrajšok — British School sa scrapuje o 12:15
  // deň vopred, tak jej riadok potrebuje byť vidno ešte pred tým (#535).
  const maxDate = useMemo(() => dashboardMaxDate(), []);
  const [date, setDate] = useState(() => dashboardDefaultDate());
  const [data, setData] = useState<GramageDashboard | null>(null);
  const [orderReport, setOrderReport] = useState<OrderReport | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [closedLoading, setClosedLoading] = useState(true);
  const [isClosed, setIsClosed] = useState(false);
  const [closeConfirmOpen, setCloseConfirmOpen] = useState(false);
  const [unlockConfirmOpen, setUnlockConfirmOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const closedRequestId = useRef(0);
  // Vyhľadávanie prevádzky v tabuľke (#573) — kolega ho používa z telefónu,
  // nech nemusí prehľadávať celý zoznam trás očami.
  const [tableSearch, setTableSearch] = useState("");
  // Hlavička sa zmestí do jedného riadku (2.9.2026) len vďaka tomu, že
  // search pole je zbalené do ikony a rozbaľuje sa až na hover/klik.
  const [searchOpen, setSearchOpen] = useState(false);
  // Poznámka prevádzky (#573) — editovateľná rovno z tabuľky namiesto obchádzky
  // cez Nastavenia prevádzky, keď treba škôlke rýchlo niečo odkázať.
  const [noteEdit, setNoteEdit] = useState<{ prevadzkaId: number; text: string } | null>(null);
  const [savingNote, setSavingNote] = useState(false);
  const [mealType, setMealType] = useState<MealType>(() => loadTablePrefs().mealType ?? "lunch");
  const [sections, setSections] = useState<string[]>(() => loadTablePrefs().sections ?? []);
  // Prázdny výber = všetky výdajné body; inak môže byť vybratých aj viac
  // (napr. Cluster A + B naraz).
  const [selectedVydaje, setSelectedVydaje] = useState<string[]>(() => loadTablePrefs().selectedVydaje ?? []);
  // "Nastavenia tabuľky" (2.9.2026) — predtým voľné filtre nad tabuľkou,
  // teraz v samostatnom modáli, nech tabuľka dostane celú výšku.
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Prázdne trasy (bez objednávok) sa defaultne UKAZUJÚ — inak to vyzerá,
  // akoby trasa vôbec neexistovala, nie že len nemá dáta.
  const [showEmpty, setShowEmpty] = useState(() => loadTablePrefs().showEmpty ?? true);
  const [clusterSummary, setClusterSummary] = useState(() => loadTablePrefs().clusterSummary ?? true);
  // Prázdny výber = diéty vo všetkých zobrazených clustroch (rovnaký "prázdne
  // = všetko" princíp ako sections/selectedVydaje).
  const [dietClusters, setDietClusters] = useState<string[]>(() => loadTablePrefs().dietClusters ?? []);
  // "Rozbaliť všetko" — namiesto zbaleného per-klienta riadku ukáže rovno
  // rozbalený PDF-formát (bez opakovaného medzisúčtu) priamo na obrazovke.
  const [expanded, setExpanded] = useState(() => loadTablePrefs().expanded ?? false);
  // "Použiť zlúčenie diét" (#568) — diéty, ktoré šéfkuchár označil ako
  // pripravované spolu so štandardom (viď /admin/diet-component-merge), sa
  // do tabuľky zlúčia. Default zapnuté, vypnutím sa tabuľka na chvíľu vráti
  // do "vždy zvlášť" pohľadu bez toho, aby sa uložené označenia zmazali.
  const [mergeDiets, setMergeDiets] = useState(() => loadTablePrefs().mergeDiets ?? true);

  // Zapamätanie "Nastavenia tabuľky" (viď loadTablePrefs vyššie) — uloží sa
  // pri každej zmene, nech admin po návrate zo škôlky vidí presne to, čo mal.
  useEffect(() => {
    saveTablePrefs({
      mealType,
      sections,
      selectedVydaje,
      showEmpty,
      clusterSummary,
      dietClusters,
      expanded,
      mergeDiets,
    });
  }, [mealType, sections, selectedVydaje, showEmpty, clusterSummary, dietClusters, expanded, mergeDiets]);

  // Prepnutie tabu jedla mení celú množinu stĺpcov/trás pod sebou — staré
  // "sections"/"selectedVydaje" (napr. "len Menu A") takmer isto nesedia na
  // nové jedlo, tabuľka pri prepnutí radšej naskočí kompletná ako by mala
  // ticho spadnúť na fallback (rovnaké chovanie ako neznámy filter v URL).
  const handleMealTypeChange = useCallback((next: MealType) => {
    setMealType(next);
    setSections([]);
    setSelectedVydaje([]);
  }, []);

  // Ktoré sekcie (raňajky / polievka / menu / olovrant), výdajné body a
  // ostatné "Nastavenia tabuľky" sa zobrazujú. Prázdny výber = kompletná
  // tabuľka. Rovnaký filter dostane obrazovka aj PDF, takže vytlačíš presne
  // to, čo vidíš.
  const sectionQuery = useMemo(() => {
    const parts = [
      `&meal_type=${mealType}`,
      ...sections.map((key) => `&section=${encodeURIComponent(key)}`),
      ...selectedVydaje.map((key) => `&vydaj=${encodeURIComponent(key)}`),
      ...dietClusters.map((key) => `&diet_cluster=${encodeURIComponent(key)}`),
    ];
    if (!showEmpty) parts.push("&show_empty=0");
    if (!clusterSummary) parts.push("&cluster_summary=0");
    if (expanded) parts.push("&expanded=1");
    if (!mergeDiets) parts.push("&merge_diets=0");
    return parts.join("");
  }, [mealType, sections, selectedVydaje, dietClusters, showEmpty, clusterSummary, expanded, mergeDiets]);

  const fetchData = useCallback(async (refresh = false) => {
    // Zámerne NEnulujeme `data`/`orderReport` pred fetchom — Nastavenia
    // tabuľky sú v samostatnom modáli podmienenom `data` (pozri nižšie), takže
    // vynulovanie by ho na chvíľu odmountovalo (bliknutie, strata scrollu).
    // Tabuľka nižšie tak počas prefiltrovania ukazuje starý obsah, kým
    // nepríde nový — mení sa len ona, modál zostáva na mieste.
    setLoading(true);
    setDashboardError(null);
    try {
      const refreshParam = refresh ? "&refresh=1" : "";
      const res = await apiFetch(`${API}/admin/meal-plans/gramage-dashboard/?date=${date}${sectionQuery}${refreshParam}`);
      if (res.ok) {
        const gramage: GramageDashboard = await res.json();
        setData(gramage);

        // Gramáž potrebuje vyplnené menu (col_groups). Keď menu ešte nie je zadané
        // — či už chýba plán úplne, alebo existuje prázdny — dotiahni aspoň počty
        // objednávok, nech admin vidí porcie namiesto prázdna.
        if (!gramage.meal_plan_id || gramage.col_groups.length === 0) {
          const reportRes = await apiFetch(`${API}/admin/summary/daily-report/?date=${date}`);
          setOrderReport(reportRes.ok ? await reportRes.json() : null);
        } else {
          setOrderReport(null);
        }
      } else {
        const body: { error?: { message?: string } } | null = await res.json().catch(() => null);
        setDashboardError(
          body?.error?.message || "Nepodarilo sa načítať tabuľku gramáže. Skúste ju obnoviť.",
        );
        setData(null);
        setOrderReport(null);
      }
    } catch (e) {
      logger.error(e);
      setDashboardError("Nepodarilo sa načítať tabuľku gramáže. Skúste ju obnoviť.");
    }
    finally { setLoading(false); }
  }, [apiFetch, date, sectionQuery]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleOpenNoteEdit = useCallback(
    (prevadzkaId: number) => {
      const row = data?.rows.find((r) => r.prevadzka_id === prevadzkaId);
      setNoteEdit({ prevadzkaId, text: row?.admin_order_note ?? "" });
    },
    [data],
  );

  const handleSaveNote = useCallback(async () => {
    if (!noteEdit) return;
    setSavingNote(true);
    try {
      const res = await apiFetch(`${API}/admin/facility-prevadzky/${noteEdit.prevadzkaId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_order_note: noteEdit.text }),
      });
      if (!res.ok) throw new Error("save failed");
      toastSuccess("Poznámka uložená.");
      setNoteEdit(null);
      await fetchData();
    } catch (e) {
      logger.error(e);
      toastError("Poznámku sa nepodarilo uložiť.");
    } finally {
      setSavingNote(false);
    }
  }, [apiFetch, noteEdit, fetchData, toastError, toastSuccess]);

  const fetchClosedState = useCallback(async () => {
    const requestId = ++closedRequestId.current;
    setClosedLoading(true);
    try {
      const res = await apiFetch(`${API}/admin/closed-days/?date=${date}`);
      if (!res.ok) throw new Error("closed-day status failed");
      const payload = await res.json() as ClosedDayResponse;
      if (requestId === closedRequestId.current) setIsClosed(payload.is_closed);
    } catch (e) {
      logger.error(e);
      if (requestId === closedRequestId.current) {
        setIsClosed(false);
        toastError("Nepodarilo sa overiť, či je deň uzavretý.");
      }
    } finally {
      if (requestId === closedRequestId.current) setClosedLoading(false);
    }
  }, [apiFetch, date, toastError]);

  useEffect(() => {
    void fetchClosedState();
  }, [fetchClosedState]);

  const handleExport = useCallback(async (fmt: "pdf", setFmt: (v: boolean) => void) => {
    setFmt(true);
    try {
      const res = await apiFetch(`${API}/admin/meal-plans/gramage-dashboard-${fmt}/?date=${date}${sectionQuery}`);
      if (!res.ok) { toastError("Chyba pri generovaní súboru."); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `gramaz_${mealType}_${date}.${fmt}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { logger.error(e); toastError("Chyba pri generovaní súboru."); }
    finally { setFmt(false); }
  }, [apiFetch, date, mealType, sectionQuery, toastError]);

  const submitClosedDayAction = useCallback(
    async (
      method: "POST" | "DELETE",
      url: string,
      setPending: (pending: boolean) => void,
      nextIsClosed: boolean,
      successMsg: string,
      genericFailMsg: string,
      failMarker: string,
    ) => {
      setPending(true);
      try {
        const res = await apiFetch(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ date }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body?.error?.message || failMarker);
        }
        setIsClosed(nextIsClosed);
        toastSuccess(successMsg);
      } catch (e) {
        logger.error(e);
        toastError(e instanceof Error && e.message !== failMarker ? e.message : genericFailMsg);
        await fetchClosedState();
      } finally {
        setPending(false);
      }
    },
    [apiFetch, date, fetchClosedState, toastError, toastSuccess],
  );

  const handleCloseDay = useCallback(
    () => submitClosedDayAction(
      "POST",
      `${API}/admin/closed-days/`,
      setClosing,
      true,
      "Deň bol uzavretý.",
      "Deň sa nepodarilo uzavrieť.",
      "close failed",
    ),
    [submitClosedDayAction],
  );

  const handleUnlockDay = useCallback(
    () => submitClosedDayAction(
      "DELETE",
      `${API}/admin/closed-days/unlock/`,
      setUnlocking,
      false,
      "Deň bol odomknutý.",
      "Deň sa nepodarilo odomknúť.",
      "unlock failed",
    ),
    [submitClosedDayAction],
  );

  // Tabuľka žije zo spec-u, takže sa aj jej prázdnosť posudzuje podľa neho.
  const hasData = Boolean(
    data && (data.spec.rows.length > 0 || data.spec.header.groups.length > 0),
  );
  const hasOrderCounts = Boolean(orderReport?.rows.some((row) => row.total > 0));

  useScrollToHashRow(hasData);

  // Enter v search poli (2.9.2026) — namiesto skrývania neshodujúcich sa
  // riadkov (to zmenšovalo tabuľku a pôsobilo, akoby dáta chýbali) len
  // odscrolluje na prvú zhodnú prevádzku, presne ako klik na jej meno.
  const handleSearchSubmit = () => {
    const term = normalizeForSearch(tableSearch);
    if (!term || !data) return;
    const match = data.rows.find(
      (row) => row.prevadzka_id != null && normalizeForSearch(row.client).includes(term),
    );
    if (match?.prevadzka_id != null) scrollToRowAndHighlight(`prevadzka-row-${match.prevadzka_id}`);
  };

  return (
    <>
      {/* Jeden kompaktný riadok namiesto PageHead s nadpisom/dátumovým popiskom
          (2.9.2026) — "Gramáž jedál" aj formátovaný dátum boli čistý text bez
          informačnej hodnoty navyše oproti samotnému dátumovému prepínaču.
          Dátum a search sú vľavo, akčné tlačidlá pevne vpravo (zpa-toolbar
          justify-content: space-between), nech pri zmene stavu (napr.
          "Deň je uzavretý") neposkakuje nič okrem tejto pravej skupiny. */}
      {/* Raňajky/obed/olovrant sú od #dashboard-per-meal-routes samostatné
          tabuľky (vlastné trasy aj poradie) — tab prepína, ktorú z troch
          práve vidno; nikdy sa nezlievajú do jednej. */}
      <div className="zpa-tabs" role="tablist" aria-label="Jedlo">
        {MEAL_TYPES.map((item) => (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={mealType === item.key}
            onClick={() => handleMealTypeChange(item.key)}
            className={`zpa-tab${mealType === item.key ? " active" : ""}`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="zpa-toolbar">
        <div className="zpa-toolbar-left">
          <AdminDateNav date={date} onChange={setDate} maxDate={maxDate} disabled={closing || unlocking} compact />

          <div className={`zpa-search-toggle${searchOpen || tableSearch ? " zpa-search-toggle--open" : ""}`}>
            <button
              type="button"
              className="zpa-navchip"
              onClick={() => setSearchOpen((v) => !v)}
              aria-label="Hľadať prevádzku"
              title="Hľadať prevádzku"
            >
              <Search size={16} />
            </button>
            <input
              type="text"
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleSearchSubmit(); } }}
              onFocus={() => setSearchOpen(true)}
              onBlur={() => { if (!tableSearch) setSearchOpen(false); }}
              placeholder="Hľadať prevádzku… (Enter odscrolluje)"
              className="zpa-search-input"
              aria-label="Hľadať prevádzku podľa mena"
            />
          </div>
        </div>

        <div className="zpa-toolbar-right">
          <Button
            variant="secondary"
            onClick={() => void fetchData(true)}
            disabled={loading}
            title="Znova načítať tabuľku priamo z databázy, bez čakania na automatický prepočet"
          >
            <RefreshCw className={loading ? "zpa-spin" : undefined} /> Obnoviť
          </Button>
          <Button variant="secondary" onClick={() => setSettingsOpen(true)} disabled={!hasData}>
            <SlidersHorizontal /> Nastavenia tabuľky
          </Button>
          <Button
            variant="danger"
            onClick={() => handleExport("pdf", setPdfLoading)}
            disabled={pdfLoading || loading || !hasData}
            title="Stiahnuť PDF"
          >
            {pdfLoading ? <Loader2 className="zpa-spin" /> : <FileText />} PDF
          </Button>
          {!closedLoading && !isClosed && (
            <Button
              variant="secondary"
              onClick={() => setCloseConfirmOpen(true)}
              disabled={closing}
              title="Uzamknúť deň"
              aria-label="Uzamknúť deň"
            >
              {closing ? <Loader2 className="zpa-spin" /> : <LockKeyhole />}
            </Button>
          )}
          {!closedLoading && isClosed && (
            <>
              <span role="status" style={{ color: "var(--green-700)", fontWeight: 700, whiteSpace: "nowrap" }}>
                <Check style={{ width: 16, verticalAlign: "middle", marginRight: 5 }} />
                Deň je uzavretý
              </span>
              <Button
                variant="secondary"
                onClick={() => setUnlockConfirmOpen(true)}
                disabled={unlocking}
                title="Odomknúť deň"
                aria-label="Odomknúť deň"
              >
                {unlocking ? <Loader2 className="zpa-spin" /> : <LockKeyholeOpen />}
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="zpa-stack">
        {/* Content */}
        {/* Kým beží prefiltrovanie (Nastavenia tabuľky) a staré dáta ešte
            máme, necháme tabuľku vidno (jemne stlmenú) namiesto toho, aby ju
            na chvíľu nahradil "Načítavam dáta…" — to by zhodilo scroll aj
            odmountovalo modál nad ňou. Placeholder patrí len prvému načítaniu. */}
        {loading && !data && <Empty>Načítavam dáta…</Empty>}
        {!loading && dashboardError && <Empty>{dashboardError}</Empty>}

        {!loading && data && !hasData && !hasOrderCounts && (
          <Empty icon={<Inbox />}>
            Pre tento deň nie sú žiadne dáta.
            {!data.meal_plan_id && (
              <span style={{ display: "block", marginTop: 4, fontSize: 12 }}>
                Jedálniček pre tento deň nebol naplánovaný.
              </span>
            )}
          </Empty>
        )}

        {data && hasData && (
          <div className="zpa-gram-fill" style={loading ? { opacity: 0.55, transition: "opacity .15s" } : undefined}>
            <GramageTable
              spec={data.spec}
              fill
              onClientNameClick={(id) => navigate(`/admin/facilities/${id}`)}
              onEditNote={handleOpenNoteEdit}
              alwaysExpanded={expanded}
            />
          </div>
        )}
        {!loading && data && !hasData && hasOrderCounts && orderReport && (
          <OrderCountsTable report={orderReport} />
        )}
      </div>

      <ConfirmationModal
        isOpen={closeConfirmOpen}
        onClose={() => setCloseConfirmOpen(false)}
        onConfirm={() => void handleCloseDay()}
        title="Uzamknúť objednávky na tento deň?"
        description="Po uzamknutí už nebude možné upravovať objednávky pre tento deň. Prípadné odomknutie bude vyžadovať samostatné potvrdenie."
        confirmText="Uzamknúť"
        variant="warning"
      />
      <ConfirmationModal
        isOpen={unlockConfirmOpen}
        onClose={() => setUnlockConfirmOpen(false)}
        onConfirm={() => void handleUnlockDay()}
        title="Odomknúť objednávky na tento deň?"
        description="Odomknutím sa deň znova otvorí na úpravy objednávok, diét a ďalších údajov."
        confirmText="Odomknúť"
        variant="warning"
      />

      {settingsOpen && data && (
        <TableSettingsModal
          sections={data.spec.sections}
          vydaje={data.spec.vydaje ?? []}
          dietClusters={dietClusters}
          showEmpty={showEmpty}
          clusterSummary={clusterSummary}
          expanded={expanded}
          mergeDiets={mergeDiets}
          onToggleSection={(key) =>
            setSections((current) =>
              toggleSelection(current, key, data.spec.sections.map((section) => section.key)),
            )
          }
          onToggleVydaj={(key) =>
            setSelectedVydaje((current) =>
              toggleSelection(current, key, (data.spec.vydaje ?? []).map((v) => v.key)),
            )
          }
          onToggleDietCluster={(key) =>
            setDietClusters((current) =>
              toggleSelection(current, key, (data.spec.vydaje ?? []).map((v) => v.key)),
            )
          }
          onShowEmptyChange={setShowEmpty}
          onClusterSummaryChange={setClusterSummary}
          onExpandedChange={setExpanded}
          onMergeDietsChange={setMergeDiets}
          onReset={() => {
            setSections([]);
            setSelectedVydaje([]);
            setDietClusters([]);
            setShowEmpty(true);
            setClusterSummary(true);
            setExpanded(false);
            setMergeDiets(true);
          }}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {noteEdit && (
        <Modal
          title="Poznámka pre prevádzku"
          onClose={() => (savingNote ? undefined : setNoteEdit(null))}
          foot={
            <>
              <Button variant="ghost" onClick={() => setNoteEdit(null)} disabled={savingNote}>Zrušiť</Button>
              <Button variant="primary" onClick={() => void handleSaveNote()} disabled={savingNote}>
                {savingNote ? <Loader2 className="zpa-spin" /> : null} Uložiť
              </Button>
            </>
          }
        >
          <Textarea
            rows={4}
            autoFocus
            value={noteEdit.text}
            placeholder="Interná poznámka k objednávkam prevádzky (vidno v tabuľke aj v PDF)."
            onChange={(e) => setNoteEdit({ ...noteEdit, text: e.target.value })}
          />
        </Modal>
      )}
    </>
  );
};

// ── OrderCountsTable ─────────────────────────────────────────────────────────

const MEAL_LABELS: Record<OrderMealKey, string> = {
  breakfast: "Raňajky",
  lunch: "Obed",
  olovrant: "Olovrant",
};

const MEAL_KEYS: OrderMealKey[] = ["breakfast", "lunch", "olovrant"];

function formatCounts(counts: Record<string, number>): string {
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([label, count]) => `${label}: ${count}`)
    .join(", ");
}

function mergeCounts(
  target: Record<string, number>,
  source: Record<string, number> | undefined,
) {
  for (const [label, count] of Object.entries(source ?? {})) {
    if (count > 0) target[label] = (target[label] ?? 0) + count;
  }
}

function mealMenus(meal: OrderMealSummary): Record<string, number> {
  const result: Record<string, number> = {};
  if (meal.categories?.length) {
    for (const category of meal.categories) mergeCounts(result, category.menus);
    return result;
  }
  mergeCounts(result, meal.menus);
  return result;
}

function mealDiets(meal: OrderMealSummary): Record<string, number> {
  const result: Record<string, number> = {};
  if (meal.categories?.length) {
    for (const category of meal.categories) mergeCounts(result, category.diets);
    return result;
  }
  mergeCounts(result, meal.diets);
  return result;
}

const OrderCountsTable: React.FC<{ report: OrderReport }> = ({ report }) => {
  const rows = report.rows.filter((row) => row.total > 0);

  return (
    <Card style={{ overflow: "hidden" }}>
      <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--line-soft)", background: "rgba(255,201,92,0.12)" }}>
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--mustard-700)" }}>
          Počty objednávok bez gramáže
        </div>
        <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 2 }}>
          Jedálniček pre tento deň nie je naplánovaný, preto sa zobrazujú iba objednané počty.
        </div>
      </div>
      <div className="zpa-table-wrap">
        <table className="zpa-table">
          <thead>
            <tr>
              <th style={{ minWidth: 220 }}>Prevádzka</th>
              {MEAL_KEYS.map((meal) => (
                <th key={meal} style={{ minWidth: 180 }}>{MEAL_LABELS[meal]}</th>
              ))}
              <th className="c" style={{ minWidth: 90 }}>Spolu</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.order_id}>
                <td>
                  <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--green-900)" }}>{row.name}</div>
                  <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{row.email}</div>
                </td>
                {MEAL_KEYS.map((meal) => {
                  const mealData = row[meal];
                  const menuText = formatCounts(mealMenus(mealData));
                  const dietText = formatCounts(mealDiets(mealData));
                  return (
                    <td key={meal} style={{ verticalAlign: "top" }}>
                      {mealData.total > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <div style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--green-900)" }}>
                            {mealData.total}
                          </div>
                          {menuText && <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{menuText}</div>}
                          {dietText && <div style={{ fontSize: 12, color: "var(--mustard-700)" }}>{dietText}</div>}
                        </div>
                      ) : (
                        <span style={{ color: "var(--line)" }}>—</span>
                      )}
                    </td>
                  );
                })}
                <td className="c" style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--green-900)" }}>
                  {row.total}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr style={{ background: "var(--bg-cream-soft)" }}>
              <td style={{ fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--green-800)" }}>Spolu</td>
              {MEAL_KEYS.map((meal) => (
                <td key={meal} style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--green-800)" }}>
                  {report.totals[meal].total > 0 ? report.totals[meal].total : "—"}
                </td>
              ))}
              <td className="c" style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums", color: "var(--green-900)" }}>
                {report.totals.grand}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
};

// ── Filter zobrazenia a tlače ────────────────────────────────────────────────
// Rovnaký výber ide na obrazovku aj do PDF — čo vidíš, to vytlačíš.

/**
 * Prepnutie jednej položky vo filtri. Prázdny výber znamená „všetko", takže
 * prvé odkliknutie musí vychádzať zo skutočne zobrazených položiek, nie z
 * prázdna; a keď sú nakoniec vybraté všetky, vraciame sa na prázdno.
 */
const toggleSelection = (current: string[], value: string, all: string[]): string[] => {
  const base = current.length ? current : all;
  const next = base.includes(value) ? base.filter((item) => item !== value) : [...base, value];
  return next.length === all.length ? [] : next;
};

/**
 * Všetky filtre a nastavenia tabuľky "Gramáž jedál" v jednom modáli (2.9.2026)
 * — predtým voľne nad tabuľkou (dva riadky chipov/dropdown), teraz tu, nech
 * tabuľka dostane celú výšku obrazovky. Rovnaký výber ide na obrazovku aj do
 * PDF — čo vidíš, to vytlačíš.
 */
const TableSettingsModal: React.FC<{
  sections: SpecSection[];
  vydaje: SpecVydaj[];
  dietClusters: string[];
  showEmpty: boolean;
  clusterSummary: boolean;
  expanded: boolean;
  mergeDiets: boolean;
  onToggleSection: (key: string) => void;
  onToggleVydaj: (key: string) => void;
  onToggleDietCluster: (key: string) => void;
  onShowEmptyChange: (v: boolean) => void;
  onClusterSummaryChange: (v: boolean) => void;
  onExpandedChange: (v: boolean) => void;
  onMergeDietsChange: (v: boolean) => void;
  onReset: () => void;
  onClose: () => void;
}> = ({
  sections,
  vydaje,
  dietClusters,
  showEmpty,
  clusterSummary,
  expanded,
  mergeDiets,
  onToggleSection,
  onToggleVydaj,
  onToggleDietCluster,
  onShowEmptyChange,
  onClusterSummaryChange,
  onExpandedChange,
  onMergeDietsChange,
  onReset,
  onClose,
}) => {
  const dietClusterOn = (key: string) => dietClusters.length === 0 || dietClusters.includes(key);
  return (
    <Modal
      title="Nastavenia tabuľky"
      onClose={onClose}
      icon={<SlidersHorizontal />}
      foot={
        <>
          <Button variant="ghost" onClick={onReset}>Obnoviť predvolené</Button>
          <Button variant="primary" onClick={onClose}>Hotovo</Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
          Filter jedál/clustra a prepínače nižšie (okrem „Zobraziť všetko rozbalené") sa tlačia aj do PDF exportu — vytlačíš presne to, čo vidíš na obrazovke.
        </div>
        <div>
          <div className="zpa-settings-lbl">Jedlá</div>
          <div className="zpa-section-filter">
            {sections.map((section) => (
              <button
                key={section.key}
                type="button"
                className={`chip${section.selected ? " on" : ""}`}
                aria-pressed={section.selected}
                onClick={() => onToggleSection(section.key)}
              >
                {section.label}
              </button>
            ))}
          </div>
        </div>

        {vydaje.length > 1 && (
          <div>
            <div className="zpa-settings-lbl">Cluster</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {vydaje.map((v) => (
                <Checkbox key={v.key} on={v.selected} onChange={() => onToggleVydaj(v.key)}>
                  {v.name}
                </Checkbox>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13.5 }}>Zobraziť prázdne prevádzky</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Prevádzky bez objednávok sa ukážu, nie skryjú.</div>
          </div>
          <Toggle on={showEmpty} onChange={onShowEmptyChange} ariaLabel="Zobraziť prázdne prevádzky" />
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13.5 }}>Zobraziť sumáre klastrov</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Pásy „SUMÁR CLUSTER ... S DIÉTAMI MŠ".</div>
          </div>
          <Toggle on={clusterSummary} onChange={onClusterSummaryChange} ariaLabel="Zobraziť sumáre klastrov" />
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13.5 }}>Použiť zlúčenie diét</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Diéty odklikané ako "spolu" (Zlúčenie diét) sa v tabuľke zlúčia so štandardom. Vypnuté = vždy zvlášť, bez ohľadu na odklikané.</div>
          </div>
          <Toggle on={mergeDiets} onChange={onMergeDietsChange} ariaLabel="Použiť zlúčenie diét" />
        </div>

        {clusterSummary && vydaje.length > 1 && (
          <div>
            <div className="zpa-settings-lbl">Diéty v sumári klastra</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {vydaje.map((v) => (
                <Checkbox key={v.key} on={dietClusterOn(v.key)} onChange={() => onToggleDietCluster(v.key)}>
                  {v.name}
                </Checkbox>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600, fontSize: 13.5 }}>Zobraziť všetko rozbalené</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Formát ako v PDF — bez zbaleného medzisúčtu za klienta. Samotné toto nastavenie sa do PDF nepremieta (PDF je vždy plne rozbalené).</div>
          </div>
          <Toggle on={expanded} onChange={onExpandedChange} ariaLabel="Zobraziť všetko rozbalené" />
        </div>
      </div>
    </Modal>
  );
};

// ── GramageTable ──────────────────────────────────────────────────────────────

export default AdminDashboard;
