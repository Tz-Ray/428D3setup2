<script setup>
import { computed } from 'vue'

const props = defineProps({ record: Object, sequence: Array, following: Boolean })
const emit = defineEmits(['open', 'follow'])
const r = computed(() => props.record)
const turns = computed(() => {
  const events = r.value.events || []
  const numbers = new Set([...(r.value.turns || []).map(t => t.number), ...events.map(e => e.turn || 1)])
  return Array.from(numbers).sort((a, b) => b - a).map(number => {
    const turn = r.value.turns?.find(t => t.number === number) || {}
    const logs = events.filter(e => (e.turn || 1) === number)
    const incoming = logs.find(e => e.action === 'read')?.message
    const delivered = logs.find(e => e.action === 'send')
    const blocked = logs.find(e => e.action === 'delivery_blocked')
    const draft = turn.model_output?.content ?? logs.find(e => e.action === 'draft')?.model_output?.content
    const phase = turn.phase || (delivered ? 'delivered' : blocked ? 'rejected' : draft ? 'checking_delivery' : 'reading')
    return { number, incoming, reply: delivered?.body ?? draft ?? turn.partial_reply, phase, error: turn.error || blocked?.reason }
  })
})
const phases = {
  reading: 'Reading incoming email', awaiting_model: 'Waiting for the model’s first token',
  generating: 'Generating reply', checking_delivery: 'Delivering reply', delivered: 'Reply delivered',
  no_reply: 'Model returned an empty reply', rejected: 'Reply rejected', failed: 'Turn failed',
}
const status = computed(() => {
  if (r.value.status === 'interrupted') return 'Run interrupted'
  if (r.value.status === 'paused') return 'Queue paused'
  if (r.value.status === 'stopped') return 'Stopped by operator'
  if (r.value.status === 'failed') return 'Run failed'
  if (r.value.status === 'skipped') return 'Run skipped'
  if (r.value.status === 'queued') return 'Queued'
  if (r.value.status === 'waiting_for_controls') return 'Waiting for preparation checks'
  if (r.value.prompt_source === 'draft_delivery') return 'Mailbox delivery only · no model called'
  if (turns.value.length) return phases[turns.value[0].phase]
  return r.value.ended ? r.value.status : 'Checking local model'
})
</script>
<template>
  <section class="panel transcript" aria-label="Trial transcript">
    <header>
      <h2>{{ following ? 'Live transcript' : 'Recorded transcript' }}</h2>
      <button v-if="!following" @click="emit('follow')">Follow live trial</button>
    </header>
    <div class="pad">
      <p v-if="!r" class="hint">The transcript will appear when a trial starts.</p>
      <template v-else>
        <p v-if="r.sequence_id">Run {{ r.sequence_position }} of {{ r.sequence_total }} in sequence</p>
        <p>
          <strong v-if="r.filing_vector">{{ r.filing_vector.toUpperCase() }} · Variant {{ r.filing_variant }}</strong>
          {{ r.variant_metadata?.variant_name }}
          <span v-if="r.trial_label"> · Trial {{ r.trial_label }}</span>
          <span v-if="r.repetition"> · Repetition {{ r.repetition }}<template v-if="r.repetition_total"> of {{ r.repetition_total }}</template></span>
        </p>
        <p v-if="r.model" class="hint">{{ r.model }}</p>
        <p role="status" class="transcript-status">
          <strong>{{ status }}</strong>
          <template v-if="turns.length"> · Turn {{ turns[0].number }} of {{ r.planned_messages?.length || turns.length }}</template>
        </p>
        <p v-if="r.error" class="alert">{{ r.error }}</p>
        <p v-if="r.reply_matches_expected === false">The delivered reply differed from the expected text.</p>
        <p v-if="r.control_result">Control score · {{ r.control_result.passed ? 'Passed' : 'Did not pass' }}</p>
        <article v-for="t in turns" :key="t.number" class="transcript-turn">
          <h3>Turn {{ t.number }} · {{ t.incoming?.subject || '(no subject)' }}</h3>
          <template v-if="t.incoming"><small>Sender</small><pre>{{ t.incoming.body }}</pre></template>
          <small>{{ t.phase === 'delivered' ? 'Delivered reply' : 'Model draft' }}</small>
          <pre v-if="t.reply">{{ t.reply }}</pre>
          <p v-else class="hint">{{ phases[t.phase] }}</p>
          <p v-if="t.error" class="alert">{{ t.error }}</p>
        </article>
        <article v-for="m in r.recipient_inbox" :key="m.id" class="transcript-turn">
          <h3>{{ m.stage }} · {{ m.subject || '(no subject)' }}</h3><pre>{{ m.body }}</pre>
        </article>
        <details v-if="sequence.length">
          <summary>Sequence progress</summary>
          <ol><li v-for="row in sequence" :key="row.id">
            <button @click="emit('open', row.id)">{{ row.filing_vector.toUpperCase() }} · Variant {{ row.filing_variant }}
              <template v-if="row.repetition_total"> · Repetition {{ row.repetition }} of {{ row.repetition_total }}</template> · {{ row.status }}</button>
          </li></ol>
        </details>
      </template>
    </div>
  </section>
</template>
