/* =============================================================
 * Zdravý Projekt — Admin shared UI primitives.
 * Thin React wrappers over the `zpa-*` classes in admin.css,
 * mirroring the design kit (.claude/design/ui_kits/admin_app).
 * ============================================================= */
import React from 'react';
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import { useDisabled } from '../../lib/editAccessContext';
import { fromDateKey, isWeekday, nextWeekday, prevWeekday, toDateString } from '../../lib/businessDay';

type Div = React.HTMLAttributes<HTMLDivElement>;

/* ── Page header ── */
export const PageHead: React.FC<{
    eyebrow?: React.ReactNode;
    title: React.ReactNode;
    /** Voliteľný obsah hneď vpravo od nadpisu, na tom istom riadku (napr.
     * kompaktný dátumový prepínač na Gramáži jedál) — nie je to `desc`, ktorý
     * ide na riadok pod nadpis. */
    titleExtra?: React.ReactNode;
    desc?: React.ReactNode;
    actions?: React.ReactNode;
}> = ({ eyebrow, title, titleExtra, desc, actions }) => (
    <div className="zpa-pagehead">
        <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            <div className="zpa-pagehead-title-row">
                <h1>{title}</h1>
                {titleExtra}
            </div>
            {desc && <p>{desc}</p>}
        </div>
        {actions && <div className="actions">{actions}</div>}
    </div>
);

/* ── Button ── */
type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'honey';
/** `allowReadOnly` = prvok nič nemení (hľadanie, filter, export), viď editAccess. */
type ReadOnlyAware = { allowReadOnly?: boolean };

export const Button: React.FC<
    React.ButtonHTMLAttributes<HTMLButtonElement> &
        ReadOnlyAware & { variant?: BtnVariant; sm?: boolean }
> = ({ variant = 'primary', sm, className = '', children, allowReadOnly, disabled, ...rest }) => (
    <button
        className={`zpa-btn zpa-btn--${variant}${sm ? ' zpa-btn--sm' : ''} ${className}`.trim()}
        disabled={useDisabled(disabled, allowReadOnly)}
        {...rest}
    >
        {children}
    </button>
);

export const IconButton: React.FC<
    React.ButtonHTMLAttributes<HTMLButtonElement> & ReadOnlyAware
> = ({ className = '', children, allowReadOnly, disabled, ...rest }) => (
    <button
        className={`zpa-iconbtn ${className}`.trim()}
        disabled={useDisabled(disabled, allowReadOnly)}
        {...rest}
    >
        {children}
    </button>
);

/* ── Card ── */
export const Card: React.FC<Div & { pad?: boolean }> = ({ pad, className = '', children, ...rest }) => (
    <div className={`zpa-card${pad ? ' zpa-card--pad' : ''} ${className}`.trim()} {...rest}>
        {children}
    </div>
);

export const CardHead: React.FC<{ title: React.ReactNode; desc?: React.ReactNode; actions?: React.ReactNode }> = ({
    title,
    desc,
    actions,
}) => (
    <div className="zpa-card-head">
        <div>
            <h3>{title}</h3>
            {desc && <p>{desc}</p>}
        </div>
        {actions && <div className="actions">{actions}</div>}
    </div>
);

/* ── Badge ── */
type BadgeTone = 'green' | 'peach' | 'teal' | 'honey' | 'coral' | 'gray' | 'orange';
export const Badge: React.FC<React.HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }> = ({
    tone = 'gray',
    className = '',
    children,
    ...rest
}) => (
    <span className={`zpa-badge zpa-badge--${tone} ${className}`.trim()} {...rest}>
        {children}
    </span>
);

/* ── Date navigator ──
 * Zdieľaný dátumový prepínač (Gramáž jedál, Kontrola objednávok) — šípky na
 * predchádzajúci/nasledujúci pracovný deň, štýlovaný popisok "deň + dátum"
 * (napr. "piatok 4. sep", klik naň otvorí natívny date picker cez skrytý
 * input) a badge Dnes/Zajtra/Posledný pracovný deň. Jeden komponent namiesto
 * kopírovania medzi obrazovkami, nech vizuálne aj funkčne nedivergujú. */
