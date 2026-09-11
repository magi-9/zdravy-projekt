import { ALL_MENU_LETTERS, CATEGORIES, DIETS, GROUP_CONFIG, SPECIAL_DIET_NAME } from '../config/constants';

export interface DietCounts {
    [key: string]: number;
}

export interface MenuCounts {
    [key: string]: number;
}

export interface CategoryData {
    menuCounts: MenuCounts;
    diets: DietCounts;
    packSeparately?: {
        menus: Record<string, number>;
        diets: Record<string, number>;
    };
    /** Rovnaká mechanika ako `packSeparately`, len s poznámkou „do GN“ pre kuchyňu.
     * Jedna porcia nemôže byť naraz v oboch — pozri `PACK_TARGET_FIELD` nižšie. */
    packSeparatelyGn?: {
        menus: Record<string, number>;
        diets: Record<string, number>;
    };
}

/** Dva vzájomne sa vylučujúce spôsoby balenia zvlášť pre tú istú porciu. */
export type PackTarget = 'zvlast' | 'gn';

const PACK_TARGET_FIELD: Record<PackTarget, 'packSeparately' | 'packSeparatelyGn'> = {
    zvlast: 'packSeparately',
    gn: 'packSeparatelyGn',
};

const otherPackTarget = (target: PackTarget): PackTarget => (target === 'gn' ? 'zvlast' : 'gn');

export interface MealData {
    [category: string]: CategoryData;
}

export interface DailyOrder {
    status?: 'draft' | 'submitted';
    breakfast: MealData;
    lunch: MealData;
    olovrant: MealData;
}

class OrderService {
    static createEmptyPackSeparately(): { menus: Record<string, number>; diets: Record<string, number> } {
        return {
            menus: {},
            diets: {}
        };
    }

    static toLocalDateString(date: Date): string {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }

    static getServerNow(): Date {
        const offsetRaw = sessionStorage.getItem('server_time_offset_ms');
        const offsetMs = offsetRaw ? Number(offsetRaw) : 0;
        return new Date(Date.now() + (Number.isFinite(offsetMs) ? offsetMs : 0));
    }

    /**
     * Slovenský popisok dátumu vzhľadom na `today` (YYYY-MM-DD) — „Dnes streda 2.9.“,
     * „Zajtra štvrtok 3.9.“, „Pozajtra piatok 4.9.“, ďalej už len „Pondelok 8.9.“.
     * `emphasized` hovorí volajúcemu, či dátum zvýrazniť (dnes/zajtra/pozajtra).
     */
    static formatRelativeDayLabel(dateStr: string, today: Date = OrderService.getServerNow()): { text: string; emphasized: boolean } {
        const date = new Date(`${dateStr}T00:00:00`);
        const todayMidnight = new Date(`${OrderService.toLocalDateString(today)}T00:00:00`);
        const diffDays = Math.round((date.getTime() - todayMidnight.getTime()) / 86400000);

        const weekday = date.toLocaleDateString('sk-SK', { weekday: 'long' });
        const weekdayCapitalized = weekday.charAt(0).toUpperCase() + weekday.slice(1);
        const dayMonth = `${date.getDate()}.${date.getMonth() + 1}.`;

        if (diffDays === 0) return { text: `Dnes ${weekday} ${dayMonth}`, emphasized: true };
        if (diffDays === 1) return { text: `Zajtra ${weekday} ${dayMonth}`, emphasized: true };
        if (diffDays === 2) return { text: `Pozajtra ${weekday} ${dayMonth}`, emphasized: true };
        return { text: `${weekdayCapitalized} ${dayMonth}`, emphasized: false };
    }

    static createEmptyCategory(): CategoryData {
        // Kategória (vek/porcia) menu neobmedzuje — schéma drží VŠETKY možné
        // menu písmená, skutočný výber robí až prevádzka (visible_menus /
        // menu_day_restrictions) filtrovaním v CategoryRow.
        const menuCounts = ALL_MENU_LETTERS.reduce((acc, menu) => ({ ...acc, [menu]: 0 }), {} as MenuCounts);

        return {
            menuCounts,
            diets: DIETS.reduce((acc, diet) => ({ ...acc, [diet]: 0 }), {} as DietCounts),
            packSeparately: this.createEmptyPackSeparately(),
            packSeparatelyGn: this.createEmptyPackSeparately()
        };
    }

