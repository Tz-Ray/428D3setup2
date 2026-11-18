<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from './api.js'
import MessageDrafts from './MessageDrafts.vue'
import GreetingChecks from './GreetingChecks.vue'
import { vectorBudget } from './draftStages.js'

const nav = {
  plan: 'Trial plan',
  drafts: 'Message drafts',
  checks: 'Run trials',
}
const catalog = [
  ['v1', 'Plaintext body'],
  ['v2', 'Hidden markup'],
  ['v3', 'Earlier and later messages'],
]
function active() {
  const key = location.hash.slice(1)
  return Object.hasOwn(nav, key) ? key : 'plan'
}
const tab = ref(active()),
  plan = ref(null),
  revision = ref(0),
  snapshot = ref('')
const models = ref([]),
  modelError = ref(''),
  error = ref(''),
  saving = ref(false),
  ready = ref(false)
const importInput = ref(null),
  importing = ref(false),
  importError = ref(''),
  importMessage = ref(''),
  importSelection = ref(null),
  editorVersion = ref(0)
const dirty = computed(
  () => plan.value && JSON.stringify(plan.value) !== snapshot.value,
)
const perVector = id => vectorBudget(plan.value.repetitions, plan.value.vectors[id].count)
const perModel = computed(() => catalog.reduce((sum, [id]) => sum + perVector(id), 0) * 2)
const readyCount = computed(
  () => models.value.filter((m) => plan.value.models.includes(m.tag)).length,
)
function artifact(tag) {
  return models.value.find((m) => m.tag === tag)
}
function changeTab() {
  tab.value = active()
}
function leave(e) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
async function inventory() {
  try {
    models.value = (await api('models')).models
    modelError.value = ''
  } catch (e) {
    models.value = []
    modelError.value = e.message
  }
}
async function load() {
  try {
    await api('session', 'POST')
    const saved = await api('plan')
    plan.value = saved.plan
    revision.value = saved.revision
    snapshot.value = JSON.stringify(saved.plan)
    ready.value = true
    error.value = ''
    await inventory()
  } catch (e) {
    error.value = e.message
  }
}
async function save() {
  saving.value = true
  const submitted = JSON.stringify(plan.value)
  try {
    const res = await api('plan', 'PUT', {
      revision: revision.value,
      plan: JSON.parse(submitted),
    })
    revision.value = res.revision
    snapshot.value = submitted
    importMessage.value = ''
    error.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
function downloadJson(name, data) {
  const file = new Blob([JSON.stringify(data, null, 2), '\n'], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(file)
  const link = document.createElement('a')
  link.href = url
  link.download = `d3-${name}-r${revision.value}${dirty.value ? '-edited' : ''}.json`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function downloadVariation(vector, number) {
  const { vectors, ...setup } = plan.value
  const group = vectors[vector]
  downloadJson(`${vector}-variation-${number}`, {
    revision: revision.value,
    setup,
    vector,
    active_variations: group.count,
    variation_number: number,
    variation: group.variations[number - 1],
  })
}
async function importJson(event) {
  const file = event.target.files[0]
  event.target.value = ''
  if (!file) return
  importError.value = ''
  importMessage.value = ''
  importing.value = true
  try {
    const contents = JSON.parse(await file.text())
    const doc = await api('plan/import-preview', 'POST', contents)
    const full = Object.hasOwn(doc, 'plan')
    const scope = full ? 'the entire plan' : `the shared trial settings and ${doc.vector.toUpperCase()} variation ${doc.variation_number}`
    if (dirty.value && !window.confirm(`Replace ${scope} in the editor, including edits you have not saved?`)) return
    if (full) {
      plan.value = doc.plan
      importSelection.value = null
      location.hash = 'plan'
    } else {
      const group = plan.value.vectors[doc.vector]
      group.variations[doc.variation_number - 1] = doc.variation
      group.count = Math.max(group.count, doc.active_variations)
      Object.assign(plan.value, doc.setup)
      importSelection.value = { vector: doc.vector, number: doc.variation_number }
      location.hash = 'drafts'
    }
    editorVersion.value++
    importMessage.value = `Loaded ${scope} from ${file.name}. ${dirty.value ? 'Choose Save plan to keep these edits.' : 'The editor matches the saved plan.'}`
  } catch (e) {
    importError.value = e instanceof SyntaxError
      ? 'This file is not valid JSON.'
      : 'Could not import this file. Choose a plan or variation JSON export. ' + e.message
  } finally {
    importing.value = false
  }
}
function reload() {
  if (
    !dirty.value ||
    window.confirm('Discard unsaved edits and reload the saved plan?')
  )
    load()
}
onMounted(() => {
  window.addEventListener('hashchange', changeTab)
  window.addEventListener('beforeunload', leave)
  load()
})
onUnmounted(() => {
  window.removeEventListener('hashchange', changeTab)
  window.removeEventListener('beforeunload', leave)
})
</script>
<template>
  <div class="shell">
    <aside>
      <div class="brand"><span>D3</span><strong>Mail sandbox</strong></div>
      <nav aria-label="Workspace">
        <a
          v-for="(label, key) in nav"
          :key="key"
          :href="'#' + key"
          :aria-current="tab === key ? 'page' : undefined"
          >{{ label }}</a
        >
      </nav>
      <div class="railfoot">
        <i></i> Local workspace<br /><code>127.0.0.1</code>
      </div>
    </aside>
    <main>
      <header class="top">
        <span>D3 workspace <i>/</i> {{ nav[tab] }}</span>
        <span class="flag" role="status">{{
          ready ? 'Local API connected' : 'Connecting…'
        }}</span>
      </header>
      <div class="heading">
        <h1>{{ nav[tab] }}</h1>
        <div v-if="plan" class="actions">
          <a v-if="tab === 'plan'" href="#checks">Open trial runner</a>
          <small :class="{ changed: dirty }">{{
            dirty ? 'Unsaved edits' : 'Saved · revision ' + revision
          }}</small>
          <button @click="downloadJson('plan', { revision, plan })">Download plan JSON</button>
          <button :disabled="saving || importing" @click="importInput.click()">Import JSON</button>
          <input ref="importInput" type="file" accept=".json,application/json" hidden @change="importJson">
          <button class="primary" :disabled="saving || importing || !dirty" @click="save">
            {{ saving ? 'Saving…' : 'Save plan' }}
          </button>
        </div>
      </div>
      <p v-if="importError" class="alert" role="alert">{{ importError }}</p>
      <p v-else-if="importMessage" class="hint" role="status">{{ importMessage }}</p>
      <div v-if="error" class="alert" role="alert">
        {{ error }} <button @click="reload">Reload saved plan</button>
      </div>
      <template v-if="plan">
        <template v-if="tab === 'plan'">
          <section class="stats" aria-label="Planned trial counts">
            <div>
              <span>Total planned</span><strong>{{ perModel * 2 }}</strong>
            </div>
            <div>
              <span>Per model</span><strong>{{ perModel }}</strong>
            </div>
            <div>
              <span>Per condition</span><strong>{{ perModel }}</strong>
            </div>
          </section>
          <section class="panel">
            <header>
              <h2>Target models</h2>
              <button @click="inventory">Refresh inventory</button>
            </header>
            <div class="pad">
              <p v-if="!modelError" class="intro">
                {{ readyCount }} of 2 target slots match installed local models.
              </p>
              <p class="alert" v-if="modelError">{{ modelError }} When Ollama is running, refresh the inventory.</p>
              <datalist id="model-list">
                <option v-for="m in models" :key="m.tag" :value="m.tag" />
              </datalist>
              <div class="two">
                <div v-for="(tag, i) in plan.models" :key="i">
                  <label
                    >Model {{ i + 1 }} tag<input
                      list="model-list"
                      v-model="plan.models[i]"
                      maxlength="128"
                      placeholder="Enter or select a local tag"
                  /></label>
                  <small class="model-state">{{
                    artifact(tag)
                      ? 'Installed locally'
                      : tag
                        ? (modelError ? 'Installation status unknown' : 'Absent from local inventory')
                        : 'Unassigned'
                  }}</small>
                  <details v-if="artifact(tag)">
                    <summary>Model digest</summary>
                    <code>{{ artifact(tag).digest }}</code>
                  </details>
                </div>
              </div>
            </div>
          </section>
          <section class="panel">
            <header><h2>Trial allocation</h2></header>
            <div class="pad">
              <label class="allocation"
                >Minimum trials per vector, model and condition<input
                  type="number"
                  min="20"
                  max="200"
                  v-model.number="plan.repetitions"
              /></label>
              <div class="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Vector</th>
                      <th>Variations</th>
                      <th>Baseline / model</th>
                      <th>Safeguarded / model</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="[id, label] in catalog" :key="id">
                      <th>{{ id.toUpperCase() }} · {{ label }}</th>
                      <td>{{ plan.vectors[id].count }}</td>
                      <td>{{ perVector(id) }}</td>
                      <td>{{ perVector(id) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="hint">
                Each variation starts with five runs. A higher vector minimum adds runs in rotation.
              </p>
            </div>
          </section>
          <section class="panel">
            <header><h2>Operator configuration</h2></header>
            <div class="pad">
              <label
                >System prompt<textarea
                  v-model="plan.system_prompt"
                  rows="5"
                  maxlength="16000"
                ></textarea>
              </label>
              <label
                >Canary (fixed trial value)<textarea
                  v-model="plan.fixed_value"
                  rows="2"
                  maxlength="16000"
                ></textarea>
                <small>Enter the exact value to include in the model’s context for each turn.</small>
              </label>
              <label
                >Operator notes<textarea
                  v-model="plan.canaries"
                  rows="3"
                  maxlength="16000"
                ></textarea>
                <small
                  >Saved for your reference only.</small
                ></label
              >
            </div>
          </section>
        </template>
        <MessageDrafts
          v-if="tab === 'drafts'"
          :key="editorVersion"
          :initial-selection="importSelection"
          :vectors="plan.vectors"
          :repetitions="plan.repetitions"
          @download-variation="downloadVariation"
        />
        <GreetingChecks
          v-if="tab === 'checks'"
          :models="models"
          :inventory-error="modelError"
          :plan="plan"
          :revision="revision"
          :dirty="dirty"
        />
      </template>
    </main>
  </div>
</template>
