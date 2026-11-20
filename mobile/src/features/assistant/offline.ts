/**
 * Offline ParkChat: answers from what Couchbase Lite already holds.
 *
 *  1. this person's earlier answers (`chat` doc `answers`, keyed by normalized question)
 *  2. the Park Guide FAQ synced in `catalog::v1` - and, on a crew member's
 *     phone only, the Crew Handbook FAQ in `handbook::v1`
 *  3. the person's own documents: profile (bookings, cart, onboarding, benefits),
 *     feed cards and the context cache the server assembled
 *
 * Mirrors backend/app/assistant.py's intent keywords so the same question
 * lands on the same cached context offline as online. The audience gate
 * holds offline by construction: a guest's phone has no handbook document.
 */
import type { Snapshot } from '../../db/localDb';
import type { Area, ChatMessage, Cta, Faq } from '../../types';

const KEYWORDS: Record<string, string[]> = {
  service_recovery: ['broke down', 'was closed', 'shut down', 'got stuck', 'evacuated', 'never seated', 'nobody helped', 'no one helped', 'disappointed', 'upset', 'terrible', 'awful', 'complain', 'unacceptable', 'frustrated', 'ruined', 'rude', 'missed our', 'cold food', 'waited over'],
  change: ['refund', 'swap', 'cancel', 'money back', 'change my', 'switch', 'exchange', 'not tall enough', "isn't tall enough"],
  booking: ['booking', 'booked', 'reservation', 'express pass', 'my plan', 'our plan', 'next ride', 'my next', 'itinerary', 'return time', 'time window', 'confirmation', 'reschedule', 'move my', 'move our', 'dinner', "what's on", 'whats on', 'plan today'],
  cart: ['cart', 'checkout', 'check out', 'basket', 'promo code', 'offer code', 'coupon', 'glow10'],
  onboarding: ['onboarding', 'paperwork', 'i-9', 'i9', 'w-4', 'w4', 'direct deposit', 'handbook', 'new hire', 'first week', 'checklist', 'code of conduct', 'safety training', 'evacuation training', 'orientation', 'forms'],
  it: ['password', 'backstage wi-fi', 'backstage wifi', 'handheld', 'scanner', 'locked out', 'it ticket', 'inc-', 'software', 'install', 'access to', 'printer', 'outlook', 'mfa', 'help desk', 'helpdesk', 'crewpass', 'log in', 'login', 'sign in', 'authenticator', 'point of sale', 'radio', 'need approval', 'system access', 'systems do i', 'ride operations console', 'console'],
  hr: ['benefits', 'medical plan', 'dental', 'vision plan', '401k', '401(k)', 'pto', 'time off', 'day off', 'days off', 'payday', 'paycheck', 'get paid', 'parental', 'hsa', 'enroll', 'crew discount', 'employee discount', 'complimentary tickets', 'crew member discount', 'sick day', 'sick leave', 'shift', 'swap a shift', 'roster'],
  experience: ['recommend', 'looking for', 'suggest', 'what should we', 'ride next', 'which ride', 'best ride', 'coaster', 'parade', 'fireworks', 'character', 'tall enough', 'height', 'wait time', 'the wait', 'toddler', 'rainy', 'compare', 'best'],
  sales: ['planning session', 'groups & events', 'group rate', 'group pricing', 'group visit', 'group of', 'school trip', 'field trip', 'band', 'choir', 'students', 'team outing', 'company event', 'reunion', 'celebration package', 'package', 'quote', 'per guest', 'book a call', 'advisor', 'chaperone', 'our group', 'bringing', 'corporate'],
  account: ['account', 'points', 'lumina club', 'loyalty', 'tier', 'my email', 'my details', 'park credit', 'member', 'my contact', 'annual pass', 'my tickets', 'my visit'],
};
const AREA: Record<string, Area> = {
  general: 'support', account: 'support', service_recovery: 'support', experience: 'support', booking: 'commerce', change: 'commerce', cart: 'commerce',
  sales: 'sales', it: 'workplace', hr: 'workplace', onboarding: 'workplace',
};
const EMPLOYEE_INTENTS = ['it', 'hr', 'onboarding'];

export function classify(q: string, audience = 'guest'): string {
  const m = q.toLowerCase();
  let best = 'general';
  let score = 0;
  for (const [intent, kws] of Object.entries(KEYWORDS)) {
    const s = kws.filter((k) => m.includes(k)).length
      * (intent === 'service_recovery' || intent === 'change' ? 2 : 1)
      * (audience === 'employee' && EMPLOYEE_INTENTS.includes(intent) ? 2 : 1);
    if (s > score) {
      best = intent;
      score = s;
    }
  }
  if (audience === 'employee' && best === 'service_recovery') best = 'it';
  return best;
}

