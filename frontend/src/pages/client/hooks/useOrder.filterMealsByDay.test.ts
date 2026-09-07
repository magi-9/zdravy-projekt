import { describe, expect, it } from 'vitest';
import { filterMealsByDay } from './useOrder';

describe('filterMealsByDay', () => {
    it('keeps everything when there are no restrictions at all', () => {
        expect(filterMealsByDay(['breakfast', 'lunch', 'olovrant'], null, '2026-09-04')).toEqual([
            'breakfast',
            'lunch',
            'olovrant',
        ]);
        expect(
            filterMealsByDay(['breakfast', 'lunch', 'olovrant'], undefined, '2026-09-04'),
        ).toEqual(['breakfast', 'lunch', 'olovrant']);
    });

    it('keeps a meal with an empty restriction list (means "every day")', () => {
        expect(
            filterMealsByDay(['breakfast', 'lunch'], { breakfast: [] }, '2026-09-01'),
        ).toEqual(['breakfast', 'lunch']);
    });

    it('hides breakfast on a day it is not restricted to (2026-09-01 is a Tuesday)', () => {
        expect(
            filterMealsByDay(['breakfast', 'lunch', 'olovrant'], { breakfast: [5] }, '2026-09-01'),
        ).toEqual(['lunch', 'olovrant']);
    });

    it('shows breakfast on the Friday it is restricted to (2026-09-04)', () => {
        expect(
            filterMealsByDay(['breakfast', 'lunch', 'olovrant'], { breakfast: [5] }, '2026-09-04'),
        ).toEqual(['breakfast', 'lunch', 'olovrant']);
    });
});
