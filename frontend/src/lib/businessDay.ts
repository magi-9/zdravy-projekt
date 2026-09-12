/**
 * Jediné miesto na frontende, ktoré vie odpovedať na "objednáva sa v tento deň?".
 *
 * Zrkadlí `backend/api/scheduling.py` — tie isté tri vrstvy voľna:
 *  1. víkend,
 *  2. `Holiday` — celosystémové voľno kuchyne (`/api/holidays/`),
 *  3. `PrevadzkaClosure` — voľno jednej prevádzky (#490, `/api/prevadzka-closures/`).
 *
 * Predtým bola víkendová podmienka rozkopírovaná v DaySelector, HomePage,
 * MenuPage, OnboardingContext a AdminDashboard (#489) — každá kópia mierne iná.
 */

/** "YYYY-MM-DD" v lokálnom čase (nie UTC — `toISOString()` posúva deň). */
export function toDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Poludnie, nie polnoc: parsovanie "YYYY-MM-DD" cez `new Date()` inak môže
 * pri niektorých zónach spadnúť o deň nižšie. */
export function fromDateKey(key: string): Date {
  return new Date(`${key}T12:00:00`);
}

export interface DayOffSets {
  /** Dátumy ("YYYY-MM-DD") celosystémového voľna. */
  holidays?: Set<string>;
  /** Dátumy ("YYYY-MM-DD") voľna konkrétnej prevádzky. */
  closures?: Set<string>;
}

export function isWeekend(date: Date): boolean {
  const day = date.getDay(); // 0=Sunday, 6=Saturday
  return day === 0 || day === 6;
}

/** Neobjednáva sa: víkend, celosystémové voľno alebo voľno prevádzky. */
export function isDayOff(date: Date, sets: DayOffSets = {}): boolean {
  if (isWeekend(date)) return true;
  const key = toDateKey(date);
  return (sets.holidays?.has(key) ?? false) || (sets.closures?.has(key) ?? false);
}

/** Prečo je deň voľný — pre hlášky, ktoré majú rozlíšiť sviatok od voľna prevádzky. */
export type DayOffReason = "weekend" | "holiday" | "closure";

export function dayOffReason(
  date: Date,
  sets: DayOffSets = {},
): DayOffReason | null {
  if (isWeekend(date)) return "weekend";
  const key = toDateKey(date);
  if (sets.holidays?.has(key)) return "holiday";
  if (sets.closures?.has(key)) return "closure";
  return null;
}

// Poistka proti nekonečnej slučke, keby prišlo voľno na roky dopredu.
const MAX_DAY_SCAN = 400;

function shift(date: Date, direction: 1 | -1, sets: DayOffSets): Date | null {
  const cursor = new Date(date);
  for (let i = 0; i < MAX_DAY_SCAN; i++) {
    if (!isDayOff(cursor, sets)) return cursor;
    cursor.setDate(cursor.getDate() + direction);
  }
  return null;
}

/** Return `date` unchanged if it's a business day, otherwise the most recent
 * preceding one (Saturday -> Friday, Sunday -> Friday). */
export function previousBusinessDay(date: Date, sets: DayOffSets = {}): Date {
  return shift(date, -1, sets) ?? new Date(date);
}

/** Opak `previousBusinessDay` — najbližší deň na objednanie od `date` dopredu. */
export function nextBusinessDay(date: Date, sets: DayOffSets = {}): Date {
  return shift(date, 1, sets) ?? new Date(date);
}

/** Prvý deň na objednanie STRIKTNE po `date` — posun v DaySelectore. */
export function stepBusinessDay(
  date: Date,
  direction: 1 | -1,
  sets: DayOffSets = {},
): Date | null {
  const cursor = new Date(date);
  for (let i = 0; i < MAX_DAY_SCAN; i++) {
    cursor.setDate(cursor.getDate() + direction);
    if (!isDayOff(cursor, sets)) return new Date(cursor);
  }
  return null;
}

