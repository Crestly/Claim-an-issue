import type { APIRoute } from 'astro';
import { buildIcs } from '../../lib/calendar';
import { programs } from '../../lib/data';

export function getStaticPaths() {
  return programs.map((p) => ({ params: { program: p.id } }));
}

export const GET: APIRoute = ({ params }) =>
  new Response(buildIcs((e) => e.program.id === params.program), {
    headers: { 'Content-Type': 'text/calendar; charset=utf-8', 'Content-Disposition': `inline; filename="${params.program}.ics"` },
  });
