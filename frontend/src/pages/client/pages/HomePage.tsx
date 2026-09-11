import { useState, useEffect, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useIsPC } from "../../../hooks/useIsPC";
import {
  Plus,
  Calendar,
  UtensilsCrossed,
  Bot,
  XCircle,
  CalendarDays,
  PenLine,
  Lock,
  Clock,
  History,
  ChevronRight,
  Settings,
  Mail,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { useAuth } from "../../../context/auth";
import { useToast } from "../../../context/ToastContext";
import OrderSummaryModal from "../components/order/OrderSummaryModal";
import OrderService, { DailyOrder } from "../services/OrderService";
import { OrderRequestError } from "../hooks/useOrder";
import { stepBusinessDay, toDateKey } from "../../../lib/businessDay";
import TourOverlay from "../components/onboarding/TourOverlay";
import { logger } from '../../../lib/logger';
import { fetchAllPages } from '../../../lib/pagination';

const API_URL = import.meta.env.VITE_API_URL || "/api";

// Shape returned by GET /api/orders/planned/
interface PlannedDay {
  date: string;
  exists: boolean;
  is_auto: boolean | null;
  is_empty: boolean | null;
  totalPortions: number;
  mealCount: { breakfast: number; lunch: number; olovrant: number };
  predictedTotal: number;
  predictedMealCount: { breakfast: number; lunch: number; olovrant: number };
  predictedData?: DailyOrder;
}

type HistoryData = Record<string, Record<string, { menuCounts: Record<string, number>; diets?: Record<string, number> }>>;

// Jedna odoslaná objednávka = jedna prevádzka za daný deň.
interface HistoryPrevadzka {
  prevadzkaId: number | null;
  name: string;
  totalPortions: number;
  mealCount: { breakfast: number; lunch: number; olovrant: number };
  data: HistoryData;
}

// Riadok histórie je deň za celý celok; detail sa rozpadá na prevádzky.
interface HistoryOrder {
  date: string;
  totalPortions: number;
  mealCount: { breakfast: number; lunch: number; olovrant: number };
  data: HistoryData;
  prevadzky: HistoryPrevadzka[];
}

interface MonthlySummary {
  total: number;
  items: { label: string; count: number }[];
}

/** First workday strictly after today (Mon–Fri).
 *
 * Sviatky ani voľno prevádzky sa tu neriešia: je to len počiatočný dátum, ktorý
 * si `/api/orders/planned/` aj tak prepíše skutočným zoznamom dní na objednanie
 * (ten už `PrevadzkaClosure` rešpektuje). */
function firstNextWorkday(): string {
  const d = OrderService.getServerNow();
  return toDateKey(stepBusinessDay(d, 1) ?? d);
}

const HomePage = () => {
  const isPC = useIsPC();
  const navigate = useNavigate();
  const [plannedDays, setPlannedDays] = useState<PlannedDay[]>([]);
  const [historyOrders, setHistoryOrders] = useState<HistoryOrder[]>([]);
  const [allHistoryOrders, setAllHistoryOrders] = useState<HistoryOrder[]>([]);
  const [showAllHistory, setShowAllHistory] = useState(false);
  const [expandedHistoryDate, setExpandedHistoryDate] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [modalOrderData, setModalOrderData] = useState<any>(null);
  const [modalOrderId, setModalOrderId] = useState<number | null>(null);
  // Prevádzky, ktoré prispeli do súhrnu vo `openDayModal` (bez zvolenej
  // aktívnej prevádzky) — OrderSummaryModal to potrebuje ukázať, inak login
  // s objednávkou vo viacerých prevádzkach nevidí, za koho súhrn je.
  const [modalPrevadzkaNames, setModalPrevadzkaNames] = useState<string[]>([]);
  const [monthlySummary, setMonthlySummary] = useState<MonthlySummary>({
    total: 0,
    items: [],
  });
  const [predictedModalDay, setPredictedModalDay] = useState<PlannedDay | null>(
    null,
  );

  const { globalDeadlines, activePrevadzka, prevadzky } = useApp();
  const prevadzkaNameById = useMemo(
    () => new Map(prevadzky.map((p) => [p.id, p.nazov])),
    [prevadzky],
  );
  const { apiFetch, user } = useAuth();
  const toast = useToast();
  const getFriendlyOrderErrorMessage = (error: unknown) => {
    // Backend pošle presný dôvod (ktoré jedlo, aký termín) v `error.message` —
    // predtým sa tu zahadzoval a nahrádzal všeobecnou hláškou (incident
    // Vyšehradská, 2.9.2026).
    if (
      error instanceof OrderRequestError &&
      error.code === "order_deadline_passed"
    ) {
      return error.message || "Objednávku už nie je možné meniť, termín uplynul.";
    }
    return "Nepodarilo sa upraviť objednávku. Skúste to znova.";
  };

  const parseOrderActionError = async (response: Response) => {
    try {
      const payload = await response.clone().json();
      throw new OrderRequestError(
        payload?.error?.message || "Request failed",
        payload?.error?.code,
      );
    } catch (error) {
      if (error instanceof OrderRequestError) {
        throw error;
      }
      const text = await response.text();
      throw new OrderRequestError(text || "Request failed");
    }
  };

  const firstWorkday = firstNextWorkday();
  const _now = OrderService.getServerNow();
  const todayStr = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}-${String(_now.getDate()).padStart(2, "0")}`;
  const todayDay = plannedDays.find((d) => d.date === todayStr) ?? null;

  const isTodayEditable = (() => {
    if (!globalDeadlines) return false;
    const now = OrderService.getServerNow();
    return (["breakfast", "lunch", "olovrant"] as const).some((meal) => {
      if ((globalDeadlines as Record<string, unknown>)[`${meal}_day_before`]) return false;
      const rawTime = globalDeadlines[meal] || "10:00";
      const [hourStr, minuteStr] = rawTime.split(":");
      const hours = Number.isFinite(Number(hourStr)) ? Number(hourStr) : 10;
      const minutes = Number.isFinite(Number(minuteStr)) ? Number(minuteStr) : 0;
      const deadline = new Date(now);
      deadline.setHours(hours, minutes, 0, 0);
      return now < deadline;
    });
  })();

  useEffect(() => {
    if (!user) return;
    apiFetch(`${API_URL}/orders/planned/`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setPlannedDays)
      .catch(logger.error);
  }, [user, apiFetch]);

  useEffect(() => {
    if (!user) return;
    const now = OrderService.getServerNow();
    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    apiFetch(`${API_URL}/orders/planned/monthly-summary/?year=${year}&month=${month}`)
      .then((r) => (r.ok ? r.json() : { total: 0, items: [] }))
      .then((data) => setMonthlySummary({
        total: data.total || 0,
        items: Array.isArray(data.items) ? data.items : [],
      }))
      .catch(logger.error);
  }, [user, apiFetch]);

  useEffect(() => {
    if (!user) return;
    const fetchHistory = async () => {
      try {
        const items = await fetchAllPages<Record<string, unknown>>(apiFetch, `${API_URL}/orders/`);
        const today = OrderService.toLocalDateString(OrderService.getServerNow());
        // Deň môže mať objednávku vo viacerých prevádzkach jedného celku —
        // riadok histórie je deň, prevádzky sú jeho detail.
        const byDate = new Map<string, HistoryOrder>();

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        items.forEach((rec: any) => {
          if (rec.status !== "submitted" || rec.date >= today) return;
          const mealData: HistoryData = rec.data || {};
          let total = 0;
          const counts = { breakfast: 0, lunch: 0, olovrant: 0 };
          ["breakfast", "lunch", "olovrant"].forEach((meal) => {
            const mealObj = mealData[meal];
            if (!mealObj) return;
            Object.values(mealObj).forEach((cat) => {
              const menuCounts = cat?.menuCounts || {};
              const c = (Object.values(menuCounts) as number[]).reduce((a, b) => a + b, 0);
              total += c;
              counts[meal as keyof typeof counts] += c;
            });
          });
          if (total <= 0) return;

          const prevadzkaId = typeof rec.prevadzka === "number" ? rec.prevadzka : null;
          const day: HistoryOrder = byDate.get(rec.date) ?? {
            date: rec.date,
            totalPortions: 0,
            mealCount: { breakfast: 0, lunch: 0, olovrant: 0 },
            data: {},
            prevadzky: [],
          };
          day.totalPortions += total;
          (["breakfast", "lunch", "olovrant"] as const).forEach((meal) => {
            day.mealCount[meal] += counts[meal];
          });
          day.prevadzky.push({
            prevadzkaId,
            name: prevadzkaNameById.get(prevadzkaId ?? -1) ?? "Prevádzka",
            totalPortions: total,
            mealCount: counts,
            data: mealData,
          });
          byDate.set(rec.date, day);
        });

        const history = Array.from(byDate.values());
        // Pri jednej prevádzke je detail dňa priamo jej objednávka (ako doteraz).
        history.forEach((day) => {
          if (day.prevadzky.length === 1) day.data = day.prevadzky[0].data;
        });
        // Cache kľúč `order_<dátum>` prevádzku nerozlišuje, takže deň rozdelený
        // medzi viac prevádzok by si navzájom prepísal dáta — seeduj len jednoznačné dni.
        const toSeed = history
          .filter((day) => day.prevadzky.length === 1)
          .map((day) => ({ date: day.date, data: day.data }));
        history.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
        setAllHistoryOrders(history);
        setHistoryOrders(history.slice(0, 5));

        if (toSeed.length > 0) {
          const CHUNK_SIZE = 5;
          let index = 0;
          const processChunk = () => {
            const end = Math.min(index + CHUNK_SIZE, toSeed.length);
            for (; index < end; index++) {
              const item = toSeed[index];
              const key = `order_${item.date}`;
              if (!localStorage.getItem(key)) {
                localStorage.setItem(key, JSON.stringify({ ...item.data, status: "submitted" }));
              }
            }
            if (index < toSeed.length) {
              if (typeof window !== "undefined" && "requestIdleCallback" in window) {
                (window as unknown as { requestIdleCallback: (cb: () => void) => void }).requestIdleCallback(processChunk);
              } else {
                setTimeout(processChunk, 10);
              }
            }
          };
          if (typeof window !== "undefined" && "requestIdleCallback" in window) {
            (window as unknown as { requestIdleCallback: (cb: () => void) => void }).requestIdleCallback(processChunk);
          } else {
            setTimeout(processChunk, 10);
          }
        }
      } catch (e) {
        logger.error("Failed to fetch order history", e);
      }
    };
    fetchHistory();
  }, [user, apiFetch, prevadzkaNameById]);

  const openDayModal = async (date: string) => {
    try {
      // Bez prevádzky vráti backend 400, keď má login objednávku vo viac
      // prevádzkach naraz — rovnaký suffix ako v useOrder.
      if (activePrevadzka?.id) {
        const r = await apiFetch(`${API_URL}/orders/by-date/${date}/?prevadzka=${activePrevadzka.id}`);
        setModalPrevadzkaNames([]);
        if (r.ok) {
          const rec = await r.json();
          setModalOrderData(rec.data || {});
          setModalOrderId(rec.id ?? null);
        } else {
          setModalOrderData({});
          setModalOrderId(null);
        }
      } else {
        // Žiadna vybraná prevádzka (napr. hneď po odoslaní objednávky — OrderPage
        // úmyselne reštartuje výber pre ĎALŠIU objednávku, viď handleSubmit).
        // Bez toho by sa tu poslal request bez `?prevadzka=` a login s
        // objednávkou vo viacerých prevádzkach dostal 400 "MultipleObjectsReturned",
        // ktoré predošlá verzia tíško vyhodnotila ako "žiadna objednávka" — hoci
        // bola uložená (Benjamíny, 2.9.2026). Namiesto toho spýtame KAŽDÚ
        // prevádzku loginu a spočítame, čo naozaj existuje.
        const results = await Promise.all(
          prevadzky.map(async (p) => {
            try {
              const r = await apiFetch(`${API_URL}/orders/by-date/${date}/?prevadzka=${p.id}`);
              if (!r.ok) return null;
              const rec = await r.json();
              return rec.data && Object.keys(rec.data).length > 0
                ? { name: p.nazov, data: rec.data as HistoryData }
                : null;
            } catch {
              return null;
            }
          }),
        );
        setModalPrevadzkaNames(
          results.filter((r): r is { name: string; data: HistoryData } => r !== null).map((r) => r.name),
        );
        const merged: HistoryData = {};
        results.forEach((entry) => {
          if (!entry) return;
          const data = entry.data;
          (["breakfast", "lunch", "olovrant"] as const).forEach((meal) => {
            const mealObj = data[meal];
            if (!mealObj) return;
            merged[meal] = merged[meal] || {};
            Object.entries(mealObj).forEach(([category, catData]) => {
              const target = merged[meal][category] || { menuCounts: {}, diets: {} };
              const menuCounts = { ...target.menuCounts };
              Object.entries(catData.menuCounts || {}).forEach(([menu, count]) => {
                menuCounts[menu] = (menuCounts[menu] || 0) + count;
              });
              const diets = { ...target.diets };
              Object.entries(catData.diets || {}).forEach(([diet, count]) => {
                diets[diet] = (diets[diet] || 0) + count;
              });
              merged[meal][category] = { menuCounts, diets };
            });
          });
        });
        setModalOrderData(merged);
        // Súhrn za viac prevádzok nemá jedno ID na editáciu/vynulovanie —
        // OrderSummaryModal to už rieši (onZero je len keď modalOrderId !== null).
        setModalOrderId(null);
      }
    } catch {
      setModalOrderData({});
      setModalOrderId(null);
    }
    setSelectedDate(date);
  };

  const handlePlannedCardClick = (day: PlannedDay) => {
    const hasPrediction = !day.exists && day.predictedTotal > 0;
    if (!day.exists && hasPrediction) {
      setPredictedModalDay(day);
    } else if (!day.exists) {
      setModalOrderData({ breakfast: {}, lunch: {}, olovrant: {} });
      setModalOrderId(null);
      setSelectedDate(day.date);
    } else {
      openDayModal(day.date);
    }
  };

  const handleZeroPredicted = async (day: PlannedDay) => {
    try {
      // Karta dňa je súčet za celok, takže vynulovanie platí pre každú
      // prevádzku. Bez `prevadzka` by backend pri viacerých ani nevedel,
      // ktorej deň vynulovať, a vrátil by 400.
      const targets: (number | undefined)[] = prevadzky.length
        ? prevadzky.map((p) => p.id)
        : [activePrevadzka?.id];
      for (const prevadzkaId of targets) {
        const res = await apiFetch(`${API_URL}/orders/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            date: day.date,
            status: "submitted",
            ...(prevadzkaId ? { prevadzka: prevadzkaId } : {}),
            // Explicitné "chcem 0" pre všetky tri chody — auto-order cron
            // toto už nikdy nesmie ticho prepísať (Jarabinka 11.9.2026,
            // pozri `DailyOrder.touched_meals`).
            touched_meals: ["breakfast", "lunch", "olovrant"],
            data: { breakfast: {}, lunch: {}, olovrant: {} },
          }),
        });
        if (!res.ok) await parseOrderActionError(res);
      }
      setPlannedDays((prev) =>
        prev.map((d) =>
          d.date === day.date
            ? { ...d, exists: true, is_empty: true, is_auto: false, totalPortions: 0, mealCount: { breakfast: 0, lunch: 0, olovrant: 0 } }
            : d,
        ),
      );
      toast.success("Objednávka bola vynulovaná.");
    } catch (e) {
      logger.error(e);
      toast.error(getFriendlyOrderErrorMessage(e));
    } finally {
      setPredictedModalDay(null);
    }
  };

  const handleZeroExisting = async () => {
    if (!selectedDate || modalOrderId === null) return;
    try {
      const res = await apiFetch(`${API_URL}/orders/${modalOrderId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: "submitted",
          touched_meals: ["breakfast", "lunch", "olovrant"],
          data: { breakfast: {}, lunch: {}, olovrant: {} },
        }),
      });
      if (!res.ok) await parseOrderActionError(res);
      const date = selectedDate;
      setPlannedDays((prev) =>
        prev.map((d) =>
          d.date === date
            ? { ...d, exists: true, is_empty: true, is_auto: false, totalPortions: 0, mealCount: { breakfast: 0, lunch: 0, olovrant: 0 } }
            : d,
        ),
      );
      setSelectedDate(null);
      setModalOrderId(null);
      toast.success("Objednávka bola vynulovaná.");
    } catch (e) {
      logger.error(e);
      toast.error(getFriendlyOrderErrorMessage(e));
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(`${dateStr}T12:00:00`);
    return d.toLocaleDateString("sk-SK", { weekday: "short", day: "numeric", month: "long" });
  };

  const formatLongDate = (dateStr: string) => {
    const d = new Date(`${dateStr}T12:00:00`);
    return d.toLocaleDateString("sk-SK", { weekday: "long", day: "numeric", month: "long" });
  };

  const getTodayEyebrow = () => {
    const d = new Date(`${todayStr}T12:00:00`);
    const day = d.toLocaleDateString("sk-SK", { weekday: "long" });
    const date = d.toLocaleDateString("sk-SK", { day: "numeric", month: "long" });
    return `${day.charAt(0).toUpperCase() + day.slice(1)} · ${date}`;
  };

  const greeting = user?.billing_name
    ? `Dobrý deň, ${user.billing_name}.`
    : "Dobrý deň.";

  // Badge helpers using zp-* classes
  const PlannedBadge = ({ day }: { day: PlannedDay }) => {
    if (!day.exists) {
      return (
        <span className="zp-pill zp-pill--auto">
          <Bot className="w-3 h-3" style={{ width: 11, height: 11 }} />
          Automatická
        </span>
      );
    }
    if (day.is_empty) {
      return (
        <span className="zp-pill zp-pill--empty">
          <XCircle style={{ width: 11, height: 11 }} />
          Bez objednávky
        </span>
      );
    }
    if (day.is_auto) {
      return (
        <span className="zp-pill zp-pill--auto">
          <Bot style={{ width: 11, height: 11 }} />
          Automatická
        </span>
      );
    }
    return (
      <span className="zp-pill zp-pill--manual">
        <PenLine style={{ width: 11, height: 11 }} />
        Manuálna
      </span>
    );
  };

  // Shared sub-components for day cards (used in both mobile and PC)
  const TodaySection = () => {
    if (!todayDay) return null;
    const day = todayDay;
    const isEmpty = day.exists && day.is_empty;
    const isUnset = !day.exists;
    const hasPrediction = isUnset && day.predictedTotal > 0;
    const isAutoFilled = isUnset && hasPrediction;
    const totalPortions = day.exists && !day.is_empty ? day.totalPortions : isAutoFilled ? day.predictedTotal : null;
    const mealCount = day.exists && !day.is_empty ? day.mealCount : isAutoFilled ? day.predictedMealCount : null;

    return (
      <div data-tour-id="tour-today-section" className="zp-section">
        <h2>
          <Clock style={{ width: 18, height: 18 }} /> Dnešná objednávka
        </h2>
        <div
          className={`zp-day zp-day--today${isEmpty ? " zp-day--empty" : ""}`}
          onClick={() => handlePlannedCardClick(day)}
          role="button"
        >
          <div className="zp-day-top">
            <div className="zp-day-left">
              <div className="zp-day-icon">
                {isEmpty ? (
                  <XCircle style={{ width: 20, height: 20 }} />
                ) : isTodayEditable ? (
                  <Clock style={{ width: 20, height: 20 }} />
                ) : (
                  <Lock style={{ width: 20, height: 20 }} />
                )}
              </div>
              <div className="flex1">
                <div className="zp-day-title">
                  {formatDate(todayStr)}
                  <span className="pill-today">DNES</span>
                </div>
                {isTodayEditable ? (
                  <span className="zp-pill zp-pill--deadline">
                    <Clock style={{ width: 11, height: 11 }} />
                    {day.exists && !day.is_empty ? "Upraviť do termínu" : "Vytvoriť do termínu"}
                  </span>
                ) : (
                  <PlannedBadge day={day} />
                )}
              </div>
            </div>
            {totalPortions !== null && (
              <div className="zp-day-count">
                {totalPortions}
                <small>porcií</small>
              </div>
            )}
          </div>
          {mealCount !== null && (
            <div className="zp-meal-chips">
              {mealCount.breakfast > 0 && (
                <span className="zp-mchip zp-mchip--breakfast">Raňajky · {mealCount.breakfast}</span>
              )}
              {mealCount.lunch > 0 && (
                <span className="zp-mchip zp-mchip--lunch">Obed · {mealCount.lunch}</span>
              )}
              {mealCount.olovrant > 0 && (
                <span className="zp-mchip zp-mchip--olovrant">Olovrant · {mealCount.olovrant}</span>
              )}
            </div>
          )}
          {isUnset && !hasPrediction && (
            <p className="zp-day-hint">Na dnešný deň nebola vytvorená žiadna objednávka.</p>
          )}
          {isEmpty && (
            <p className="zp-day-hint">Bez objednávky. V tento deň vám nepríde žiadne jedlo.</p>
          )}
        </div>
      </div>
    );
  };

  const PlannedSection = ({ gridClass }: { gridClass?: string }) => (
    <div data-tour-id="tour-planned-section" className="zp-section">
      <h2>
        <CalendarDays style={{ width: 18, height: 18 }} /> Plánované objednávky
      </h2>
      <div className={gridClass}>
        {plannedDays
          .filter((d) => d.date !== todayStr)
          .map((day) => {
            const isEmpty = day.exists && day.is_empty;
            const isUnset = !day.exists;
            const hasPrediction = isUnset && day.predictedTotal > 0;
            const isAutoFilled = isUnset && hasPrediction;
            const totalPortions = day.exists && !day.is_empty ? day.totalPortions : isAutoFilled ? day.predictedTotal : null;
            const mealCount = day.exists && !day.is_empty ? day.mealCount : isAutoFilled ? day.predictedMealCount : null;

            return (
              <div
                key={day.date}
                className={`zp-day${isEmpty ? " zp-day--empty" : isUnset && !hasPrediction ? " zp-day--unset" : ""}`}
                onClick={() => handlePlannedCardClick(day)}
                role="button"
              >
                <div className="zp-day-top">
                  <div className="zp-day-left">
                    <div className="zp-day-icon">
                      {isEmpty ? (
                        <XCircle style={{ width: 20, height: 20 }} />
                      ) : isUnset ? (
                        <Bot style={{ width: 20, height: 20 }} />
                      ) : day.is_auto ? (
                        <Bot style={{ width: 20, height: 20 }} />
                      ) : (
                        <Calendar style={{ width: 20, height: 20 }} />
                      )}
                    </div>
                    <div className="flex1">
                      <div className="zp-day-title">{formatDate(day.date)}</div>
                      <PlannedBadge day={day} />
                    </div>
                  </div>
                  {totalPortions !== null && (
                    <div className="zp-day-count" style={totalPortions === 0 ? { color: "var(--ink-mute)" } : {}}>
                      {totalPortions}
                      <small>porcií</small>
                    </div>
                  )}
                </div>
                {mealCount !== null && (
                  <div className="zp-meal-chips">
                    {mealCount.breakfast > 0 && (
                      <span className="zp-mchip zp-mchip--breakfast">Raňajky · {mealCount.breakfast}</span>
                    )}
                    {mealCount.lunch > 0 && (
                      <span className="zp-mchip zp-mchip--lunch">Obed · {mealCount.lunch}</span>
                    )}
                    {mealCount.olovrant > 0 && (
                      <span className="zp-mchip zp-mchip--olovrant">Olovrant · {mealCount.olovrant}</span>
                    )}
                  </div>
                )}
                {isUnset && !hasPrediction && (
                  <p className="zp-day-hint">Žiadna história na predikciu</p>
                )}
                {isEmpty && (
                  <p className="zp-day-hint">Bez objednávky. V tento deň vám nepríde žiadne jedlo.</p>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );

  const MonthlySummarySection = ({ style }: { style?: React.CSSProperties }) => (
    <>
      <div className="zp-section">
        <h2>
          <CalendarDays style={{ width: 18, height: 18 }} /> Mesačný súhrn
        </h2>
      </div>
      <div className="zp-monthly" style={style}>
        <div className="eye">Tento mesiac</div>
        <h3>
          Mesačný súhrn
          <small>
            {new Date().toLocaleDateString("sk-SK", { month: "long", year: "numeric" })} · doteraz odoberané
          </small>
        </h3>
        <div className="zp-monthly-grid">
          {(() => {
            const MEAL_LABELS = new Set(["Raňajky", "Obed", "Olovrant"]);
            const mealItems = monthlySummary.items.filter((i) => MEAL_LABELS.has(i.label));
            const display = mealItems.length > 0 ? mealItems : [{ label: "Zatiaľ bez odberu", count: 0 }];
            return display;
          })().map((item) => (
            <div className="zp-monthly-stat" key={item.label}>
              <div className="num">{item.count}</div>
              <div className="lbl">{item.label}</div>
            </div>
          ))}
        </div>
        <div className="zp-monthly-foot">
          <span>Spolu</span>
          <span>
            <strong>{monthlySummary.total}</strong> porcií
          </span>
        </div>
      </div>
    </>
  );

  const HistorySection = () => (
    <div data-tour-id="tour-history-section" className="zp-section pc-hist">
      <h2 className="with-action">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <History style={{ width: 18, height: 18 }} /> História
        </span>
        {allHistoryOrders.length > 5 && (
          <button
            className="zp-btn zp-btn--ghost zp-btn--sm"
            onClick={() => setShowAllHistory((v) => !v)}
          >
            {showAllHistory ? "Menej ←" : `Viac (${allHistoryOrders.length}) →`}
          </button>
        )}
      </h2>

      {(showAllHistory ? allHistoryOrders : historyOrders).length === 0 ? (
        <div className="zp-empty">
          <UtensilsCrossed />
          <p style={{ margin: "8px 0 0", fontSize: 14 }}>História je prázdna</p>
        </div>
      ) : (
        (showAllHistory ? allHistoryOrders : historyOrders).map((order) => {
          const isSplit = order.prevadzky.length > 1;
          const isExpanded = expandedHistoryDate === order.date;
          return (
            <div key={order.date} style={{ marginBottom: 8 }}>
              <div
                className="zp-day"
                style={{ background: "var(--bg-cream-soft)" }}
                onClick={() => {
                  // Jedna prevádzka → rovno detail dňa. Viac → rozbaľ prevádzky.
                  if (isSplit) {
                    setExpandedHistoryDate(isExpanded ? null : order.date);
                    return;
                  }
                  setModalOrderData(order.data);
                  setSelectedDate(order.date);
                }}
                role="button"
                aria-expanded={isSplit ? isExpanded : undefined}
              >
                <div className="zp-day-top">
                  <div className="zp-day-left">
                    <div
                      className="zp-day-icon"
                      style={{ background: "rgba(114,136,75,0.12)", color: "var(--green-700)" }}
                    >
                      <Calendar style={{ width: 20, height: 20 }} />
                    </div>
                    <div className="pc-hist-body">
                      <div className="zp-day-title">{formatDate(order.date)}</div>
                      <span className="zp-pill" style={{ background: "rgba(114,136,75,0.16)", color: "var(--green-700)" }}>
                        Vybavená
                      </span>
                      {isSplit ? (
                        <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
                          {order.prevadzky.length} prevádzky · {isExpanded ? "skry rozpis" : "zobraz rozpis"}
                        </div>
                      ) : (
                        (["breakfast", "lunch", "olovrant"] as const).flatMap((meal) =>
                          Object.entries(order.data?.[meal] || {}).flatMap(([category, categoryData]) =>
                            Object.entries(categoryData?.diets || {})
                              .filter(([, count]) => count > 0)
                              .map(([dietName, count]) => (
                                <div key={`${order.date}-${meal}-${category}-${dietName}`} style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
                                  {category} · {dietName} · {count}x
                                </div>
                              ))
                          )
                        )
                      )}
                    </div>
                  </div>
                  <div className="zp-day-count" style={{ fontSize: 19 }}>
                    {order.totalPortions}
                    <small>porcií</small>
                  </div>
                </div>
              </div>

              {isSplit && isExpanded && (
                <div style={{ marginTop: 4, paddingLeft: 12 }}>
                  {order.prevadzky.map((p) => (
                    <div
                      key={`${order.date}-${p.prevadzkaId ?? p.name}`}
                      className="zp-day"
                      style={{ background: "var(--bg-cream-soft)", marginTop: 4 }}
                      onClick={() => {
                        setModalOrderData(p.data);
                        setSelectedDate(order.date);
                      }}
                      role="button"
                    >
                      <div className="zp-day-top">
                        <div className="zp-day-left">
                          <div className="pc-hist-body">
                            <div className="zp-day-title" style={{ fontSize: 14 }}>{p.name}</div>
                            {(["breakfast", "lunch", "olovrant"] as const).flatMap((meal) =>
                              Object.entries(p.data?.[meal] || {}).flatMap(([category, categoryData]) =>
                                Object.entries(categoryData?.diets || {})
                                  .filter(([, count]) => count > 0)
                                  .map(([dietName, count]) => (
                                    <div key={`${order.date}-${p.prevadzkaId}-${meal}-${category}-${dietName}`} style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
                                      {category} · {dietName} · {count}x
                                    </div>
                                  ))
                              )
                            )}
                          </div>
                        </div>
                        <div className="zp-day-count" style={{ fontSize: 16 }}>
                          {p.totalPortions}
                          <small>porcií</small>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );

  const modals = (
    <>
      <OrderSummaryModal
        isOpen={!!selectedDate}
        onClose={() => {
          setSelectedDate(null);
          setModalOrderId(null);
        }}
        orderDate={selectedDate ?? ""}
        orderData={modalOrderData}
        globalDeadlines={globalDeadlines}
        isAuto={!!plannedDays.find((d) => d.date === selectedDate)?.is_auto}
        onZero={modalOrderId !== null ? handleZeroExisting : undefined}
        prevadzkaNames={modalPrevadzkaNames}
        onDelete={() => {
          if (selectedDate) {
            setPlannedDays((prev) =>
              prev.map((d) =>
                d.date === selectedDate
                  ? { ...d, exists: false, is_auto: null, is_empty: null, totalPortions: 0, mealCount: { breakfast: 0, lunch: 0, olovrant: 0 } }
                  : d,
              ),
            );
            setHistoryOrders((prev) => prev.filter((o) => o.date !== selectedDate));
            setSelectedDate(null);
            setModalOrderId(null);
          }
        }}
      />
      <OrderSummaryModal
        isOpen={!!predictedModalDay}
        onClose={() => setPredictedModalDay(null)}
        orderDate={predictedModalDay?.date ?? ""}
        orderData={predictedModalDay?.predictedData}
        globalDeadlines={globalDeadlines}
        isPredicted
        predictedMealCount={predictedModalDay?.predictedMealCount}
        onZero={() => predictedModalDay && handleZeroPredicted(predictedModalDay)}
      />
    </>
  );

  if (isPC) {
    return (
      <div className="pc-wrap">
        {/* Hero CTA */}
        <a
          data-tour-id="tour-new-order-btn"
          href={`/order?date=${firstWorkday}`}
          className="pc-hero"
          onClick={(e) => { e.preventDefault(); navigate(`/order?date=${firstWorkday}`); }}
        >
          <div className="bubble">
            <Plus style={{ width: 28, height: 28 }} />
          </div>
          <div className="body">
            <div className="eye">Pripravte novú</div>
            <h3>Nová objednávka</h3>
            <div className="when">{formatLongDate(firstWorkday)}</div>
          </div>
          <div className="chev">
            <ChevronRight style={{ width: 22, height: 22 }} />
          </div>
        </a>

        <p className="zp-disclaimer">
          Objednávky sa automaticky preklápajú na ďalší deň, pokiaľ ich manuálne neupravíte.
        </p>

        <div className="pc-home-grid">
          <div className="pc-col">
            <TodaySection />
            <PlannedSection gridClass="pc-daygrid" />
          </div>
          <div className="pc-col">
            <MonthlySummarySection style={{ margin: 0 }} />
            <HistorySection />
          </div>
        </div>

        {modals}
        <TourOverlay />
      </div>
    );
  }

  return (
    <div className="zp-app">
      <div className="zp-grain" style={{ minHeight: "100%" }}>
        {/* Top bar */}
        <div className="zp-topbar">
          <img
            src="/logo-zdravy-projekt.png"
            alt="Zdravý projekt"
            style={{ height: 32, width: "auto", display: "block" }}
          />
          <div style={{ display: "flex", gap: 4 }}>
            <Link
              to="/inbox"
              className="zp-iconbtn"
              aria-label="Správy"
            >
              <Mail />
            </Link>
            <Link
              to="/settings"
              className="zp-iconbtn"
              aria-label="Nastavenia"
              data-tour-id="tour-profile-btn"
            >
              <Settings />
            </Link>
          </div>
        </div>

        {/* Greeting */}
        <div className="zp-greeting">
          <span className="zp-eyebrow">{getTodayEyebrow()}</span>
          <h1>{greeting}</h1>
          <p>Tu je váš týždeň v Zdravom projekte.</p>
        </div>

        {/* Hero CTA */}
        <Link
          data-tour-id="tour-new-order-btn"
          to={`/order?date=${firstWorkday}`}
          className="zp-hero-cta"
        >
          <span className="icon-bubble">
            <Plus style={{ width: 26, height: 26, strokeWidth: 1.8 }} />
          </span>
          <span className="body">
            <span className="eye">Pripravte novú</span>
            <h3>Nová objednávka</h3>
            <span className="when">{formatLongDate(firstWorkday)}</span>
          </span>
          <span className="chev">
            <ChevronRight style={{ width: 22, height: 22 }} />
          </span>
        </Link>

        {/* Auto-rollover disclaimer */}
        <p className="zp-disclaimer">
          Objednávky sa automaticky preklápajú na ďalší deň, pokiaľ ich manuálne neupravíte.
        </p>

        <TodaySection />
        <PlannedSection />

        <MonthlySummarySection />

        <HistorySection />

        {modals}
      </div>
      <TourOverlay />
    </div>
  );
};

export default HomePage;