export const normalize = (q: string) => q.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim().slice(0, 120);

const nice = (iso?: string | null) => {
  if (!iso) return '';
  const [y, mo, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, mo - 1, d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

function bestFaq(m: string, pool: Faq[]): Faq | undefined {
  return pool
    .map((f) => ({ f, s: f.keywords.filter((k) => m.includes(k)).reduce((n, k) => n + 1 + (k.split(' ').length - 1), 0) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)[0]?.f;
}

export function answerOffline(q: string, snap: Snapshot): Omit<ChatMessage, 'id' | 'at' | 'role'> {
  const p = snap.profile;
  const audience = p?.audience ?? 'guest';
  const intent = classify(q, audience);
  const area = AREA[intent];
  const prior = snap.chat?.answers?.[normalize(q)];
  if (prior) {
    return { text: prior.reply, intent, area: prior.area ?? area, offline: true, context: { status: 'device', latency_ms: 0 } };
  }
  const m = q.toLowerCase();
  if (EMPLOYEE_INTENTS.includes(intent) && audience !== 'employee') {
    // No handbook on this phone - there is nothing to answer from, by design.
    return {
      text: "That one's for the Lumina Park crew workspace - IT, shifts, benefits and onboarding answers are only available to signed-in crew members.",
      intent, area, offline: true, restricted: true, context: { status: 'none', latency_ms: 0 },
    };
  }
  const workplace = EMPLOYEE_INTENTS.includes(intent);
  const pool = [...(workplace ? snap.handbook?.faq ?? [] : []), ...(snap.catalog?.faq ?? []), ...(workplace ? [] : snap.handbook?.faq ?? [])];
  const faq = bestFaq(m, pool);
  const ctx = snap.contexts[intent];
  const actions: Cta[] = [];
  let text: string | null = null;
  const personal = /\b(i|i'm|me|my|mine|we|our|us)\b/i.test(q) && !/^\s*(how (do|can) (i|we)|what (do|should) (i|we)|where (do|can) (i|we)|when (do|can) (i|we))\b/i.test(q);

  if (p && personal) {
    if (intent === 'booking' && p.bookings?.length) {
      const upcoming = p.bookings.filter((x) => x.status === 'upcoming').sort((a, b) => `${a.date}`.localeCompare(`${b.date}`));
      const named = upcoming.find((x) => x.items.some((i) => i.name.toLowerCase().split(/[^a-z]+/).some((w) => w.length >= 5 && m.includes(w))))
        ?? (/(dinner|lunch|breakfast|reservation)/.test(m) ? upcoming.find((x) => x.kind === 'dining') : undefined);
      const o = named ?? upcoming[0] ?? p.bookings[0];
      const when = (x: typeof o) => `${x.date === p.export_date ? 'today' : nice(x.date)}${x.time_window ? `, ${x.time_window}` : ''}`;
      text = o.status === 'upcoming'
        ? !named && upcoming.length > 1 && /(plan|itinerary|what'?s on)/.test(m)
          ? `From your phone, here's your plan: ${upcoming.slice(0, 4).map((x) => `${x.items[0].name} ${when(x)}`).join('; ')}.`
          : `From your phone: your ${o.items[0].name} ${o.kind} (booking ${o.booking_id}) is ${when(o)}${o.confirmation ? ` - confirmation ${o.confirmation}` : ''}. You can move the time now and it's sent when you're back online.`
        : `Booking ${o.booking_id} was ${o.status}${o.date ? ` on ${nice(o.date)}` : ''}.`;
      actions.push({ label: `Open ${o.items[0].name}`, screen: 'booking', args: { booking_id: o.booking_id } });
    } else if (intent === 'change' || intent === 'service_recovery') {
      const opts = snap.feed?.cards.find((c) => c.kind === 'change')?.options ?? [];
      if (opts.length) {
        text = `You're offline, but your change options are on this device: ${opts.slice(0, 3).map((o) => `${o.name} (${o.days_left <= 0 ? 'last day to change' : `${o.days_left} more days`})`).join('; ')}. Swap or refund one now and I'll send it the moment you're back online.`;
        actions.push({ label: 'Swap or refund a booking', screen: 'change' });
      }
    } else if (intent === 'cart' && p.cart?.items?.length) {
      const c = p.cart;
      text = `Your cart is saved on this device: ${c.items.map((i) => i.name).join(' and ')} ($${c.subtotal_usd})${c.offer ? ` - code ${c.offer.code} takes ${c.offer.pct_off}% off until ${nice(c.offer.expires)}` : ''}. Book them now and it's placed as soon as you reconnect.`;
      actions.push({ label: 'Book them', tool: 'checkout_cart', args: { apply_offer: true } });
    } else if (intent === 'sales' || (intent === 'experience' && audience === 'lead')) {
      const card = snap.feed?.cards.find((c) => c.kind === 'planning');
      if (p.planning_session) text = `You're booked with ${p.planning_session.advisor} on ${nice(p.planning_session.date)} at ${p.planning_session.time}.`;
      else if (card?.slots?.length) {
        text = 'You can pick a planning session time offline - open slots are saved on this device, and your booking is sent when you reconnect.';
        actions.push({ label: 'Pick a time', screen: 'planning' });
      }
    } else if (intent === 'account' && p.loyalty) {
      text = `You're a ${p.loyalty.tier} ${p.loyalty.program} member with ${p.loyalty.points.toLocaleString('en-US')} points.${p.visit ? ` Your ${p.visit.ticket} covers ${nice(p.visit.start)} to ${nice(p.visit.end)}.` : ''}`;
    } else if (intent === 'onboarding' && p.onboarding) {
      const pend = p.onboarding.tasks.filter((t) => t.status !== 'complete').sort((a, b) => (a.due_date < b.due_date ? -1 : 1));
      text = pend.length
        ? `From your phone: ${pend.length} onboarding task${pend.length > 1 ? 's' : ''} left. Next is ${pend[0].title}, due ${nice(pend[0].due_date)}. You can sign offline - it syncs when you're connected.`
        : 'Your onboarding is complete.';
      if (pend.length) actions.push({ label: 'Open my checklist', screen: 'onboarding' });
    } else if (intent === 'hr' && p.hr) {
      const sh = p.hr.schedule?.next_shift;
      if (/(shift|roster)/.test(m) && sh && !/^\s*how\b/.test(m)) {
        text = `From your phone: your next shift is ${sh.date === p.export_date ? 'today' : nice(sh.date)}, ${sh.start} to ${sh.end} at ${sh.location}.`;
      } else if (/(time off|pto|day off|days off)/.test(m)) {
        text = `You have ${p.hr.pto.balance_days} days of paid time off. Pick your dates now; the request goes to ${p.employment?.manager} when you reconnect.`;
        actions.push({ label: 'Request time off', screen: 'timeoff' });
      } else if (/(paid|payday|paycheck)/.test(m)) {
        text = `Your next pay date is ${nice(p.hr.pay.next_pay_date)}.`;
      } else if (!p.hr.benefits.enrolled) {
        text = `You haven't enrolled in benefits yet - your window closes ${nice(p.hr.benefits.enrollment_deadline)}. The plans are saved on this device.`;
        actions.push({ label: 'Compare plans & enroll', screen: 'benefits' });
      }
    } else if (intent === 'it' && p.it) {
      const t = p.it.open_tickets;
      if (/(password|locked|sign in|log in|login)/.test(m)) {
        text = `Your password expires in ${p.it.password_expires_in_days} days. A reset needs a connection, but I can queue it now and it runs when you're back online.`;
        actions.push({ label: 'Reset my password', tool: 'reset_password', args: { system: 'sso' } });
      } else {
        text = t.length
          ? `Your open tickets: ${t.map((x) => `${x.ticket_id} - ${x.summary} (${x.status.replace(/_/g, ' ')})`).join('; ')}. You can open another offline; it's sent when you reconnect.`
          : "You're offline, but you can write up a ticket now - it's sent to the help desk when you reconnect.";
        actions.push({ label: 'Open a help desk ticket', screen: 'ticket', args: { summary: q.slice(0, 160) } });
      }
    }
  }
  if (!text && faq) text = faq.a;
  if (!text && ctx?.kb_playbook?.[0]) text = ctx.kb_playbook[0].answer ?? ctx.kb_playbook[0].content;
  if (!text) {
    text = "You're offline right now, so I can only answer from what's saved on your phone. Ask me again when you're connected - or open For You, which works offline.";
  }
  return {
    text,
    intent,
    area,
    actions,
    offline: true,
    context: { status: ctx || faq ? 'device' : 'none', latency_ms: 0 },
    sources: faq && text === faq.a ? [{ title: `${workplace ? 'Crew Handbook' : 'Park Guide'} (on device)`, snippet: faq.q, kind: 'couchbase-lite' }] : [],
  };
}
