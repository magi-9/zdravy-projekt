import React, { useEffect, useMemo, useState } from 'react';
import { Apple, Coffee, Copy, Trash2, Utensils, X } from 'lucide-react';
import DietSelector from '../client/components/order/DietSelector';
import OrderFormBody from '../client/components/order/OrderFormBody';
import OrderSummary from '../client/components/order/OrderSummary';
import PackSeparatelySelector from '../client/components/order/PackSeparatelySelector';
import OrderService, { DailyOrder, MealData, PackTarget } from '../client/services/OrderService';
import { filterMealsByDay, filterMenusByDay, getVisibleMenusForMeal as resolveVisibleMenusForMeal } from '../client/hooks/useOrder';
import { CATEGORIES } from '../client/config/constants';
import { useAuth } from '../../context/auth';
import { useToast } from '../../context/ToastContext';
import { Button, Field, Input } from './ui';

const API_URL = import.meta.env.VITE_API_URL || '/api';
const CLOSED_DAY_MESSAGE = 'Deň je uzavretý, objednávky sa už nedajú upravovať.';

interface ExistingOrder {
    id: number;
    date: string;
    data: {
        breakfast?: unknown;
        lunch?: unknown;
        olovrant?: unknown;
        special_diet_note?: unknown;
    };
}

interface Props {
    clientId?: string | number | null;
    prevadzkaId: string | number;
    visibleMenus: string[];
    /** `{menu písmeno: [ISO deň, 1=pondelok..7=nedeľa]}` — napr. Menu B len v piatok. */
    menuDayRestrictions?: Record<string, number[]> | null;
    visibleMeals: string[];
    /** `{jedlo: [ISO deň, 1=pondelok..7=nedeľa]}` — napr. raňajky len v piatok. */
    mealDayRestrictions?: Record<string, number[]> | null;
    visibleDiets: number[];
    portionTypeNames: string[];
    packSeparatelyEnabled: boolean;
    allDiets: { id: number; name: string }[];
    existingOrder?: ExistingOrder | null;
    /** Objednávky prevádzky — zdroj pre „Načítať z včerajška“ (obed predošlého dňa). */
    knownOrders?: ExistingOrder[];
    onClose: () => void;
    onSaved: () => void;
}

type MealKey = 'breakfast' | 'lunch' | 'olovrant';

type PackSeparatelyMealKey = MealKey | 'fullDay';

const MEAL_CONFIG: { key: MealKey; label: string; icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }> }[] = [
    { key: 'breakfast', label: 'Raňajky', icon: Coffee },
    { key: 'lunch', label: 'Obed', icon: Utensils },
    { key: 'olovrant', label: 'Olovrant', icon: Apple },
];

const FALLBACK_CATEGORIES = CATEGORIES;

const getBaseCategories = (portionTypeNames: string[]) =>
    portionTypeNames.length > 0 ? portionTypeNames : FALLBACK_CATEGORIES;

const _categoryHasCounts = (categoryData: unknown): boolean => {
    if (!categoryData || typeof categoryData !== 'object') return false;
    const menuCounts = (categoryData as { menuCounts?: Record<string, number> }).menuCounts;
    if (!menuCounts) return false;
    return Object.values(menuCounts).some((count) => (count || 0) > 0);
};

// Vracia len kategórie, ktoré majú v uloženej objednávke reálne nenulové počty —
// prázdna kostra (kľúč prítomný, počty 0) sa nepočíta. Denný auto-vytvorený
// záznam má kostru pre VŠETKY veľkosti bez ohľadu na visible_portion_types
// prevádzky, takže brať do editora každý existujúci kľúč by vrátilo do UI aj
// veľkosti, ktoré má prevádzka zámerne vypnuté (#Rusovce — objednanie Jasle
// napriek tomu, že prevádzka má povolené len Škôlku a Dospelých).
const extractCategoriesFromMeal = (meal: unknown): string[] => {
    if (!meal || typeof meal !== 'object' || Array.isArray(meal)) return [];
    return Object.entries(meal as Record<string, unknown>)
        .filter(([, categoryData]) => _categoryHasCounts(categoryData))
        .map(([key]) => key);
};

