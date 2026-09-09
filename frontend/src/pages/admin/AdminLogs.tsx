import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import {
    AlertTriangle,
    Bug,
    ChevronDown,
    ChevronRight,
    Info,
    RefreshCw,
    XCircle,
} from 'lucide-react';

import { useAuth } from '../../context/auth';
import { logger } from '../../lib/logger';
import { SECTION, canRead } from '../../lib/sections';
import { PageHead, Button, Card, Field, Input, Select, SearchBox } from './ui';
import type { BadgeTone } from './eventLogDisplay';
import {
    ORDER_EVENT_TYPES,
    actorDisplay,
    eventTone,
    orderActionLabel,
    summarizeOrderMeals,
    targetDisplay,
} from './eventLogDisplay';

const API_URL = import.meta.env.VITE_API_URL || '/api';
const LEVELS = ['INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;
// Objednávkové zmeny (vytvorenie/úprava/zmazanie) majú vlastnú kartu
// "Objednávky" s vlastným filtrom podľa dňa a prevádzky — v "Udalosti (audit)"
// by len duplikovali riadky bez toho detailu, preto tu nie sú ani vo filtri,
// ani vo výsledkoch (viď `fetchEvents` nižšie).
const EVENT_TYPES = [
    ['auto_order_run', 'Spustenie auto-objednávok'],
    ['cron_run', 'Cron úloha dobehla'],
    ['cron_skipped', 'Cron úloha preskočená (víkend/voľný deň)'],
    ['cron_failed', 'Cron úloha zlyhala'],
    ['push_broadcast', 'Odoslanie push notifikácie'],
    ['settings_change', 'Zmena nastavení'],
    ['deploy_version', 'Nasadená nová verzia'],
] as const;

// Priateľský slovenský názov pre "Nadchádzajúce" — `entry.task` je stabilná
// dotted-path identita (`api.tasks.scrape_edupage_orders_task`), zatiaľ čo
// `entry.name` je interný cron slug (napr. `edupage-scrape-breakfast-lunch`)
// zobrazený len ako doplnok, nie ako hlavný text.
const TASK_LABELS_SK: Record<string, string> = {
    'api.tasks.scrape_edupage_orders_task': 'EduPage scrape',
    'api.tasks.send_push_deadline_reminder_task': 'Push pripomienka',
    'api.tasks.send_weekly_order_reminder_task': 'Týždenná pripomienka',
    'api.tasks.apply_auto_orders_task': 'Auto-objednávky',
    'api.tasks.send_daily_report_task': 'Denný report',
    'api.tasks.purge_old_event_logs_task': 'Čistenie starých záznamov',
    'celery.backend_cleanup': 'Interná Celery úloha',
    // Syntetický riadok bez vlastného cronu — appka uzávierku vynucuje
    // priebežne, nie na spustenie úlohy (viď `_deadline_lock_entries`).
    'order-lock': 'Uzávierka objednávok',
};

function taskLabel(entry: UpcomingEventEntry): string {
    return TASK_LABELS_SK[entry.task] ?? entry.name;
}

// Kategórie pre "Nadchádzajúce" — namiesto jednej tabuľky zoradenej podľa
// najbližšieho behu (poradie kariet sa tak menilo priebežne s časom) sa karty
// zoskupia podľa toho, čo robia, a vedľa seba v mriežke (#573 follow-up:
// "nie len ako zoznam, netreba to zoradiť").
const UPCOMING_CATEGORIES: { label: string; match: (entry: UpcomingEventEntry) => boolean }[] = [
    { label: 'Uzávierky objednávok', match: (e) => e.task === 'order-lock' },
    { label: 'EduPage scrape', match: (e) => e.task === 'api.tasks.scrape_edupage_orders_task' },
    {
        label: 'Push pripomienky',
        match: (e) => e.task === 'api.tasks.send_push_deadline_reminder_task'
            || e.task === 'api.tasks.send_weekly_order_reminder_task',
    },
    { label: 'Auto-objednávky', match: (e) => e.task === 'api.tasks.apply_auto_orders_task' },
    { label: 'Denné reporty', match: (e) => e.task === 'api.tasks.send_daily_report_task' },
    {
        label: 'Údržba systému',
        match: (e) => e.task === 'api.tasks.purge_old_event_logs_task' || e.task === 'celery.backend_cleanup',
    },
];

function groupUpcomingByCategory(entries: UpcomingEventEntry[]) {
    const groups = UPCOMING_CATEGORIES.map((category) => ({ ...category, entries: [] as UpcomingEventEntry[] }));
    const rest: UpcomingEventEntry[] = [];
    for (const entry of entries) {
        const group = groups.find((g) => g.match(entry));
        if (group) group.entries.push(entry);
        else rest.push(entry);
    }
    if (rest.length > 0) groups.push({ label: 'Ostatné', match: () => false, entries: rest });
    return groups.filter((g) => g.entries.length > 0);
}

type ActiveTab = 'events' | 'orders' | 'upcoming' | 'system';

interface AdminLogEntry {
    id: number;
    timestamp: string;
    level: string;
    logger: string;
    line: number;
    process: number;
    message: string;
    traceback: string | null;
}

interface AdminLogsResponse {
    results: AdminLogEntry[];
    available_loggers: string[];
}

interface EventLogEntry {
    id: number;
    event_type: string;
    event_type_label: string;
    actor: number | null;
    actor_email?: string;
    actor_name?: string;
    actor_label: string;
    target_user: number | null;
    target_user_email?: string;
    target_user_name?: string;
    prevadzka: number | null;
    prevadzka_nazov?: string | null;
    summary: string;
    payload: Record<string, unknown>;
    created_at: string;
}

interface EventLogsResponse {
    count: number;
    next: string | null;
    previous: string | null;
    results: EventLogEntry[];
}

interface PushPreview {
    title: string;
    body: string;
}

interface UpcomingEventEntry {
    name: string;
    task: string;
    description: string;
    next_run: string | null;
    days: string | null;
    push_preview?: PushPreview | null;
}

interface UpcomingEventsResponse {
    results: UpcomingEventEntry[];
}

interface FieldChange {
    from?: unknown;
    to?: unknown;
}

function formatDiffValue(value: unknown) {
    if (
        value == null
        || value === ''
        || (Array.isArray(value) && value.length === 0)
        || (typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0)
    ) return '(prázdne)';
    if (typeof value === 'string') return value;
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

export function EventPayloadDetails({ payload }: { payload: Record<string, unknown> }) {
    const changes = payload.changes;
    if (changes && typeof changes === 'object' && !Array.isArray(changes)) {
        const lines = Object.entries(changes as Record<string, FieldChange>).map(
            ([field, change]) => (
                `${field}: ${formatDiffValue(change?.from)} -> ${formatDiffValue(change?.to)}`
            ),
        );
        return <pre className="tb">{lines.join('\n')}</pre>;
    }
    return <pre className="tb">{JSON.stringify(payload, null, 2)}</pre>;
}

/** Pevné SK časové pásmo — nespoliehať sa na timezone prehliadača/OS
 * (ten býva na serveroch/VM často UTC, čo posúva zobrazený čas o hodiny). */
const SK_TIME_ZONE = 'Europe/Bratislava';

function formatTime(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat('sk-SK', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit',
        timeZone: SK_TIME_ZONE,
    }).format(date);
}

/** Dátum a čas na dva riadky: `14.08.` nad `07:30`.
 *
 * Jednoriadkový tvar so sekundami zaberal v tabuľke najširší stĺpec, hoci
 * sekundy pri auditnej udalosti nikto nečíta. Rok je z riadku tiež preč —
 * v zozname zoradenom od najnovšieho ho nesie kontext, nie každý riadok. */
export function EventTime({ value }: { value: string }) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return <span className="zpa-time">{value}</span>;
    const day = new Intl.DateTimeFormat('sk-SK', { day: '2-digit', month: '2-digit', timeZone: SK_TIME_ZONE }).format(date);
    const time = new Intl.DateTimeFormat('sk-SK', { hour: '2-digit', minute: '2-digit', timeZone: SK_TIME_ZONE }).format(date);
    return (
        <span className="zpa-time" title={formatTime(value)}>
            <span className="zpa-time__day">{day}</span>
            <span className="zpa-time__hm">{time}</span>
        </span>
    );
}

