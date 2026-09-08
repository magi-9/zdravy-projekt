export interface MaintenanceSettings {
  maintenance_enabled?: boolean;
  maintenance_starts_at?: string | null;
  maintenance_ends_at?: string | null;
}

export function isMaintenanceActive(settings: MaintenanceSettings, now = Date.now()): boolean {
  const start = settings.maintenance_starts_at ? Date.parse(settings.maintenance_starts_at) : NaN;
  const end = settings.maintenance_ends_at ? Date.parse(settings.maintenance_ends_at) : NaN;
  return Boolean(settings.maintenance_enabled && start <= now && now < end);
}

/** Administrátori nesmú byť zamknutí z vlastnej konzoly počas update-u. */
export function shouldShowMaintenance(
  settings: MaintenanceSettings,
  user: RoleBearer | null | undefined,
  now = Date.now(),
): boolean {
  return isMaintenanceActive(settings, now) && !isAdminOrAbove(user);
}
import { isAdminOrAbove, type RoleBearer } from './roles';