const buildCategories = (portionTypeNames: string[], existingOrder?: ExistingOrder | null) => {
    const categories = new Set(getBaseCategories(portionTypeNames));
    if (existingOrder?.data) {
        extractCategoriesFromMeal(existingOrder.data.breakfast).forEach((key) => categories.add(key));
        extractCategoriesFromMeal(existingOrder.data.lunch).forEach((key) => categories.add(key));
        extractCategoriesFromMeal(existingOrder.data.olovrant).forEach((key) => categories.add(key));
    }
    return Array.from(categories);
};

function buildInitialOrder(categories: string[], existingOrder?: ExistingOrder | null): DailyOrder {
    const emptyMeal = () => OrderService.createEmptyMealFor(categories);
    const empty = {
        status: 'draft' as const,
        breakfast: emptyMeal(),
        lunch: emptyMeal(),
        olovrant: emptyMeal(),
    };
    if (!existingOrder?.data) return empty;

    const enforceOrEmpty = (raw: unknown): MealData =>
        OrderService.enforceStructure(raw, emptyMeal()) as MealData;

    return {
        status: 'draft',
        breakfast: enforceOrEmpty(existingOrder.data.breakfast),
        lunch: enforceOrEmpty(existingOrder.data.lunch),
        olovrant: enforceOrEmpty(existingOrder.data.olovrant),
    };
}

const packFieldFor = (target: PackTarget): 'packSeparately' | 'packSeparatelyGn' =>
    target === 'gn' ? 'packSeparatelyGn' : 'packSeparately';
const otherPackTarget = (target: PackTarget): PackTarget => (target === 'gn' ? 'zvlast' : 'gn');

// Jedna porcia nemôže byť naraz "zvlášť" aj "zvlášť do GN" - dostupný počet pre
// TENTO cieľ je objednané mínus to, čo už drží ten druhý (viď packSeparately.ts
// na klientskej strane objednávky, kde platí rovnaké pravidlo).
const buildPackSeparatelyItemsForTarget = (categories: string[], target: PackTarget, mealData?: MealData) =>
    categories.flatMap((category) => {
        const categoryData = mealData?.[category];
        if (!categoryData) return [];

        const otherField = packFieldFor(otherPackTarget(target));

        const menuItems = Object.entries(categoryData.menuCounts || {})
            .filter(([, orderedCount]) => orderedCount > 0)
            .map(([menuKey, rawOrderedCount]) => ({
                category,
                kind: 'menus' as const,
                keyName: menuKey,
                orderedCount: Math.max(0, rawOrderedCount - (categoryData[otherField]?.menus?.[menuKey] || 0)),
                count: categoryData[packFieldFor(target)]?.menus?.[menuKey] || 0,
                target,
            }));

        const dietItems = Object.entries(categoryData.diets || {})
            .filter(([, orderedCount]) => orderedCount > 0)
            .map(([dietKey, rawOrderedCount]) => ({
                category,
                kind: 'diets' as const,
                keyName: dietKey,
                orderedCount: Math.max(0, rawOrderedCount - (categoryData[otherField]?.diets?.[dietKey] || 0)),
                count: categoryData[packFieldFor(target)]?.diets?.[dietKey] || 0,
                target,
            }));

        return [...menuItems, ...dietItems];
    });

const buildPackSeparatelyItems = (categories: string[], mealData?: MealData) => [
    ...buildPackSeparatelyItemsForTarget(categories, 'zvlast', mealData),
    ...buildPackSeparatelyItemsForTarget(categories, 'gn', mealData),
];