    static createEmptyMeal(): MealData {
        return CATEGORIES.reduce((acc, cat) => ({ ...acc, [cat]: this.createEmptyCategory() }), {} as MealData);
    }

    static createEmptyMealFor(categories: string[]): MealData {
        return categories.reduce((acc, cat) => ({ ...acc, [cat]: this.createEmptyCategory() }), {} as MealData);
    }

    static createEmptyOrder(): DailyOrder {
        return {
            status: 'draft',
            breakfast: this.createEmptyMeal(),
            lunch: this.createEmptyMeal(),
            olovrant: this.createEmptyMeal()
        };
    }

    static getAvailableDiets(categoryName: string, enabledDiets: string[]): string[] {
        const availableMenus = GROUP_CONFIG[categoryName] || [];
        const hasMenuV = availableMenus.includes('V');

        if (hasMenuV) {
            return enabledDiets.filter(d => d !== 'Vegetariánske');
        }
        return enabledDiets;
    }

    /**
     * Ako getAvailableDiets, ale vždy doplní „Špeciálna" diétu — tá nie je
     * reálny Diet záznam v DB, takže sa nikdy neobjaví v enabledDiets/
     * visible_diets, a musí sa dopĺňať na strane klienta na každom mieste,
     * kde sa diéty ponúkajú na výber (klientský formulár aj admin editor).
     */
    static getAvailableDietsWithSpecial(categoryName: string, enabledDiets: string[]): string[] {
        const diets = OrderService.getAvailableDiets(categoryName, enabledDiets);
        if (!diets.includes(SPECIAL_DIET_NAME)) {
            return [...diets, SPECIAL_DIET_NAME];
        }
        return diets;
    }

    /** Súčet všetkých diétnych porcií v kategórii. */
    static getDietTotal(categoryData: Pick<CategoryData, 'diets'>): number {
        return (Object.values(categoryData.diets || {}) as number[])
            .reduce((a, b) => a + b, 0);
    }

    /**
     * Počet bežných (nediétnych) porcií Menu A — to, čo klient vidí a edituje.
     *
     * `menuCounts.A` drží CELKOVÝ počet porcií Menu A vrátane diétnych (diéta je
     * naďalej podmnožina Menu A, tak ako to čaká backend, gramáž aj exporty).
     * UI ale zadáva bežné porcie zvlášť a diéty sa k nim pripočítavajú, takže
     * na vstupe/výstupe formulára prevádzame medzi týmito dvoma pohľadmi.
     */
    static getPlainMenuACount(categoryData: CategoryData): number {
        return Math.max(0, (categoryData.menuCounts?.['A'] || 0) - this.getDietTotal(categoryData));
    }

    static updateMenuCount(currentOrder: DailyOrder, mealKey: 'breakfast' | 'lunch' | 'olovrant', category: string, menuType: string, count: number): DailyOrder {
        const newCount = Math.max(0, count);
        const categoryData = currentOrder[mealKey][category];

        // Pri Menu A je `count` počet BEŽNÝCH porcií — diéty sa k nemu pripočítajú.
        // Znižovanie Menu A preto (na rozdiel od minulosti) diéty nekráti.
        const storedCount = menuType === 'A'
            ? newCount + this.getDietTotal(categoryData)
            : newCount;

        const newMenuCounts = {
            ...categoryData.menuCounts,
            [menuType]: storedCount
        };

        const nextCategoryData = this.withClampedPackSeparately({
            ...categoryData,
            menuCounts: newMenuCounts
        });

        return {
            ...currentOrder,
            [mealKey]: {
                ...currentOrder[mealKey],
                [category]: nextCategoryData
            }
        };
    }