export const AdminDateNav: React.FC<{
    date: string;
    onChange: (date: string) => void;
    maxDate: string;
    disabled?: boolean;
    compact?: boolean;
    className?: string;
}> = ({ date, onChange, maxDate, disabled, compact, className = '' }) => {
    const inputRef = React.useRef<HTMLInputElement>(null);
    const actualToday = React.useMemo(() => toDateString(new Date()), []);
    // Zložené ručne z troch samostatných formátovačov — spojený skeleton
    // (weekday+day+month:'short') si ICU pre sk-SK prekladá na numerický
    // mesiac ("piatok 4. 9."), samostatný `month: 'short'` formátovač ale
    // správne vráti skratku ("sep"), preto "piatok 4. sep".
    const label = React.useMemo(() => {
        const d = fromDateKey(date);
        const weekday = new Intl.DateTimeFormat('sk-SK', { weekday: 'long' }).format(d);
        const month = new Intl.DateTimeFormat('sk-SK', { month: 'short' }).format(d).replace('.', '');
        return `${weekday} ${d.getDate()}. ${month}`;
    }, [date]);

    const openPicker = () => {
        const input = inputRef.current;
        if (!input || disabled) return;
        if (typeof input.showPicker === 'function') input.showPicker();
        else input.focus();
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        if (!val || !isWeekday(fromDateKey(val))) return;
        if (val <= maxDate) onChange(val);
    };

    return (
        <Card className={`zpa-datenav-card ${className}`.trim()}>
            <div className={`zpa-datenav${compact ? ' zpa-datenav--compact' : ''}`}>
                <button
                    type="button"
                    className="zpa-navchip"
                    onClick={() => onChange(prevWeekday(date))}
                    disabled={disabled}
                    aria-label="Predchádzajúci deň"
                    title="Predchádzajúci deň"
                >
                    <ChevronLeft />
                </button>
                <div className="mid">
                    <button
                        type="button"
                        className="curr zpa-datenav-currbtn"
                        onClick={openPicker}
                        disabled={disabled}
                        title="Vybrať dátum"
                    >
                        {label}
                    </button>
                    <input
                        ref={inputRef}
                        type="date"
                        value={date}
                        max={maxDate}
                        disabled={disabled}
                        onChange={handleInputChange}
                        className="zpa-datenav-hidden-input"
                        aria-label="Vybrať dátum"
                        tabIndex={-1}
                    />
                    {date === actualToday && <Badge tone="orange">Dnes</Badge>}
                    {date === maxDate && date !== actualToday && date > actualToday && (
                        <Badge tone="orange">Zajtra</Badge>
                    )}
                    {date === maxDate && date !== actualToday && date < actualToday && (
                        <Badge tone="gray">Posledný pracovný deň</Badge>
                    )}
                </div>
                <button
                    type="button"
                    className="zpa-navchip"
                    onClick={() => {
                        const n = nextWeekday(date);
                        if (n <= maxDate) onChange(n);
                    }}
                    disabled={disabled || date >= maxDate}
                    aria-label="Nasledujúci deň"
                    title="Nasledujúci deň"
                >
                    <ChevronRight />
                </button>
            </div>
        </Card>
    );
};

/* ── Form controls ── */
export const Field: React.FC<{
    label?: React.ReactNode;
    req?: boolean;
    hint?: React.ReactNode;
    children: React.ReactNode;
    as?: 'label' | 'div';
}> = ({ label, req, hint, children, as: Component = 'label' }) => (
    <Component className="zpa-field">
        {label && (
            <span className="zpa-label">
                {label}
                {req && <span className="req"> *</span>}
                {hint && <span className="hint"> {hint}</span>}
            </span>
        )}
        {children}
    </Component>
);

