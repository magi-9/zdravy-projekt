import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronDown, ChevronUp, KeyRound, Plus, Pencil, RotateCcw, Trash2, Copy, AlertTriangle, Send, Gauge, ClipboardCheck, Download, StickyNote } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useToast } from "../../context/ToastContext";
import AdminOrderEditorModal from "./AdminOrderEditorModal";
import ConfirmationModal from "../client/components/ui/ConfirmationModal";
import { logger } from '../../lib/logger';
import { Card, CardHead, Button, IconButton, Badge, Checkbox, Textarea, Modal, Empty, Toggle, SearchBox } from "./ui";
import { LoginFields, type Login, type LoginForm } from "./facility/LoginFields";
import { LoginPasswordStatusBadge } from "./facility/LoginPasswordStatus";
import { resendLoginInvite } from "./facility/loginInvite";
import { PrevadzkaFields, type EdupageConnectionOption, type PrevadzkaForm } from "./facility/PrevadzkaFields";
import { EMPTY_LOGIN } from "./facility/constants";
import PrevadzkaClosures from "./facility/PrevadzkaClosures";
import { DietColorSwatch } from "./DietColorSwatch";
import { toDateKey } from "../../lib/businessDay";

interface Diet {
  id: number;
  name: string;
  color?: string;
  base_colors?: string[];
}

interface PortionType {
  id: number;
  name: string;
  is_active: boolean;
}

interface UserProfile {
  is_edupage: boolean;
  api_identifier: string;
  company_name: string;
  billing_name?: string;
}

interface AdminUser {
  id: number;
  email: string;
  is_active: boolean;
  is_staff: boolean;
  profile: UserProfile | null;
}

interface FacilityDetail {
  id: number;
  celok: number;
  celok_nazov: string;
  nazov: string;
  adresa: string;
  edupage_connection: number | null;
  edupage_connection_name?: string | null;
  edupage_match: string;
  report_alias: string;
  delivery_note: string;
  sort_order: number;
  is_active: boolean;
  celok_zdroj_objednavok: string;
  visible_menus: string[];
  menu_day_restrictions?: Record<string, number[]> | null;
  visible_meals: string[];
  visible_diets: number[];
  visible_portion_types?: number[] | null;
  admin_order_note: string;
  client_user_id: number | null;
  pack_separately_enabled: boolean;
  adults_pack_separately_enabled: boolean;
  olovrant_s_obedom: boolean;
  orders_count: number | null;
  // Priradené diéty s poznámkou per (prevádzka, diéta) — pozri PrevadzkaDiet
  // na backende. Zdroj pre `dietNotes` pri načítaní; samotné priradenie
  // (ktoré diéty sú povolené) ostáva vo `visible_diets`.
  diet_assignments?: { diet: number; name: string; color?: string; note: string }[];
}

interface CelokDetail {
  id: number;
  nazov: string;
  logins: Login[];
}

interface OrderData {
  lunch?: unknown;
  soup?: string;
  breakfast?: unknown;
  olovrant?: unknown;
  special_diet_note?: unknown;
}

interface DailyOrder {
  id: number;
  date: string;
  status: string;
  data: OrderData;
}

interface ScrapeResult {
  connection_id: number;
  name: string;
  status: string;
  reason?: string;
  error?: string;
  warnings?: string[];
  unmapped_letters?: string[];
  config_notes?: string[];
  attention?: string[];
  orders?: { prevadzka: string; status: string; order_id: number }[];
}

// "D" a "VEGE1" nie sú tu — sú British School špecifiká (Cluster C, kusový
// sumár), spravované len cez seed/DB pre tú jednu prevádzku, nie ako
// všeobecná voľba pre každú (user 4.9.2026: "disabled teda neviditeľná inak
// pre british úplne rovnako ako menu Vege 1").
const ALL_MENUS = ["A", "B", "C", "V"];
const ALL_MEALS = ["breakfast", "lunch", "olovrant"];
// Dashboard zobrazí len pár posledných objednávok, kým admin nerozbalí celú
// históriu — ušetrí request/payload pre prevádzky s dlhou históriou.
const RECENT_ORDERS_LIMIT = 3;
// ISO deň v týždni: 1=pondelok..5=piatok (objednávky idú len na pracovné dni).
const WEEKDAYS: { day: number; label: string }[] = [
  { day: 1, label: "Po" },
  { day: 2, label: "Ut" },
  { day: 3, label: "St" },
  { day: 4, label: "Št" },
  { day: 5, label: "Pi" },
];
const API = import.meta.env.VITE_API_URL || "/api";
const MEAL_LABELS: Record<string, string> = {
  breakfast: "Raňajky",
  lunch: "Obed",
  olovrant: "Olovrant",
};

