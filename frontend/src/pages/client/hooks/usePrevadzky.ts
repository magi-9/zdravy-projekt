import { useEffect, useState } from 'react';
import { useAuth } from '../../../context/auth';
import { logger } from '../../../lib/logger';

const API_URL = import.meta.env.VITE_API_URL || '/api';

export interface PrevadzkaDiet {
    id: number;
    name: string;
    description?: string | null;
    is_active?: boolean;
    sort_order?: number;
}

export interface PrevadzkaPortionType {
    id: number;
    name: string;
    is_active?: boolean;
    sort_order?: number;
}

export interface Prevadzka {
    id: number;
    nazov: string;
    adresa: string;
    celok: string;
    visible_menus: string[];
    /** {menu písmeno: [ISO deň 1=Po..7=Ne]} — chýbajúci kľúč/prázdny zoznam = každý deň. */
    menu_day_restrictions?: Record<string, number[]> | null;
    visible_meals: string[];
    /** {jedlo: [ISO deň 1=Po..7=Ne]} — chýbajúci kľúč/prázdny zoznam = každý deň. */
    meal_day_restrictions?: Record<string, number[]> | null;
    visible_diets: PrevadzkaDiet[];
    visible_portion_types?: PrevadzkaPortionType[] | null;
    pack_separately_enabled: boolean;
}

/**
 * Prevádzky, za ktoré prihlásený klient smie objednávať.
 *
 * Jedna prevádzka → klient nič nevyberá a objednáva ako doteraz.
 * Viac → musí najprv vybrať, za ktorú prevádzku hlási.
 */
export const usePrevadzky = () => {
    const { apiFetch } = useAuth();
    const [prevadzky, setPrevadzky] = useState<Prevadzka[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;

        const load = async () => {
            try {
                const response = await apiFetch(`${API_URL}/prevadzky/`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data: Prevadzka[] = await response.json();
                if (!cancelled) setPrevadzky(data);
            } catch (e) {
                logger.error('Failed to load prevadzky', e);
                if (!cancelled) setPrevadzky([]);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        load();
        return () => {
            cancelled = true;
        };
    }, [apiFetch]);

    return {
        prevadzky,
        loading,
        // Pri jednej prevádzke ju posielame implicitne — backend si ju domyslí,
        // ale posielať ju explicitne je lacnejšie než sa spoliehať na default.
        single: prevadzky.length === 1 ? prevadzky[0] : null,
        needsChoice: prevadzky.length > 1,
    };
};

export default usePrevadzky;
