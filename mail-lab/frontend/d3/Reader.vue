<script setup>
import { computed } from 'vue'
const props = defineProps({ source: { type: String, required: true } })

// Template contents have no browsing context. Rebuild only passive elements before
// serialization. The iframe never receives the sender's document or URL attributes.
const allowed = new Set(
  'a abbr address article aside b bdi bdo blockquote br caption cite code col colgroup dd del details div dl dt em figcaption figure footer h1 h2 h3 h4 h5 h6 header hr i img ins kbd li main mark ol p pre q s samp section small span strong sub summary sup table tbody td tfoot th thead time tr u ul wbr style'.split(
    ' ',
  ),
)
const omitted = new Set(
  'base embed iframe link math meta noscript object script svg template title'.split(
    ' ',
  ),
)
const attributes = new Set(
  'alt class colspan dir height hidden id lang open reversed rowspan start style title width'.split(
    ' ',
  ),
)
function passive(node, parent) {
  if (node.nodeType === Node.TEXT_NODE) {
    parent.append(document.createTextNode(node.data))
    return
  }
  if (
    node.nodeType !== Node.ELEMENT_NODE ||
    node.namespaceURI !== 'http://www.w3.org/1999/xhtml'
  )
    return
  const tag = node.localName
  if (omitted.has(tag)) return
  let container = parent
  if (allowed.has(tag)) {
    container = document.createElement(tag)
    for (const attr of node.attributes) {
      if (attributes.has(attr.name))
        container.setAttribute(attr.name, attr.value)
    }
    parent.append(container)
  }
  if (tag === 'style') {
    container.textContent = node.textContent.replaceAll('<', '\\3c ')
    return
  }
  for (const child of node.childNodes) passive(child, container)
}
const doc = computed(() => {
  const parsed = document.createElement('template')
  parsed.innerHTML = props.source
  const clean = document.createElement('template')
  for (const node of parsed.content.childNodes) passive(node, clean.content)
  const policy =
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
  return (
    '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' +
    policy +
    '"><style>body{font:16px/1.5 system-ui,sans-serif;overflow-wrap:anywhere}</style>' +
    clean.innerHTML
  )
})
</script>
<template>
  <iframe
    sandbox=""
    referrerpolicy="no-referrer"
    title="Local HTML reader"
    :srcdoc="doc"
  ></iframe>
</template>
