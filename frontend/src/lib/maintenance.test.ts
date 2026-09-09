import { describe, expect, it } from 'vitest';
import { shouldShowMaintenance } from './maintenance';

const activeWindow = {
  maintenance_enabled: true,
  maintenance_starts_at: '2026-09-08T10:00:00Z',
  maintenance_ends_at: '2026-09-08T12:00:00Z',
};

describe('shouldShowMaintenance', () => {
  it('blocks a client but never an admin during an active window', () => {
    const now = Date.parse('2026-09-08T11:00:00Z');
    expect(shouldShowMaintenance(activeWindow, { role: 'klient' }, now)).toBe(true);
    expect(shouldShowMaintenance(activeWindow, { role: 'admin', is_staff: true }, now)).toBe(false);
    expect(shouldShowMaintenance(activeWindow, { role: 'superadmin', is_staff: true }, now)).toBe(false);
  });
});