    static updateDiet(currentOrder: DailyOrder, mealKey: 'breakfast' | 'lunch' | 'olovrant', category: string, diet: string, count: number): DailyOrder {
        const categoryData = currentOrder[mealKey][category];

        // Diéty sa pripočítavajú bez limitu: bežné (nediétne) porcie ostávajú
        // konštantné a celkové `menuCounts.A` rastie/klesá spolu s počtom diét.
        const plainMenuACount = this.getPlainMenuACount(categoryData);

        const newCount = Math.max(0, count);
        const newDiets = { ...categoryData.diets, [diet]: newCount };

        const nextCategoryData = this.withClampedPackSeparately({
            ...categoryData,
            menuCounts: {
                ...categoryData.menuCounts,
                A: plainMenuACount + this.getDietTotal({ diets: newDiets })
            },
            diets: newDiets
        });

        return {
            ...currentOrder,
            [mealKey]: {
                ...currentOrder[mealKey],
                [category]: nextCategoryData
            }
        };
    }

    static updatePackSeparately(
        currentOrder: DailyOrder,
        mealKey: 'breakfast' | 'lunch' | 'olovrant',
        category: string,
        kind: 'menus' | 'diets',
        key: string,
        count: number,
        target: PackTarget = 'zvlast'
    ): DailyOrder {
        const categoryData = currentOrder[mealKey][category];
        const rawMax = kind === 'menus'
            ? categoryData.menuCounts?.[key] || 0
            : categoryData.diets?.[key] || 0;
        // Jedna porcia nemôže byť naraz "zvlášť" aj "zvlášť do GN" - kapacita pre
        // tento cieľ je objednaný počet mínus to, čo už drží ten druhý.
        const otherField = PACK_TARGET_FIELD[otherPackTarget(target)];
        const otherCount = categoryData[otherField]?.[kind]?.[key] || 0;
        const maxAllowed = Math.max(0, rawMax - otherCount);
        const nextCount = Math.min(Math.max(0, count), maxAllowed);
        const field = PACK_TARGET_FIELD[target];
        const currentPackSeparately = categoryData[field] || this.createEmptyPackSeparately();
        const nextKindCounts = { ...(currentPackSeparately[kind] || {}) };

        if (nextCount <= 0) {
            delete nextKindCounts[key];
        } else {
            nextKindCounts[key] = nextCount;
        }

        return {
            ...currentOrder,
            [mealKey]: {
                ...currentOrder[mealKey],
                [category]: {
                    ...categoryData,
                    [field]: this.cleanupPackSeparately({
                        ...currentPackSeparately,
                        [kind]: nextKindCounts
                    })
                }
            }
        };
    }

    static getPackSeparatelyAdjustments(before: CategoryData, after: CategoryData) {
        const adjustments: { kind: 'menus' | 'diets'; key: string; count: number; target: PackTarget }[] = [];

        (['zvlast', 'gn'] as const).forEach((target) => {
            const field = PACK_TARGET_FIELD[target];
            const previous = before[field] || this.createEmptyPackSeparately();
            const next = after[field] || this.createEmptyPackSeparately();

            (['menus', 'diets'] as const).forEach((kind) => {
                const keys = new Set([
                    ...Object.keys(previous[kind] || {}),
                    ...Object.keys(next[kind] || {})
                ]);

                keys.forEach((key) => {
                    const prevCount = previous[kind]?.[key] || 0;
                    const nextCount = next[kind]?.[key] || 0;
                    if (nextCount < prevCount) {
                        adjustments.push({ kind, key, count: nextCount, target });
                    }
                });
            });
        });

        return adjustments;
    }

    /** Zoradí jedno pole {menus,diets} počtov na maximum `rawMax(kind, key)`. */
    private static clampPackFields(
        packSeparately: { menus: Record<string, number>; diets: Record<string, number> },
        rawMax: (kind: 'menus' | 'diets', key: string) => number
    ) {
        const clampKind = (kind: 'menus' | 'diets') =>
            Object.entries(packSeparately[kind] || {}).reduce((acc, [key, value]) => {
                const nextValue = Math.min(Math.max(0, value), Math.max(0, rawMax(kind, key)));
                if (nextValue > 0) acc[key] = nextValue;
                return acc;
            }, {} as Record<string, number>);

        return { menus: clampKind('menus'), diets: clampKind('diets') };
    }

