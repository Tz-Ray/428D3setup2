<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { api } from './api.js'
import { draftStages, plannedRepetitions, vectorBudget } from './draftStages.js'
import TrialTranscript from './TrialTranscript.vue'
const props = defineProps({
  models: Array,
  inventoryError: String,
  plan: Object,
  revision: Number,
  dirty: Boolean,
})
const current = ref(null),
  transcript = ref(null),
  history = ref([]),
  chosen = ref(''),
  info = ref(null)
const source = ref('saved_sequence'),
  slot = ref(0),
  expected = ref(''),
  subject = ref('Local trial'),
  seed = ref(1000),
  controlRepetitions = ref(5),
  filingVector = ref('v1'),
  filingVariant = ref(1)
const working = ref(false),
  error = ref(''),
  pollError = ref(''),
  following = ref(true)
let timer,
  mounted = true,
  reading = 0
const model = computed(() =>
  props.models.find((m) => m.tag === props.plan.models[slot.value]),
)
const activeStatuses = ['queued', 'running', 'paused', 'waiting_for_controls']
const pending = computed(() => history.value.some(r => activeStatuses.includes(r.status)))
const activeQueue = computed(() => history.value.find(r => r.sequence_id && activeStatuses.includes(r.status)))
const finishing = computed(() => history.value.some(r => r.id && r.sequence_id === activeQueue.value?.sequence_id && r.status === 'running'))
const controlBusy = ref(false), controlError = ref('')
async function controlQueue(action) {
  const id = activeQueue.value?.sequence_id
  if (!id || controlBusy.value) return
  controlBusy.value = true
  controlError.value = ''
  try {
    await api('sequences/' + id + '/' + action, 'POST')
    await refresh()
  } catch (e) {
    controlError.value = e.message
  } finally {
    controlBusy.value = false
  }
}
const usingVariant = computed(() => source.value === 'variant')
function draftEmails(vector, draft) {
  return draftStages(vector, draft)
    .map(s => ({ label: s.label, subject: s.mail[s.subjectField], body: s.mail[s.bodyField] }))
    .filter(m => m.subject.trim() || m.body.trim())
}
const incomingDrafts = computed(() => draftEmails(filingVector.value, props.plan.vectors[filingVector.value].variations[filingVariant.value - 1]))
const sequenceMode = computed(() => ['saved_sequence', 'fruit_sequence'].includes(source.value))
const selectedRuns = computed(() => plannedRepetitions(
  props.plan.repetitions, props.plan.vectors[filingVector.value].count, filingVariant.value - 1))
