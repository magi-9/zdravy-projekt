import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import OrderService, { CategoryData, DailyOrder, MealData, PackTarget } from '../services/OrderService';
import { useAuth } from '../../../context/auth';
import { CATEGORIES } from '../config/constants';
import { logger } from '../../../lib/logger';
import { fetchAllPages } from '../../../lib/pagination';
import { fromDateKey, toDateKey } from '../../../lib/businessDay';
import { useToast } from '../../../context/ToastContext';
import type { Prevadzka } from './usePrevadzky';

/** Riadok z `/api/prevadzka-closures/` — voľno jednej prevádzky (#490). */
interface PrevadzkaClosure {
    id: number;
    prevadzka: number;
    date_from: string;
    date_to: string;
    reason: string;
}

const API_URL = import.meta.env.VITE_API_URL || '/api';

// Celodenná objednávka drží počty v `fullDayData` mimo `DailyOrder.breakfast/
// lunch/olovrant` — tento label ich v `restrictedMenuCeilingsRef` odlíši od
// bežných jedál (nemôže kolidovať s reálnym mealKey, tie sú len breakfast/
// lunch/olovrant).
const FULL_DAY_CEILING_LABEL = 'fullDay';

// Jedálniček items are stored under 4 categories (breakfast_snack/soup/
// main_course/afternoon_snack); the order form groups by 3 meal keys
// (breakfast/lunch/olovrant), with soup+main_course both counting toward
// "lunch" since they're ordered together.
const JEDALNICEK_CATEGORY_TO_MEAL_KEY: Record<string, string> = {
    breakfast_snack: 'breakfast',
    soup: 'lunch',
    main_course: 'lunch',
    afternoon_snack: 'olovrant',
};

interface PortionType {
    id: number;
    name: string;
    coefficient: string;
    coefficient_pct: number;
    is_active: boolean;
}

interface ClientContactInfo {
    name: string;
    role: string;
    email: string;
    phone: string;
}

interface DietDetail {
    id: number;
    name: string;
    description?: string | null;
    is_active?: boolean;
    sort_order?: number;
}

type ApiErrorPayload = {
    error?: {
        code?: string;
        message?: string;
    };
};

export const getVisibleMenusForMeal = (
    mealKey: 'breakfast' | 'lunch' | 'olovrant',
    adminVisibleMenus: string[],
) => (mealKey === 'lunch' ? adminVisibleMenus : ['A']);

/** ISO deň v týždni pre `date` (YYYY-MM-DD): 1=pondelok..7=nedeľa. */
const isoWeekday = (date: string): number => {
    const day = new Date(`${date}T12:00:00`).getDay();
    return day === 0 ? 7 : day;
};

/** Menu B napr. „len v piatok" (#menu_day_restrictions) — mimo povolených dní
 * sa v zozname neponúka, aj keď je inak vo `visible_menus` zapnuté. */
export const filterMenusByDay = (
    menus: string[],
    dayRestrictions: Record<string, number[]> | null | undefined,
    date: string,
): string[] => {
    if (!dayRestrictions) return menus;
    const weekday = isoWeekday(date);
    return menus.filter((menu) => {
        const allowedDays = dayRestrictions[menu];
        return !allowedDays || allowedDays.length === 0 || allowedDays.includes(weekday);
    });
};

export class OrderRequestError extends Error {
    code?: string;

    constructor(message: string, code?: string) {
        super(message);
        this.name = 'OrderRequestError';
        this.code = code;
    }
}

const parseApiError = async (response: Response) => {
    try {
        const payload = await response.clone().json() as ApiErrorPayload;
        return new OrderRequestError(payload.error?.message || 'Request failed', payload.error?.code);
    } catch {
        const text = await response.text();
        return new OrderRequestError(text || 'Request failed');
    }
};

// Helper for safe localStorage parsing
// Now using OrderService.enforceStructure
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const safeParse = (key: string, fallback: any) => {
    try {
        const saved = localStorage.getItem(key);
        if (!saved) return fallback;
        const parsed = JSON.parse(saved);
        return OrderService.enforceStructure(parsed, fallback);
    } catch {
        return fallback;
    }
};

