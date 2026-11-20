import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useData } from '@/src/data/DataContext';
import { theme } from '@/src/theme';
import type { ChangeOption } from '@/src/types';
import { Button, Card, Empty, fmtDate, money, Pill, SectionTitle } from '@/src/ui/components';
import { ChoiceRow } from '@/src/ui/Choice';
import { form, OFFLINE_NOTE } from '@/src/ui/form';
import { RequestTracker } from '@/src/ui/RequestTracker';

/**
 * Swaps and refunds. The options come from the For You feed's change card
 * (or the cached change context), so the whole flow works offline - useful in
 * a queue with one bar of signal. Confirm
 * creates a `change_booking` request, which the Changes Agent runs through Couchbase Labs Agent Operations Manager.
 */
export default function ChangeScreen() {
  const params = useLocalSearchParams<{ booking_id?: string; exp_id?: string; resolution?: string; swap_exp_id?: string }>();
  const { snap, request } = useData();
  const card = snap.feed?.cards.find((c) => c.kind === 'change');
  const fromCtx = ((snap.contexts.change?.facts?.data?.items ?? []) as (ChangeOption & { eligible: boolean })[]).filter((i) => i.eligible);
  const all: ChangeOption[] = card?.options ?? fromCtx;
  const options = params.booking_id && !params.exp_id ? all.filter((o) => o.booking_id === params.booking_id) : all;
  const initial = options.find((o) => o.exp_id === params.exp_id && (!params.booking_id || o.booking_id === params.booking_id)) ?? (options.length === 1 ? options[0] : undefined);
  const [key, setKey] = useState(initial ? `${initial.booking_id}/${initial.exp_id}` : undefined);
  const sel = options.find((o) => `${o.booking_id}/${o.exp_id}` === key);
  const [reason, setReason] = useState<string | undefined>();
  const [mode, setMode] = useState<'refund' | 'swap'>(params.resolution === 'swap' ? 'swap' : 'refund');
  const [ex, setEx] = useState<string | undefined>(params.swap_exp_id);
  const [reqId, setReqId] = useState<string | null>(null);
  const reasons = card?.reasons ?? snap.catalog?.change_reasons ?? ['Change of plans', "Someone isn't tall enough", 'Weather'];

  if (!snap.profile) return null;
  const smallest = (snap.profile.visit?.party ?? []).filter((m) => m.height_in != null).sort((a, b) => a.height_in! - b.height_in!)[0];
  if (!options.length) return <Empty icon="swap-horizontal-outline" title="Nothing to change" body="Upcoming bookings appear here until their change cut-off: the day before your visit, or the day itself for Gold and Platinum members." />;
  const exSel = sel?.swap_options.find((x) => x.exp_id === ex);
  const ready = !!sel && !!reason && (mode === 'refund' || !!exSel);

  const submit = async () => {
    if (!sel || !reason) return;
    const args: Record<string, unknown> = { booking_id: sel.booking_id, exp_id: sel.exp_id, reason, resolution: mode };
    if (mode === 'swap' && exSel) args.swap_exp_id = exSel.exp_id;
    const req = await request('change_booking', args, mode === 'swap' ? `Swap ${sel.name} for ${exSel?.name}` : `Refund ${sel.name} · ${money(sel.price)} back`);
    setReqId(req._id);
  };

  return (
    <ScrollView contentContainerStyle={form.body}>
      {reqId ? <RequestTracker id={reqId} onRetry={() => setReqId(null)} /> : (
        <>
          <SectionTitle title="Which booking?" />
          {options.map((o) => {
            const k = `${o.booking_id}/${o.exp_id}`;
            return (
              <Pressable key={k} onPress={() => { setKey(k); setEx(undefined); }}>
                <Card style={[form.opt, key === k && form.optSel]}>
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text style={form.h3}>{o.name}</Text>
                    <Text style={form.meta}>{o.booking_id} · {fmtDate(o.date)}{o.time_window ? ` · ${o.time_window}` : ''} · {money(o.price)}</Text>
                    <Pill label={o.days_left <= 0 ? 'Last day to change' : `${o.days_left} day${o.days_left === 1 ? '' : 's'} left to change`} tone={o.days_left <= 0 ? 'red' : 'ok'} icon="time-outline" />
                  </View>
                  <Ionicons name={key === k ? 'radio-button-on' : 'radio-button-off'} size={22} color={theme.color.ink} />
                </Card>
              </Pressable>
            );
          })}

          {sel ? (
            <>
              <SectionTitle title="Why?" />
              <ChoiceRow options={reasons.map((r) => ({ value: r, label: r }))} value={reason} onChange={setReason} />

              <View style={form.seg}>
                {(['refund', 'swap'] as const).map((m) => (
                  <Pressable key={m} onPress={() => setMode(m)} style={[form.segBtn, mode === m && form.segOn]}>
                    <Text style={[form.segText, mode === m && { color: theme.color.onDark }]}>{m === 'refund' ? `Refund ${money(sel.price)}` : 'Swap'}</Text>
                  </Pressable>
                ))}
              </View>

              {mode === 'swap' ? (
                sel.swap_options.map((x) => {
                  const need = snap.catalog?.experiences.find((e) => e.exp_id === x.exp_id)?.min_height_in ?? 0;
                  const tooShort = need > 0 && smallest != null && smallest.height_in! < need;
                  const off = x.places_left <= 0 || tooShort;
                  return (
                    <Pressable key={x.exp_id} onPress={() => setEx(x.exp_id)} disabled={off}>
                      <Card style={[form.opt, ex === x.exp_id && form.optSel, off && { opacity: 0.45 }]}>
                        <View style={{ flex: 1, gap: 4 }}>
                          <Text style={{ fontWeight: '700', color: theme.color.text }}>{x.name}</Text>
                          <Text style={form.meta}>
                            {tooShort ? `Needs ${need}" - ${smallest!.name} is ${smallest!.height_in}"` : need > 0 && smallest ? `${smallest.name} is tall enough (${need}") · ` : ''}
                            {tooShort ? '' : x.price === sel.price ? 'Even swap' : x.price > sel.price ? `${money(x.price - sel.price)} more` : `${money(sel.price - x.price)} back to your card`}
                          </Text>
                        </View>
                        <Pill label={x.places_left > 0 ? (x.places_left <= 3 ? `Only ${x.places_left} left` : 'Places open') : 'Full'} tone={x.places_left <= 3 ? 'warn' : 'neutral'} />
                      </Card>
                    </Pressable>
                  );
                })
              ) : (
                <Card style={{ padding: 16, gap: 6 }}>
                  <Text style={form.meta}>The booking is cancelled and {money(sel.price)} goes back to your card within 3 business days. The place is released for another party.</Text>
                </Card>
              )}

              <View style={{ marginTop: 14 }}>
                <Button label={mode === 'swap' ? 'Confirm swap' : 'Confirm refund'} icon="checkmark" disabled={!ready} onPress={() => void submit()} />
              </View>
              <Text style={form.tiny}>Confirm hands this to the Changes Agent through Couchbase Labs Agent Operations Manager. {OFFLINE_NOTE}</Text>
            </>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}
