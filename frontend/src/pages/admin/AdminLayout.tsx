import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import {
    Gauge,
    ClipboardCheck,
    CalendarDays,
    BookOpen,
    Building,
    Route as RouteIcon,
    Salad,
    Combine,
    Sliders,
    Umbrella,
    Scroll,
    Bell,
    Shield,
    LogOut,
    Menu,
} from 'lucide-react';
import { useAuth } from '../../context/auth';
import { isSuperadmin } from '../../lib/roles';
import { SECTION, canRead } from '../../lib/sections';
import { visibleNav, type NavEntry } from './adminNav';
import { Modal, Button } from './ui';
import AdminProfileModal from './AdminProfileModal';
import { APP_VERSION } from '../../lib/appVersion';


const NAV: NavEntry[] = [
    { kind: 'item', to: '/admin/dashboard', label: 'Tabuľka', icon: Gauge, section: SECTION.dashboard },
    { kind: 'item', to: '/admin/prevadzka-overview', label: 'Kontrola objednávok', icon: ClipboardCheck, section: SECTION.podklady },
    { kind: 'item', to: '/admin/delivery-layout', label: 'Poradie a trasy', icon: RouteIcon, section: SECTION.trasy },
    { kind: 'item', to: '/admin/meal-plan', label: 'Jedálniček', icon: CalendarDays, section: SECTION.jedalnicek },
    { kind: 'item', to: '/admin/diet-component-merge', label: 'Zlúčenie diét', icon: Combine, section: SECTION.jedalnicek },
    { kind: 'item', to: '/admin/meal-catalog', label: 'Katalóg jedál', icon: BookOpen, section: SECTION.katalog },
    { kind: 'section', label: 'Prevádzky', icon: Building },
    { kind: 'item', to: '/admin/facilities', label: 'Správa prevádzok', icon: Building, section: SECTION.prevadzky },
    { kind: 'section', label: 'Nastavenia', icon: Sliders },
    { kind: 'item', to: '/admin/diets', label: 'Diéty', icon: Salad, section: SECTION.diety },
    { kind: 'item', to: '/admin/settings', label: 'Systémové nastavenia', icon: Sliders, superadminOnly: true, section: SECTION.nastavenia },
    { kind: 'item', to: '/admin/holidays', label: 'Voľné dni', icon: Umbrella, section: SECTION.volneDni },
    { kind: 'item', to: '/admin/logs', label: 'Udalosti', icon: Scroll, section: SECTION.udalosti },
    { kind: 'section', label: 'Komunikácia', icon: Bell },
    { kind: 'item', to: '/admin/push-notifications', label: 'Notifikácie', icon: Bell, section: SECTION.notifikacie },
    { kind: 'section', label: 'Oprávnenia', icon: Shield },
    { kind: 'item', to: '/admin/roles', label: 'Správa adminov', icon: Shield, superadminOnly: true, section: SECTION.pristupy },
];

const AdminLayout: React.FC = () => {
    const { logout, user } = useAuth();
    const location = useLocation();
    const nav = React.useMemo(
        () => visibleNav(NAV, isSuperadmin(user), (s) => canRead(user?.sections, s)),
        [user],
    );
    const [navOpen, setNavOpen] = React.useState(false);
    const [showLogoutModal, setShowLogoutModal] = React.useState(false);
    const [showProfileModal, setShowProfileModal] = React.useState(false);

    React.useEffect(() => {
        setNavOpen(false);
    }, [location.pathname]);

    const isActive = (to: string) => location.pathname.startsWith(to);

    const displayName =
        user?.first_name || user?.last_name
            ? `${user.first_name || ''} ${user.last_name || ''}`.trim()
            : user?.email?.split('@')[0] || 'Administrátor';
    const initial = (displayName[0] || 'A').toUpperCase();

    return (
        <div className={`zpa-app${navOpen ? ' nav-open' : ''}`}>
            {/* Mobile top bar */}
            <div className="zpa-topbar">
                <img src="/logo-zdravy-projekt.png" alt="Zdravý projekt" />
                <button className="zpa-iconbtn" aria-label="Otvoriť menu" onClick={() => setNavOpen(true)}>
                    <Menu />
                </button>
            </div>

            {navOpen && <div className="zpa-scrim-nav" onClick={() => setNavOpen(false)} />}

            <aside className="zpa-sidebar">
                <div className="zpa-side-inner">
                    <div className="zpa-brand">
                        <div className="brand-mini">
                            <img src="/logo-zdravy-projekt.png" alt="Zdravý projekt" />
                        </div>
                        <div className="brand-full">
                            <img src="/logo-zdravy-projekt.png" alt="Zdravý projekt" />
                            <span className="badge">Administrácia</span>
                            <span className="zpa-version">v{APP_VERSION}</span>
                        </div>
                    </div>

                    <nav className="zpa-nav">
                        {nav.map((n, i) => {
                            if (n.kind === 'section') {
                                const Ic = n.icon;
                                return (
                                    <div className="zpa-nav-section" key={`s${i}`}>
                                        <Ic />
                                        <span className="lbl">{n.label}</span>
                                    </div>
                                );
                            }
                            const Ic = n.icon;
                            return (
                                <Link
                                    key={n.to}
                                    to={n.to}
                                    className={`zpa-nav-item${isActive(n.to) ? ' active' : ''}`}
                                    title={n.label}
                                >
                                    <Ic />
                                    <span className="lbl">{n.label}</span>
                                </Link>
                            );
                        })}
                    </nav>

                    <div className="zpa-user">
                        <button
                            type="button"
                            className="zpa-user-btn"
                            onClick={() => setShowProfileModal(true)}
                            title="Upraviť profil"
                        >
                            <div className="avatar">{initial}</div>
                            <div className="body">
                                <div className="nm">{displayName}</div>
                                <div className="em">{user?.email}</div>
                            </div>
                        </button>
                        <button className="logout" onClick={() => setShowLogoutModal(true)} title="Odhlásiť sa">
                            <LogOut />
                        </button>
                    </div>
                </div>
            </aside>

            <main className="zpa-main" id="zpa-main">
                <div className={`zpa-content${location.pathname === '/admin/dashboard' ? ' zpa-content--wide zpa-content--fill' : ''}`}>
                    <Outlet />
                </div>
            </main>

            {showLogoutModal && (
                <Modal
                    title="Naozaj sa chcete odhlásiť?"
                    onClose={() => setShowLogoutModal(false)}
                    foot={
                        <>
                            <Button variant="ghost" onClick={() => setShowLogoutModal(false)}>
                                Zrušiť
                            </Button>
                            <Button
                                variant="danger"
                                onClick={() => {
                                    setShowLogoutModal(false);
                                    void logout();
                                }}
                            >
                                Odhlásiť sa
                            </Button>
                        </>
                    }
                >
                    <p style={{ margin: 0, color: 'var(--ink-2)' }}>Budete presmerovaný na prihlasovaciu obrazovku.</p>
                </Modal>
            )}

            {showProfileModal && <AdminProfileModal onClose={() => setShowProfileModal(false)} />}
        </div>
    );
};

export default AdminLayout;
