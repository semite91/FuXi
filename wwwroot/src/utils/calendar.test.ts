import { expect, test } from 'vitest';
import { dayHours } from './calendar';

// The test runs in Node, whose time zone follows TZ. The app itself has no Node types.
const processEnv = (globalThis as unknown as { process: { env: Record<string, string | undefined> } }).process.env;

test('review: a daylight-saving day has one row per real hour and no repeated hour', () => {
  const previousZone = processEnv.TZ;
  processEnv.TZ = 'Europe/Berlin';

  try {
    // Clocks jump from 02:00 to 03:00 on 29 March 2026 in Berlin.
    const hours = dayHours(new Date(2026, 2, 29, 12));
    const instants = hours.map((hour) => hour.getTime());

    expect(new Set(instants).size).toBe(instants.length);
    expect(hours).toHaveLength(23);
  } finally {
    processEnv.TZ = previousZone;
  }
});
