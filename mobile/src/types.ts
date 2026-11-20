/** Document shapes replicated from Couchbase (scope `pk`) into Couchbase Lite. */

export type Audience = 'guest' | 'lead' | 'employee';
export type Area = 'support' | 'commerce' | 'sales' | 'workplace';

export type BookingItem = { exp_id: string; name: string; qty: number; price: number };

/** An express pass, a dining reservation, a show seat or an add-on. */
export type Booking = {
  booking_id: string;
  booked_at: string;
  status: 'upcoming' | 'completed' | 'cancelled';
  kind: 'express pass' | 'dining' | 'show' | 'tour' | 'add-on' | string;
  items: BookingItem[];
  subtotal_usd: number;
  discount_usd?: number;
  offer_code?: string | null;
  total_usd: number;
  party_size?: number;
  confirmation: string | null;
  date: string | null;
  time_window: string | null;
  completed_at: string | null;
  events: { at: string; text: string }[];
};

export type ChangeRecord = {
  change_id: string; booking_id: string; exp_id: string; name: string; reason: string; resolution: 'refund' | 'swap';
  status: string; created_at: string; refund_usd?: number; swap_name?: string;
};

export type PartyMember = { name: string; age: number; height_in: number | null };
export type Visit = { start: string; end: string; ticket: string; hotel: string | null; reservation_name?: string; party: PartyMember[] };
export type Shift = { date: string; start: string; end: string; location: string; role: string };

export type OnboardingTask = {
  task_id: string; title: string; kind: 'form' | 'sign' | 'training'; due_date: string; status: 'pending' | 'complete'; completed_at: string | null;
};

export type Ticket = { ticket_id: string; category: string; summary: string; status: string; priority: string; opened_at: string; queue?: string };

export type Profile = {
  type: 'profile';
  user_id: string;
  audience: Audience;
  group_code: string;
  account_id: string;
  export_date: string;
  rev: number;
  first_name: string;
  last_name: string;
  email: string | null;
  phone?: string | null;
  home_city: string;
  region: string;
  preferences: { interests: string[]; communication_channel: string; favorite_land: string | null };
  segments?: { id: string; name: string; status?: string }[];
  ml_scores: Record<string, number | string | string[] | null> & { model_version: string; segment: string; next_best_action: string };
  identity?: Record<string, string>;
  // guests
  loyalty?: { program: string; tier: string; points: number; member_since: string };
  visit?: Visit;
  bookings?: Booking[];
  cart?: { updated_at: string; items: BookingItem[]; subtotal_usd: number; abandoned_days: number; offer: { code: string; pct_off: number; expires: string } | null } | null;
  changes?: ChangeRecord[];
  credits?: { credit_id: string; amount_usd: number; reason: string; issued_at: string }[];
  history?: { lifetime_value_usd: number; bookings_count: number; avg_booking_usd: number; changes_count: number };
  // trip planners
  organization?: { name: string; group_type: string; members: number; size_band: string; city: string };
  lead?: { source: string; status: string; score: number; party_size: number | null; budget_band: string | null; timeline: string | null; interest: string[]; owner: string | null; role: string };
  planning_session?: { date: string; time: string; topic: string; channel: string; advisor: string } | null;
  // crew members
  employment?: { title: string; department: string; manager: string; location: string; start_date: string; tenure_days: number; employment_type: string };
  it?: {
    devices: { asset_tag: string; type: string; model: string; os: string }[];
    systems_access: string[];
    open_tickets: Ticket[];
    password_expires_in_days: number;
    mfa_enrolled: boolean;
  };
  hr?: {
    benefits: { enrolled: boolean; medical: string | null; dental: string | null; vision: string | null; k401_pct: number; enrollment_deadline: string | null };
    pto: { balance_days: number; used_days: number; accrual_per_month?: number; requests: { start_date: string; end_date: string; days: number; status: string }[] };
    pay: { frequency: string; next_pay_date: string };
    schedule?: { next_shift: Shift | null; shifts_this_week: number };
  };
  onboarding?: { status: 'in_progress' | 'complete'; tasks: OnboardingTask[] };
};

export type Cta = { label: string; screen?: string; tool?: string; ask?: string; args?: Record<string, unknown> };

export type ChangeOption = {
  booking_id: string; exp_id: string; name: string; price: number; date: string; time_window: string | null; days_left: number; cutoff_days: number;
  swap_options: { exp_id: string; name: string; price: number; places_left: number }[];
};

export type SlotDay = { date: string; slots: { time: string; open: number }[] };

export type FeedCard = {
  card_id: string;
  kind: 'booking' | 'change' | 'cart' | 'experience' | 'planning' | 'lead' | 'onboarding' | 'benefits' | 'ticket' | 'it' | 'timeoff' | 'reward' | 'shift';
  palette: string;
  area: Area;
  title: string;
  subtitle: string;
  reason: string;
  badge: string;
  score: number;
  rank: number;
  cta: Cta;
  options?: ChangeOption[];   // change card: everything the Change screen needs, so it works offline
  reasons?: string[];
  slots?: SlotDay[];          // planning card: open slots for the Planning session screen
  topics?: string[];
  channels?: string[];
};

