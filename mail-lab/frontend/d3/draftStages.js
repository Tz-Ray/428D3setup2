export function vectorBudget(budget, count) {
  return Math.max(20, budget, 5 * count)
}

export function plannedRepetitions(budget, count, index) {
  const total = vectorBudget(budget, count)
  return Math.floor(total / count) + Number(index < total % count)
}

export function draftStages(vector, variation) {
  function stage(id, label, mail, reply = true) {
    return {
      id, label, mail, reply,
      subjectField: id === 'later' ? 'later_subject' : 'subject',
      bodyField: id === 'later' ? 'later_body' : 'body',
    }
  }
  const first = stage('first', 'First message', variation)
  if (vector !== 'v3') return [first]
  return [
    ...variation.prior_emails.map((mail, i) => stage('prior-' + i, 'Prior email ' + (i + 1), mail, false)),
    first,
    stage('later', 'Follow-up 1', variation),
    ...variation.additional_followups.map((mail, i) => stage('follow-' + i, 'Follow-up ' + (i + 2), mail)),
  ]
}