export const Input: React.FC<
    React.InputHTMLAttributes<HTMLInputElement> & ReadOnlyAware
> = ({ className = '', allowReadOnly, disabled, ...rest }) => (
    <input
        className={`zpa-input ${className}`.trim()}
        disabled={useDisabled(disabled, allowReadOnly)}
        {...rest}
    />
);

const DIET_COLORS = [
    // One consistent saturation/lightness level across the full hue wheel.
    // This keeps every diet equally prominent without repeating light/dark
    // variants of the same eight colours.
    '#D83131', '#D85B31', '#D88531', '#D8AE31', '#D8D831', '#AED831',
    '#85D831', '#5BD831', '#31D831', '#31D85B', '#31D885', '#31D8AE',
    '#31D8D8', '#31AED8', '#3185D8', '#315BD8', '#3131D8', '#5B31D8',
    '#8531D8', '#AE31D8', '#D831D8', '#D831AE', '#D83185', '#D8315B',
];

export const ColorSwatchPicker: React.FC<{
    value: string;
    onChange: (value: string) => void;
    ariaLabel: string;
}> = ({ value, onChange, ariaLabel }) => {
    const [open, setOpen] = React.useState(false);
    const [showCustomColor, setShowCustomColor] = React.useState(
        () => !!value && !DIET_COLORS.includes(value.toUpperCase())
    );
    const [focusedColor, setFocusedColor] = React.useState<string | null>(null);

    const selectColor = (color: string) => {
        onChange(color);
        setOpen(false);
    };

    return (
        <>
            <button
                type="button"
                className="zpa-color-trigger"
                aria-label={`Vybrať ${ariaLabel}`}
                aria-haspopup="dialog"
                aria-expanded={open}
                onClick={() => setOpen(true)}
            >
                <span className="zpa-color-trigger-swatch" style={{ background: value }} aria-hidden="true" />
                <span>{value.toUpperCase()}</span>
                <span className="zpa-color-trigger-action">Zmeniť</span>
            </button>
            {open && (
                <Modal title={ariaLabel} onClose={() => setOpen(false)}>
                    <div role="group" aria-label={ariaLabel} className="zpa-color-grid">
                        {DIET_COLORS.map((color) => {
                            const selected = value.toUpperCase() === color;
                            const focused = focusedColor === color;

                            return (
                                <button
                                    key={color}
                                    type="button"
                                    aria-label={`${ariaLabel}: ${color}`}
                                    aria-pressed={selected}
                                    onClick={() => selectColor(color)}
                                    onFocus={() => setFocusedColor(color)}
                                    onBlur={() => setFocusedColor(null)}
                                    className="zpa-color-option"
                                    style={{
                                        background: color,
                                        boxShadow: focused
                                            ? '0 0 0 3px var(--green-700)'
                                            : selected
                                              ? '0 0 0 3px var(--green-900)'
                                              : '0 0 0 1px rgba(39, 52, 34, 0.22)',
                                    }}
                                />
                            );
                        })}
                    </div>
                    <button
                        type="button"
                        aria-expanded={showCustomColor}
                        onClick={() => setShowCustomColor((shown) => !shown)}
                        className="zpa-color-custom-toggle"
                    >
                        Vlastná farba
                    </button>
                    {showCustomColor && (
                        <Input
                            type="color"
                            value={value}
                            onChange={(e) => selectColor(e.target.value)}
                            aria-label={ariaLabel}
                            style={{ width: 64, padding: 4 }}
                        />
                    )}
                </Modal>
            )}
        </>
    );
};

export const Select: React.FC<
    React.SelectHTMLAttributes<HTMLSelectElement> & ReadOnlyAware
> = ({ className = '', children, allowReadOnly, disabled, ...rest }) => (
    <select
        className={`zpa-select ${className}`.trim()}
        disabled={useDisabled(disabled, allowReadOnly)}
        {...rest}
    >
        {children}
    </select>
);

