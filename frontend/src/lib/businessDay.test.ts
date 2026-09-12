import { describe, expect, it } from "vitest";
import {
  businessDays,
  dashboardDefaultDate,
  dashboardMaxDate,
  dayOffReason,
  isDayOff,
  nextBusinessDay,
  previousBusinessDay,
  stepBusinessDay,
  toDateKey,
} from "./businessDay";

// August 2026: 10. je pondelok, 8. sobota, 9. nedeľa.
const monday = () => new Date(2026, 7, 10);
const saturday = () => new Date(2026, 7, 8);
const sunday = () => new Date(2026, 7, 9);
const atHour = (date: Date, hour: number) => {
  const result = new Date(date);
  result.setHours(hour, 0, 0, 0);
  return result;
};

describe("previousBusinessDay", () => {
  it("leaves a weekday unchanged", () => {
    expect(previousBusinessDay(monday()).getDate()).toBe(10);
  });

  it("rolls a Saturday back to Friday", () => {
    const result = previousBusinessDay(saturday());
    expect(result.getDay()).toBe(5);
    expect(result.getDate()).toBe(7);
  });

  it("rolls a Sunday back to Friday", () => {
    const result = previousBusinessDay(sunday());
    expect(result.getDay()).toBe(5);
    expect(result.getDate()).toBe(7);
  });

  it("skips a holiday as well as the weekend", () => {
    const holidays = new Set(["2026-08-07"]);
    expect(toDateKey(previousBusinessDay(saturday(), { holidays }))).toBe("2026-08-06");
  });
});

describe("isDayOff / dayOffReason", () => {
  it("separates weekend, holiday and prevádzka closure", () => {
    const sets = {
      holidays: new Set(["2026-08-11"]),
      closures: new Set(["2026-08-12"]),
    };
    expect(dayOffReason(saturday(), sets)).toBe("weekend");
    expect(dayOffReason(new Date(2026, 7, 11), sets)).toBe("holiday");
    expect(dayOffReason(new Date(2026, 7, 12), sets)).toBe("closure");
    expect(dayOffReason(monday(), sets)).toBeNull();
  });

  it("ignores closures when none are passed", () => {
    expect(isDayOff(new Date(2026, 7, 12))).toBe(false);
    expect(isDayOff(new Date(2026, 7, 12), { closures: new Set(["2026-08-12"]) })).toBe(true);
  });
});

describe("nextBusinessDay / stepBusinessDay", () => {
  it("nextBusinessDay keeps a business day, stepBusinessDay always moves", () => {
    expect(toDateKey(nextBusinessDay(monday()))).toBe("2026-08-10");
    expect(toDateKey(stepBusinessDay(monday(), 1)!)).toBe("2026-08-11");
    expect(toDateKey(stepBusinessDay(monday(), -1)!)).toBe("2026-08-07");
  });

  it("steps over a closed range", () => {
    const closures = new Set(["2026-08-11", "2026-08-12", "2026-08-13"]);
    expect(toDateKey(stepBusinessDay(monday(), 1, { closures })!)).toBe("2026-08-14");
  });
});

describe("businessDays", () => {
  it("returns the next N ordering days, skipping every kind of day off", () => {
    const days = businessDays(monday(), 3, {
      holidays: new Set(["2026-08-11"]),
      closures: new Set(["2026-08-12"]),
    });
    expect(days.map(toDateKey)).toEqual(["2026-08-10", "2026-08-13", "2026-08-14"]);
  });
});

// Hodinový EduPage priebežný náhľad (`_sync_edupage_preview_scrape_schedule`)
// dopĺňa dáta na dnes + 2 pracovné dni celý deň, takže dashboard už nemusí
// čakať na konkrétnu hodinu ako predtým (#535, len pre zajtrajšok) — vždy
// odomkne rovnaké okno, bez ohľadu na to, kedy sa otvorí.
describe("dashboardMaxDate", () => {
  it("extends 2 business days ahead of today, any hour", () => {
    expect(dashboardMaxDate(atHour(monday(), 0))).toBe("2026-08-12");
    expect(dashboardMaxDate(atHour(monday(), 23))).toBe("2026-08-12");
  });

  it("skips the weekend when counting the 2 business days ahead", () => {
    const friday = new Date(2026, 7, 7);
    expect(dashboardMaxDate(atHour(friday, 12))).toBe("2026-08-11");
  });

  it("Sunday collapses to Friday first, same result as Friday", () => {
    expect(dashboardMaxDate(atHour(sunday(), 12))).toBe("2026-08-11");
  });

  it("Saturday collapses to Friday first, same result as Friday", () => {
    expect(dashboardMaxDate(atHour(saturday(), 12))).toBe("2026-08-11");
  });

  it("skips a holiday inside the 2-business-day window", () => {
    const holidays = new Set(["2026-08-11"]);
    expect(dashboardMaxDate(atHour(monday(), 12), { holidays })).toBe("2026-08-13");
  });
});

// #539 — tomorrow is navigable from noon (dashboardMaxDate above), but the
// default view a freshly-opened dashboard shows stays on today until 21:00,
// so nobody opens the table at 14:00 and lands on a day that's still running.
describe("dashboardDefaultDate", () => {
  it("stays on today at noon, even though tomorrow is already unlocked", () => {
    expect(dashboardDefaultDate(atHour(monday(), 12))).toBe("2026-08-10");
  });

  it("stays on today just before 21:00", () => {
    expect(dashboardDefaultDate(atHour(monday(), 20))).toBe("2026-08-10");
  });

  it("switches to tomorrow from 21:00 on a weekday whose tomorrow is a workday", () => {
    expect(dashboardDefaultDate(atHour(monday(), 21))).toBe("2026-08-11");
  });

  it("switches past the weekend — Friday 21:00 shows the upcoming Monday", () => {
    const friday = new Date(2026, 7, 7);
    expect(dashboardDefaultDate(atHour(friday, 21))).toBe("2026-08-10");
  });

  it("does not switch to a tomorrow that is a holiday", () => {
    const holidays = new Set(["2026-08-11"]);
    expect(dashboardDefaultDate(atHour(monday(), 21), { holidays })).toBe("2026-08-10");
  });
});