export const useOrder = (activePrevadzkaId?: number, waitForPrevadzkaChoice = false, prevadzky: Prevadzka[] = []) => {
    const { apiFetch, user } = useAuth();
    const { warning: toastWarning } = useToast();
    const parseDate = (dateStr: string) => new Date(`${dateStr}T12:00:00`);
    const scopedKey = useCallback(
        (base: string, date: string) =>
            activePrevadzkaId ? `${base}_${date}_prevadzka_${activePrevadzkaId}` : `${base}_${date}`,
        [activePrevadzkaId]
    );
    // Settings

    const [portionTypes, setPortionTypes] = useState<PortionType[]>([]);
    const packSeparatelyEnabled = prevadzky.find((item) => item.id === activePrevadzkaId)?.pack_separately_enabled ?? false;

    const [touchedMeals, setTouchedMeals] = useState<Set<string>>(new Set());

    // State
    const [selectedDate, setSelectedDate] = useState(
        OrderService.toLocalDateString(OrderService.getServerNow())
    );
    // Ref mirrors selectedDate synchronously so persistence effects never write
    // the previous day's currentOrder under the new date key (race condition fix)
    const selectedDateRef = useRef(selectedDate);
    const loadedPrevadzkaIdRef = useRef(activePrevadzkaId);
    // "Zamknutý" strop pre Menu B/C/D po prísnom termíne — naposledy potvrdená
    // (server/submit) hodnota, nad ktorú sa už nedá zvýšiť, len znížiť
    // (user 2.9.2026). Aktualizuje sa pri načítaní objednávky zo servera a po
    // úspešnom submite; medzitýmové lokálne úpravy ho nemenia.
    const restrictedMenuCeilingsRef = useRef<Record<string, number>>({});
    // Promise pre aktuálne prebiehajúci (alebo posledný dobehnutý) GET
    // objednávky pre (selectedDate, activePrevadzkaId) — `submitOrder` naň
    // čaká, aby nedotknuté jedlo neposlal so starým localStorage draftom
    // skôr, než príde serverová odpoveď (Emjoy, 3.9.2026).
    const orderLoadRef = useRef<Promise<DailyOrder | null>>(Promise.resolve(null));
    const [prevDayLunches, setPrevDayLunches] = useState(0);

    const [activeMeals, setActiveMeals] = useState<Record<string, boolean>>(() => safeParse(scopedKey('activeMeals', selectedDate), { breakfast: false, lunch: true, olovrant: false }));

    const [fullDayOrder, setFullDayOrderState] = useState<boolean>(() =>
        safeParse(scopedKey('fullDayOrder', selectedDate), false)
    );

    const [fullDayData, setFullDayData] = useState<MealData>(() =>
        safeParse(scopedKey('fullDayData', selectedDate), OrderService.createEmptyMeal())
    );

    const [specialDietNote, setSpecialDietNote] = useState<string>(() =>
        safeParse(scopedKey('specialDietNote', selectedDate), '')
    );

    const [currentOrder, setCurrentOrder] = useState<DailyOrder>(() => {
        // Use Factory for initial state
        const initial: DailyOrder = {
            status: 'draft',
            breakfast: OrderService.createEmptyMeal(),
            lunch: OrderService.createEmptyMeal(),
            olovrant: OrderService.createEmptyMeal()
        };
        return safeParse(scopedKey('order', selectedDate), initial);
    });

    // Keep ref in sync — runs before other effects that depend on selectedDate
    useEffect(() => {
        selectedDateRef.current = selectedDate;
    }, [selectedDate, scopedKey]);

    // Load prev day lunches
    useEffect(() => {
        const prevDate = parseDate(selectedDate);
        prevDate.setDate(prevDate.getDate() - 1);
        const prevDateStr = OrderService.toLocalDateString(prevDate);
        const prevOrderSaved = localStorage.getItem(scopedKey('order', prevDateStr));
        if (prevOrderSaved) {
            try {
                const prevOrder = JSON.parse(prevOrderSaved);
                setPrevDayLunches(OrderService.calculatePrevDayLunches(prevOrder));
            } catch { setPrevDayLunches(0); }
        } else {
            setPrevDayLunches(0);
        }
    }, [selectedDate, scopedKey]);

    // Persistence
    // NOTE: order/activeMeals persistence intentionally does NOT include selectedDate
    // as a dependency — only currentOrder/activeMeals changes trigger a write.
    // selectedDateRef ensures we always write under the correct (new) date key
    // without the race condition where the new selectedDate fires the effect with
    // the old currentOrder value (which would corrupt the new date's localStorage entry).
    useEffect(() => {
        if (loadedPrevadzkaIdRef.current !== activePrevadzkaId) return;
        localStorage.setItem(scopedKey('order', selectedDateRef.current), JSON.stringify(currentOrder));
    }, [currentOrder, activePrevadzkaId, scopedKey]);
    useEffect(() => {
        if (loadedPrevadzkaIdRef.current !== activePrevadzkaId) return;
        localStorage.setItem(scopedKey('activeMeals', selectedDateRef.current), JSON.stringify(activeMeals));
    }, [activeMeals, activePrevadzkaId, scopedKey]);
    useEffect(() => {
        if (loadedPrevadzkaIdRef.current !== activePrevadzkaId) return;
        localStorage.setItem(scopedKey('fullDayOrder', selectedDateRef.current), JSON.stringify(fullDayOrder));
    }, [fullDayOrder, activePrevadzkaId, scopedKey]);
    useEffect(() => {
        if (loadedPrevadzkaIdRef.current !== activePrevadzkaId) return;
        localStorage.setItem(scopedKey('fullDayData', selectedDateRef.current), JSON.stringify(fullDayData));
    }, [fullDayData, activePrevadzkaId, scopedKey]);
    useEffect(() => {
        if (loadedPrevadzkaIdRef.current !== activePrevadzkaId) return;
        localStorage.setItem(scopedKey('specialDietNote', selectedDateRef.current), JSON.stringify(specialDietNote));
    }, [specialDietNote, activePrevadzkaId, scopedKey]);

    // Reset/Re-init on Date Change
    useEffect(() => {
        const emptyOrder = {
            breakfast: OrderService.createEmptyMeal(),
            lunch: OrderService.createEmptyMeal(),
            olovrant: OrderService.createEmptyMeal()
        };

        // On new date, if no local storage, default to all closed
        const defaultActive = { breakfast: false, lunch: false, olovrant: false };
        let newActive = safeParse(scopedKey('activeMeals', selectedDate), defaultActive);
        if (!newActive) {
            newActive = defaultActive;
        }

        const newOrder = safeParse(scopedKey('order', selectedDate), emptyOrder) as DailyOrder;

        loadedPrevadzkaIdRef.current = activePrevadzkaId;
        setTouchedMeals(new Set());
        setActiveMeals(newActive);
        setCurrentOrder(newOrder);
        // Predbežný strop z lokálneho draftu — server fetch nižšie ho prepíše
        // autoritatívnou hodnotou hneď, ako odpovie.
        restrictedMenuCeilingsRef.current = OrderService.extractRestrictedMenuCounts(newOrder);
        setFullDayOrderState(safeParse(scopedKey('fullDayOrder', selectedDate), false));
        const loadedFullDayData = safeParse(scopedKey('fullDayData', selectedDate), OrderService.createEmptyMeal());
        setFullDayData(loadedFullDayData);
        // Celodenná objednávka nemá vlastný server fetch (ide pod 'breakfast' v
        // payloade až pri submite) — localStorage je tu jediný zdroj "posledného
        // potvrdeného" stavu, kým nepríde ďalší úspešný submit.
        restrictedMenuCeilingsRef.current = {
            ...restrictedMenuCeilingsRef.current,
            ...OrderService.extractRestrictedMenuCountsForMeal(loadedFullDayData, FULL_DAY_CEILING_LABEL),
        };
        setSpecialDietNote(safeParse(scopedKey('specialDietNote', selectedDate), ''));
    }, [selectedDate, activePrevadzkaId, scopedKey]);

    // Fetch Order from API (server authority; merges into local state)
    useEffect(() => {
        let isMounted = true;

        const loadOrder = async (): Promise<DailyOrder | null> => {
            try {
                if (waitForPrevadzkaChoice && !activePrevadzkaId) return null;
                const suffix = activePrevadzkaId ? `?prevadzka=${activePrevadzkaId}` : '';
                const response = await apiFetch(`${API_URL}/orders/by-date/${selectedDate}/${suffix}`);
                if (response.ok) {
                    // API returns { id, status, data: { breakfast..., special_diet_note? } }
                    const serverOrder = await response.json() as { id: number, status: 'draft' | 'submitted', data: DailyOrder & { special_diet_note?: unknown, full_day_order?: unknown } };

                    if (serverOrder && serverOrder.data && Object.keys(serverOrder.data).length > 0) {
                        // Server has data
                        if (isMounted) {
                            // Merge mechanism could be complex, for now Server Authority wins
                            const merged = OrderService.enforceStructure(serverOrder.data, OrderService.createEmptyOrder());
                            merged.status = serverOrder.status; // Ensure status is synced
                            setCurrentOrder(merged);
                            restrictedMenuCeilingsRef.current = OrderService.extractRestrictedMenuCounts(merged);
                            // `special_diet_note` nie je súčasť createEmptyOrder() schémy, takže ho
                            // enforceStructure vyššie zahodí — bez tohto poznámka uložená na serveri
                            // nikdy nedôjde do UI a zdrojom pravdy zostane len localStorage draftu
                            // (ten je per-browser, takže na inom zariadení/po vyčistení je prázdny aj
                            // keď server poznámku má). Server je tu autoritatívny rovnako ako pri counts.
                            setSpecialDietNote(
                                typeof serverOrder.data.special_diet_note === 'string'
                                    ? serverOrder.data.special_diet_note
                                    : ''
                            );

                            // `full_day_order` bol predtým len vo frontend localStorage,
                            // per-browser — na inom zariadení appka o Celodennej "nevedela"
                            // a editovala jedlá nezávisle, takže sa dala nechtiac odoslať
                            // len časť dňa (Veselý Úľ, 4.9.2026). Server je tu autoritatívny
                            // rovnako ako pri counts a poznámke vyššie; keď je zapnutý, jeho
                            // tri jedlá sú vždy identické (tak ich posiela `submitOrder`
                            // nižšie), takže dáta pre prepínač stačí zobrať z ktoréhokoľvek.
                            const isFullDayOrder = serverOrder.data.full_day_order === true;
                            setFullDayOrderState(isFullDayOrder);
                            if (isFullDayOrder) {
                                setFullDayData(merged.breakfast);
                            }

                            // Update active meals based on content
                            setActiveMeals(prevActive => {
                                const newActive = { ...prevActive };
                                if (!OrderService.isMealEmpty(merged.breakfast)) newActive.breakfast = true;
                                if (!OrderService.isMealEmpty(merged.lunch)) newActive.lunch = true;
                                if (!OrderService.isMealEmpty(merged.olovrant)) newActive.olovrant = true;
                                return newActive;
                            });
                            return merged;
                        }
                    }
                }
            } catch (e) {
                logger.error("Failed to fetch order", e);
            }
            return null;
        };

        // `submitOrder` na tento promise čaká, aby pre jedlá, ktorých sa klient
        // v tejto session nedotkol, mohol použiť čerstvú serverovú hodnotu
        // namiesto prípadne zastaraného localStorage draftu (Emjoy, 3.9.2026 —
        // viď komentár pri `submitOrder`).
        orderLoadRef.current = user ? loadOrder() : Promise.resolve(null);

        return () => { isMounted = false; };
    }, [selectedDate, apiFetch, user, activePrevadzkaId, waitForPrevadzkaChoice]); // Depend on selectedDate

    const [globalDeadlines, setGlobalDeadlines] = useState({ breakfast: '10:00', breakfast_day_before: false, lunch: '10:00', lunch_day_before: false, olovrant: '10:00', olovrant_day_before: false, menu_bc: '07:30', menu_bc_days_before: 2 });
    const [clientContactInfo, setClientContactInfo] = useState<ClientContactInfo>({
        name: '',
        role: '',
        email: '',
        phone: '',
    });

    // Fetch Global Settings
    useEffect(() => {
        const fetchSettings = async () => {
            try {
                const res = await apiFetch(`${API_URL}/admin/global-settings/`);
                if (res.ok) {
                    const data = await res.json();
                    // Map backend fields (deadline_*) to expected state structure
                    const mapped = {
                        breakfast: data.deadline_breakfast || '10:00',
                        breakfast_day_before: !!data.deadline_breakfast_is_day_before,
                        lunch: data.deadline_lunch || '10:00',
                        lunch_day_before: !!data.deadline_lunch_is_day_before,
                        olovrant: data.deadline_olovrant || '10:00',
                        olovrant_day_before: !!data.deadline_olovrant_is_day_before,
                        menu_bc: data.deadline_menu_bc || '07:30',
                        menu_bc_days_before: data.deadline_menu_bc_days_before ?? 2,
                    };
                    setGlobalDeadlines(mapped);
                    setClientContactInfo({
                        name: data.client_contact_name || '',
                        role: data.client_contact_role || '',
                        email: data.client_contact_email || '',
                        phone: data.client_contact_phone || '',
                    });
                }
            } catch (e) {
                logger.error("Failed to fetch global settings", e);
            }
        };
        if (user) fetchSettings();
    }, [apiFetch, user]);

    useEffect(() => {
        const fetchPortionTypes = async () => {
            try {
                const res = await apiFetch(`${API_URL}/admin/portion-types/`);
                if (!res.ok) return;
                const data = await res.json();
                const items: PortionType[] = Array.isArray(data) ? data : data.results || [];
                setPortionTypes(items.filter((item) => item.is_active));
            } catch (e) {
                logger.error("Failed to fetch portion types", e);
            }
        };
        if (user) fetchPortionTypes();
    }, [apiFetch, user]);

    // Meal plan availability: mealKey → Set of available menu_variants; null = no plan = no restriction
    const [mealPlanAvailability, setMealPlanAvailability] = useState<Record<string, Set<string>> | null>(null);
    const [dietMenuVariantMap, setDietMenuVariantMap] = useState<Record<string, string>>({});

    useEffect(() => {
        const controller = new AbortController();
        const fetchDietMenuVariantMap = async () => {
            try {
                const res = await apiFetch(`${API_URL}/diets/menu-variant-map/?date=${selectedDate}`, { signal: controller.signal });
                if (!res.ok) return;
                const data = await res.json() as Record<string, string>;
                if (controller.signal.aborted) return;
                setDietMenuVariantMap(data);
            } catch (e) {
                if (controller.signal.aborted) return;
                logger.error("Failed to fetch diet menu variant map", e);
            }
        };
        if (user && packSeparatelyEnabled) fetchDietMenuVariantMap();
        return () => controller.abort();
    }, [selectedDate, apiFetch, user, packSeparatelyEnabled]);

    useEffect(() => {
        const controller = new AbortController();
        const fetchMealPlanAvailability = async () => {
            try {
                const res = await apiFetch(`${API_URL}/meal-plans/by-date/?date=${selectedDate}`, { signal: controller.signal });
                if (!res.ok) {
                    if (controller.signal.aborted) return;
                    setMealPlanAvailability(null);
                    return;
                }
                const data = await res.json();
                if (!data.exists || !Array.isArray(data.items) || data.items.length === 0) {
                    if (controller.signal.aborted) return;
                    setMealPlanAvailability(null);
                    return;
                }
                // A meal key is only restricted to specific menu variants when
                // its published item(s) actually carry a menu_variant. A single
                // uniform selection (no menu_variant) means the meal is available for
                // every menu variant, so it must NOT be treated as "occupied".
                const availability: Record<string, Set<string>> = {};
                const unrestrictedMealKeys = new Set<string>();
                for (const item of data.items) {
                    const mealKey = JEDALNICEK_CATEGORY_TO_MEAL_KEY[item.category] || item.category;
                    if (item.menu_variant) {
                        if (!availability[mealKey]) availability[mealKey] = new Set();
                        availability[mealKey].add(item.menu_variant);
                    } else {
                        unrestrictedMealKeys.add(mealKey);
                    }
                }
                for (const mealKey of unrestrictedMealKeys) {
                    delete availability[mealKey];
                }
                if (controller.signal.aborted) return;
                setMealPlanAvailability(availability);
            } catch (e) {
                if (controller.signal.aborted) return;
                logger.error("Failed to fetch meal plan availability", e);
                setMealPlanAvailability(null);
            }
        };
        if (user) fetchMealPlanAvailability();
        return () => controller.abort();
    }, [selectedDate, apiFetch, user]);

    // Holidays: set of date strings "YYYY-MM-DD" that are blocked
    const [holidays, setHolidays] = useState<Set<string>>(new Set());

    useEffect(() => {
        const fetchHolidays = async () => {
            try {
                const allHolidays: { date: string }[] = [];
                let url: string | null = `${API_URL}/holidays/`;
                while (url) {
                    const res = await apiFetch(url);
                    if (!res.ok) break;
                    const data = await res.json();
                    if (Array.isArray(data)) {
                        allHolidays.push(...data);
                        break;
                    }
                    allHolidays.push(...(data.results ?? []));
                    url = data.next ?? null;
                }
                setHolidays(new Set(allHolidays.map((h) => h.date)));
            } catch (e) {
                logger.error("Failed to fetch holidays", e);
            }
        };
        if (user) fetchHolidays();
    }, [apiFetch, user]);

    // Voľno prevádzky (#490): na rozdiel od `holidays` platí len pre jednu
    // prevádzku, takže sa načíta všetko dostupné a filtruje sa až podľa
    // aktívnej prevádzky — prepnutie prevádzky tak nestojí ďalší request.
    const [allClosures, setAllClosures] = useState<PrevadzkaClosure[]>([]);

    useEffect(() => {
        const fetchClosures = async () => {
            try {
                const rows = await fetchAllPages<PrevadzkaClosure>(
                    apiFetch,
                    `${API_URL}/prevadzka-closures/`,
                );
                setAllClosures(rows);
            } catch (e) {
                logger.error("Failed to fetch prevadzka closures", e);
            }
        };
        if (user) fetchClosures();
    }, [apiFetch, user]);

    const closures = useMemo(() => {
        const days = new Set<string>();
        for (const closure of allClosures) {
            if (activePrevadzkaId && closure.prevadzka !== activePrevadzkaId) continue;
            const cursor = fromDateKey(closure.date_from);
            const last = fromDateKey(closure.date_to);
            // Rozsah sa rozbalí na jednotlivé dni, aby ho `businessDay` helper
            // aj banner v OrderPage vedeli overiť jedným `Set.has()`.
            while (cursor <= last) {
                days.add(toDateKey(cursor));
                cursor.setDate(cursor.getDate() + 1);
            }
        }
        return days;
    }, [allClosures, activePrevadzkaId]);

    // Order persistence: no autosave/debounce writes draft orders to the backend.
    // Draft state is kept only in localStorage (see safeParse logic above) to survive page refreshes.


    // Lazy Copy Logic: Trigger when a meal is OPENED (active becomes true)
    useEffect(() => {
        if (!currentOrder) return;

        // Check for specific meals that need copying
        // We do this check first to avoid expensive history lookup if not needed
        const mealsToCopy: (keyof DailyOrder)[] = [];
        (['breakfast', 'lunch', 'olovrant'] as const).forEach(mealKey => {
            if (activeMeals[mealKey] && !touchedMeals.has(mealKey)) {
                if (OrderService.isMealEmpty(currentOrder[mealKey])) {
                    if (currentOrder.status !== 'submitted') {
                        mealsToCopy.push(mealKey);
                    }
                }
            }
        });

        if (mealsToCopy.length === 0) return;

        // Perform History Lookup (Optimized - outside loop)
        const history: (DailyOrder & { date: string })[] = [];
        // Use loop to avoid mutation of single Date object
        for (let i = 1; i <= 30; i++) {
            const curr = parseDate(selectedDate);
            curr.setDate(curr.getDate() - i);
            const dStr = OrderService.toLocalDateString(curr);
            const raw = localStorage.getItem(scopedKey('order', dStr));
            if (raw) {
                try {
                    const p = JSON.parse(raw);
                    // Safe cast since we assign it
                    (p as DailyOrder & { date: string }).date = dStr;
                    history.push(p as DailyOrder & { date: string });
                } catch (e) {
                    logger.error('Failed to parse stored order for date', dStr, e);
                    // Clean up malformed data
                    localStorage.removeItem(`order_${dStr}`);
                }
            }
        }

        const template = OrderService.findLastNonZeroDay(history, selectedDate);
        if (template) {
            let hasUpdates = false;
            const updatesObj: Partial<DailyOrder> = {};
            const newTouched = new Set(touchedMeals);

            mealsToCopy.forEach(mealKey => {
                // Check if key corresponds to a meal property (DailyOrder has 'status' which is string)
                if (mealKey === 'status') return;

                const mealData = template[mealKey] as MealData;
                if (mealData && !OrderService.isMealEmpty(mealData)) {
                    if (import.meta.env.DEV) {
                        logger.debug(`Lazy copying ${mealKey} from ${(template as unknown as { date: string }).date}`);
                    }
                    updatesObj[mealKey] = JSON.parse(JSON.stringify(mealData));
                    newTouched.add(mealKey);
                    hasUpdates = true;
                }
            });

            if (hasUpdates) {
                setCurrentOrder(prev => ({ ...prev, ...updatesObj }));
                setTouchedMeals(newTouched);
            }
        }

        // We use functional updates or separate logic to avoid dependency cycle.
        // But strictly here, since we depend on `currentOrder` to CHECK emptiness, 
        // and then SET `currentOrder` if empty, it will naturally re-run.
        // The re-run will find it NOT empty, and thus stabilize.
        // To be safe against "React Hook useEffect has missing dependencies", we include them.
    }, [activeMeals, selectedDate, currentOrder, touchedMeals, scopedKey]);

    // Kopírovanie medzi chodmi je výhradne akcia používateľa (tlačidlá „Načítať z…“).
    // Automatické kopírovanie na pozadí tu kedysi bolo, ale keďže sa spúšťalo len kým
    // bol cieľový chod „nedotknutý“, raz zabralo a inokedy nie — presne tá nestabilita,
    // ktorú klient hlásil. Jednorazová akcia je predvídateľná a hodnoty ostávajú
    // ručne editovateľné.

    // Actions


    const toggleMeal = (mealKey: string) => {
        setActiveMeals(prev => ({ ...prev, [mealKey]: !prev[mealKey] }));
    };

    const toggleFullDay = () => {
        setFullDayOrderState(prev => !prev);
    };

    /**
     * Celodenka drží dáta mimo `currentOrder` (jeden MealData, ktorý sa pri odoslaní
     * rozkopíruje do všetkých chodov). Aby platili tie isté pravidlá vrátane
     * „zabaliť zvlášť“, obalíme MealData do dočasnej objednávky a použijeme rovnaké
     * `OrderService` updatery ako pri chodoch.
     */
    const wrapFullDay = (meal: MealData): DailyOrder => ({
        status: 'draft' as const,
        breakfast: meal,
        lunch: OrderService.createEmptyMeal(),
        olovrant: OrderService.createEmptyMeal(),
    });

    const updateFullDayMenuCount = (category: string, menuType: string, count: number) => {
        // Rovnaký zamknutý strop ako bežná objednávka (viď `updateMenuCount`) —
        // celodenná objednávka má vlastný blob mimo DailyOrder, ale rovnaký
        // Menu B/C/D termín (user 2.9.2026).
        let clampedCount = count;
        if (
            OrderService.RESTRICTED_MENUS.includes(menuType)
            && !OrderService.checkMenuBcDeadline(selectedDate, globalDeadlines)
        ) {
            const ceiling = restrictedMenuCeilingsRef.current[`${FULL_DAY_CEILING_LABEL}|${category}|${menuType}`] ?? 0;
            if (clampedCount > ceiling) {
                clampedCount = ceiling;
            }
        }

        notifyCategoryAdjustments(
            fullDayData[category],
            OrderService.updateMenuCount(wrapFullDay(fullDayData), 'breakfast', category, menuType, clampedCount).breakfast[category]
        );
        setFullDayData(prev =>
            OrderService.updateMenuCount(wrapFullDay(prev), 'breakfast', category, menuType, clampedCount).breakfast
        );
    };

    const updateFullDayDiet = (category: string, diet: string, count: number) => {
        notifyCategoryAdjustments(
            fullDayData[category],
            OrderService.updateDiet(wrapFullDay(fullDayData), 'breakfast', category, diet, count).breakfast[category]
        );
        setFullDayData(prev =>
            OrderService.updateDiet(wrapFullDay(prev), 'breakfast', category, diet, count).breakfast
        );
    };

    const updateFullDayPackSeparately = (
        category: string,
        kind: 'menus' | 'diets',
        key: string,
        count: number,
        target: PackTarget = 'zvlast'
    ) => {
        setFullDayData(prev =>
            OrderService.updatePackSeparately(wrapFullDay(prev), 'breakfast', category, kind, key, count, target).breakfast
        );
    };

    const clearFullDay = () => {
        setFullDayData(OrderService.createEmptyMeal());
    };



    /**
     * Upozorní, keď zníženie objednaného počtu stiahlo naviazaný „zvlášť“ počet.
     *
     * Zámerne beží MIMO `setCurrentOrder` updateru: updater musí byť čistý, a toast
     * je setState iného kontextu — vnútri updateru by sa v StrictMode spustil dvakrát
     * a menil cudzí komponent počas render fázy.
     */
    const notifyCategoryAdjustments = (
        beforeCategory?: CategoryData,
        afterCategory?: CategoryData
    ) => {
        if (!beforeCategory || !afterCategory) return;
        OrderService.getPackSeparatelyAdjustments(beforeCategory, afterCategory).forEach(
            ({ count: nextCount, target }) => {
                const label = target === 'gn' ? 'Zvlášť do GN' : 'Zvlášť';
                toastWarning(`${label} počet znížený na ${nextCount} (limit objednávky).`);
            }
        );
    };

    const notifyPackSeparatelyAdjustments = (
        before: DailyOrder,
        after: DailyOrder,
        mealKey: 'breakfast' | 'lunch' | 'olovrant',
        category: string
    ) => {
        notifyCategoryAdjustments(before[mealKey]?.[category], after[mealKey]?.[category]);
    };

    const updateDiet = (mealKey: 'breakfast' | 'lunch' | 'olovrant', category: string, diet: string, count: number) => {
        setTouchedMeals(prev => {
            const next = new Set(prev);
            next.add(mealKey);
            return next;
        });
        notifyPackSeparatelyAdjustments(
            currentOrder,
            OrderService.updateDiet(currentOrder, mealKey, category, diet, count),
            mealKey,
            category
        );
        setCurrentOrder((prev) => ({
            ...OrderService.updateDiet(prev, mealKey, category, diet, count),
            status: 'draft',
        }));
    };

    const updatePackSeparately = (
        mealKey: 'breakfast' | 'lunch' | 'olovrant',
        category: string,
        kind: 'menus' | 'diets',
        key: string,
        count: number,
        target: PackTarget = 'zvlast'
    ) => {
        setTouchedMeals(prev => {
            const next = new Set(prev);
            next.add(mealKey);
            return next;
        });
        setCurrentOrder((prev) => ({ ...OrderService.updatePackSeparately(prev, mealKey, category, kind, key, count, target), status: 'draft' }));
    };

    const clearMeal = (mealKey: 'breakfast' | 'lunch' | 'olovrant') => {
        setTouchedMeals(prev => {
            const next = new Set(prev);
            next.add(mealKey);
            return next;
        });
        setCurrentOrder((prev) => ({
            ...prev,
            [mealKey]: OrderService.createEmptyMeal(),
            status: 'draft',
        }));
    };



    const submitOrder = async (date: string, prevadzkaId = activePrevadzkaId) => {
        // Backend ukladá `data` ako celok, žiadny merge (`instance.data = new_data`
        // v serializeri) — submit tak musí poslať kompletnú a AKTUÁLNU objednávku
        // za všetky jedlá naraz, nielen to, čo klient práve upravil. Počkáme na
        // počiatočný GET pre (date, prevadzkaId): kým nedobehne, `currentOrder`
        // môže byť ešte starý localStorage draft z inej session/zariadenia.
        // Pre jedlo, ktoré klient v TEJTO session vôbec nezmenil (`touchedMeals`),
        // uprednostníme čerstvú serverovú hodnotu pred týmto draftom — inak by
        // sa nedotknuté jedlo (napr. obed) potichu prepísalo starými/nulovými
        // počtami a vynulovalo tak reálne objednané Menu B/C (Emjoy, 3.9.2026:
        // škola upravila len raňajky, appka poslala aj nedotknutý obed so
        // starým draftom a vymazala tak objednané Menu B/C).
        const freshOrder = await orderLoadRef.current;

        const isMealActive = (key: 'breakfast' | 'lunch' | 'olovrant') =>
            fullDayOrder ? adminVisibleMeals.includes(key) : activeMeals[key];

        const mealData = (key: 'breakfast' | 'lunch' | 'olovrant') => {
            if (fullDayOrder) return fullDayData;
            if (freshOrder && !touchedMeals.has(key)) return freshOrder[key];
            return currentOrder[key];
        };

        const payload = {
            breakfast: isMealActive('breakfast') ? mealData('breakfast') : OrderService.createEmptyMeal(),
            lunch: isMealActive('lunch') ? mealData('lunch') : OrderService.createEmptyMeal(),
            olovrant: isMealActive('olovrant') ? mealData('olovrant') : OrderService.createEmptyMeal(),
        };

        try {
            const response = await apiFetch(`${API_URL}/orders/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    date,
                    status: 'submitted',
                    ...(prevadzkaId ? { prevadzka: prevadzkaId } : {}),
                    data: {
                        ...payload,
                        special_diet_note: specialDietNote || undefined,
                        // Server-persistovaný príznak (Veselý Úľ, 4.9.2026 — viď
                        // komentár vyššie) — appka ho pri ďalšom načítaní vie obnoviť
                        // na ktoromkoľvek zariadení, nielen tam, kde bol zapnutý.
                        full_day_order: fullDayOrder,
                    }
                })
            });

            if (!response.ok) {
                throw await parseApiError(response);
            }

            // Only update local state AFTER successful API call
            const orderWithStatus: DailyOrder = {
                ...currentOrder,
                ...payload,
                status: 'submitted'
            };
            setCurrentOrder(orderWithStatus);
            restrictedMenuCeilingsRef.current = OrderService.extractRestrictedMenuCounts(orderWithStatus);
            if (fullDayOrder) {
                // Celodenná objednávka ide v payloade pod 'breakfast', ale jej
                // vlastný strop žije pod FULL_DAY_CEILING_LABEL — extrakcia vyššie
                // by ho inak omylom zapísala pod 'breakfast' a `updateFullDayMenuCount`
                // by ho nikdy nenašla.
                restrictedMenuCeilingsRef.current = {
                    ...restrictedMenuCeilingsRef.current,
                    ...OrderService.extractRestrictedMenuCountsForMeal(fullDayData, FULL_DAY_CEILING_LABEL),
                };
            }

            logger.debug('Order submitted to API');
            return true;
        } catch (e) {
            logger.error('Failed to submit order to API', e);
            throw e;
        }
    };

    const deleteOrder = async (date: string, prevadzkaId = activePrevadzkaId) => {
        const empty: DailyOrder = {
            status: 'draft',
            breakfast: OrderService.createEmptyMeal(),
            lunch: OrderService.createEmptyMeal(),
            olovrant: OrderService.createEmptyMeal()
        };

        // If we are deleting the currently viewed order, update state
        if (date === selectedDate) {
            setCurrentOrder(empty);
            setActiveMeals({ breakfast: false, lunch: false, olovrant: false });
            // local storage updates via useEffect
        } else {
            // If deleting another day (e.g. from history), manually clear its local storage
            // so it doesn't persist as "submitted" or "dirty"
            localStorage.removeItem(scopedKey('order', date));
            localStorage.removeItem(scopedKey('activeMeals', date));
        }

        try {
            // Soft delete by setting status to draft and empty data
            await apiFetch(`${API_URL}/orders/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    date,
                    status: 'draft',
                    ...(prevadzkaId ? { prevadzka: prevadzkaId } : {}),
                    data: empty
                })
            });
            logger.debug('Order deleted/reset on API');
        } catch (e) {
            logger.error('Failed to delete order on API', e);
        }
    };

    // Admin Constraints
    // Fall back to defaults only when the setting is null/undefined;
    // an explicitly empty array means "show none".
    const prevadzkaSettings = prevadzky.find((item) => item.id === activePrevadzkaId);

    const adminVisibleMenusSetting = prevadzkaSettings?.visible_menus;
    // "D" nie je vo fallbacku — je to British School špecifikum (Cluster C),
    // musí zostať zosynchronizované s `DEFAULT_VISIBLE_MENUS`
    // (backend/api/default_visibility.py).
    const adminVisibleMenusBase = adminVisibleMenusSetting == null
        ? ['A', 'B', 'C', 'V']
        : adminVisibleMenusSetting;
    const adminVisibleMenus = filterMenusByDay(
        adminVisibleMenusBase,
        prevadzkaSettings?.menu_day_restrictions,
        selectedDate,
    );

    const resolvedVisibleMenusForMeal = (mealKey: 'breakfast' | 'lunch' | 'olovrant') =>
        getVisibleMenusForMeal(mealKey, adminVisibleMenus);

    const adminVisibleMealsSetting = prevadzkaSettings?.visible_meals;
    const adminVisibleMeals = adminVisibleMealsSetting == null
        ? ['breakfast', 'lunch', 'olovrant']
        : adminVisibleMealsSetting;

    const visibleDietSetting = prevadzkaSettings?.visible_diets as
        | DietDetail[]
        | undefined;
    const visibleDietDetails: DietDetail[] =
        visibleDietSetting && visibleDietSetting.length > 0
        ? [...visibleDietSetting].sort(
            (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.name.localeCompare(b.name, 'sk')
        )
        : [];
    const adminVisibleDiets = visibleDietDetails.length > 0
        ? visibleDietDetails.map(d => d.name)
        : [];

    const getAvailableDiets = (categoryName: string) =>
        OrderService.getAvailableDietsWithSpecial(categoryName, adminVisibleDiets);



    // Enhanced updateMenuCount to handle forced diets
    const updateMenuCount = (mealKey: 'breakfast' | 'lunch' | 'olovrant', category: string, menuType: string, count: number) => {
        // Menu B/C/D po prísnom termíne: nedá sa nahlásiť/zvýšiť nad naposledy
        // potvrdený (server/submit) počet, len znížiť/odhlásiť — pokus o vyššie
        // číslo (aj cez tlačidlo +, aj priamym zadaním) sa preskočí naspäť na
        // ten zamknutý strop (user 2.9.2026). Backend to aj tak vynúti
        // (`_validate_deadlines`), toto je len rovnaká UX bez zbytočného
        // zamietnutého requestu.
        let clampedCount = count;
        if (
            OrderService.RESTRICTED_MENUS.includes(menuType)
            && !OrderService.checkMenuBcDeadline(selectedDate, globalDeadlines)
        ) {
            const ceiling = restrictedMenuCeilingsRef.current[`${mealKey}|${category}|${menuType}`] ?? 0;
            if (clampedCount > ceiling) {
                clampedCount = ceiling;
            }
        }

        setTouchedMeals(prev => {
            const next = new Set(prev);
            next.add(mealKey);
            return next;
        });
        notifyPackSeparatelyAdjustments(
            currentOrder,
            OrderService.updateMenuCount(currentOrder, mealKey, category, menuType, clampedCount),
            mealKey,
            category
        );
        setCurrentOrder((prev) => ({
            ...OrderService.updateMenuCount(prev, mealKey, category, menuType, clampedCount),
            status: 'draft',
        }));
    };

    /** Immediately copy yesterday’s lunch into breakfast. Returns true if data was found. */
    /** Menu B/C/D zo skopírovaného jedla zastropuje na strop CIEĽOVÉHO chodu, keď
     * je termín Menu B/C už zavretý — inak by kopírovanie (z iného dňa/chodu,
     * spred termínu) obišlo `updateMenuCount`-ov strop a appka by nechala
     * cudzie B/C/D prejsť až do zamietnutého submitu (Little Big, 3.9.2026). */
    const clampCopiedMealIfLocked = (meal: MealData, targetMealKey: string): MealData => {
        if (OrderService.checkMenuBcDeadline(selectedDate, globalDeadlines)) return meal;
        return OrderService.clampRestrictedMenusForMeal(meal, restrictedMenuCeilingsRef.current, targetMealKey);
    };

    const loadBreakfastFromPrevLunch = (): boolean => {
        const prevDate = parseDate(selectedDate);
        prevDate.setDate(prevDate.getDate() - 1);
        const prevDateStr = OrderService.toLocalDateString(prevDate);
        const raw = localStorage.getItem(scopedKey('order', prevDateStr));
        if (raw) {
            try {
                const prevOrder = JSON.parse(raw);
                if (prevOrder.lunch && !OrderService.isMealEmpty(prevOrder.lunch)) {
                    setCurrentOrder((prev) => ({
                        ...prev,
                        breakfast: clampCopiedMealIfLocked(JSON.parse(JSON.stringify(prevOrder.lunch)), 'breakfast'),
                        status: 'draft',
                    }));
                    setActiveMeals(prev => ({ ...prev, breakfast: true }));
                    setTouchedMeals(prev => { const n = new Set(prev); n.add('breakfast'); return n; });
                    return true;
                }
            } catch (e) { logger.error(e); }
        }
        return false;
    };

    /** Immediately copy today’s current breakfast into lunch. Returns true if breakfast had data. */
    const copyLunchFromCurrentBreakfast = (): boolean => {
        if (OrderService.isMealEmpty(currentOrder.breakfast)) return false;
        setCurrentOrder((prev) => ({
            ...prev,
            lunch: clampCopiedMealIfLocked(JSON.parse(JSON.stringify(prev.breakfast)), 'lunch'),
            status: 'draft',
        }));
        setActiveMeals(prev => ({ ...prev, lunch: true }));
        setTouchedMeals(prev => { const n = new Set(prev); n.add('lunch'); return n; });
        return true;
    };

    /** Immediately copy today’s current lunch into olovrant. Returns true if lunch had data. */
    const copyOlovrantFromCurrentLunch = (): boolean => {
        if (OrderService.isMealEmpty(currentOrder.lunch)) return false;
        setCurrentOrder((prev) => ({
            ...prev,
            olovrant: clampCopiedMealIfLocked(JSON.parse(JSON.stringify(prev.lunch)), 'olovrant'),
            status: 'draft',
        }));
        setActiveMeals(prev => ({ ...prev, olovrant: true }));
        setTouchedMeals(prev => { const n = new Set(prev); n.add('olovrant'); return n; });
        return true;
    };

    // Na rozdiel od visible_menus/visible_meals/visible_diets (kde prázdne pole
    // znamená vedomú voľbu adminom) je visible_portion_types M2M, ktoré môže byť
    // prázdne aj len preto, že ešte nebolo dobackfillované (viď default_visibility.py) —
    // preto tu prázdne pole znamená "bez obmedzenia", rovnako ako v _build_auto_data.
    const adminVisiblePortionTypesSetting = prevadzkaSettings?.visible_portion_types;
    const adminVisiblePortionTypeNames = !adminVisiblePortionTypesSetting || adminVisiblePortionTypesSetting.length === 0
        ? null
        : new Set(adminVisiblePortionTypesSetting.map((portionType) => portionType.name));
    const availableCategories =
        portionTypes.length > 0 ? portionTypes.map((pt) => pt.name) : CATEGORIES;
    const enabledCategories = adminVisiblePortionTypeNames == null
        ? availableCategories
        : availableCategories.filter((name) => adminVisiblePortionTypeNames.has(name));

    return {
        enabledCategories,
        portionTypes,
        visibleDietDetails,
        selectedDate, setSelectedDate,
        currentOrder, activeMeals, toggleMeal,
        fullDayOrder, toggleFullDay,
        fullDayData, updateFullDayMenuCount, updateFullDayDiet, updateFullDayPackSeparately, clearFullDay,
        specialDietNote, setSpecialDietNote,
        updateMenuCount, updateDiet, updatePackSeparately,
        getAvailableDiets,
        prevDayLunches,
        clearMeal,
        loadBreakfastFromPrevLunch,
        copyLunchFromCurrentBreakfast,
        copyOlovrantFromCurrentLunch,
        submitOrder, deleteOrder,
        adminVisibleMenus,
        getVisibleMenusForMeal: resolvedVisibleMenusForMeal,
        adminVisibleMeals,
        globalDeadlines,
        clientContactInfo,
        holidays,
        closures,
        mealPlanAvailability,
        packSeparatelyEnabled,
        dietMenuVariantMap,
    };
};