    private static withClampedPackSeparately(categoryData: CategoryData): CategoryData {
        const rawMax = (kind: 'menus' | 'diets', key: string) =>
            kind === 'menus' ? categoryData.menuCounts?.[key] || 0 : categoryData.diets?.[key] || 0;

        // "Zvlášť" sa zoradí ako prvé (dostane prednosť pri konflikte), "do GN"
        // sa potom zmestí len do toho, čo "zvlášť" nezobralo - jedna porcia
        // nesmie byť naraz v oboch.
        const zvlast = this.clampPackFields(
            categoryData.packSeparately || this.createEmptyPackSeparately(),
            rawMax
        );
        const gn = this.clampPackFields(
            categoryData.packSeparatelyGn || this.createEmptyPackSeparately(),
            (kind, key) => rawMax(kind, key) - (zvlast[kind]?.[key] || 0)
        );

        return {
            ...categoryData,
            packSeparately: this.cleanupPackSeparately(zvlast),
            packSeparatelyGn: this.cleanupPackSeparately(gn)
        };
    }

    private static cleanupPackSeparately(packSeparately: { menus: Record<string, number>; diets: Record<string, number> }) {
        if (Object.keys(packSeparately.menus).length === 0 && Object.keys(packSeparately.diets).length === 0) {
            return undefined;
        }
        return packSeparately;
    }

    static calculatePrevDayLunches(prevOrder: DailyOrder | null): number {
        if (!prevOrder || !prevOrder.lunch) return 0;

        return Object.values(prevOrder.lunch || {}).reduce((acc: number, cat: CategoryData) => {
            if (cat.menuCounts) {
                return acc + Object.values(cat.menuCounts).reduce((sum: number, val: number) => sum + val, 0);
            }
            return acc;
        }, 0);
    }

    /**
     * Kľúče, ktorých obsah je mapa počtov s OTVORENOU množinou názvov.
     *
     * Diéty si definuje admin (`Diet` model → `prevadzka.visible_diets`), takže
     * ich mená nevie konštanta `DIETS` poznať — tá je len default pre prázdnu
     * objednávku. Keby ich `enforceStructure` filtrovala schémou, vlastná diéta
     * by sa pri načítaní ticho zahodila, prepísala do `currentOrder` aj
     * localStorage, a najbližšie odoslanie by ju vynulovalo aj v DB.
     *
     * `menuCounts` zámerne NIE je v zozname: schéma drží kanonickú množinu
     * `ALL_MENU_LETTERS`, takže filtrovanie neznámych kľúčov (napr. cudzí
     * scrape formát) tu ostáva žiaduce — skutočné obmedzenie „čo sa ponúka“
     * ale robí až prevádzka (visible_menus), nie táto schéma.
     */
    private static readonly OPEN_COUNT_MAP_KEYS = new Set(['diets']);

    /** Zlúči mapu počtov: defaulty zo schémy + všetky platné počty z dát. */
    private static enforceCountMap(
        data: unknown,
        schema: Record<string, unknown>
    ): Record<string, number> {
        const result = { ...schema } as Record<string, number>;
        if (!data || typeof data !== 'object' || Array.isArray(data)) return result;

        Object.entries(data as Record<string, unknown>).forEach(([key, value]) => {
            if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) return;
            result[key] = value;
        });

