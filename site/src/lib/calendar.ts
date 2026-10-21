import { programs, type Program, type ProgramEvent } from './data';
import { SITE_NAME, SITE_URL } from '../config';

export interface FlatEvent extends ProgramEvent { program: Program; }

export function allEvents(): FlatEvent[] {
  const out: FlatEvent[] = [];
  for (const p of programs) for (const e of p.events) out.push({ ...e, program: p });
  return out.sort((a, b) => a.start.localeCompare(b.start));
}

export function statusLabel(s: ProgramEvent['status']): string {
  return { verified: 'verified on official page', 'from-brief': 'not re-verified on primary page', expected: 'expected pattern, NOT announced', unverified: 'dates unverified' }[s];
}

function icsDate(iso: string): string {
  return iso.replace(/-/g, '');
}
function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
function escapeIcs(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
}
function fold(line: string): string {
  // RFC 5545: lines max 75 octets; fold with CRLF + space.
  const out: string[] = [];
  let cur = '';
  for (const ch of line) {
    if (Buffer.byteLength(cur + ch, 'utf8') > 73) { out.push(cur); cur = ' ' + ch; } else cur += ch;
  }
  out.push(cur);
  return out.join('\r\n');
}

export function buildIcs(filter?: (e: FlatEvent) => boolean): string {
  const now = new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', `PRODID:-//${SITE_NAME}//Program calendar//EN`, 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeIcs(`${SITE_NAME} – open-source program calendar`)}`,
    `X-WR-CALDESC:${escapeIcs('Deadlines for GSoC, Outreachy, LFX Mentorship, Summer of Bitcoin, MLH Fellowship and Season of KDE. Entries marked EXPECTED are not announced. Always confirm on the official page.')}`,
    'REFRESH-INTERVAL;VALUE=DURATION:P1D', 'X-PUBLISHED-TTL:P1D',
  ];
  for (const e of allEvents()) {
    if (filter && !filter(e)) continue;
    const uid = `${e.program.id}-${e.start}-${e.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)}@${new URL(SITE_URL).host}`;
    const end = e.end ? addDays(e.end, 1) : addDays(e.start, 1); // DTEND is exclusive for all-day events
    const prefix = e.status === 'expected' ? '[EXPECTED] ' : e.status === 'unverified' ? '[UNVERIFIED] ' : '';
    const desc = `${statusLabel(e.status)}. Official: ${e.program.timeline_url}. Last verified ${e.program.last_verified}. Calendar by ${SITE_NAME} (${SITE_URL}/calendar/). ${SITE_NAME} is not affiliated with any program.`;
    lines.push('BEGIN:VEVENT', `UID:${uid}`, `DTSTAMP:${now}`, `DTSTART;VALUE=DATE:${icsDate(e.start)}`, `DTEND;VALUE=DATE:${icsDate(end)}`,
      fold(`SUMMARY:${escapeIcs(`${prefix}${e.program.short}: ${e.title}`)}`), fold(`DESCRIPTION:${escapeIcs(desc)}`), `URL:${e.program.timeline_url}`,
      `CATEGORIES:${e.program.short},${e.kind}`, `STATUS:${e.status === 'verified' ? 'CONFIRMED' : 'TENTATIVE'}`, 'END:VEVENT');
  }
  lines.push('END:VCALENDAR');
  return lines.join('\r\n') + '\r\n';
}
