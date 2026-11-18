<script setup>
import { computed, ref, watch } from 'vue'
import Reader from './Reader.vue'
import { draftStages, plannedRepetitions } from './draftStages.js'

const props = defineProps({ vectors: Object, repetitions: Number, initialSelection: Object })
const emit = defineEmits(['download-variation'])
const catalog = [
  ['v1', 'Plaintext body'],
  ['v2', 'Hidden markup'],
  ['v3', 'Earlier and later messages'],
]
const key = ref(props.initialSelection?.vector || 'v1')
const index = ref(Math.min(props.initialSelection?.number || 1, props.vectors[key.value].count) - 1)
const selectedKey = ref('first')
const group = computed(() => props.vectors[key.value])
const variation = computed(() => group.value.variations[index.value])
const stages = computed(() => draftStages(key.value, variation.value))
const selected = computed(
  () => stages.value.find((s) => s.id === selectedKey.value) || stages.value[0],
)
const source = computed(() => selected.value.mail[selected.value.bodyField])
watch(
  variation,
  () => {
    selectedKey.value = 'first'
  },
  { flush: 'sync' },
)
function addMail(prior) {
  const list = prior
    ? variation.value.prior_emails
    : variation.value.additional_followups
  list.push({ subject: '', body: '' })
  selectedKey.value = (prior ? 'prior-' : 'follow-') + (list.length - 1)
}
function removeMail() {
  const v = variation.value
  const list = selected.value.reply ? v.additional_followups : v.prior_emails
  const mail = selected.value.mail
  const position = list.indexOf(mail)
  if (position < 0) return
  if (
    (mail.subject || mail.body) &&
    !window.confirm('Remove this draft email from the plan?')
  )
    return
  selectedKey.value = 'first'
  list.splice(position, 1)
}
const bytes = computed(() => new TextEncoder().encode(source.value).length)
function selectVector(vector) {
  key.value = vector
  index.value = 0
  selectedKey.value = 'first'
}
function setCount(count) {
  group.value.count = Number(count)
  index.value = Math.min(index.value, group.value.count - 1)
}
</script>
<template>
  <div class="vector-nav" aria-label="Choose vector">
    <button
      v-for="[id, title] in catalog"
      :key="id"
      :aria-pressed="key === id"
      @click="selectVector(id)"
    >
      <small>{{ id.toUpperCase() }}</small
      >{{ title }}
    </button>
  </div>
  <section class="panel">
    <header>
      <h2>{{ catalog.find((v) => v[0] === key)[1] }}</h2>
      <label class="inline"
        >Variations
        <select :value="group.count" @change="setCount($event.target.value)">
          <option :value="4">4</option>
          <option :value="5">5</option>
        </select>
      </label>
    </header>
    <div class="pad">
      <div class="chips" aria-label="Choose variation">
        <button
          v-for="n in group.count"
          :key="n"
          :aria-pressed="index === n - 1"
          @click="index = n - 1"
        >
          Variation {{ n }}
        </button>
      </div>
      <button class="variation-download" @click="emit('download-variation', key, index + 1)">
        Download variation JSON
      </button>
      <label
        >Variation name<input v-model="variation.name" maxlength="255"
      /></label>
      <section v-if="key === 'v3'" class="thread-plan">
        <h3>Planned thread</h3>
        <ol aria-label="Planned thread">
          <li v-for="(stage, i) in stages" :key="stage.id">
            <button
              :aria-pressed="stage.id === selected.id"
              @click="selectedKey = stage.id"
            >
              {{ stage.label }}
            </button>
            <small v-if="stage.reply">{{
              i === stages.length - 1
                ? 'Planned reply · end of thread'
                : 'Planned reply'
            }}</small>
          </li>
        </ol>
        <div class="chips">
          <button @click="addMail(true)">Add prior email</button>
          <button @click="addMail(false)">Add follow-up</button>
          <button
            v-if="selected.id !== 'first' && selected.id !== 'later'"
            @click="removeMail"
          >
            Remove selected email
          </button>
        </div>
      </section>
      <label
        >Subject<input v-model="selected.mail[selected.subjectField]" maxlength="255"
      /></label>
      <div class="edit-grid">
        <label
          >{{ key === 'v2' ? 'HTML source' : 'Plaintext source' }}
          <textarea
            v-model="selected.mail[selected.bodyField]"
            maxlength="16000"
            rows="10"
            spellcheck="false"
          ></textarea>
          <small>{{ bytes }} UTF-8 bytes</small>
        </label>
        <div>
          <h3>Reader preview</h3>
          <p v-if="!source" class="blank">
            The preview will appear as you type.
          </p>
          <Reader v-else-if="key === 'v2'" :source="source" />
          <pre v-else class="reader-plain">{{ source }}</pre>
        </div>
      </div>
      <p class="hint" v-if="key === 'v2'">
        The local reader applies embedded and inline CSS. It drops active
        elements, navigation and external resources. The source editor preserves
        the draft markup.
      </p>
      <p class="hint" v-if="key === 'v3'">
        Prior emails establish the thread. The first message and each follow-up
        have one planned reply slot.
      </p>
      <p class="hint">
        {{ plannedRepetitions(repetitions, group.count, index) }}
        planned repetitions for this variation. A full plan shares empty slots’ runs among the populated variations.
      </p>
    </div>
  </section>
</template>