const ClientDetail: React.FC = () => {
  const { id: facilityId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { apiFetch } = useAuth();
  const { success, error: toastError, warning: toastWarning } = useToast();

  const [facility, setFacility] = useState<FacilityDetail | null>(null);
  const [user, setUser] = useState<AdminUser | null>(null);
  const [allDiets, setAllDiets] = useState<Diet[]>([]);
  const [portionTypes, setPortionTypes] = useState<PortionType[]>([]);
  const [connections, setConnections] = useState<EdupageConnectionOption[]>([]);
  const [celok, setCelok] = useState<CelokDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<"dashboard" | "udaje" | "objednavanie" | "diety" | "closures" | "logins" | "order_note">("dashboard");

  // Settings State
  const [menus, setMenus] = useState<Set<string>>(new Set());
  const [menuDayRestrictions, setMenuDayRestrictions] = useState<Record<string, number[]>>({});
  const [meals, setMeals] = useState<Set<string>>(new Set());
  const [userDiets, setUserDiets] = useState<Set<number>>(new Set());
  // Poznámka per (prevádzka, diéta) — kľúč je Diet.id. Edituje sa cez
  // popover na tabe Diéty, ukladá sa spolu s ostatnými nastaveniami.
  const [dietNotes, setDietNotes] = useState<Record<number, string>>({});
  const [dietSearch, setDietSearch] = useState("");
  const [dietNoteTarget, setDietNoteTarget] = useState<Diet | null>(null);
  const [dietNoteDraft, setDietNoteDraft] = useState("");
  const [visiblePortionTypes, setVisiblePortionTypes] = useState<Set<number> | null>(null);
  const [adminOrderNote, setAdminOrderNote] = useState("");
  const [packSeparatelyEnabled, setPackSeparatelyEnabled] = useState(false);
  const [adultsPackSeparatelyEnabled, setAdultsPackSeparatelyEnabled] = useState(false);
  const [olovrantSObedom, setOlovrantSObedom] = useState(false);
  const [prevadzkaForm, setPrevadzkaForm] = useState<PrevadzkaForm>({
    nazov: "",
    adresa: "",
    edupage_connection: null,
    edupage_match: "",
    report_alias: "",
    delivery_note: "",
    sort_order: 0,
    is_active: true,
  });

  // Login CRUD
  const [loginTarget, setLoginTarget] = useState<Login | null | undefined>(undefined);
  const [loginDeleteTarget, setLoginDeleteTarget] = useState<Login | null>(null);
  const [loginForm, setLoginForm] = useState<LoginForm>(EMPTY_LOGIN);
  const [loginSaving, setLoginSaving] = useState(false);
  const [loginDeleting, setLoginDeleting] = useState(false);

  // Prevádzka delete
  const [showDeleteFacility, setShowDeleteFacility] = useState(false);
  const [facilityDeleting, setFacilityDeleting] = useState(false);
  const [facilityDeleteError, setFacilityDeleteError] = useState("");

  // Dashboard State
  const [recentOrders, setRecentOrders] = useState<DailyOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [expandedOrderId, setExpandedOrderId] = useState<number | null>(null);
  // História objednávok sa načítava po stránkach — pri prevádzke s dlhou
  // históriou `fetchAllPages` (všetko naraz) trvalo neúnosne dlho.
  const [ordersPage, setOrdersPage] = useState(1);
  const [ordersHasNext, setOrdersHasNext] = useState(false);
  // Kým admin nerozbalí celú históriu, dashboard ťahá len posledné
  // `RECENT_ORDERS_LIMIT` objednávky (menej requestov/payloadu).
  const [historyExpanded, setHistoryExpanded] = useState(false);

  // Order actions
  const [deleteOrderTarget, setDeleteOrderTarget] = useState<DailyOrder | null>(null);
  const [resetOrderTarget, setResetOrderTarget] = useState<DailyOrder | null>(null);
  const [copyOrderTarget, setCopyOrderTarget] = useState<DailyOrder | null>(null);
  const [editOrderTarget, setEditOrderTarget] = useState<DailyOrder | null>(null);
  const [showNewOrderModal, setShowNewOrderModal] = useState(false);
  const [orderActionLoading, setOrderActionLoading] = useState(false);

  // Manuálny EduPage scrape (per prevádzka, ale reálne beží na celom
  // pripojení — pozri handleRunScrape).
  const [scrapeModalOpen, setScrapeModalOpen] = useState(false);
  const [scrapeDate, setScrapeDate] = useState(() => toDateKey(new Date()));
  const [scraping, setScraping] = useState(false);
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null);
  const facilityRequestSeq = useRef(0);

  // Password reset
  const [sendingReset, setSendingReset] = useState(false);
  const [showResetConfirmation, setShowResetConfirmation] = useState(false);

  // Resend pozvánky pre konkrétny login (pending/failed stav hesla)
  const [resendingLoginId, setResendingLoginId] = useState<number | null>(null);

  // Objednávka si diéty pamätá pod názvom, nie pod ID. Katalóg preto hľadáme
  // podľa mena, aby sme k nemu vedeli dokresliť farbu ako inde v admine.
  const dietByName = useMemo(
    () => new Map(allDiets.map((diet) => [diet.name, diet])),
    [allDiets],
  );

  const applyFacilitySettings = useCallback((data: FacilityDetail) => {
    setMenus(new Set(data.visible_menus?.length ? data.visible_menus : ALL_MENUS));
    setMenuDayRestrictions(data.menu_day_restrictions || {});
    setMeals(new Set(data.visible_meals?.length ? data.visible_meals : ALL_MEALS));
    setUserDiets(new Set(data.visible_diets || []));
    setDietNotes(
      Object.fromEntries((data.diet_assignments || []).map((a) => [a.diet, a.note])),
    );
    setVisiblePortionTypes(
      data.visible_portion_types == null
        ? null
        : new Set(data.visible_portion_types),
    );
    setAdminOrderNote(data.admin_order_note || "");
    setPackSeparatelyEnabled(!!data.pack_separately_enabled);
    setAdultsPackSeparatelyEnabled(!!data.adults_pack_separately_enabled);
    setOlovrantSObedom(!!data.olovrant_s_obedom);
    setPrevadzkaForm({
      nazov: data.nazov,
      adresa: data.adresa || "",
      edupage_connection: data.edupage_connection ?? null,
      edupage_match: data.edupage_match || "",
      report_alias: data.report_alias || "",
      delivery_note: data.delivery_note || "",
      sort_order: data.sort_order || 0,
      is_active: data.is_active,
    });
  }, []);

  const fetchCelok = useCallback(async (celokId: number) => {
    try {
      const res = await apiFetch(`${API}/admin/celky/${celokId}/`);
      if (res.ok) {
        const data = await res.json();
        setCelok(data);
        return;
      }
    } catch (e) {
      logger.error(e);
    }
    setCelok(null);
  }, [apiFetch]);

  const fetchUser = useCallback(async (userId: number): Promise<AdminUser | null> => {
    try {
      const res = await apiFetch(`${API}/admin/users/${userId}/`);
      if (res.ok) {
        const data = await res.json();
        return data;
      }
    } catch (e) {
      logger.error(e);
    }
    return null;
  }, [apiFetch]);

  const fetchFacility = useCallback(async () => {
    if (!facilityId) return null;
    const requestSeq = ++facilityRequestSeq.current;
    try {
      const res = await apiFetch(`${API}/admin/facility-prevadzky/${facilityId}/`);
      if (res.ok) {
        const data = await res.json();
        if (requestSeq !== facilityRequestSeq.current) return null;
        setFacility(data);
        applyFacilitySettings(data);
        await fetchCelok(data.celok);
        if (requestSeq !== facilityRequestSeq.current) return null;
        setUser(null);
        if (data.client_user_id) {
          const userData = await fetchUser(data.client_user_id);
          if (requestSeq !== facilityRequestSeq.current) return null;
          setUser(userData);
        }
        return data as FacilityDetail;
      }
      if (requestSeq !== facilityRequestSeq.current) return null;
      setFacility(null);
      return null;
    } catch (e) {
      logger.error(e);
      if (requestSeq !== facilityRequestSeq.current) return null;
      setFacility(null);
      return null;
    }
  }, [apiFetch, facilityId, fetchUser, fetchCelok, applyFacilitySettings]);

  const fetchConnections = useCallback(async () => {
    try {
      const res = await apiFetch(`${API}/admin/edupage-connections/`);
      if (res.ok) {
        const data = await res.json();
        setConnections(Array.isArray(data) ? data : data.results || []);
      }
    } catch (e) {
      logger.error(e);
    }
  }, [apiFetch]);

  const fetchDiets = useCallback(async () => {
    try {
      const res = await apiFetch(`${import.meta.env.VITE_API_URL || "/api"}/diets/`);
      if (res.ok) {
        const data = await res.json();
        setAllDiets(Array.isArray(data) ? data : data.results || []);
      }
    } catch (e) {
      logger.error(e);
    }
  }, [apiFetch]);

  const fetchPortionTypes = useCallback(async () => {
    try {
      const res = await apiFetch(`${import.meta.env.VITE_API_URL || "/api"}/admin/portion-types/`);
      if (res.ok) {
        const data = await res.json();
        const items: PortionType[] = Array.isArray(data) ? data : data.results || [];
        setPortionTypes(items.filter((item) => item.is_active));
      } else {
        setPortionTypes([]);
      }
    } catch (e) {
      logger.error(e);
      setPortionTypes([]);
    }
  }, [apiFetch]);

  const fetchOrders = useCallback(async () => {
    if (!facilityId) return;
    setOrdersLoading(true);
    try {
      const pageSizeQuery = historyExpanded ? "" : `&page_size=${RECENT_ORDERS_LIMIT}`;
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/orders/?prevadzka=${facilityId}&page=${ordersPage}${pageSizeQuery}`,
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // Backend vracia DRF stránkovanie ({results, next}); ošetri aj holé pole,
      // keby stránkovanie niekedy vypadlo.
      if (Array.isArray(data)) {
        setRecentOrders(data);
        setOrdersHasNext(false);
      } else {
        setRecentOrders(data.results ?? []);
        setOrdersHasNext(Boolean(data.next));
      }
    } catch (e) {
      logger.error(e);
    } finally {
      setOrdersLoading(false);
    }
  }, [apiFetch, facilityId, ordersPage, historyExpanded]);

  const handleSendPasswordReset = async () => {
    if (!user) return;
    setSendingReset(true);
    try {
      const res = await apiFetch(`${import.meta.env.VITE_API_URL || "/api"}/auth/password-reset/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email }),
      });
      if (res.ok) {
        success(`Reset link bol odoslaný na ${user.email}.`);
      } else {
        toastError("Nepodarilo sa odoslať reset link.");
      }
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri odosielaní reset linku.");
    } finally {
      setSendingReset(false);
    }
  };

  const handleResendInvite = async (login: Login) => {
    setResendingLoginId(login.user_id);
    const result = await resendLoginInvite(apiFetch, API, login);
    if (result.ok) {
      success(`Pozvánka bola znova odoslaná na ${login.email}.`);
      if (celok) await fetchCelok(celok.id);
    } else {
      toastError(result.detail || "Nepodarilo sa odoslať pozvánku.");
    }
    setResendingLoginId(null);
  };

  const handleDeleteOrder = async () => {
    if (!deleteOrderTarget || !facilityId) return;
    setOrderActionLoading(true);
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/orders/${deleteOrderTarget.id}/?prevadzka=${encodeURIComponent(facilityId)}`,
        { method: "DELETE" },
      );
      if (res.ok || res.status === 204) {
        success("Objednávka bola odstránená.");
        setDeleteOrderTarget(null);
        fetchOrders();
      } else {
        toastError("Nepodarilo sa odstrániť objednávku.");
      }
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri odstraňovaní objednávky.");
    } finally {
      setOrderActionLoading(false);
    }
  };

  const handleResetOrder = async () => {
    if (!resetOrderTarget || !facilityId) return;
    setOrderActionLoading(true);
    try {
      const res = await apiFetch(
        `${import.meta.env.VITE_API_URL || "/api"}/orders/${resetOrderTarget.id}/?prevadzka=${encodeURIComponent(facilityId)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data: {} }),
        },
      );
      if (res.ok) {
        success("Objednávka bola vynulovaná.");
        setResetOrderTarget(null);
        fetchOrders();
      } else {
        toastError("Nepodarilo sa vynulovať objednávku.");
      }
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri vynulovaní objednávky.");
    } finally {
      setOrderActionLoading(false);
    }
  };

  // Endpoint /orders/ je pri POST upsert na (prevadzka, date) — bezpečne
  // prepíše prípadnú existujúcu dnešnú objednávku (na to upozorňuje potvrdzovací modal).
  const handleCopyToToday = async () => {
    if (!copyOrderTarget || !facilityId || !facility) return;
    setOrderActionLoading(true);
    try {
      const today = toDateKey(new Date());
      const query = user?.id ? `?user_id=${encodeURIComponent(String(user.id))}` : "";
      const res = await apiFetch(`${API}/orders/${query}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: today, data: copyOrderTarget.data, prevadzka: facility.id }),
      });
      if (res.ok) {
        success("Objednávka bola skopírovaná na dnešný deň.");
        setCopyOrderTarget(null);
        fetchOrders();
      } else {
        const body = await res.json().catch(() => ({}));
        toastError(body?.error?.message || "Nepodarilo sa skopírovať objednávku.");
      }
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri kopírovaní objednávky.");
    } finally {
      setOrderActionLoading(false);
    }
  };

  // Scrape beží per EduPage pripojenie, nie per prevádzka — connection_id
  // môže patriť viacerým prevádzkam naraz (napr. Zdravé Brúško: 5 celkov na
  // jednom URL). Tlačidlo je na detaile jednej prevádzky, ale reálne prepíše
  // dáta všetkých prevádzok na tom istom pripojení — na to varuje modal a
  // presne to ukáže aj `orders` v `scrapeResult` po dobehnutí.
  const handleRunScrape = async () => {
    if (!facility?.edupage_connection) return;
    setScraping(true);
    setScrapeResult(null);
    try {
      const res = await apiFetch(`${API}/admin/edupage-connections/scrape/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: scrapeDate, connection_id: facility.edupage_connection }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        toastError(body?.error || "Načítanie z EduPage zlyhalo.");
        return;
      }
      const result: ScrapeResult | undefined = body?.results?.[0];
      setScrapeResult(result ?? null);
      if (!result || result.status === "error") {
        toastError(result?.error || "Načítanie z EduPage zlyhalo.");
      } else if (result.status === "empty" || result.status === "skipped") {
        toastWarning(`EduPage nevrátil žiadne dáta pre ${scrapeDate} (${result.reason || result.warnings?.join(", ") || "prázdny výsledok"}).`);
      } else {
        success(`Načítané z EduPage (${scrapeDate}): ${result.orders?.length ?? 0} prevádzok.`);
        fetchOrders();
      }
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri načítaní z EduPage.");
    } finally {
      setScraping(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    setFacility(null);
    setUser(null);
    setRecentOrders([]);
    setExpandedOrderId(null);
    setActiveTab("dashboard");
    setCelok(null);
    setHistoryExpanded(false);
    setOrdersPage(1);
    Promise.all([fetchFacility(), fetchDiets(), fetchPortionTypes(), fetchConnections()]).finally(() => setLoading(false));
  }, [fetchFacility, fetchDiets, fetchPortionTypes, fetchConnections]);

  useEffect(() => {
    if (activeTab === "dashboard") {
      fetchOrders();
    }
  }, [activeTab, fetchOrders]);

  const handleSave = async () => {
    if (!facility) return;
    setSaving(true);
    try {
      // Obmedzenie dní necháva len pre menu, ktoré ešte je vôbec zapnuté v
      // Viditeľnom menu, a len keď má naozaj vybraný aspoň jeden deň (prázdny
      // výber = "každý deň", netreba ho ukladať).
      const cleanedMenuDayRestrictions = Object.fromEntries(
        Object.entries(menuDayRestrictions).filter(
          ([menu, days]) => menus.has(menu) && days.length > 0,
        ),
      );
      const payload = {
        ...prevadzkaForm,
        visible_menus: Array.from(menus),
        menu_day_restrictions: cleanedMenuDayRestrictions,
        visible_meals: Array.from(meals),
        visible_diets: Array.from(userDiets),
        diet_notes: Object.fromEntries(
          Array.from(userDiets)
            .filter((id) => dietNotes[id])
            .map((id) => [String(id), dietNotes[id]]),
        ),
        visible_portion_types: visiblePortionTypes == null
          ? portionTypes.map((item) => item.id)
          : Array.from(visiblePortionTypes),
        admin_order_note: adminOrderNote,
        pack_separately_enabled: packSeparatelyEnabled,
        adults_pack_separately_enabled: adultsPackSeparatelyEnabled,
        olovrant_s_obedom: olovrantSObedom,
      };

      const res = await apiFetch(`${API}/admin/facility-prevadzky/${facility.id}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json().catch(() => null);
        if (data) {
          setFacility(data);
          applyFacilitySettings(data);
        }
        success("Nastavenia boli uložené.");
        navigate("/admin/facilities");
      } else {
        toastError("Nepodarilo sa uložiť nastavenia.");
      }
    } catch (e) {
      logger.error(e);
      toastError("Nastala chyba pri ukladaní nastavení.");
    } finally {
      setSaving(false);
    }
  };

  const openAddLogin = () => {
    if (!facility) return;
    setLoginTarget(null);
    setLoginForm({ ...EMPTY_LOGIN, company_name: facility.nazov });
  };

  const openEditLogin = (login: Login) => {
    setLoginTarget(login);
    setLoginForm({ email: login.email, company_name: login.company_name });
  };

  const closeLoginEditor = () => {
    setLoginTarget(undefined);
    setLoginForm(EMPTY_LOGIN);
  };

  const saveLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!facility || !loginForm.company_name.trim() || !loginForm.email.trim()) {
      toastError("Názov a email loginu sú povinné.");
      return;
    }
    setLoginSaving(true);
    try {
      const editing = loginTarget ?? null;
      const res = await apiFetch(
        editing ? `${API}/admin/users/${editing.user_id}/` : `${API}/admin/users/`,
        {
          method: editing ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: loginForm.email,
            company_name: loginForm.company_name,
            is_staff: false,
            is_active: true,
            celok: facility.celok,
            prevadzky: editing ? editing.prevadzka_ids : [facility.id],
          }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toastError(data?.error?.details?.email?.[0] || data?.email?.[0] || data?.error?.message || "Nepodarilo sa uložiť login.");
        return;
      }
      success(editing ? "Login bol upravený." : "Login bol vytvorený.");
      closeLoginEditor();
      await fetchCelok(facility.celok);
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri ukladaní loginu.");
    } finally {
      setLoginSaving(false);
    }
  };

  const deleteLogin = async () => {
    if (!facility || !loginDeleteTarget) return;
    setLoginDeleting(true);
    try {
      const res = await apiFetch(`${API}/admin/users/${loginDeleteTarget.user_id}/`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) {
        const data = await res.json().catch(() => ({}));
        toastError(data?.error?.message || "Nepodarilo sa odstrániť login.");
        return;
      }
      success(`Login „${loginDeleteTarget.email}“ bol odstránený.`);
      setLoginDeleteTarget(null);
      await fetchCelok(facility.celok);
    } catch (e) {
      logger.error(e);
      toastError("Chyba pri odstraňovaní loginu.");
    } finally {
      setLoginDeleting(false);
    }
  };

  const deleteFacility = async () => {
    if (!facility) return;
    setFacilityDeleting(true);
    setFacilityDeleteError("");
    try {
      const res = await apiFetch(`${API}/admin/facility-prevadzky/${facility.id}/`, { method: "DELETE" });
      if (res.ok || res.status === 204) {
        success(`Prevádzka „${facility.nazov}“ bola odstránená.`);
        navigate("/admin/facilities");
        return;
      }
      const data = await res.json().catch(() => ({}));
      setFacilityDeleteError(data?.error?.message || "Nepodarilo sa odstrániť prevádzku.");
    } catch (e) {
      logger.error(e);
      setFacilityDeleteError("Chyba pri odstraňovaní prevádzky.");
    } finally {
      setFacilityDeleting(false);
    }
  };

  const toggleSet = <T,>(set: Set<T>, value: T, setter: (s: Set<T>) => void) => {
    const newSet = new Set(set);
    if (newSet.has(value)) newSet.delete(value);
    else newSet.add(value);
    setter(newSet);
  };

  const openDietNote = (diet: Diet) => {
    setDietNoteTarget(diet);
    setDietNoteDraft(dietNotes[diet.id] || "");
  };

  const saveDietNoteDraft = () => {
    if (!dietNoteTarget) return;
    setDietNotes((prev) => ({ ...prev, [dietNoteTarget.id]: dietNoteDraft }));
    setDietNoteTarget(null);
  };

  if (loading) return <div className="zpa-empty">Načítavam…</div>;
  if (!facility) return <div className="zpa-empty" style={{ color: "var(--coral-600)" }}>Prevádzka nenájdená</div>;

  const isEdupageClient = facility.celok_zdroj_objednavok === "edupage" || user?.profile?.is_edupage === true;
  const canResetPassword = Boolean(user && !user.profile?.is_edupage);
  const orderEditorMenus = Array.from(menus);
  const portionTypeNames = portionTypes
    .filter((item) => visiblePortionTypes == null || visiblePortionTypes.has(item.id))
    .map((item) => item.name);
  const orderEditorMeals = Array.from(meals);
  const orderEditorDiets = Array.from(userDiets);
  const facilityLogins = (celok?.logins ?? []).filter((login) => login.prevadzka_ids.includes(facility.id));
  const assignedDiets = allDiets.filter((diet) => userDiets.has(diet.id));
  const dietSearchQuery = dietSearch.trim().toLowerCase();
  const dietSearchResults = dietSearchQuery
    ? allDiets.filter((diet) => !userDiets.has(diet.id) && diet.name.toLowerCase().includes(dietSearchQuery))
    : [];

  const mealCount = (data: unknown): number => {
    let count = 0;
    if (data && typeof data === "object") {
      Object.values(data).forEach((cat: unknown) => {
        const category = cat as { menuCounts?: Record<string, number> };
        if (category?.menuCounts) count += Object.values(category.menuCounts).reduce((a, b) => a + Number(b), 0);
      });
    } else if (typeof data === "string" && data) {
      count = 1;
    } else if (data === true) {
      count = 1;
    }
    return count;
  };

  const tabs: { key: typeof activeTab; label: string }[] = [
    { key: "dashboard", label: "Prehľad objednávok" },
    { key: "udaje", label: "Údaje" },
    { key: "objednavanie", label: "Objednávanie" },
    { key: "diety", label: "Diéty" },
    { key: "closures", label: "Voľno" },
    { key: "logins", label: "Loginy" },
    { key: "order_note", label: "Poznámka k objednávke" },
  ];

  return (
    <>
      <div style={{ maxWidth: 1040, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>
        <div>
          <button className="zpa-btn zpa-btn--ghost zpa-btn--sm" onClick={() => navigate("/admin/facilities")} style={{ marginBottom: 16, paddingLeft: 0 }}>
            <ChevronLeft /> Späť na správu prevádzok
          </button>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <span className="zpa-avatar-sm" style={{ width: 60, height: 60, fontSize: 24 }}>{facility.nazov.charAt(0).toUpperCase()}</span>
              <div>
                <h1 style={{ fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 700, color: "var(--green-900)", margin: 0 }}>
                  {facility.nazov}
                </h1>
                <p style={{ color: "var(--ink-3)", margin: "4px 0 0" }}>{facility.celok_nazov}</p>
                {facility.adresa && (
                  <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "2px 0 0" }}>{facility.adresa}</p>
                )}
                {isEdupageClient && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                    <Badge tone="teal">Edupage prevádzka</Badge>
                    {user?.profile?.api_identifier && (
                      <span style={{ fontSize: 13, color: "var(--ink-3)", fontFamily: "ui-monospace, monospace" }}>ID: {user.profile.api_identifier}</span>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <Button
                variant="secondary"
                onClick={() => navigate(`/admin/dashboard#prevadzka-row-${facility.id}`)}
                title="Otvoriť túto prevádzku v tabuľke gramáže"
              >
                <Gauge /> Tabuľka
              </Button>
              <Button
                variant="secondary"
                onClick={() => navigate(`/admin/prevadzka-overview#prevadzka-row-${facility.id}`)}
                title="Otvoriť túto prevádzku v dodaní podkladov"
              >
                <ClipboardCheck /> Dodanie podkladov
              </Button>
              {canResetPassword && (
                <Button variant="secondary" onClick={() => setShowResetConfirmation(true)} disabled={sendingReset} title="Odoslať reset hesla na email">
                  <KeyRound /> {sendingReset ? "Odosielam…" : "Reset hesla"}
                </Button>
              )}
              {facility.edupage_connection && (
                <Button
                  variant="secondary"
                  onClick={() => { setScrapeResult(null); setScrapeModalOpen(true); }}
                  title="Manuálne stiahnuť objednávky z EduPage pre zvolený deň"
                >
                  <Download /> Scrapnúť z EduPage
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="zpa-tabs" style={{ maxWidth: "fit-content", gap: 4 }}>
          {tabs.map((t) => (
            <button key={t.key} type="button" onClick={() => setActiveTab(t.key)} className={`zpa-tab${activeTab === t.key ? " active" : ""}`} style={{ flex: "none", padding: "12px 20px" }}>
              {t.label}
            </button>
          ))}
        </div>

        {activeTab === "dashboard" && (
          <Card style={{ overflow: "hidden" }}>
            <div className="zpa-card-head" style={{ padding: "16px 24px", borderBottom: "1px solid var(--line-soft)" }}>
              <h3>História objednávok</h3>
              <Button sm onClick={() => setShowNewOrderModal(true)}>
                <Plus /> Nová objednávka
              </Button>
            </div>
            {ordersLoading ? (
              <Empty>Načítavam objednávky…</Empty>
            ) : recentOrders.length === 0 ? (
              <Empty>Táto prevádzka zatiaľ nemá žiadne objednávky.</Empty>
            ) : (
              <div className="zpa-table-wrap">
                <table className="zpa-table">
                  <thead>
                    <tr>
                      <th>Dátum</th>
                      <th>Súhrn</th>
                      <th className="r">Akcie</th>
                      <th style={{ width: 32 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentOrders.map((order) => {
                      const summaries: string[] = [];
                      const breakfastCount = mealCount(order.data.breakfast);
                      if (breakfastCount > 0) summaries.push(`${breakfastCount}x Raňajky`);
                      const lunchCount = mealCount(order.data.lunch);
                      if (lunchCount > 0) summaries.push(`${lunchCount}x Obed`);
                      const olovrantCount = mealCount(order.data.olovrant);
                      if (olovrantCount > 0) summaries.push(`${olovrantCount}x Olovrant`);
                      const summaryText = summaries.length > 0 ? summaries.join(", ") : "-";
                      const isExpanded = expandedOrderId === order.id;
                      const specialDietNote =
                        typeof order.data.special_diet_note === "string"
                          ? order.data.special_diet_note.trim()
                          : "";

                      return (
                        <React.Fragment key={order.id}>
                          <tr style={isExpanded ? { background: "var(--bg-cream-soft)" } : undefined}>
                            <td style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--green-900)", cursor: "pointer" }} onClick={() => setExpandedOrderId(isExpanded ? null : order.id)}>
                              {order.date}
                            </td>
                            <td style={{ fontWeight: 600, color: "var(--ink-2)", cursor: "pointer" }} onClick={() => setExpandedOrderId(isExpanded ? null : order.id)}>
                              {summaryText}
                            </td>
                            <td className="r">
                              <div style={{ display: "inline-flex", gap: 4 }}>
                                <IconButton onClick={() => setEditOrderTarget(order)} title="Upraviť objednávku" aria-label="Upraviť objednávku"><Pencil /></IconButton>
                                {order.date !== toDateKey(new Date()) && (
                                  <IconButton onClick={() => setCopyOrderTarget(order)} title="Skopírovať na dnes" aria-label="Skopírovať na dnes"><Copy /></IconButton>
                                )}
                                <IconButton onClick={() => setResetOrderTarget(order)} title="Vynulovať objednávku" aria-label="Vynulovať objednávku"><RotateCcw /></IconButton>
                                <IconButton onClick={() => setDeleteOrderTarget(order)} title="Odstrániť objednávku" aria-label="Odstrániť objednávku"><Trash2 /></IconButton>
                              </div>
                            </td>
                            <td className="c" style={{ cursor: "pointer", color: "var(--ink-mute)" }} onClick={() => setExpandedOrderId(isExpanded ? null : order.id)}>
                              {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                            </td>
                          </tr>
                          {isExpanded && (
                            <tr style={{ background: "var(--bg-cream-warm)" }}>
                              <td colSpan={4} style={{ borderTop: "1px solid var(--line-soft)" }}>
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 24, fontSize: 14 }}>
                                  {[
                                    { title: "Raňajky", data: order.data.breakfast },
                                    { title: "Obed", data: order.data.lunch },
                                    { title: "Olovrant", data: order.data.olovrant },
                                  ].map(({ title, data }) => (
                                    <div key={title}>
                                      <div style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--green-900)", marginBottom: 8, borderBottom: "1px solid var(--line-soft)", paddingBottom: 4 }}>{title}</div>
                                      {(() => {
                                        if (!data) return <span style={{ color: "var(--ink-mute)" }}>-</span>;
                                        if (typeof data === "string") return <span>{data === "true" ? "Áno" : data}</span>;
                                        if (data === true) return <span>Áno</span>;
                                        const items: React.JSX.Element[] = [];
                                        Object.entries(data).forEach(([catName, catData]) => {
                                          if (!catData || typeof catData !== "object") return;
                                          const category = catData as { menuCounts?: Record<string, number>; diets?: Record<string, number> };
                                          const menuCounts = category.menuCounts || {};
                                          const diets = category.diets || {};
                                          const totalPortions = Object.values(menuCounts).reduce((a, b) => a + Number(b), 0);
                                          // Súhrn „5x Diéta" nepovedal, o ktoré diéty ide. Rozpíš ich
                                          // po jednej — dáta na to v objednávke sú.
                                          const dietEntries = Object.entries(diets)
                                            .filter(([, count]) => Number(count) > 0)
                                            .sort(([a], [b]) => a.localeCompare(b, "sk"));
                                          // Rovnako súhrn nepovedal, koľko bolo z ktorého menu písmena
                                          // (napr. Menu B pre dospelých) — rozpíš aj tie, keď je z čoho
                                          // vyberať (jedno jediné písmeno by len duplikovalo súhrn).
                                          const menuEntries = Object.entries(menuCounts)
                                            .filter(([, count]) => Number(count) > 0)
                                            .sort(([a], [b]) => {
                                              return ALL_MENUS.includes(a) && ALL_MENUS.includes(b)
                                                ? ALL_MENUS.indexOf(a) - ALL_MENUS.indexOf(b)
                                                : a.localeCompare(b, "sk");
                                            });
                                          if (Number(totalPortions) > 0) {
                                            items.push(
                                              <div key={catName} style={{ display: "flex", flexDirection: "column", marginBottom: 4, borderBottom: "1px solid var(--line-soft)", paddingBottom: 4 }}>
                                                <span style={{ fontWeight: 600, color: "var(--ink-1)" }}>{String(totalPortions)}x {catName}</span>
                                                {menuEntries.length > 1 && menuEntries.map(([menu, count]) => (
                                                  <span key={`menu-${menu}`} style={{ fontSize: 12, color: "var(--ink-mute)", paddingLeft: 8, display: "inline-flex", alignItems: "center", gap: 6 }}>
                                                    <span aria-hidden="true">•</span>
                                                    <span>{String(count)}x Menu {menu}</span>
                                                  </span>
                                                ))}
                                                {dietEntries.map(([dietName, count]) => {
                                                  const diet = dietByName.get(dietName);
                                                  return (
                                                    <span key={dietName} style={{ fontSize: 12, color: "var(--green-600)", paddingLeft: 8, display: "inline-flex", alignItems: "center", gap: 6 }}>
                                                      <span aria-hidden="true">•</span>
                                                      <DietColorSwatch color={diet?.color} baseColors={diet?.base_colors} size={9} />
                                                      <span>{String(count)}x {dietName}</span>
                                                    </span>
                                                  );
                                                })}
                                              </div>,
                                            );
                                          }
                                        });
                                        return items.length ? <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>{items}</div> : <span style={{ color: "var(--ink-mute)" }}>-</span>;
                                      })()}
                                    </div>
                                  ))}
                                </div>
                                {order.data.soup && typeof order.data.soup === "string" && (
                                  <div style={{ marginTop: 16, paddingTop: 8, borderTop: "1px solid var(--line-soft)" }}>
                                    <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--green-900)", marginRight: 8 }}>Polievka:</span>
                                    <span>{order.data.soup}</span>
                                  </div>
                                )}
                                {specialDietNote && (
                                  <div style={{ marginTop: 16, paddingTop: 8, borderTop: "1px solid var(--line-soft)" }}>
                                    <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, color: "var(--green-900)", marginRight: 8 }}>Špeciálna diéta:</span>
                                    <span>{specialDietNote}</span>
                                  </div>
                                )}
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {!ordersLoading && !historyExpanded && ordersHasNext && (
              <div style={{ display: "flex", justifyContent: "center", padding: "14px 20px", borderTop: "1px solid var(--line-soft)" }}>
                <Button
                  variant="secondary"
                  sm
                  onClick={() => { setExpandedOrderId(null); setHistoryExpanded(true); }}
                >
                  Zobraziť celú históriu
                </Button>
              </div>
            )}
            {!ordersLoading && historyExpanded && (recentOrders.length > 0 || ordersPage > 1) && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 20px", borderTop: "1px solid var(--line-soft)" }}>
                <Button
                  variant="secondary"
                  sm
                  disabled={ordersPage === 1}
                  onClick={() => { setExpandedOrderId(null); setOrdersPage((page) => page - 1); }}
                >
                  Predchádzajúca
                </Button>
                <span>Strana {ordersPage}</span>
                <Button
                  variant="secondary"
                  sm
                  disabled={!ordersHasNext}
                  onClick={() => { setExpandedOrderId(null); setOrdersPage((page) => page + 1); }}
                >
                  Ďalšia
                </Button>
              </div>
            )}
          </Card>
        )}

        {activeTab === "udaje" && (
          <div className="zpa-stack">
            <Card pad>
              <CardHead title="Údaje prevádzky" desc="Základné údaje prevádzky — identita, adresa a EduPage napojenie." />
              <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 8 }}>
                <PrevadzkaFields
                  form={prevadzkaForm}
                  setForm={setPrevadzkaForm}
                  connections={connections}
                  showEdupage={facility.celok_zdroj_objednavok === "edupage"}
                />
              </div>
            </Card>

            <Card pad style={{ borderColor: "var(--coral-300)" }}>
              <CardHead
                title="Nebezpečná zóna"
                desc="Odstránenie prevádzky je nevratné a je možné iba vtedy, ak nemá žiadne objednávky."
                actions={
                  <Button
                    variant="danger"
                    sm
                    onClick={() => {
                      setFacilityDeleteError("");
                      setShowDeleteFacility(true);
                    }}
                  >
                    <Trash2 /> Odstrániť prevádzku
                  </Button>
                }
              />
            </Card>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={handleSave} disabled={saving}>{saving ? "Ukladám…" : "Uložiť nastavenia"}</Button>
            </div>
          </div>
        )}

        {activeTab === "objednavanie" && (
          <div className="zpa-stack">
            <div className="zpa-grid-2">
              <Card pad>
                <CardHead title="Viditeľné menu" desc="Vyberte, ktoré typy menu sa zobrazia pre obed. Raňajky a olovrant majú vždy len menu A." />
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                  {ALL_MENUS.map((menu) => {
                    const selectedDays = new Set(menuDayRestrictions[menu] || []);
                    return (
                      <div key={menu} style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
                        <Checkbox on={menus.has(menu)} onChange={() => toggleSet(menus, menu, setMenus)}>
                          Menu {menu}
                        </Checkbox>
                        {menus.has(menu) && (
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            {WEEKDAYS.map(({ day, label }) => {
                              const on = selectedDays.has(day);
                              return (
                                <button
                                  key={day}
                                  type="button"
                                  className={`zpa-daypill${on ? " on" : ""}`}
                                  aria-label={`Menu ${menu} - ${label}`}
                                  title={`Menu ${menu} bude dostupné v tento deň${selectedDays.size === 0 ? " (teraz: každý deň)" : ""}`}
                                  onClick={() => {
                                    const next = new Set(selectedDays);
                                    if (next.has(day)) next.delete(day);
                                    else next.add(day);
                                    setMenuDayRestrictions((prev) => ({
                                      ...prev,
                                      [menu]: Array.from(next).sort(),
                                    }));
                                  }}
                                >
                                  {label}
                                </button>
                              );
                            })}
                            <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
                              {selectedDays.size === 0 ? "každý deň" : "len vybrané dni"}
                            </span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>

              <Card pad>
                <CardHead title="Viditeľné jedlá" desc="Nastavte, ktoré chody dňa sú dostupné." />
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                  {ALL_MEALS.map((meal) => (
                    <Checkbox
                      key={meal}
                      on={meals.has(meal)}
                      onChange={() => {
                        if (meals.has(meal) && meals.size === 1) {
                          toastWarning("Prevádzka musí mať povolený aspoň jeden chod.");
                          return;
                        }
                        toggleSet(meals, meal, setMeals);
                      }}
                    >
                      {MEAL_LABELS[meal] ?? meal}
                    </Checkbox>
                  ))}
                </div>
              </Card>

              <Card pad>
                <CardHead title="Viditeľné veľkosti porcií" desc="Vyberte, ktoré veľkosti porcií sa zobrazia klientovi v objednávke." />
                {portionTypes.length === 0 ? (
                  <Empty>V systéme nie sú definované žiadne veľkosti porcií.</Empty>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                    {portionTypes.map((portionType) => (
                      <Checkbox
                        key={portionType.id}
                        on={visiblePortionTypes == null || visiblePortionTypes.has(portionType.id)}
                        onChange={() => {
                          const current = visiblePortionTypes == null
                            ? new Set(portionTypes.map((item) => item.id))
                            : visiblePortionTypes;
                          toggleSet(current, portionType.id, setVisiblePortionTypes);
                        }}
                      >
                        {portionType.name}
                      </Checkbox>
                    ))}
                  </div>
                )}
              </Card>

              <Card pad>
                <CardHead title="Balenie a výdaj" desc="Nastavenia súvisiace s balením a výdajom jedla — signály pre kuchyňu a gramážnu tabuľku." />
                <div style={{ display: "flex", flexDirection: "column", gap: 16, marginTop: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--ink-1)", fontSize: 14 }}>Zabaliť zvlášť</div>
                      <div style={{ color: "var(--ink-3)", fontSize: 13 }}>
                        Povoliť klientovi označiť vybrané položky na balenie zvlášť.
                      </div>
                    </div>
                    <Toggle
                      on={packSeparatelyEnabled}
                      onChange={setPackSeparatelyEnabled}
                      ariaLabel="Povoliť zabaliť zvlášť"
                    />
                  </div>

                  {isEdupageClient && (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                      <div>
                        <div style={{ fontWeight: 600, color: "var(--ink-1)", fontSize: 14 }}>Dospelí zvlášť</div>
                        <div style={{ color: "var(--ink-3)", fontSize: 13 }}>
                          V gramážnej tabuľke (aj v PDF) sa všetky porcie „Dospelý (SŠ)“ automaticky vykážu ako zabalené zvlášť.
                        </div>
                      </div>
                      <Toggle
                        on={adultsPackSeparatelyEnabled}
                        onChange={setAdultsPackSeparatelyEnabled}
                        ariaLabel="Automaticky baliť dospelých zvlášť"
                      />
                    </div>
                  )}

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                    <div>
                      <div style={{ fontWeight: 600, color: "var(--ink-1)", fontSize: 14 }}>Olovrant ide s obedom</div>
                      <div style={{ color: "var(--ink-3)", fontSize: 13 }}>
                        V gramážnej tabuľke (aj v PDF) sa olovrant tejto prevádzky zvýrazní žlto — ide s obedovým rozvozom.
                      </div>
                    </div>
                    <Toggle
                      on={olovrantSObedom}
                      onChange={setOlovrantSObedom}
                      ariaLabel="Olovrant ide s obedom"
                    />
                  </div>
                </div>
              </Card>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={handleSave} disabled={saving}>{saving ? "Ukladám…" : "Uložiť nastavenia"}</Button>
            </div>
          </div>
        )}

        {activeTab === "diety" && (
          <div className="zpa-stack">
            <Card pad>
              <CardHead
                title="Povolené diéty"
                desc="Diéty, ktoré si prevádzka môže vybrať v objednávke. Ku každej môžete pridať internú poznámku."
                actions={<Button variant="ghost" sm onClick={() => navigate("/admin/diets")}><Plus /> Pridať novú diétu</Button>}
              />
              {assignedDiets.length === 0 ? (
                <Empty>Prevádzka zatiaľ nemá priradenú žiadnu diétu.</Empty>
              ) : (
                <div style={{ marginTop: 8 }}>
                  {assignedDiets.map((diet) => (
                    <div key={diet.id} className="zpa-listrow" style={{ paddingInline: 0 }}>
                      <DietColorSwatch color={diet.color} baseColors={diet.base_colors} size={12} />
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div className="lr-ttl" style={{ textTransform: "none" }}>{diet.name}</div>
                        {dietNotes[diet.id] && <div className="lr-sub">{dietNotes[diet.id]}</div>}
                      </div>
                      <IconButton
                        onClick={() => openDietNote(diet)}
                        title="Poznámka k diéte"
                        aria-label={`Poznámka k diéte ${diet.name}`}
                      >
                        <StickyNote />
                      </IconButton>
                      <IconButton
                        onClick={() => toggleSet(userDiets, diet.id, setUserDiets)}
                        title="Odobrať diétu"
                        aria-label={`Odobrať diétu ${diet.name}`}
                      >
                        <Trash2 />
                      </IconButton>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            <Card pad>
              <CardHead title="Priradiť diétu" desc="Vyhľadajte diétu podľa názvu a priraďte ju prevádzke." />
              <div style={{ marginTop: 8 }}>
                <SearchBox value={dietSearch} onChange={setDietSearch} placeholder="Hľadať diétu…" />
                {dietSearchQuery && (
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                    {dietSearchResults.length === 0 ? (
                      <div style={{ color: "var(--ink-mute)", fontSize: 13, padding: "6px 4px" }}>Žiadna diéta nenájdená.</div>
                    ) : (
                      dietSearchResults.map((diet) => (
                        <button
                          key={diet.id}
                          type="button"
                          className="zpa-btn zpa-btn--ghost zpa-btn--sm"
                          style={{ justifyContent: "flex-start", gap: 8 }}
                          onClick={() => {
                            toggleSet(userDiets, diet.id, setUserDiets);
                            setDietSearch("");
                          }}
                        >
                          <DietColorSwatch color={diet.color} baseColors={diet.base_colors} size={10} />
                          {diet.name}
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>
            </Card>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={handleSave} disabled={saving}>{saving ? "Ukladám…" : "Uložiť diéty"}</Button>
            </div>
          </div>
        )}

        {activeTab === "logins" && (
          <Card pad>
            <CardHead
              title="Loginy prevádzky"
              desc="Spravujte prihlasovacie údaje používateľov tejto prevádzky."
              actions={<Button sm onClick={openAddLogin}><Plus /> Pridať login</Button>}
            />
            {facilityLogins.length === 0 ? (
              <Empty>Táto prevádzka nemá žiadne loginy.</Empty>
            ) : (
              <div>
                {facilityLogins.map((login) => (
                  <div key={login.user_id} className="zpa-listrow" style={{ paddingInline: 0 }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div className="lr-ttl" style={{ textTransform: "none" }}>{login.company_name || login.email}</div>
                      <div className="lr-sub">{login.email}</div>
                    </div>
                    {login.is_edupage && <Badge tone="teal">EduPage</Badge>}
                    <LoginPasswordStatusBadge status={login.password_status} />
                    {(login.password_status === "pending" || login.password_status === "failed") && (
                      <IconButton
                        onClick={() => handleResendInvite(login)}
                        disabled={resendingLoginId === login.user_id}
                        title="Znova odoslať pozvánku na nastavenie hesla"
                        aria-label={`Znova odoslať pozvánku pre ${login.email}`}
                      >
                        <Send />
                      </IconButton>
                    )}
                    <IconButton
                      onClick={() => openEditLogin(login)}
                      title="Upraviť login"
                      aria-label={`Upraviť login ${login.email}`}
                    >
                      <Pencil />
                    </IconButton>
                    <IconButton
                      onClick={() => setLoginDeleteTarget(login)}
                      title="Odstrániť login"
                      aria-label={`Odstrániť login ${login.email}`}
                    >
                      <Trash2 />
                    </IconButton>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {activeTab === "closures" && <PrevadzkaClosures prevadzkaId={facility.id} />}

        {activeTab === "order_note" && (
          <div className="zpa-stack">
            <Card pad>
              <CardHead title="Poznámka k objednávke" desc="Táto poznámka sa zobrazuje iba v admin dashboarde po rozkliknutí prevádzky, nad súhrnnými číslami." />
              <div style={{ marginTop: 8 }}>
                <Textarea value={adminOrderNote} onChange={(e) => setAdminOrderNote(e.target.value)} rows={6} placeholder="Sem zadajte internú poznámku k objednávkam prevádzky…" />
              </div>
            </Card>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button onClick={handleSave} disabled={saving}>{saving ? "Ukladám…" : "Uložiť poznámku"}</Button>
            </div>
          </div>
        )}
      </div>

      {/* ── Password reset confirmation ── */}
      {user && (
      <ConfirmationModal
        isOpen={showResetConfirmation}
        onClose={() => setShowResetConfirmation(false)}
        onConfirm={handleSendPasswordReset}
        title="Odoslať reset hesla"
        description={`Naozaj chcete odoslať reset link na ${user.email}? Prevádzka si cez tento odkaz bude môcť nastaviť nové heslo.`}
        confirmText={sendingReset ? "Odosielam..." : "Odoslať"}
        cancelText="Zrušiť"
        variant="warning"
      />
      )}

      {/* ── Login add/edit ── */}
      {loginTarget !== undefined && (
        <Modal
          title={loginTarget
            ? `Upraviť login — ${loginTarget.email}`
            : `Pridať login — ${facility.nazov}`}
          onClose={closeLoginEditor}
          foot={
            <>
              <Button variant="ghost" onClick={closeLoginEditor} disabled={loginSaving}>Zrušiť</Button>
              <Button type="submit" form="facility-login-form" disabled={loginSaving}>
                {loginSaving ? "Ukladám…" : loginTarget ? "Uložiť" : "Vytvoriť login"}
              </Button>
            </>
          }
        >
          <form id="facility-login-form" onSubmit={saveLogin} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <LoginFields form={loginForm} setForm={setLoginForm} />
          </form>
        </Modal>
      )}

      {/* ── Login delete confirmation ── */}
      {loginDeleteTarget && (
        <Modal
          title="Odstrániť login"
          onClose={() => setLoginDeleteTarget(null)}
          icon={<AlertTriangle />}
          iconKind="danger"
          foot={
            <>
              <Button variant="ghost" onClick={() => setLoginDeleteTarget(null)} disabled={loginDeleting}>Zrušiť</Button>
              <Button variant="danger" onClick={deleteLogin} disabled={loginDeleting}>
                {loginDeleting ? "Odstraňujem…" : "Odstrániť"}
              </Button>
            </>
          }
        >
          <p style={{ margin: 0, color: "var(--ink-2)", lineHeight: 1.6 }}>
            Naozaj odstrániť login <strong style={{ color: "var(--green-900)" }}>{loginDeleteTarget.email}</strong>?
          </p>
        </Modal>
      )}

      {/* ── Poznámka k diéte (popover) ── */}
      {dietNoteTarget && (
        <Modal
          title={`Poznámka — ${dietNoteTarget.name}`}
          onClose={() => setDietNoteTarget(null)}
          foot={
            <>
              <Button variant="ghost" onClick={() => setDietNoteTarget(null)}>Zrušiť</Button>
              <Button onClick={saveDietNoteDraft}>Uložiť poznámku</Button>
            </>
          }
        >
          <Textarea
            value={dietNoteDraft}
            onChange={(e) => setDietNoteDraft(e.target.value)}
            rows={3}
            placeholder="Napr. alergik, nahlásiť kuchyni…"
          />
        </Modal>
      )}

      {/* ── Facility delete confirmation ── */}
      {showDeleteFacility && (
        <Modal
          title="Odstrániť prevádzku"
          onClose={() => {
            if (!facilityDeleting) {
              setShowDeleteFacility(false);
              setFacilityDeleteError("");
            }
          }}
          icon={<AlertTriangle />}
          iconKind="danger"
          foot={
            <>
              <Button
                variant="ghost"
                onClick={() => {
                  setShowDeleteFacility(false);
                  setFacilityDeleteError("");
                }}
                disabled={facilityDeleting}
              >
                Zrušiť
              </Button>
              <Button variant="danger" onClick={deleteFacility} disabled={facilityDeleting}>
                {facilityDeleting ? "Odstraňujem…" : "Odstrániť"}
              </Button>
            </>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p style={{ margin: 0, color: "var(--ink-2)", lineHeight: 1.6 }}>
              Naozaj odstrániť prevádzku „<strong style={{ color: "var(--green-900)" }}>{facility.nazov}</strong>“? Táto akcia je nevratná.
            </p>
            {(facility.orders_count ?? 0) > 0 && (
              <p style={{ margin: 0, color: "var(--coral-700)", lineHeight: 1.6 }}>
                Prevádzka má existujúce objednávky, ktoré zablokujú jej odstránenie.
              </p>
            )}
            {facilityDeleteError && (
              <p role="alert" style={{ margin: 0, color: "var(--coral-700)", lineHeight: 1.6 }}>
                {facilityDeleteError}
              </p>
            )}
          </div>
        </Modal>
      )}

      {/* ── Delete order confirmation modal ── */}
      {deleteOrderTarget && (
        <Modal
          title="Odstrániť objednávku"
          onClose={() => setDeleteOrderTarget(null)}
          icon={<AlertTriangle />}
          iconKind="danger"
          foot={
            <>
              <Button variant="ghost" onClick={() => setDeleteOrderTarget(null)} disabled={orderActionLoading}>Zrušiť</Button>
              <Button variant="danger" onClick={handleDeleteOrder} disabled={orderActionLoading}>{orderActionLoading ? "Odstraňujem…" : "Odstrániť"}</Button>
            </>
          }
        >
          <p style={{ margin: 0, color: "var(--ink-2)", lineHeight: 1.6 }}>
            Naozaj chcete odstrániť objednávku zo dňa <strong style={{ color: "var(--green-900)" }}>{deleteOrderTarget.date}</strong>? Táto akcia je nevratná.
          </p>
        </Modal>
      )}

      {/* ── Create / Edit order modal ── */}
      {(showNewOrderModal || editOrderTarget) && facilityId && (
        <AdminOrderEditorModal
          clientId={user?.id ?? null}
          prevadzkaId={facility.id}
          visibleMenus={orderEditorMenus}
          menuDayRestrictions={menuDayRestrictions}
          visibleMeals={orderEditorMeals}
          visibleDiets={orderEditorDiets}
          portionTypeNames={portionTypeNames}
          packSeparatelyEnabled={packSeparatelyEnabled}
          allDiets={allDiets}
          existingOrder={editOrderTarget ?? null}
          knownOrders={recentOrders}
          onClose={() => {
            setShowNewOrderModal(false);
            setEditOrderTarget(null);
          }}
          onSaved={() => {
            setShowNewOrderModal(false);
            setEditOrderTarget(null);
            fetchOrders();
          }}
        />
      )}

      {/* ── Reset order confirmation modal ── */}
      {resetOrderTarget && (
        <Modal
          title="Vynulovať objednávku"
          onClose={() => setResetOrderTarget(null)}
          icon={<RotateCcw />}
          iconKind="warn"
          foot={
            <>
              <Button variant="ghost" onClick={() => setResetOrderTarget(null)} disabled={orderActionLoading}>Zrušiť</Button>
              <Button variant="honey" onClick={handleResetOrder} disabled={orderActionLoading}>{orderActionLoading ? "Vynulujem…" : "Vynulovať"}</Button>
            </>
          }
        >
          <p style={{ margin: 0, color: "var(--ink-2)", lineHeight: 1.6 }}>
            Naozaj chcete vynulovať objednávku zo dňa <strong style={{ color: "var(--green-900)" }}>{resetOrderTarget.date}</strong>? Všetky položky budú vymazané, záznam zostane zachovaný.
          </p>
        </Modal>
      )}

      {/* ── Copy order to today confirmation modal ── */}
      {copyOrderTarget && (
        <Modal
          title="Skopírovať objednávku na dnes"
          onClose={() => setCopyOrderTarget(null)}
          icon={<Copy />}
          foot={
            <>
              <Button variant="ghost" onClick={() => setCopyOrderTarget(null)} disabled={orderActionLoading}>Zrušiť</Button>
              <Button variant="primary" onClick={handleCopyToToday} disabled={orderActionLoading}>{orderActionLoading ? "Kopírujem…" : "Skopírovať"}</Button>
            </>
          }
        >
          <p style={{ margin: 0, color: "var(--ink-2)", lineHeight: 1.6 }}>
            Naozaj chcete skopírovať objednávku zo dňa <strong style={{ color: "var(--green-900)" }}>{copyOrderTarget.date}</strong> na dnešný deň (
            <strong style={{ color: "var(--green-900)" }}>{toDateKey(new Date())}</strong>)?
            {recentOrders.some((o) => o.date === toDateKey(new Date())) && (
              <> Prevádzka už na dnes objednávku má — táto akcia ju prepíše.</>
            )}
          </p>
        </Modal>
      )}

      {/* ── Manual EduPage scrape modal ── */}
      {scrapeModalOpen && (
        <Modal
          title="Scrapnúť z EduPage"
          onClose={() => { if (!scraping) setScrapeModalOpen(false); }}
          icon={<Download />}
          iconKind="warn"
          foot={
            <>
              <Button variant="ghost" onClick={() => setScrapeModalOpen(false)} disabled={scraping}>Zavrieť</Button>
              <Button variant="honey" onClick={handleRunScrape} disabled={scraping}>
                {scraping ? "Sťahujem…" : "Spustiť scrape"}
              </Button>
            </>
          }
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 6 }}>Deň</label>
              <input
                type="date"
                className="zpa-input"
                value={scrapeDate}
                disabled={scraping}
                onChange={(e) => e.target.value && setScrapeDate(e.target.value)}
                style={{ width: "auto" }}
              />
            </div>
            <p style={{ margin: 0, color: "var(--ink-2)", lineHeight: 1.6 }}>
              Táto akcia stiahne aktuálne dáta z EduPage pre <strong style={{ color: "var(--green-900)" }}>{scrapeDate}</strong> a{" "}
              <strong style={{ color: "var(--green-900)" }}>úplne prepíše</strong> objednávky na tento deň — pre{" "}
              <strong style={{ color: "var(--green-900)" }}>všetky prevádzky</strong>, ktoré sú napojené na rovnaké EduPage pripojenie ako{" "}
              {facility.nazov}
              {facility.edupage_connection_name ? ` (${facility.edupage_connection_name})` : ""}, nielen na túto jednu. Vypíše sa presný zoznam prevádzok, ktorých sa to dotklo.
            </p>
            {scrapeResult && (
              <div style={{ borderTop: "1px solid var(--line-soft)", paddingTop: 12, fontSize: 13.5 }}>
                {scrapeResult.status === "error" && (
                  <p style={{ color: "var(--red-700, #b91c1c)", margin: 0 }}>Chyba: {scrapeResult.error}</p>
                )}
                {(scrapeResult.status === "empty" || scrapeResult.status === "skipped") && (
                  <p style={{ color: "var(--ink-2)", margin: 0 }}>
                    Prázdny výsledok{scrapeResult.reason ? ` — ${scrapeResult.reason}` : ""}
                    {scrapeResult.warnings && scrapeResult.warnings.length > 0 ? ` (${scrapeResult.warnings.join(", ")})` : ""}.
                  </p>
                )}
                {scrapeResult.status === "updated" && (
                  <>
                    <p style={{ margin: "0 0 6px", fontWeight: 600, color: "var(--green-900)" }}>Prepísané prevádzky:</p>
                    <ul style={{ margin: 0, paddingLeft: 20 }}>
                      {scrapeResult.orders?.map((o) => (
                        <li key={o.order_id}>{o.prevadzka} ({o.status === "created" ? "nová" : "prepísaná"})</li>
                      ))}
                    </ul>
                    {scrapeResult.unmapped_letters && scrapeResult.unmapped_letters.length > 0 && (
                      <p style={{ marginTop: 8, color: "var(--honey-700, #a16207)" }}>
                        Neznáme diéty: {scrapeResult.unmapped_letters.join(", ")}
                      </p>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}
    </>
  );
};

export default ClientDetail;