        return result;
    }

    static enforceStructure<T>(data: unknown, schema: T): T {
        if (!data) return schema;
        if (typeof data !== 'object') return schema;

        if (Array.isArray(schema)) {
            return (Array.isArray(data) ? data : schema) as T;
        }

        if (!schema || typeof schema !== 'object') {
            return data as T;
        }

        const dataRecord = data as Record<string, unknown>;
        const schemaRecord = schema as Record<string, unknown>;
        if (Object.keys(schemaRecord).length === 0) {
            return dataRecord as T;
        }
        const result: Record<string, unknown> = { ...schemaRecord };

        Object.keys(schemaRecord).forEach(key => {
            if (Object.prototype.hasOwnProperty.call(dataRecord, key)) {
                const schemaValue = schemaRecord[key];
                if (this.OPEN_COUNT_MAP_KEYS.has(key)) {
                    result[key] = this.enforceCountMap(
                        dataRecord[key],
                        (schemaValue ?? {}) as Record<string, unknown>
                    );
                } else if (typeof schemaValue === 'object' && schemaValue !== null && !Array.isArray(schemaValue)) {
                    result[key] = this.enforceStructure(dataRecord[key], schemaValue);
                } else {
                    result[key] = dataRecord[key];
                }
            }
        });

        return result as T;
    }

    // Deadline logic
    // `daysBefore` generalizes the old boolean "is day before" flag (1) to an
    // arbitrary number of calendar days before the meal date (used by the
    // menu B/C deadline, which falls e.g. 2 days before at 7:30).
    private static checkDeadlineDaysBefore(dateStr: string, deadlineStr: string, daysBefore: number): boolean {
        const now = this.getServerNow();
        const todayStr = this.toLocalDateString(now);

        if (daysBefore > 0) {
            const mealDate = new Date(dateStr + 'T00:00:00');
            const deadlineDate = new Date(mealDate);
            deadlineDate.setDate(deadlineDate.getDate() - daysBefore);
            const deadlineDateStr = this.toLocalDateString(deadlineDate);

            if (deadlineDateStr > todayStr) return true;   // deadline day is in the future
            if (deadlineDateStr < todayStr) return false;  // deadline day has passed

            // Deadline day is today – check the time
            const [h, m] = deadlineStr.split(':').map(Number);
            const currentMinutes = now.getHours() * 60 + now.getMinutes();
            return currentMinutes < h * 60 + m;
        }

        // Same-day deadline behaviour
        if (dateStr > todayStr) return true;
        if (dateStr < todayStr) return false;

        const [h, m] = deadlineStr.split(':').map(Number);
        const deadlineMinutes = h * 60 + m;
        const currentTime = now.getHours() * 60 + now.getMinutes();

        return currentTime < deadlineMinutes;
    }

    static checkDeadline(dateStr: string, mealKey: string, deadlines?: { breakfast: string, breakfast_day_before?: boolean, lunch: string, lunch_day_before?: boolean, olovrant: string, olovrant_day_before?: boolean }): boolean {
        if (!deadlines) {
            const now = this.getServerNow();
            const todayStr = this.toLocalDateString(now);
            if (dateStr > todayStr) return true;
            return false;
        }

        const defaultTime = "10:00";
        let deadlineStr = defaultTime;
        let isDayBefore = false;
        if (mealKey === 'breakfast') { deadlineStr = deadlines.breakfast || defaultTime; isDayBefore = !!deadlines.breakfast_day_before; }
        if (mealKey === 'lunch') { deadlineStr = deadlines.lunch || defaultTime; isDayBefore = !!deadlines.lunch_day_before; }
        if (mealKey === 'olovrant') { deadlineStr = deadlines.olovrant || defaultTime; isDayBefore = !!deadlines.olovrant_day_before; }

        return this.checkDeadlineDaysBefore(dateStr, deadlineStr, isDayBefore ? 1 : 0);
    }

    // Menu B/C majú vlastný, prísnejší termín (napr. 7:30 dva dni vopred),
    // rovnaký pre všetky jedlá — pozri backend `_validate_deadlines`.
    static checkMenuBcDeadline(dateStr: string, deadlines?: { menu_bc?: string, menu_bc_days_before?: number }): boolean {
        if (!deadlines || !deadlines.menu_bc) return true;
        return this.checkDeadlineDaysBefore(dateStr, deadlines.menu_bc, deadlines.menu_bc_days_before ?? 2);
    }

    // Zdieľané s backendom (`_RESTRICTED_MENUS` v api/serializers.py) — tieto
    // menu majú prísnejší, samostatný termín na NOVÉ/vyššie objednávky.
    static readonly RESTRICTED_MENUS = ['B', 'C', 'D'];

    /** {"label|category|menuType": count} pre jedno MealData — zdieľané medzi
     * `extractRestrictedMenuCounts` (breakfast/lunch/olovrant) a celodenný strop
     * (`fullDay` label), ktorý má vlastný, mimo `DailyOrder` uložený blob. */
    static extractRestrictedMenuCountsForMeal(
        mealData: MealData | undefined,
        label: string
    ): Record<string, number> {
        const result: Record<string, number> = {};
        Object.entries(mealData || {}).forEach(([category, categoryData]) => {
            this.RESTRICTED_MENUS.forEach((menuType) => {
                const count = categoryData?.menuCounts?.[menuType];
                if (count) {
                    result[`${label}|${category}|${menuType}`] = count;
                }
            });
        });
        return result;
    }

    /** {"meal|category|menuType": count} snímka reštrikovaných menu z objednávky —
     * slúži ako "zamknutý" strop, nad ktorý sa po prísnom termíne už nedá ísť
     * (user 2.9.2026: nahlásiť/zvýšiť len do termínu, odhlásiť/znížiť aj po ňom). */
    static extractRestrictedMenuCounts(order: DailyOrder): Record<string, number> {
        const result: Record<string, number> = {};
        (['breakfast', 'lunch', 'olovrant'] as const).forEach((mealKey) => {
            Object.assign(result, this.extractRestrictedMenuCountsForMeal(order[mealKey], mealKey));
        });
        return result;
    }

    /** Zastropuje Menu B/C/D v `mealData` na `ceilings[label|category|menuType]`
     * (chýbajúci kľúč = strop 0) — rovnaké pravidlo ako `updateMenuCount`, len
     * aplikované na celé skopírované jedlo naraz. Kopírovacie akcie ("Načítať z
     * včerajška", "Kopírovať z obeda"...) menili `currentOrder` priamo mimo
     * `updateMenuCount`, takže cudzie B/C/D z iného dňa/chodu (spred termínu)
     * mohli obísť strop a appka to nechala prejsť až do zamietnutého submitu
     * (nahlásené 3.9.2026, Little Big — ich celé menu je len A/B/C). Volať len
     * keď je termín Menu B/C už zavretý — pred termínom netreba nič orezávať. */
    static clampRestrictedMenusForMeal(
        mealData: MealData,
        ceilings: Record<string, number>,
        label: string
    ): MealData {
        const clamped: MealData = {};
        Object.entries(mealData).forEach(([category, categoryData]) => {
            const menuCounts = { ...categoryData.menuCounts };
            this.RESTRICTED_MENUS.forEach((menuType) => {
                if (!(menuType in menuCounts)) return;
                const ceiling = ceilings[`${label}|${category}|${menuType}`] ?? 0;
                if (menuCounts[menuType] > ceiling) menuCounts[menuType] = ceiling;
            });
            clamped[category] = { ...categoryData, menuCounts };
        });
        return clamped;
    }

    static fastCopy<T>(source: T): T {
        return JSON.parse(JSON.stringify(source));
    }

    static isMealEmpty(meal?: MealData | null): boolean {
        if (!meal) return true;
        for (const catKey in meal) {
            const categoryData = meal[catKey];
            if (!categoryData || !categoryData.menuCounts) continue;
            const total = Object.values(categoryData.menuCounts).reduce((acc: number, val: number) => acc + val, 0);
            if (total > 0) return false;
        }
        return true;
    }

    static findLastNonZeroDay(history: (DailyOrder & { date: string })[], currentDateStr: string): DailyOrder | null {
        // 1. Filter out future dates (and current date)
        // 2. Sort descending
        const validHistory = history
            .filter(o => o.date < currentDateStr)
            .sort((a, b) => b.date.localeCompare(a.date));

        for (const order of validHistory) {
            // Check if any meal has content
            const hasContent = !this.isMealEmpty(order.breakfast) ||
                !this.isMealEmpty(order.lunch) ||
                !this.isMealEmpty(order.olovrant);

            if (hasContent) {
                return order;
            }
        }
        return null;
    }

    static mergeOrders(current: DailyOrder, source: DailyOrder, touchedMeals: Set<string>): DailyOrder {
        const result = this.fastCopy(current); // Start with current state

        (['breakfast', 'lunch', 'olovrant'] as const).forEach(mealKey => {
            // If user hasn't touched this meal, we can overwrite it
            if (!touchedMeals.has(mealKey)) {
                // Only copy if source has data, OR if we want to aggressively copy "emptiness"
                // The requirement says: "If intervention ... edit only lunch ... remaining meals are copied"
                // This implies overwriting with source is the default behavior for untouched fields.

                // However, we must be careful. If source is empty, do we overwrite current?
                // Yes, if we want to replicate the "previous day" exactly.
                // But usually current starts empty anyway.

                result[mealKey] = this.fastCopy(source[mealKey]);
            }
        });

        return result;
    }
}

export default OrderService;