const vectorRuns = computed(() => ['v1', 'v2', 'v3'].map(vector => {
  const group = props.plan.vectors[vector]
  const populated = group.variations.slice(0, group.count).some(draft => draftEmails(vector, draft).length)
  return { vector, count: populated ? vectorBudget(props.plan.repetitions, group.count) : 0 }
}))
const missingVector = computed(() => vectorRuns.value.find(group => !group.count)?.vector)
const savedRuns = computed(() => vectorRuns.value.reduce((total, group) => total + group.count, 0))
const launchCount = computed(() => {
  if (usingVariant.value && incomingDrafts.value.length) return selectedRuns.value
  if (source.value === 'saved_sequence') return savedRuns.value
})
const needsModel = computed(() => true)
const sequenceRows = computed(() => {
  if (!current.value?.sequence_id) return []
  return history.value.filter(r => r.sequence_id === current.value.sequence_id)
    .sort((a,b) => a.sequence_position - b.sequence_position)
})
const preset = computed(() => source.value)
const sample = computed(() => ['fruit', 'guess'].includes(preset.value))
const prompt = computed(
  () =>
    ({
      greeting: info.value?.system_prompt,
      fruit: info.value?.fruit_prompt,
      guess: info.value?.guess_prompt,
      saved: props.plan.system_prompt,
      variant: props.plan.system_prompt,
    })[preset.value],
)
const fixedValue = computed(() =>
  preset.value === 'guess' ? info.value?.guess_value : preset.value === 'fruit' ? '' : props.plan.fixed_value,
)
const subjectBodies = computed(() =>
  source.value === 'guess'
    ? info.value?.guess_emails
    : [source.value === 'fruit' ? info.value?.fruit_email : info.value?.body],
)
async function refresh() {
  const requested = ++reading
  try {
    const rows = await api('checks')
    if (!mounted || requested !== reading) return
    history.value = rows
    if (following.value && rows.length) {
      const active = rows.find(r => r.status === 'running') || rows.find(r => r.status === 'waiting_for_controls')
      const queued = rows.filter(r => ['queued', 'paused'].includes(r.status)).sort((a,b) => a.sequence_position - b.sequence_position)
      const latest = rows.reduce((a,b) => (a.ended || a.started) >= (b.ended || b.started) ? a : b)
      chosen.value = (active || queued[0] || latest).id
    }
    if (chosen.value) {
      const record = await api('checks/' + chosen.value)
      if (mounted && requested === reading) current.value = record
    }
    if (requested === reading) pollError.value = ''
  } catch (e) {
    if (mounted && requested === reading) pollError.value = e.message
  }
}
async function start() {
  working.value = true
  error.value = ''
  try {
    const result = sequenceMode.value
      ? await api('sequences', 'POST', {
          revision: props.revision, slot: slot.value, digest: model.value?.digest,
          seed: seed.value, source: source.value === 'fruit_sequence' ? 'fruit' : 'saved',
        })
      : await api('checks', 'POST', {
          revision: props.revision,
          slot: slot.value,
          digest: model.value.digest,
          prompt_source: usingVariant.value ? 'draft_control' : source.value,
          expected: sample.value || usingVariant.value ? '' : expected.value,
          seed: seed.value,
          control_repetitions: controlRepetitions.value,
          filing_vector: filingVector.value,
          filing_variant: filingVariant.value,
          subject: subject.value,
        })
    following.value = true
    chosen.value = result.id
    clearTimeout(timer)
    await poll()
    await nextTick()
    transcript.value?.$el.scrollIntoView({ block: 'start' })
  } catch (e) {
    error.value = e.message
  } finally {
    working.value = false
  }
}
async function poll() {
  const iteration = ++pollGeneration
  await refresh()
  if (mounted && iteration === pollGeneration) timer = setTimeout(poll, pending.value ? 400 : 2000)
}
let pollGeneration = 0
function openRecord(id) {
  following.value = false
  chosen.value = id
  refresh()
}
function follow() {
  following.value = true
  refresh()
}
function trialLabel(row) {
  return row.trial_label || ({ fruit: '0', guess: '0.1' })[row.preset]
}
function recordLabel(row) {
  if (row.preset === 'draft_delivery') return 'Mailbox delivery'
  if (row.preset === 'saved_replay') return row.repetition_total
    ? `Saved replay · Repetition ${row.repetition} of ${row.repetition_total}` : 'Saved variant replay'
  const trial = trialLabel(row)
  if (row.input_source === 'saved_variant') return 'Saved variant · Trial ' + trial
  if (row.input_source === 'fruit_sequence') return 'Fruit questions · Trial ' + trial
  return trial ? 'Trial ' + trial : 'Greeting check'
}
onMounted(async () => {
  try {
    info.value = await api('greeting')
    expected.value = info.value.expected
  } catch (e) {
    error.value = e.message
    return
  }
  await poll()
})
onUnmounted(() => {
  mounted = false
  clearTimeout(timer)
})
</script>
<template>
  <section v-if="activeQueue" class="panel" aria-label="Queue controls">
    <header><h2>Queue controls</h2></header>
    <div class="pad">
      <p role="status" v-if="activeQueue.queue_state === 'paused'">
        {{ finishing ? 'Pausing after the current repetition.' : 'Paused. Resume to run the next repetition.' }}
      </p>
      <p role="status" v-else-if="activeQueue.queue_state === 'stopped'">Stopping the current model request…</p>
      <div class="actions" v-if="activeQueue.queue_state !== 'stopped'">
        <button v-if="activeQueue.queue_state === 'paused'" :disabled="controlBusy" @click="controlQueue('resume')">Resume queue</button>
        <button v-else :disabled="controlBusy" @click="controlQueue('pause')">Pause after current repetition</button>
        <button :disabled="controlBusy" @click="controlQueue('stop')">Stop queue</button>
      </div>
    </div>
  </section>
  <p v-if="controlError" role="alert" class="alert">{{ controlError }}</p>
  <TrialTranscript ref="transcript" :record="current" :sequence="sequenceRows" :following="following" @open="openRecord" @follow="follow" />
  <p v-if="pollError" role="alert" class="alert">Transcript update failed. Retrying… {{ pollError }}</p>
  <section class="panel">
    <header>
      <h2>Start a local trial</h2>
    </header>
    <div class="pad" v-if="info">
      <label>Scenario<select v-model="source">
        <option value="saved_sequence">Full saved plan · V1 → V2 → V3</option>
        <option value="variant">Replay one saved variant</option>
        <option value="fruit_sequence">Fruit questions across V1–V3</option>
        <option value="greeting">Greeting check prompt</option>
        <option value="saved">Saved operator prompt · greeting email</option>
        <option value="fruit">Trial 0 · Greeting and fruit</option>
        <option value="guess">Trial 0.1 · Three fruit guesses</option>
      </select></label>
      <p v-if="source === 'saved_sequence'" class="intro">
        <template v-if="missingVector">Add an email to {{ missingVector.toUpperCase() }} to start the full plan.</template>
        <template v-else>
          <template v-for="(group, i) in vectorRuns" :key="group.vector">{{ i ? ' → ' : '' }}{{ group.vector.toUpperCase() }} ({{ group.count }} runs)</template>.
          Each vector finishes before the next starts.
        </template>
      </p>
      <p v-else-if="source === 'fruit_sequence'" class="intro">
        Runs the built-in plain greeting, formatted fruit card and two three-question threads in order.
      </p>
      <p v-else-if="usingVariant" class="intro">
        Llama reads the saved system prompt and fixed trial value, then the subject and body of each email. Each reply is delivered before the next V3 email arrives.
      </p>
      <template v-else>
        <p class="intro">
          <template v-if="sample"
            >Each incoming email waits for the preceding reply. The run ends after
            the last planned reply reaches the sender.</template
          >
          <template v-else
            >The mailbox delivers the model’s reply. You can compare it with expected text after delivery.</template
          >
        </p>
        <ol aria-label="Planned incoming mail">
          <li v-for="body in subjectBodies" :key="body">{{ body }}</li>
        </ol>
      </template>
      <label v-if="needsModel">Target model<select v-model="slot">
        <option v-for="(tag, i) in plan.models" :key="i" :value="i">{{ tag || 'Unassigned target' }}</option>
      </select></label>
      <div v-if="!sequenceMode" class="two">
        <label>{{ usingVariant ? 'Vector' : 'Log vector' }}<select :aria-label="usingVariant ? 'Vector' : 'Log vector'" v-model="filingVector" @change="filingVariant = 1">
          <option v-for="v in ['v1','v2','v3']" :key="v" :value="v">{{ v.toUpperCase() }}</option>
        </select></label>
        <label>{{ usingVariant ? 'Variant' : 'Log variant' }}<select :aria-label="usingVariant ? 'Variant' : 'Log variant'" v-model="filingVariant">
          <option v-for="n in plan.vectors[filingVector].count" :key="n" :value="n">Variant {{ n }}{{ plan.vectors[filingVector].variations[n-1].name ? ' · ' + plan.vectors[filingVector].variations[n-1].name : '' }}</option>
        </select></label>
      </div>
      <template v-if="usingVariant">
        <ol v-if="incomingDrafts.length" aria-label="Emails to deliver">
          <li v-for="mail in incomingDrafts" :key="mail.label">
            <details>
              <summary>{{ mail.label }} · {{ mail.subject || '(no subject)' }}</summary>
              <pre class="inline-code">{{ mail.body }}</pre>
            </details>
          </li>
        </ol>
        <p v-else class="hint">This variant has no email to send. Enter a subject or body in <a href="#drafts">Message drafts</a> and save the plan.</p>
      </template>
      <template v-if="!sequenceMode">
        <label v-if="!usingVariant">Trial email subject<input v-model="subject" maxlength="255" /></label>
        <pre class="inline-code">{{
          prompt || 'Enter a system prompt on the trial plan.'
        }}</pre>
        <template v-if="fixedValue">
          <h3>Fixed trial value</h3>
          <pre class="inline-code">{{ fixedValue }}</pre>
        </template>
        <label v-if="!sample && !usingVariant"
          >Expected reply (optional)<input v-model="expected" maxlength="512"
        /></label>
        <label v-if="!sample && !usingVariant">Repetitions per control
          <select v-model="controlRepetitions">
            <option :value="1">1 each</option>
            <option :value="5">5 each</option>
          </select>
          <small>Trial 0 checks for a greeting and a fruit. Trial 0.1 checks the three guesses. The primary trial starts after both pass.</small>
        </label>
      </template>
        <label v-if="needsModel"
          >Sampling seed<input
            type="number"
            min="0"
            max="2147483647"
            step="1"
            v-model.number="seed"
        /></label>
      <div class="actions">
        <button
          class="primary"
          @click="start"
          :disabled="
            working || dirty || pending || (usingVariant && !incomingDrafts.length) ||
            (source === 'saved_sequence' && (missingVector || !plan.system_prompt.trim())) ||
            (needsModel && (!model || (!sequenceMode && !prompt?.trim()) ||
              !Number.isInteger(seed) || seed < 0 || seed > 2147483647))
          "
        >
          <template v-if="pending">Trial in progress…</template>
          <template v-else-if="launchCount">Start {{ launchCount }} planned {{ launchCount === 1 ? 'run' : 'runs' }}</template>
          <template v-else>Start trial</template>
        </button>
        <span v-if="dirty">Save the plan first.</span
        ><span v-else-if="needsModel && inventoryError"
          >Ollama inventory is unavailable. Check the service and refresh the
          trial plan.</span
        ><span v-else-if="needsModel && !model"
          >Select an installed model in the trial plan.</span
        >
      </div>
    </div>
    <p v-if="error" role="alert" class="alert">{{ error }}</p>
  </section>
  <section class="panel">
    <header>
      <h2>Conversation logs</h2>
      <span class="flag">{{ history.length }} records</span>
    </header>
    <div class="pad">
      <p v-if="!history.length" class="hint">No trials recorded.</p>
      <label v-else
        >Recorded check<select v-model="chosen" @change="openRecord(chosen)">
          <option v-for="r in history" :key="r.id" :value="r.id">
            {{ r.filing_vector ? r.filing_vector.toUpperCase() + ' / variant ' + r.filing_variant + ' · ' : '' }}{{ recordLabel(r) }} · {{ new Date(r.started).toLocaleString() }} · {{ r.status }} ·
            {{ r.id.slice(0, 8) }}
          </option>
        </select></label
      >
      <template v-if="current">
        <div v-if="current.log_folder">
          <p>Local folder <code>mail-lab/d3-state/{{ current.log_folder }}</code></p>
          <p v-if="current.variant_metadata">{{ current.variant_metadata.vector_id.toUpperCase() }} · {{ current.variant_metadata.vector_name }} / Variant {{ current.variant_metadata.variant_number }} · {{ current.variant_metadata.variant_name || '(unnamed)' }}</p>
          <p class="actions" v-if="current.ended">
            <a :href="'/api/checks/' + current.id + '/files/conversation.txt'" target="_blank" rel="noopener">Open conversation</a>
            <a :href="'/api/checks/' + current.id + '/files/record.json'" target="_blank" rel="noopener">Open full JSON</a>
          </p>
          <p v-for="number in current.available_turns" :key="number">
            <a :href="'/api/checks/' + current.id + '/files/turn-' + String(number).padStart(2,'0') + '.json'" target="_blank" rel="noopener">Turn {{ number }} · mailbox and model record</a>
          </p>
        </div>
        <p v-if="current.trial_label" class="hint">Trial {{ current.trial_label }}
          <template v-if="current.parent_id"> · Repetition {{ current.repetition }} ·
            <button @click="openRecord(current.parent_id)">View primary trial</button>
          </template>
        </p>
        <ol v-if="current.controls" aria-label="Required control records">
          <li v-for="c in current.controls" :key="c.id">
            <button :disabled="c.status === 'pending'" @click="openRecord(c.id)">
              Trial {{ c.trial_label }} · Repetition {{ c.repetition }} · {{ c.status }}
            </button>
          </li>
        </ol>
        <details v-if="current.control_result">
          <summary>Control {{ current.control_result.passed ? 'passed' : 'did not pass' }}</summary>
          <pre class="inline-code">{{ JSON.stringify(current.control_result,null,2) }}</pre>
        </details>
        <div class="result-title">
          <h3>{{ current.model || 'Saved draft delivery' }}</h3>
          <strong :class="['status', current.status]">{{
            current.status
          }}</strong>
        </div>
        <p v-if="current.error" class="alert">{{ current.error }}</p>
        <section v-if="current.prompt_source === 'draft_delivery'" aria-label="Recipient inbox">
          <h3>Recipient inbox</h3>
          <div v-for="m in current.recipient_inbox" :key="m.id" class="inbox">
            <h4>{{ m.stage }} · {{ m.subject || '(no subject)' }}</h4>
            <small>#{{ m.id }} · {{ m.sender }} → {{ m.recipient }} · {{ m.delivered_at }} · {{ m.media_type }}</small>
            <pre>{{ m.body }}</pre>
          </div>
        </section>
        <template v-else>
          <details>
            <summary>Exact model input and build</summary>
            <dl>
              <dt>Model digest</dt>
              <dd>
                <code>{{ current.digest }}</code>
              </dd>
              <dt>Sampling temperature</dt>
              <dd>{{ current.options?.temperature ?? 'Unrecorded' }}</dd>
              <dt>Sampling seed</dt>
              <dd>{{ current.options?.seed ?? 'Unrecorded' }}</dd>
              <dt>Selected prompt SHA-256</dt>
              <dd>
                <code>{{ current.system_sha256 }}</code>
              </dd>
            </dl>
            <template v-if="current.turns?.length > 1">
              <details v-for="turn in current.turns" :key="turn.number">
                <summary>Turn {{ turn.number }} model input</summary>
                <pre class="inline-code">{{
                  JSON.stringify(turn.model_input, null, 2)
                }}</pre>
              </details>
            </template>
            <pre v-else class="inline-code">{{
              JSON.stringify(current.model_input || [], null, 2)
            }}</pre>
          </details>
          <ol class="events">
            <li v-for="(e, i) in current.events" :key="i">
              <div>
                <b>{{ e.action.replaceAll('_', ' ') }}</b
                ><small
                  ><template v-if="e.turn">Turn {{ e.turn }} · </template>Message
                  {{ e.message_id }} · {{ e.time }}</small
                >
              </div>
              <pre>{{
                e.message?.body ?? e.model_output?.content ?? e.body ?? e.reason
              }}</pre>
            </li>
          </ol>
          <h3>Sender inbox</h3>
          <p v-if="!current.sender_inbox.length" class="hint">
            No verified delivery.
          </p>
          <div v-for="m in current.sender_inbox" :key="m.id" class="inbox">
            <small
              >{{ m.sender }} → {{ m.recipient }} · #{{ m.id }} replying to #{{
                m.parent
              }}</small
            >
            <pre>{{ m.body }}</pre>
          </div>
        </template>
        <details>
          <summary>Full check record</summary>
          <pre class="inline-code">{{ JSON.stringify(current, null, 2) }}</pre>
        </details>
      </template>
    </div>
  </section>
</template>