export type FeedDoc = {
  type: 'feed';
  audience: Audience;
  cards: FeedCard[];
  model_version: string;
  segment: string;
  export_date: string;
  generated_at: string;
};

export type ActivityItem = {
  item_id: string;
  kind: string;
  title: string;
  status: string;
  date?: string;
  time?: string;
  charge_usd?: number;
  amount_usd?: number;
  refund_usd?: number;
  swap_name?: string;
  created_at: string;
};

export type RequestStatus = 'pending' | 'processing' | 'awaiting_approval' | 'confirmed' | 'accepted' | 'submitted' | 'failed';

export type ActionRequest = {
  _id: string;
  type: 'request';
  user_id: string;
  tool: string;
  args: Record<string, unknown>;
  title: string;
  status: RequestStatus;
  created_at: string;
  summary?: string;
  charge_usd?: number;
  governed?: boolean;
  trace_id?: string | null;
  /** Couchbase Labs Agent Operations Manager agent identity that ran it: the assistant, or the Changes Agent for swaps, refunds and credits. */
  agent?: 'parkchat-assistant' | 'parkchat-changes-agent' | string;
  memories_recalled?: number;
  remembered?: boolean;
  approval_id?: string | null;
  completed_at?: string | null;
  _local?: boolean; // created on this device, not yet acknowledged by the server
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  at: string;
  intent?: string;
  area?: Area;
  actions?: Cta[];
  restricted?: boolean;
  context?: {
    status: string | null; latency_ms: number; kb_mode?: string; build_ms?: number; rag_app?: string; knowledge?: string; source?: string;
    // the system-of-record round trip (ticketing/CDP, CRM or HRIS) made while building this context
    sor?: { system: string; label: string; mode: string; latency_ms: number; segments: string[] } | null;
  };
  llm?: { status: string; namespace?: string | null; similarity?: number | null; latency_ms?: number | null; stub?: boolean; composed_locally?: boolean };
  sources?: { title: string; snippet: string; kind: string }[];
  offline?: boolean;
  pending?: boolean;
};

export type ChatDoc = { type: 'chat'; messages: ChatMessage[]; answers: Record<string, { reply: string; intent: string; area?: Area; at: string }> };

export type ContextDoc = {
  type: 'context_cache';
  intent: string;
  area: Area;
  personal: boolean;
  export_date: string;
  built_at: string;
  build_ms: number;
  kb_mode: string;
  kb_profile: { title: string; content: string }[];
  kb_playbook: { title: string; content: string; answer?: string }[];
  facts: { tool?: string; data?: any };
};

export type Faq = { q: string; a: string; keywords: string[]; section?: string; intent?: string };

export type Experience = {
  exp_id: string; name: string; category: string; land: string; price: number; min_height_in: number; typical_wait_min: number;
  tags: string[]; family: string; blurb: string;
};

/** `catalog::v1` - on the `catalog` channel, so every signed-in phone has it. */
export type Catalog = {
  type: 'catalog';
  export_date: string;
  park: { name: string; support_phone: string; support_hours: string; business_brand: string; loyalty_program: string; park_hours: string };
  lands: { id: string; name: string; city: string; hours: string }[];
  experiences: Experience[];
  packages: { code: string; name: string; party_size: number[]; price_per_guest: number; includes: string[]; blurb: string }[];
  time_windows: string[];
  change_reasons: string[];
  change_cutoff_days: Record<string, number>;
  planning_topics: string[];
  planning_times: string[];
  planning_channels: string[];
  budget_bands: string[];
  timelines: string[];
  faq: Faq[];
};

/** `handbook::v1` - on the `employees` channel: only a crew member's phone ever receives it. */
export type Handbook = {
  type: 'handbook';
  export_date: string;
  it_categories: { id: string; name: string; queue: string; sla_hours: number }[];
  it_priorities: string[];
  systems: { id: string; name: string; approval: boolean; default: boolean }[];
  benefit_plans: Record<'medical' | 'dental' | 'vision', { id: string; name: string; employee_cost_per_paycheck: number; deductible?: number; blurb: string }[]>;
  onboarding_tasks: { task_id: string; title: string; kind: string; due_day: number; detail: string }[];
  k401_match_pct: number;
  faq: Faq[];
};

export type SyncState = {
  engine: 'couchbase-lite' | 'preview';
  status: 'connecting' | 'connected' | 'idle' | 'busy' | 'offline' | 'paused' | 'error' | 'stopped';
  lastSyncAt: number | null;
  pendingPush: number;
  detail?: string;
  endpoint?: string;
};
