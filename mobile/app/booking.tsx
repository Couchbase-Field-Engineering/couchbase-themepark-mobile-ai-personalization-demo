import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useData } from '@/src/data/DataContext';
import { theme } from '@/src/theme';
import { Button, Card, Empty, fmtDate, money, Pill, SectionTitle } from '@/src/ui/components';
import { ChoiceRow } from '@/src/ui/Choice';
import { addDays, short } from '@/src/ui/dates';
import { form, OFFLINE_NOTE } from '@/src/ui/form';
import { RequestTracker } from '@/src/ui/RequestTracker';

const STEPS = ['Booked', 'Confirmed', 'Checked in'];
const MOVABLE = ['express pass', 'dining', 'show'];

/** One booking - an express pass, a table, a show seat - straight from the profile document in Couchbase Lite. */
export default function BookingScreen() {
  const params = useLocalSearchParams<{ booking_id?: string; reschedule?: string }>();
  const { snap, request } = useData();
  const p = snap.profile;
  const bookings = p?.bookings ?? [];
  const o = bookings.find((x) => x.booking_id === params.booking_id) ?? bookings.find((x) => x.status === 'upcoming') ?? bookings[0];
  const [day, setDay] = useState<string | undefined>(o?.date ?? undefined);
  const [win, setWin] = useState<string | undefined>(o?.time_window ?? undefined);
  const [reqId, setReqId] = useState<string | null>(null);
  if (!p || !o) return <Empty icon="ticket-outline" title="No bookings" body="Express passes, dining and shows you book appear here." />;

  const today = p.export_date;
  const at = o.status === 'completed' ? 2 : 1;
  const canMove = o.status === 'upcoming' && MOVABLE.includes(o.kind) && !!o.date && o.date >= today;
  const last = p.visit?.end && p.visit.end > (o.date ?? today) ? p.visit.end : o.date ?? today;
  const days: string[] = [];
  for (let d = today; canMove && d <= last && days.length < 8; d = addDays(d, 1)) days.push(d);
  const moved = !!day && !!win && (day !== o.date || win !== o.time_window);

  // Who in the party is too short for this ride? (heights come with the visit, on the profile)
  const exp = snap.catalog?.experiences.find((e) => e.exp_id === o.items[0]?.exp_id);
  const short_ = exp?.min_height_in ? (p.visit?.party ?? []).find((m) => m.height_in != null && m.height_in < exp.min_height_in) : undefined;
  const land = snap.catalog?.lands.find((l) => l.id === exp?.land);

  const submit = async () => {
    if (!day || !moved) return;
    const req = await request('reschedule_booking', { booking_id: o.booking_id, date: day, window: win ?? o.time_window ?? '' }, `Move ${o.items[0]?.name} to ${short(day)}, ${win}`);
    setReqId(req._id);
  };

  return (
    <ScrollView contentContainerStyle={form.body}>
      <Card style={{ padding: 16, gap: 6 }}>
        <View style={form.rowBetween}>
          <Text style={form.meta}>{o.kind.toUpperCase()} · {o.booking_id}</Text>
          <Pill label={o.status} tone={o.status === 'completed' ? 'ok' : o.status === 'cancelled' ? 'neutral' : 'orange'} />
        </View>
        <Text style={form.h2}>{o.items[0]?.name}</Text>
        <Text style={form.h3}>
          {o.status === 'cancelled' ? 'Cancelled' : `${o.date === today ? 'Today' : fmtDate(o.date, { weekday: 'long', month: 'long', day: 'numeric' })}${o.time_window ? ` · ${o.time_window}` : ' · all day'}`}
        </Text>
        <Text style={form.meta}>
          {land ? `${land.name} · ` : ''}party of {o.party_size ?? p.visit?.party.length ?? 1}{o.confirmation ? ` · confirmation ${o.confirmation}` : ''}
        </Text>
        {o.status !== 'cancelled' ? (
          <View style={styles.track}>
            {STEPS.map((s, i) => (
              <View key={s} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
                <View style={[styles.node, i <= at && { backgroundColor: theme.color.red, borderColor: theme.color.red }]}>
                  {i <= at ? <Ionicons name="checkmark" size={12} color={theme.color.onDark} /> : null}
                </View>
                <Text style={[styles.nodeText, i <= at && { color: theme.color.ink, fontWeight: '700' }]}>{s}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </Card>

      {short_ && exp && o.status === 'upcoming' ? (
        <Card style={{ padding: 16, gap: 8, borderColor: theme.color.red, borderWidth: 1 }}>
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <Ionicons name="alert-circle" size={18} color={theme.color.red} />
            <Text style={[form.h3, { flex: 1 }]}>{short_.name} is {short_.height_in}" - {exp.name} needs {exp.min_height_in}"</Text>
          </View>
          <Text style={form.meta}>Swap it for a ride the whole party can go on, or use rider swap at the entrance so the adults take turns.</Text>
          <View style={{ alignItems: 'flex-start' }}>
            <Button small label="Swap for another ride" icon="swap-horizontal" onPress={() => router.push({ pathname: '/change', params: { booking_id: o.booking_id, exp_id: o.items[0].exp_id, resolution: 'swap' } })} />
          </View>
        </Card>
      ) : null}

      <SectionTitle title="What's booked" />
      <Card style={{ padding: 16, gap: 8 }}>
        {o.items.map((i) => (
          <View key={i.exp_id} style={form.rowBetween}>
            <Text style={{ fontWeight: '700', color: theme.color.text, flex: 1 }}>{i.name}</Text>
            <Text style={form.meta}>{money(i.price)}</Text>
          </View>
        ))}
        {exp ? <Text style={form.meta}>{exp.blurb}{exp.typical_wait_min ? ` Standby wait is usually about ${exp.typical_wait_min} minutes.` : ''}</Text> : null}
        <View style={[form.rowBetween, { borderTopWidth: 1, borderTopColor: theme.color.border, paddingTop: 8 }]}>
          <Text style={form.meta}>Total{o.offer_code ? ` · ${o.offer_code} applied` : ''}</Text>
          <Text style={{ fontWeight: '700', color: theme.color.text }}>{money(o.total_usd)}</Text>
        </View>
        {o.status === 'upcoming' ? (
          <View style={{ alignItems: 'flex-start', marginTop: 4 }}>
            <Button small kind="ghost" label="Swap or refund" icon="swap-horizontal" onPress={() => router.push({ pathname: '/change', params: { booking_id: o.booking_id } })} />
          </View>
        ) : null}
      </Card>

      <SectionTitle title="History" />
      <Card style={{ padding: 16, gap: 10 }}>
        {[...o.events].reverse().map((e, i) => (
          <View key={i} style={{ flexDirection: 'row', gap: 10 }}>
            <Ionicons name={i === 0 ? 'radio-button-on' : 'ellipse-outline'} size={14} color={i === 0 ? theme.color.red : theme.color.faint} style={{ marginTop: 3 }} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: theme.color.text, fontWeight: i === 0 ? '700' : '400' }}>{e.text}</Text>
              <Text style={form.meta}>{fmtDate(e.at)}</Text>
            </View>
          </View>
        ))}
      </Card>

      {reqId ? <RequestTracker id={reqId} onRetry={() => setReqId(null)} /> : canMove ? (
        <>
          <SectionTitle title={params.reschedule ? 'Pick a new time' : 'Need a different time?'} />
          <ChoiceRow options={days.map((d) => ({ value: d, label: d === today ? 'Today' : short(d) }))} value={day} onChange={setDay} />
          <View style={{ height: 8 }} />
          <ChoiceRow options={(snap.catalog?.time_windows ?? ['11:00am-12:00pm', '3:00pm-4:00pm', '7:30pm-8:30pm']).map((w) => ({ value: w, label: w }))} value={win} onChange={setWin} />
          <View style={{ marginTop: 14 }}>
            <Button label={moved ? `Move to ${day === today ? 'today' : short(day!)}, ${win}` : 'Choose a new time'} icon="calendar" disabled={!moved} onPress={() => void submit()} />
          </View>
          <Text style={form.tiny}>{OFFLINE_NOTE}</Text>
        </>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  track: { flexDirection: 'row', marginTop: 14 },
  node: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: theme.color.border, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.color.surface },
  nodeText: { fontSize: 10, color: theme.color.faint, textAlign: 'center' },
});