export const Textarea: React.FC<
    React.TextareaHTMLAttributes<HTMLTextAreaElement> & ReadOnlyAware
> = ({ className = '', allowReadOnly, disabled, ...rest }) => (
    <textarea
        className={`zpa-textarea ${className}`.trim()}
        disabled={useDisabled(disabled, allowReadOnly)}
        {...rest}
    />
);

export const Toggle: React.FC<
    { on: boolean; onChange: (v: boolean) => void; disabled?: boolean; ariaLabel?: string } & ReadOnlyAware
> = ({ on, onChange, disabled: ownDisabled, ariaLabel, allowReadOnly }) => {
    const disabled = useDisabled(ownDisabled, allowReadOnly);
    return (
    <button
        type="button"
        className={`zpa-switch${on ? ' on' : ''}`}
        aria-pressed={on}
        aria-label={ariaLabel}
        disabled={disabled}
        onClick={() => onChange(!on)}
    />
    );
};

export const Checkbox: React.FC<
    { on: boolean; onChange: (v: boolean) => void; children?: React.ReactNode } & ReadOnlyAware
> = ({ on, onChange, children, allowReadOnly }) => (
    <button
        type="button"
        className={`zpa-check${on ? ' on' : ''}`}
        disabled={useDisabled(undefined, allowReadOnly)}
        onClick={() => onChange(!on)}
    >
        <span className="box">{on && <CheckMark />}</span>
        {children}
    </button>
);

const CheckMark = () => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
        <path d="M20 6 9 17l-5-5" />
    </svg>
);

export const SearchBox: React.FC<{
    value: string;
    onChange: (v: string) => void;
    placeholder?: string;
    className?: string;
}> = ({ value, onChange, placeholder, className = '' }) => (
    <div className={`zpa-search ${className}`.trim()}>
        <Search />
        <input className="zpa-input" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
    </div>
);

/* ── Stat card ── */
export const StatCard: React.FC<{ num: React.ReactNode; label: React.ReactNode; slot?: React.ReactNode }> = ({
    num,
    label,
    slot,
}) => (
    <div className="zpa-statcard">
        <div>
            <div className="num">{num}</div>
            <div className="lbl">{label}</div>
        </div>
        {slot}
    </div>
);

/* ── Empty state ── */
export const Empty: React.FC<{ icon?: React.ReactNode; children: React.ReactNode }> = ({ icon, children }) => (
    <div className="zpa-empty">
        {icon}
        <div>{children}</div>
    </div>
);

/* ── Modal ── */
export const Modal: React.FC<{
    title?: React.ReactNode;
    onClose?: () => void;
    children: React.ReactNode;
    foot?: React.ReactNode;
    wide?: boolean;
    icon?: React.ReactNode;
    iconKind?: 'danger' | 'warn' | 'ok' | '';
}> = ({ title, onClose, children, foot, wide, icon, iconKind = '' }) => (
    <div
        className="zpa-scrim"
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose?.();
        }}
    >
        <div className={`zpa-modal${wide ? ' zpa-modal--wide' : ''}`}>
            {title !== undefined && (
                <div className="zpa-modal-head">
                    <h3>{title}</h3>
                    {onClose && (
                        <button className="zpa-modal-close" onClick={onClose} aria-label="Zavrieť">
                            <X />
                        </button>
                    )}
                </div>
            )}
            <div className="zpa-modal-body">
                {icon && <div className={`zpa-modal-icon ${iconKind}`}>{icon}</div>}
                {children}
            </div>
            {foot && <div className="zpa-modal-foot">{foot}</div>}
        </div>
    </div>
);

/* ── Table helpers (use plain <table className="zpa-table"> within) ── */
export const TableWrap: React.FC<Div> = ({ className = '', children, ...rest }) => (
    <div className={`zpa-table-wrap ${className}`.trim()} {...rest}>
        {children}
    </div>
);
