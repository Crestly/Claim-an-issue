import type { APIRoute } from 'astro';
import { buildIcs } from '../lib/calendar';

export const GET: APIRoute = () =>
  new Response(buildIcs(), { headers: { 'Content-Type': 'text/calendar; charset=utf-8', 'Content-Disposition': 'inline; filename="programs.ics"' } });