/** Dátum objednávky (`payload.date`), na ktorú sa úprava vzťahuje — nie čas
 * zápisu do logu, ktorý je v stĺpci "Čas". Je to obyčajný dátum bez času,
 * preto sa formátuje bez prevodu časového pásma (ten by ho pri polnoci vedel
 * posunúť o deň). */
function orderDayLabel(payload: Record<string, unknown>): string {
    const raw = payload.date;
    if (typeof raw !== 'string') return '—';
    const [year, month, day] = raw.split('-');
    if (!year || !month || !day) return raw;
    return `${day}.${month}.${year}`;
}

function levelTone(level: string): BadgeTone {
    if (level === 'CRITICAL' || level === 'ERROR') return 'coral';
    if (level === 'WARNING') return 'honey';
    return 'teal';
}

function levelIcon(level: string) {
    if (level === 'CRITICAL' || level === 'ERROR') return <XCircle />;
    if (level === 'WARNING') return <AlertTriangle />;
    return <Info />;
}

function LevelBadge({ level, muted }: { level: string; muted?: boolean }) {
    return (
        <span className={`zpa-badge zpa-badge--${muted ? 'gray' : levelTone(level)}`}>
            {levelIcon(level)}
            {level}
        </span>
    );
}

export default function AdminLogs() {
    const { apiFetch, user } = useAuth();
    // Systémové logy sú prevádzková diagnostika — vidí ich len superadmin.
    // Audit („Udalosti") je pre admina, preto je obrazovka pod sekciou `udalosti`.
    const canSeeSystem = canRead(user?.sections, SECTION.logy);
    const canSeeUpcoming = canRead(user?.sections, SECTION.nadchadzajuce);
    const [activeTab, setActiveTab] = useState<ActiveTab>('events');
    useEffect(() => {
        if (!canSeeSystem && activeTab === 'system') setActiveTab('events');
        if (!canSeeUpcoming && activeTab === 'upcoming') setActiveTab('events');
    }, [canSeeSystem, canSeeUpcoming, activeTab]);

    const [events, setEvents] = useState<EventLogEntry[]>([]);
    const [eventCount, setEventCount] = useState(0);
    const [eventType, setEventType] = useState('');
    const [actor, setActor] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [eventPage, setEventPage] = useState(1);
    const [eventHasNext, setEventHasNext] = useState(false);
    const [eventLoading, setEventLoading] = useState(true);
    const [eventError, setEventError] = useState<string | null>(null);
    const [expandedEvents, setExpandedEvents] = useState<Set<number>>(() => new Set());

    const [orderEvents, setOrderEvents] = useState<EventLogEntry[]>([]);
    const [orderCount, setOrderCount] = useState(0);
    const [orderType, setOrderType] = useState('');
    const [orderPrevadzka, setOrderPrevadzka] = useState('');
    const [orderDateFrom, setOrderDateFrom] = useState('');
    const [orderDateTo, setOrderDateTo] = useState('');
    const [orderPage, setOrderPage] = useState(1);
    const [orderHasNext, setOrderHasNext] = useState(false);
    const [orderLoading, setOrderLoading] = useState(true);
    const [orderError, setOrderError] = useState<string | null>(null);
    const [expandedOrders, setExpandedOrders] = useState<Set<number>>(() => new Set());

    const [upcoming, setUpcoming] = useState<UpcomingEventEntry[]>([]);
    const [upcomingLoading, setUpcomingLoading] = useState(true);
    const [upcomingError, setUpcomingError] = useState<string | null>(null);
    const [expandedUpcoming, setExpandedUpcoming] = useState<Set<string>>(() => new Set());
    const upcomingGroups = useMemo(() => groupUpcomingByCategory(upcoming), [upcoming]);

    const [entries, setEntries] = useState<AdminLogEntry[]>([]);
    const [availableLoggers, setAvailableLoggers] = useState<string[]>([]);
    const [selectedLevels, setSelectedLevels] = useState<string[]>(['WARNING', 'ERROR', 'CRITICAL']);
    const [selectedLogger, setSelectedLogger] = useState('');
    const [search, setSearch] = useState('');
    const [limit, setLimit] = useState(200);
    const [systemLoading, setSystemLoading] = useState(true);
    const [systemError, setSystemError] = useState<string | null>(null);
    const [expandedSystem, setExpandedSystem] = useState<Set<number>>(() => new Set());

    const fetchEvents = useCallback(async () => {
        setEventLoading(true);
        setEventError(null);
        try {
            const params = new URLSearchParams({ ordering: '-created_at', page: String(eventPage) });
            if (eventType) {
                params.set('event_type', eventType);
            } else {
                // Bez konkrétneho filtra by "všetky typy" zahŕňalo aj objednávkové
                // zmeny — tie majú vlastnú kartu "Objednávky".
                params.set('exclude_event_type', ORDER_EVENT_TYPES.join(','));
            }
            if (actor.trim()) params.set('actor', actor.trim());
            if (dateFrom) params.set('date_from', dateFrom);
            if (dateTo) params.set('date_to', dateTo);
            const res = await apiFetch(`${API_URL}/admin/event-logs/?${params.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as EventLogsResponse;
            setEvents(data.results);
            setEventCount(data.count);
            setEventHasNext(Boolean(data.next));
        } catch (e) {
            logger.error(e);
            setEventError('Udalosti sa nepodarilo načítať');
        } finally {
            setEventLoading(false);
        }
    }, [actor, apiFetch, dateFrom, dateTo, eventPage, eventType]);

    const fetchOrderEvents = useCallback(async () => {
        setOrderLoading(true);
        setOrderError(null);
        try {
            const params = new URLSearchParams({
                ordering: '-created_at',
                page: String(orderPage),
                event_type: orderType || ORDER_EVENT_TYPES.join(','),
            });
            if (orderPrevadzka.trim()) params.set('prevadzka', orderPrevadzka.trim());
            if (orderDateFrom) params.set('date_from', orderDateFrom);
            if (orderDateTo) params.set('date_to', orderDateTo);
            const res = await apiFetch(`${API_URL}/admin/event-logs/?${params.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as EventLogsResponse;
            setOrderEvents(data.results);
            setOrderCount(data.count);
            setOrderHasNext(Boolean(data.next));
        } catch (e) {
            logger.error(e);
            setOrderError('Objednávkové udalosti sa nepodarilo načítať');
        } finally {
            setOrderLoading(false);
        }
    }, [apiFetch, orderDateFrom, orderDateTo, orderPage, orderPrevadzka, orderType]);

    const fetchSystemLogs = useCallback(async () => {
        setSystemLoading(true);
        setSystemError(null);
        try {
            const params = new URLSearchParams({ limit: String(limit), ordering: '-timestamp' });
            if (selectedLevels.length > 0) params.set('level', selectedLevels.join(','));
            if (selectedLogger) params.set('logger', selectedLogger);
            if (search.trim()) params.set('search', search.trim());
            const res = await apiFetch(`${API_URL}/admin/logs/?${params.toString()}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as AdminLogsResponse;
            setEntries(data.results);
            setAvailableLoggers(data.available_loggers);
        } catch (e) {
            logger.error(e);
            setSystemError('Systémové logy sa nepodarilo načítať');
        } finally {
            setSystemLoading(false);
        }
    }, [apiFetch, limit, search, selectedLevels, selectedLogger]);

    const fetchUpcoming = useCallback(async () => {
        setUpcomingLoading(true);
        setUpcomingError(null);
        try {
            const res = await apiFetch(`${API_URL}/admin/upcoming-events/`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = (await res.json()) as UpcomingEventsResponse;
            setUpcoming(data.results);
        } catch (e) {
            logger.error(e);
            setUpcomingError('Nadchádzajúce udalosti sa nepodarilo načítať');
        } finally {
            setUpcomingLoading(false);
        }
    }, [apiFetch]);

    useEffect(() => { void fetchEvents(); }, [fetchEvents]);
    useEffect(() => { void fetchOrderEvents(); }, [fetchOrderEvents]);
    useEffect(() => { if (canSeeUpcoming) void fetchUpcoming(); }, [canSeeUpcoming, fetchUpcoming]);
    useEffect(() => { void fetchSystemLogs(); }, [fetchSystemLogs]);
    useEffect(() => { setEventPage(1); }, [actor, dateFrom, dateTo, eventType]);
    useEffect(() => { setOrderPage(1); }, [orderPrevadzka, orderDateFrom, orderDateTo, orderType]);

    const counts = useMemo(() => entries.reduce<Record<string, number>>((acc, entry) => {
        acc[entry.level] = (acc[entry.level] || 0) + 1;
        return acc;
    }, {}), [entries]);

    const toggleLevel = (level: string) => setSelectedLevels((current) =>
        current.includes(level) ? current.filter((item) => item !== level) : [...current, level]);

    const toggleExpanded = <T,>(setter: React.Dispatch<React.SetStateAction<Set<T>>>, id: T) => {
        setter((current) => {
            const next = new Set(current);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
        });
    };

    const loading = activeTab === 'events' ? eventLoading
        : activeTab === 'orders' ? orderLoading
            : activeTab === 'upcoming' ? upcomingLoading : systemLoading;
    const refresh = () => {
        if (activeTab === 'events') return fetchEvents();
        if (activeTab === 'orders') return fetchOrderEvents();
        if (activeTab === 'upcoming') return fetchUpcoming();
        return fetchSystemLogs();
    };

    return (
        <>
            <PageHead
                eyebrow="Nastavenia"
                title="Logy"
                desc="Audit administrátorských udalostí a technické logy backendu"
                actions={
                    <Button
                        variant="secondary"
                        onClick={() => void refresh()}
                        disabled={loading}
                    >
                        <RefreshCw className={loading ? 'zpa-spin' : ''} />
                        Obnoviť
                    </Button>
                }
            />

            <div className="zpa-stack">
                <Card style={{ overflow: 'hidden' }}>
                    <div className="zpa-tabs">
                        <button type="button" onClick={() => setActiveTab('events')} className={`zpa-tab${activeTab === 'events' ? ' active' : ''}`}>
                            Udalosti (audit)
                        </button>
                        <button type="button" onClick={() => setActiveTab('orders')} className={`zpa-tab${activeTab === 'orders' ? ' active' : ''}`}>
                            Objednávky
                        </button>
                        {canSeeUpcoming && (
                            <button type="button" onClick={() => setActiveTab('upcoming')} className={`zpa-tab${activeTab === 'upcoming' ? ' active' : ''}`}>
                                Nadchádzajúce
                            </button>
                        )}
                        {canSeeSystem && (
                            <button type="button" onClick={() => setActiveTab('system')} className={`zpa-tab${activeTab === 'system' ? ' active' : ''}`}>
                                Systémové logy
                            </button>
                        )}
                    </div>
                </Card>

                {activeTab === 'events' ? (
                    <>
                        <Card pad>
                            <div className="zpa-grid-3">
                                <Field label="Typ udalosti">
                                    <Select value={eventType} onChange={(e) => setEventType(e.target.value)}>
                                        <option value="">Všetky typy</option>
                                        {EVENT_TYPES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                                    </Select>
                                </Field>
                                <Field label="ID aktora">
                                    <Input type="number" min="1" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Všetci aktéri" />
                                </Field>
                                <div className="zpa-grid-2">
                                    <Field label="Od"><Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></Field>
                                    <Field label="Do"><Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></Field>
                                </div>
                            </div>
                        </Card>

                        {eventError && <div className="zpa-empty">{eventError}</div>}
                        <Card style={{ overflow: 'hidden' }}>
                            <div className="zpa-card-head" style={{ padding: '14px 20px', borderBottom: '1px solid var(--line-soft)' }}>
                                <h3>Udalosti ({eventCount})</h3>
                            </div>
                            {eventLoading ? <div className="zpa-empty">Načítavam…</div> : events.length === 0 ? (
                                <div className="zpa-empty">Žiadne udalosti pre aktuálne filtre</div>
                            ) : (
                                <div className="zpa-table-wrap">
                                    <table className="zpa-table">
                                        <thead><tr><th>Čas</th><th>Typ</th><th>Kto</th><th>Cieľ</th><th>Súhrn</th><th /></tr></thead>
                                        <tbody>
                                            {events.map((entry) => {
                                                const isExpanded = expandedEvents.has(entry.id);
                                                return (
                                                    <Fragment key={entry.id}>
                                                        <tr>
                                                            <td><EventTime value={entry.created_at} /></td>
                                                            <td>
                                                                <span className={`zpa-badge zpa-badge--${eventTone(entry.event_type)}`}>
                                                                    {entry.event_type_label}
                                                                </span>
                                                            </td>
                                                            <td>{actorDisplay(entry)}</td>
                                                            <td>{targetDisplay(entry)}</td>
                                                            <td>{entry.summary}</td>
                                                            <td className="r">
                                                                <Button variant="ghost" sm onClick={() => toggleExpanded(setExpandedEvents, entry.id)}>
                                                                    {isExpanded ? <ChevronDown /> : <ChevronRight />} Detail
                                                                </Button>
                                                            </td>
                                                        </tr>
                                                        {isExpanded && (
                                                            <tr>
                                                                <td colSpan={6}><EventPayloadDetails payload={entry.payload} /></td>
                                                            </tr>
                                                        )}
                                                    </Fragment>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 20px', borderTop: '1px solid var(--line-soft)' }}>
                                <Button variant="secondary" sm disabled={eventPage === 1 || eventLoading} onClick={() => setEventPage((page) => page - 1)}>Predchádzajúca</Button>
                                <span>Strana {eventPage}</span>
                                <Button variant="secondary" sm disabled={!eventHasNext || eventLoading} onClick={() => setEventPage((page) => page + 1)}>Ďalšia</Button>
                            </div>
                        </Card>
                    </>
                ) : activeTab === 'orders' ? (
                    <>
                        <Card pad>
                            <div className="zpa-grid-3">
                                <Field label="Typ zmeny">
                                    <Select value={orderType} onChange={(e) => setOrderType(e.target.value)}>
                                        <option value="">Vytvorenie, úprava aj zmazanie</option>
                                        <option value="order_admin_create">Vytvorenie</option>
                                        <option value="order_admin_update">Úprava</option>
                                        <option value="order_admin_delete">Zmazanie</option>
                                    </Select>
                                </Field>
                                <Field label="ID prevádzky">
                                    <Input type="number" min="1" value={orderPrevadzka} onChange={(e) => setOrderPrevadzka(e.target.value)} placeholder="Všetky prevádzky" />
                                </Field>
                                <div className="zpa-grid-2">
                                    <Field label="Od"><Input type="date" value={orderDateFrom} onChange={(e) => setOrderDateFrom(e.target.value)} /></Field>
                                    <Field label="Do"><Input type="date" value={orderDateTo} onChange={(e) => setOrderDateTo(e.target.value)} /></Field>
                                </div>
                            </div>
                        </Card>

                        {orderError && <div className="zpa-empty">{orderError}</div>}
                        <Card style={{ overflow: 'hidden' }}>
                            <div className="zpa-card-head" style={{ padding: '14px 20px', borderBottom: '1px solid var(--line-soft)' }}>
                                <h3>Objednávky ({orderCount})</h3>
                            </div>
                            {orderLoading ? <div className="zpa-empty">Načítavam…</div> : orderEvents.length === 0 ? (
                                <div className="zpa-empty">Žiadne objednávkové udalosti pre aktuálne filtre</div>
                            ) : (
                                <div className="zpa-table-wrap">
                                    <table className="zpa-table">
                                        <thead><tr><th>Čas (BA)</th><th>Zmena</th><th>Deň objednávky</th><th>Prevádzka</th><th>Kto</th><th>Koľko čoho</th><th /></tr></thead>
                                        <tbody>
                                            {orderEvents.map((entry) => {
                                                const isExpanded = expandedOrders.has(entry.id);
                                                return (
                                                    <Fragment key={entry.id}>
                                                        <tr>
                                                            <td><EventTime value={entry.created_at} /></td>
                                                            <td>
                                                                <span className={`zpa-badge zpa-badge--${eventTone(entry.event_type)}`}>
                                                                    {orderActionLabel(entry.event_type)}
                                                                </span>
                                                            </td>
                                                            <td>{orderDayLabel(entry.payload)}</td>
                                                            <td>{entry.prevadzka_nazov || (entry.prevadzka ? `#${entry.prevadzka}` : '—')}</td>
                                                            <td>{actorDisplay(entry)}</td>
                                                            <td>{summarizeOrderMeals(entry.payload)}</td>
                                                            <td className="r">
                                                                <Button variant="ghost" sm onClick={() => toggleExpanded(setExpandedOrders, entry.id)}>
                                                                    {isExpanded ? <ChevronDown /> : <ChevronRight />} Detail
                                                                </Button>
                                                            </td>
                                                        </tr>
                                                        {isExpanded && (
                                                            <tr>
                                                                <td colSpan={7}>
                                                                    <div style={{ marginBottom: 8, color: 'var(--ink-mute)' }}>{entry.summary}</div>
                                                                    <EventPayloadDetails payload={entry.payload} />
                                                                </td>
                                                            </tr>
                                                        )}
                                                    </Fragment>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 20px', borderTop: '1px solid var(--line-soft)' }}>
                                <Button variant="secondary" sm disabled={orderPage === 1 || orderLoading} onClick={() => setOrderPage((page) => page - 1)}>Predchádzajúca</Button>
                                <span>Strana {orderPage}</span>
                                <Button variant="secondary" sm disabled={!orderHasNext || orderLoading} onClick={() => setOrderPage((page) => page + 1)}>Ďalšia</Button>
                            </div>
                        </Card>
                    </>
                ) : activeTab === 'upcoming' ? (
                    <>
                        {upcomingError && <div className="zpa-empty">{upcomingError}</div>}
                        {upcomingLoading ? (
                            <Card className="zpa-card--pad"><div className="zpa-empty">Načítavam…</div></Card>
                        ) : upcoming.length === 0 ? (
                            <Card className="zpa-card--pad"><div className="zpa-empty">Žiadne naplánované úlohy</div></Card>
                        ) : (
                            <div className="zpa-stack">
                                {upcomingGroups.map((group) => (
                                    <Card key={group.label} className="zpa-card--pad">
                                        <div className="zpa-card-head" style={{ padding: 0, border: 'none', marginBottom: 14 }}>
                                            <h3>{group.label} ({group.entries.length})</h3>
                                        </div>
                                        <div className="zpa-grid-cards">
                                            {group.entries.map((entry) => {
                                                const isExpanded = expandedUpcoming.has(entry.name);
                                                return (
                                                    <div key={entry.name} className="zpa-upcoming-card">
                                                        <div className="zpa-upcoming-card__head">
                                                            <div>
                                                                <div className="zpa-upcoming-card__title">{taskLabel(entry)}</div>
                                                                <div className="zpa-upcoming-card__name">{entry.name}</div>
                                                            </div>
                                                            {entry.next_run ? <EventTime value={entry.next_run} /> : <span className="zpa-time">—</span>}
                                                        </div>
                                                        <p className="zpa-upcoming-card__desc">{entry.description || entry.task}</p>
                                                        <div className="zpa-upcoming-card__foot">
                                                            <span className="zpa-upcoming-card__days">Dni: <strong>{entry.days ?? '—'}</strong></span>
                                                            {entry.push_preview && (
                                                                <Button variant="ghost" sm onClick={() => toggleExpanded(setExpandedUpcoming, entry.name)}>
                                                                    {isExpanded ? <ChevronDown /> : <ChevronRight />} Text správy
                                                                </Button>
                                                            )}
                                                        </div>
                                                        {isExpanded && entry.push_preview && (
                                                            <pre className="tb">{`${entry.push_preview.title}\n\n${entry.push_preview.body}`}</pre>
                                                        )}
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </>
                ) : (
                    <>
                        <div className="zpa-statusgrid">
                            {LEVELS.map((level) => <div key={level} className="zpa-statcard"><LevelBadge level={level} /><span className="num">{counts[level] || 0}</span></div>)}
                        </div>
                        <Card pad>
                            <div className="zpa-grid-3">
                                <Field label="Hľadať"><SearchBox value={search} onChange={setSearch} placeholder="Text správy alebo traceback" /></Field>
                                <Field label="Zdroj">
                                    <Select value={selectedLogger} onChange={(e) => setSelectedLogger(e.target.value)}>
                                        <option value="">Všetky zdroje</option>
                                        {availableLoggers.map((item) => <option key={item} value={item}>{item}</option>)}
                                    </Select>
                                </Field>
                                <Field label="Počet">
                                    <Select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
                                        <option value={100}>100</option><option value={200}>200</option><option value={500}>500</option>
                                    </Select>
                                </Field>
                            </div>
                            <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                {LEVELS.map((level) => (
                                    <button key={level} type="button" onClick={() => toggleLevel(level)} style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer' }}>
                                        <LevelBadge level={level} muted={!selectedLevels.includes(level)} />
                                    </button>
                                ))}
                            </div>
                        </Card>
                        {systemError && <div className="zpa-empty">{systemError}</div>}
                        <Card style={{ overflow: 'hidden' }}>
                            <div className="zpa-card-head" style={{ padding: '14px 20px', borderBottom: '1px solid var(--line-soft)' }}><h3>Záznamy ({entries.length})</h3></div>
                            {systemLoading ? <div className="zpa-empty">Načítavam…</div> : entries.length === 0 ? <div className="zpa-empty">Žiadne logy pre aktuálne filtre</div> : (
                                <div>{entries.map((entry) => {
                                    const isExpanded = expandedSystem.has(entry.id);
                                    return (
                                        <div key={entry.id} className="zpa-log">
                                            <div className="ts">{formatTime(entry.timestamp)}</div>
                                            <div><LevelBadge level={entry.level} /></div>
                                            <div style={{ minWidth: 0 }}>
                                                <div className="src" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                                                    <span>{entry.logger}:{entry.line}</span>
                                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: 'var(--bg-cream-soft)', padding: '1px 6px', borderRadius: 'var(--radius-sm)' }}><Bug style={{ width: 12, height: 12 }} /> PID {entry.process}</span>
                                                </div>
                                                <pre className="msg">{entry.message}</pre>
                                            </div>
                                            {entry.traceback ? <button className="zpa-btn zpa-btn--ghost zpa-btn--sm" onClick={() => toggleExpanded(setExpandedSystem, entry.id)}>{isExpanded ? <ChevronDown /> : <ChevronRight />} Detail</button> : <span />}
                                            {entry.traceback && isExpanded && <pre className="tb">{entry.traceback}</pre>}
                                        </div>
                                    );
                                })}</div>
                            )}
                        </Card>
                    </>
                )}
            </div>
        </>
    );
}