/** Prvých `count` dní na objednanie od `start` vrátane. */
export function businessDays(
  start: Date,
  count: number,
  sets: DayOffSets = {},
): Date[] {
  const days: Date[] = [];
  const cursor = new Date(start);
  for (let i = 0; i < MAX_DAY_SCAN && days.length < count; i++) {
    if (!isDayOff(cursor, sets)) days.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

// ── Reťazcové obaly ──────────────────────────────────────────────────────────
// Admin Prehľad a kuchyňská obrazovka pracujú s dátumom ako "YYYY-MM-DD".
// Sú postavené nad funkciami vyššie, takže rešpektujú aj sviatky a voľno
// prevádzky — nie len víkend (#489).

/** Alias k `toDateKey` pre volajúcich, ktorí pracujú s `Date`. */
export const toDateString = toDateKey;

/** Pracovný deň v zmysle „nie víkend". Na dátumový input, ktorý sviatky nerieši. */
export function isWeekday(date: Date): boolean {
  return !isWeekend(date);
}

export function prevWeekday(key: string, sets: DayOffSets = {}): string {
  const day = stepBusinessDay(fromDateKey(key), -1, sets);
  return day ? toDateKey(day) : key;
}

export function nextWeekday(key: string, sets: DayOffSets = {}): string {
  const day = stepBusinessDay(fromDateKey(key), 1, sets);
  return day ? toDateKey(day) : key;
}

/** Dnešok, alebo najbližší predchádzajúci deň na objednanie. */
export function lastWeekdayToday(sets: DayOffSets = {}): string {
  return toDateKey(previousBusinessDay(new Date(), sets));
}

/** O koľko pracovných dní dopredu (od dnešku/posledného pracovného dňa) smie
 * dashboard tabuľka (admin Prehľad, kuchyňa, admin/prevadzka-overview)
 * navigovať dopredu. Zosúladené s hodinovým EduPage priebežným náhľadom
 * (`_sync_edupage_preview_scrape_schedule`, `EDUPAGE_PREVIEW_SCRAPE_DAYS_
 * AHEAD` v `backend/api/signals.py`), ktorý dopĺňa čísla na presne toľko dní
 * dopredu — bez neho by odomknutý deň v dashboarde často ostal prázdny. */
const DASHBOARD_DAYS_AHEAD = 2;

/** Od ktorej hodiny je zajtrajšok už natoľko "hotový" deň, že sa oplatí ho
 * ukázať ako predvolený pri otvorení tabuľky — po večernom scrapi (den-
 * vopred jedlá bežia okolo 20:xx), nie hneď od polnoci. Odomknutie
 * (`dashboardMaxDate`) a predvolený pohľad (`dashboardDefaultDate`) sú preto
 * zámerne dve rôzne hranice, nie jedna. */
const DASHBOARD_NEXT_DAY_DEFAULT_HOUR = 21;

/**
 * Najneskorší deň, ktorý smie dashboard tabuľka (admin Prehľad, kuchyňa,
 * admin/prevadzka-overview) zobraziť: dnešok (alebo posledný pracovný deň
 * pred víkendom/sviatkom, ak dnešok sám je voľno), plus `DASHBOARD_DAYS_
 * AHEAD` ďalších pracovných dní. Bez hodinovej podmienky — hodinový EduPage
 * priebežný náhľad dopĺňa dáta na toto okno priebežne celý deň, takže
 * netreba čakať na konkrétny čas ako predtým (#535, len pre zajtrajšok).
 */
export function dashboardMaxDate(now: Date = new Date(), sets: DayOffSets = {}): string {
  const start = previousBusinessDay(now, sets);
  const days = businessDays(start, DASHBOARD_DAYS_AHEAD + 1, sets);
  return toDateKey(days[days.length - 1] ?? start);
}

/**
 * Deň, ktorý má dashboard tabuľka predvolene ukázať pri otvorení. Zámerne
 * inde ako `dashboardMaxDate` (#539) — zajtrajšok je síce navigovateľný (viď
 * vyššie), ale ako predvolený pohľad naskočí až od
 * `DASHBOARD_NEXT_DAY_DEFAULT_HOUR` (21:00): dovtedy má admin/kuchyňa pri
 * otvorení tabuľky pred očami dnešok, nie deň, ktorý ešte len prebieha.
 */
export function dashboardDefaultDate(now: Date = new Date(), sets: DayOffSets = {}): string {
  if (now.getHours() < DASHBOARD_NEXT_DAY_DEFAULT_HOUR) {
    return toDateKey(previousBusinessDay(now, sets));
  }
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  // V piatok po večernom scrapi už kuchyňa pripravuje pondelok. Predchádzajúce
  // pravidlo tu kvôli sobote vrátilo späť piatok, takže Gramáž/Kontrola/
  // Zlúčenie diét ukazovali už vybavený deň namiesto najbližšieho pracovného.
  // Sviatok alebo voľno v iný deň zostáva zámerne na dnešku — naň sa nesmie
  // potichu preskočiť bez potvrdeného náhľadu dát.
  if (isWeekend(tomorrow)) return toDateKey(nextBusinessDay(tomorrow, sets));
  if (isDayOff(tomorrow, sets)) return toDateKey(previousBusinessDay(now, sets));
  return toDateKey(tomorrow);
}

export function formatDay(key: string): string {
  return fromDateKey(key).toLocaleDateString('sk-SK', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}