const AdminOrderEditorModal: React.FC<Props> = ({
    clientId,
    prevadzkaId,
    visibleMenus,
    menuDayRestrictions,
    visibleMeals,
    mealDayRestrictions,
    visibleDiets,
    portionTypeNames,
    packSeparatelyEnabled,
    allDiets,
    existingOrder,
    knownOrders = [],
    onClose,
    onSaved,
}) => {
    const { apiFetch } = useAuth();
    const toast = useToast();

    const categories = useMemo(
        () => buildCategories(portionTypeNames, existingOrder),
        [portionTypeNames, existingOrder],
    );
    const emptyMeal = useMemo(() => OrderService.createEmptyMealFor(categories), [categories]);
    const [date, setDate] = useState<string>(existingOrder?.date ?? OrderService.toLocalDateString(new Date()));
    const dateLabel = useMemo(() => OrderService.formatRelativeDayLabel(date), [date]);
    // Raňajky napr. "len v piatok" (#meal_day_restrictions) — editor predtým
    // toto obmedzenie vôbec nepoznal, takže admin vedel zapísať zakázaný deň
    // aj tam, kde ho klientský OrderPage už dávno skrýva.
    const visibleMealsForDay = useMemo(
        () => filterMealsByDay(visibleMeals, mealDayRestrictions, date),
        [visibleMeals, mealDayRestrictions, date],
    );
    const visibleMealsList = useMemo(
        () => MEAL_CONFIG.filter((m) => visibleMealsForDay.length === 0 || visibleMealsForDay.includes(m.key)),
        [visibleMealsForDay],
    );
    const firstVisibleMealKey = visibleMealsList[0]?.key;
    const enabledDietNames = useMemo(
        () => allDiets.filter((d) => visibleDiets.includes(d.id)).map((d) => d.name),
        [allDiets, visibleDiets],
    );
    // Menu B napr. "len v piatok" (#menu_day_restrictions) — rovnaká logika.
    const visibleMenusForMeal = (meal: MealKey) =>
        filterMenusByDay(resolveVisibleMenusForMeal(meal, visibleMenus), menuDayRestrictions, date);
    const [order, setOrder] = useState<DailyOrder>(() => buildInitialOrder(categories, existingOrder));
    const [fullDayOrder, setFullDayOrder] = useState(false);
    const [fullDayData, setFullDayData] = useState<MealData>(() => {
        const initialOrder = buildInitialOrder(categories, existingOrder);
        return firstVisibleMealKey ? OrderService.fastCopy(initialOrder[firstVisibleMealKey]) : OrderService.createEmptyMealFor(categories);
    });
    const [specialDietNote, setSpecialDietNote] = useState(
        typeof existingOrder?.data?.special_diet_note === 'string' ? existingOrder.data.special_diet_note : '',
    );
    const [activeMeals, setActiveMeals] = useState<Record<MealKey, boolean>>(() => {
        const initial = buildInitialOrder(categories, existingOrder);
        return {
            breakfast: !OrderService.isMealEmpty(initial.breakfast),
            lunch: !OrderService.isMealEmpty(initial.lunch),
            olovrant: !OrderService.isMealEmpty(initial.olovrant),
        };
    });
    const [activeDietModal, setActiveDietModal] = useState<{ meal: PackSeparatelyMealKey; category: string } | null>(null);
    const [packSeparatelyOpen, setPackSeparatelyOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [closedState, setClosedState] = useState<'checking' | 'open' | 'closed' | 'error'>('checking');

    useEffect(() => {
        let active = true;
        setClosedState('checking');

        const fetchClosedState = async () => {
            try {
                const res = await apiFetch(`${API_URL}/admin/closed-days/?date=${date}`);
                if (!res.ok) throw new Error('closed-day status failed');
                const payload = await res.json() as { is_closed: boolean };
                if (active) setClosedState(payload.is_closed ? 'closed' : 'open');
            } catch {
                if (active) setClosedState('error');
            }
        };

        void fetchClosedState();
        return () => {
            active = false;
        };
    }, [apiFetch, date]);

    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [onClose]);

    const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
        if (e.target === e.currentTarget) onClose();
    };

    const getAvailableDiets = (category: string): string[] =>
        OrderService.getAvailableDietsWithSpecial(category, enabledDietNames);

    const toggleMeal = (key: MealKey) => {
        setActiveMeals((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const toggleFullDay = () => {
        setFullDayOrder((prev) => !prev);
    };

    const updateMenuCount = (meal: MealKey, category: string, menuType: string, val: number) => {
        setOrder((prev) => OrderService.updateMenuCount(prev, meal, category, menuType, val));
    };

    const updateDiet = (meal: MealKey, category: string, diet: string, count: number) => {
        setOrder((prev) => OrderService.updateDiet(prev, meal, category, diet, count));
    };

    const wrapFullDay = (meal: MealData): DailyOrder => ({
        status: 'draft',
        breakfast: meal,
        lunch: emptyMeal,
        olovrant: emptyMeal,
    });

    const updateFullDayMenuCount = (category: string, menuType: string, val: number) => {
        setFullDayData((prev) =>
            OrderService.updateMenuCount(wrapFullDay(prev), 'breakfast', category, menuType, val).breakfast,
        );
    };

    const updateFullDayDiet = (category: string, diet: string, count: number) => {
        setFullDayData((prev) =>
            OrderService.updateDiet(wrapFullDay(prev), 'breakfast', category, diet, count).breakfast,
        );
    };

    const updatePackSeparately = (
        meal: PackSeparatelyMealKey,
        category: string,
        kind: 'menus' | 'diets',
        key: string,
        count: number,
        target: PackTarget = 'zvlast',
    ) => {
        if (meal === 'fullDay') {
            setFullDayData((prev) =>
                OrderService.updatePackSeparately(wrapFullDay(prev), 'breakfast', category, kind, key, count, target).breakfast,
            );
            return;
        }

        setOrder((prev) => OrderService.updatePackSeparately(prev, meal, category, kind, key, count, target));
    };

    const clearMeal = (meal: MealKey) => {
        setOrder((prev) => ({
            ...prev,
            [meal]: OrderService.createEmptyMealFor(categories),
            status: 'draft',
        }));
        setActiveMeals((prev) => ({ ...prev, [meal]: false }));
    };

    const copyMeal = (source: MealKey, target: MealKey) => {
        if (OrderService.isMealEmpty(order[source])) return false;
        setOrder((prev) => ({
            ...prev,
            [target]: OrderService.fastCopy(prev[source]),
            status: 'draft',
        }));
        setActiveMeals((prev) => ({ ...prev, [target]: true }));
        return true;
    };

    /** Nahrá obed z predošlého dňa do raňajok — obdoba klientskeho „Načítať z včerajška“. */
    const loadBreakfastFromPrevLunch = () => {
        const prevDate = new Date(`${date}T12:00:00`);
        prevDate.setDate(prevDate.getDate() - 1);
        const prevDateStr = OrderService.toLocalDateString(prevDate);

        const prevOrder = knownOrders.find((item) => item.date === prevDateStr);
        if (!prevOrder) return false;

        const prevLunch = buildInitialOrder(categories, prevOrder).lunch;
        if (OrderService.isMealEmpty(prevLunch)) return false;

        setOrder((prev) => ({
            ...prev,
            breakfast: OrderService.fastCopy(prevLunch),
            status: 'draft',
        }));
        setActiveMeals((prev) => ({ ...prev, breakfast: true }));
        return true;
    };

    const clearFullDay = () => {
        setFullDayData(OrderService.createEmptyMealFor(categories));
    };

    const packSeparatelySections = useMemo(() => {
        const sections = fullDayOrder
            ? [
                {
                    meal: 'fullDay' as const,
                    mealLabel: 'Celý deň',
                    items: buildPackSeparatelyItems(categories, fullDayData),
                },
            ]
            : visibleMealsList.map(({ key, label }) => ({
                meal: key,
                mealLabel: label,
                items: buildPackSeparatelyItems(categories, order[key]),
            }));

        return sections.filter((section) => section.items.length > 0);
    }, [categories, fullDayData, fullDayOrder, order, visibleMealsList]);

    const activePackSeparatelyItems = useMemo(
        () =>
            packSeparatelySections
                .map((section) => ({
                    ...section,
                    items: section.items.filter((item) => item.count > 0),
                }))
                .filter((section) => section.items.length > 0),
        [packSeparatelySections],
    );

    const hasSpecialDietOrdered = (): boolean => {
        const checkMeal = (meal: MealData) =>
            Object.values(meal).some((cat) => (cat.diets?.['Špeciálna'] ?? 0) > 0);
        if (fullDayOrder) return checkMeal(fullDayData);
        return visibleMealsList.some(({ key }) => activeMeals[key] && checkMeal(order[key]));
    };

    const resetOrder = () => {
        setOrder(buildInitialOrder(categories, null));
        setFullDayOrder(false);
        setFullDayData(OrderService.createEmptyMealFor(categories));
        setSpecialDietNote('');
        setActiveMeals({ breakfast: false, lunch: false, olovrant: false });
        toast.success('Objednávka bola vynulovaná.');
    };

    const handleSave = async () => {
        let effectiveClosedState = closedState;
        if (effectiveClosedState === 'checking') {
            try {
                const statusRes = await apiFetch(`${API_URL}/admin/closed-days/?date=${date}`);
                if (!statusRes.ok) throw new Error('closed-day status failed');
                const statusPayload = await statusRes.json() as { is_closed: boolean };
                effectiveClosedState = statusPayload.is_closed ? 'closed' : 'open';
                setClosedState(effectiveClosedState);
            } catch {
                effectiveClosedState = 'error';
                setClosedState('error');
            }
        }
        if (effectiveClosedState !== 'open') {
            toast.error(effectiveClosedState === 'closed' ? CLOSED_DAY_MESSAGE : 'Stav dňa sa nepodarilo overiť. Úpravy sú zablokované.');
            return;
        }
        setSaving(true);
        try {
            const snapshot: DailyOrder = OrderService.fastCopy(order);
            const payloadData = {
                breakfast: fullDayOrder
                    ? (visibleMealsList.some((meal) => meal.key === 'breakfast') ? OrderService.fastCopy(fullDayData) : emptyMeal)
                    : (activeMeals.breakfast ? snapshot.breakfast : emptyMeal),
                lunch: fullDayOrder
                    ? (visibleMealsList.some((meal) => meal.key === 'lunch') ? OrderService.fastCopy(fullDayData) : emptyMeal)
                    : (activeMeals.lunch ? snapshot.lunch : emptyMeal),
                olovrant: fullDayOrder
                    ? (visibleMealsList.some((meal) => meal.key === 'olovrant') ? OrderService.fastCopy(fullDayData) : emptyMeal)
                    : (activeMeals.olovrant ? snapshot.olovrant : emptyMeal),
                special_diet_note: specialDietNote.trim() || undefined,
            };

            const query = clientId ? `?user_id=${encodeURIComponent(String(clientId))}` : '';

            if (existingOrder) {
                const res = await apiFetch(`${API_URL}/orders/${existingOrder.id}/?prevadzka=${encodeURIComponent(String(prevadzkaId))}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ data: payloadData, prevadzka: prevadzkaId }),
                });
                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    toast.error(body?.error?.message || 'Nepodarilo sa uložiť objednávku.');
                    return;
                }
                toast.success('Objednávka bola uložená.');
            } else {
                const res = await apiFetch(`${API_URL}/orders/${query}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date, data: payloadData, prevadzka: prevadzkaId }),
                });
                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    const msg =
                        body?.error?.details?.date?.[0] ||
                        body?.error?.message ||
                        'Chyba pri vytváraní objednávky.';
                    toast.error(msg);
                    return;
                }
                toast.success('Objednávka bola vytvorená.');
            }
            onSaved();
        } catch {
            toast.error('Nepodarilo sa uložiť objednávku.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div
            className="zpa-scrim"
            style={{ alignItems: 'flex-start', overflowY: 'auto', padding: 16 }}
            onClick={handleOverlayClick}
        >
            <div
                className="zpa-modal"
                style={{ maxWidth: 780, width: '100%', margin: '16px 0', maxHeight: 'none' }}
                role="dialog"
                aria-modal="true"
                aria-labelledby="admin-order-editor-title"
            >
                <div className="zpa-modal-head">
                    <div>
                        <h3 id="admin-order-editor-title">
                            {existingOrder ? 'Upraviť objednávku' : 'Nová objednávka'}
                        </h3>
                        {existingOrder && (
                            <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: '2px 0 0' }}>{existingOrder.date}</p>
                        )}
                    </div>
                    <button type="button" aria-label="Zavrieť" onClick={onClose} className="zpa-modal-close">
                        <X />
                    </button>
                </div>

                {!existingOrder && (
                    <div style={{ padding: '20px 24px 0' }}>
                        <Field label="Dátum objednávky">
                            <Input id="order-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} style={{ width: 'auto' }} />
                        </Field>
                        {/* Dnes/zajtra/pozajtra sa oplatí zvýrazniť — admin si najčastejšie
                            objednáva na jeden z týchto dní a inak si musí dátum sám prepočítať. */}
                        <p style={{
                            margin: '6px 0 0',
                            fontSize: 13,
                            fontWeight: dateLabel.emphasized ? 700 : 400,
                            color: dateLabel.emphasized ? 'var(--mustard-700)' : 'var(--ink-3)',
                        }}>
                            {dateLabel.text}
                        </p>
                    </div>
                )}

                {closedState === 'checking' && (
                    <div role="status" style={{ padding: '24px', color: 'var(--ink-3)' }}>
                        Overujem stav dňa…
                    </div>
                )}

                {closedState === 'closed' && (
                    <div role="alert" style={{ margin: '20px 24px', padding: 16, borderRadius: 12, background: 'rgba(180, 83, 9, 0.1)', color: 'var(--mustard-700)', fontWeight: 700 }}>
                        {CLOSED_DAY_MESSAGE}
                    </div>
                )}

                {closedState === 'error' && (
                    <div role="alert" style={{ margin: '20px 24px', padding: 16, borderRadius: 12, background: 'rgba(185, 28, 28, 0.08)', color: 'var(--red-700)', fontWeight: 700 }}>
                        Stav dňa sa nepodarilo overiť. Úpravy sú zablokované.
                    </div>
                )}

                {(closedState === 'open' || closedState === 'checking') && <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16, pointerEvents: closedState === 'checking' ? 'none' : undefined, opacity: closedState === 'checking' ? 0.55 : 1 }}>
                    <OrderFormBody
                        categories={categories}
                        visibleMealsList={visibleMealsList}
                        fullDayOrder={fullDayOrder}
                        onToggleFullDay={toggleFullDay}
                        fullDayData={fullDayData}
                        fullDayVisibleMenus={visibleMenus}
                        onFullDayMenuCount={updateFullDayMenuCount}
                        onOpenFullDayDiets={(category) => setActiveDietModal({ meal: 'fullDay', category })}
                        onClearFullDay={clearFullDay}
                        order={order}
                        activeMeals={activeMeals}
                        onToggleMeal={toggleMeal}
                        onMenuCountChange={updateMenuCount}
                        onOpenDiets={(meal, category) => setActiveDietModal({ meal, category })}
                        getVisibleMenusForMeal={visibleMenusForMeal}
                        getAvailableDiets={getAvailableDiets}
                        mealActions={(meal) => {
                            if (meal === 'breakfast') {
                                return (
                                    <>
                                        <button
                                            className="zp-btn zp-btn--secondary zp-btn--sm"
                                            style={{ flex: 1 }}
                                            onClick={() => {
                                                if (loadBreakfastFromPrevLunch()) {
                                                    toast.success('Raňajky načítané z obeda (včera).');
                                                } else {
                                                    toast.info('Nemám dáta z včerajšieho obeda.');
                                                }
                                            }}
                                        >
                                            <Copy style={{ width: 12, height: 12 }} /> Načítať z včerajška
                                        </button>
                                        <button
                                            className="zp-btn zp-btn--danger zp-btn--sm"
                                            onClick={() => clearMeal('breakfast')}
                                        >
                                            <Trash2 style={{ width: 12, height: 12 }} /> Vymazať
                                        </button>
                                    </>
                                );
                            }
                            if (meal === 'lunch') {
                                return (
                                    <>
                                        <button
                                            className="zp-btn zp-btn--secondary zp-btn--sm"
                                            style={{ flex: 1 }}
                                            onClick={() => {
                                                const copied = copyMeal('breakfast', 'lunch');
                                                if (copied) {
                                                    toast.success('Obed načítaný z raňajok.');
                                                } else {
                                                    toast.info('Raňajky sú prázdne, nie je čo kopírovať.');
                                                }
                                            }}
                                        >
                                            <Copy style={{ width: 12, height: 12 }} /> Načítať z raňajok
                                        </button>
                                        <button
                                            className="zp-btn zp-btn--danger zp-btn--sm"
                                            onClick={() => clearMeal('lunch')}
                                        >
                                            <Trash2 style={{ width: 12, height: 12 }} /> Vymazať
                                        </button>
                                    </>
                                );
                            }
                            return (
                                <>
                                    <button
                                        className="zp-btn zp-btn--secondary zp-btn--sm"
                                        style={{ flex: 1 }}
                                        onClick={() => {
                                            const copied = copyMeal('lunch', 'olovrant');
                                            if (copied) {
                                                toast.success('Olovrant skopírovaný z obeda.');
                                            } else {
                                                toast.info('Obed je prázdny, nie je čo kopírovať.');
                                            }
                                        }}
                                    >
                                        <Copy style={{ width: 12, height: 12 }} /> Kopírovať z obeda
                                    </button>
                                    <button
                                        className="zp-btn zp-btn--danger zp-btn--sm"
                                        onClick={() => clearMeal('olovrant')}
                                    >
                                        <Trash2 style={{ width: 12, height: 12 }} /> Vymazať
                                    </button>
                                </>
                            );
                        }}
                        isMealEditable={() => true}
                        mealStatusMessage={() => fullDayOrder ? <>Celodenná objednávka je aktívna</> : null}
                        packSeparatelyEnabled={packSeparatelyEnabled}
                        activePackSeparatelyItems={activePackSeparatelyItems}
                        onOpenPackSeparately={() => setPackSeparatelyOpen(true)}
                        onUpdatePackSeparately={updatePackSeparately}
                        showSpecialDietNote={hasSpecialDietOrdered()}
                        specialDietNote={specialDietNote}
                        onSpecialDietNoteChange={setSpecialDietNote}
                        tourIds={false}
                    />

                    <OrderSummary
                        order={order}
                        activeMeals={activeMeals}
                        date={date}
                        onSubmit={handleSave}
                        onReset={resetOrder}
                        submitLabel="Uložiť objednávku"
                    />
                </div>}

                <div className="zpa-modal-foot">
                    <Button variant="ghost" onClick={onClose}>Zrušiť</Button>
                    {(closedState === 'open' || closedState === 'checking') && (
                        <Button onClick={handleSave} disabled={saving}>
                            {saving ? 'Ukladám…' : 'Uložiť'}
                        </Button>
                    )}
                </div>
            </div>

            {activeDietModal && (
                <DietSelector
                    isOpen={true}
                    onClose={() => setActiveDietModal(null)}
                    categoryLabel={activeDietModal.category}
                    enabledDiets={getAvailableDiets(activeDietModal.category)}
                    diets={
                        activeDietModal.meal === 'fullDay'
                            ? fullDayData[activeDietModal.category]?.diets ?? {}
                            : order[activeDietModal.meal]?.[activeDietModal.category]?.diets ?? {}
                    }
                    onUpdateDiet={(diet, count) =>
                        activeDietModal.meal === 'fullDay'
                            ? updateFullDayDiet(activeDietModal.category, diet, count)
                            : updateDiet(activeDietModal.meal, activeDietModal.category, diet, count)
                    }
                />
            )}

            {packSeparatelyEnabled && (
                <PackSeparatelySelector
                    isOpen={packSeparatelyOpen}
                    onClose={() => setPackSeparatelyOpen(false)}
                    sections={packSeparatelySections}
                    onUpdatePackSeparately={updatePackSeparately}
                />
            )}
        </div>
    );
};

export default AdminOrderEditorModal;
