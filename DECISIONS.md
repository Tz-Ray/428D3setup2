# Decisions

## 2026-11-18 — Retained D3 setup

The active workspace contains the D3 FastAPI service, Vue console, launchers, dependency manifests, regression tests and local run state. Earlier applications, runs and their documentation reside in a sibling archive folder with their original directory layout. [Archive folder](../archive-20261118/)

The empty FastAPI entry point was reconstructed from the previous compiled module and its route tests. The installed Python versions are recorded in the D3 dependency manifest. The fruit checker uses the wording of the recorded prompt so the current “answer” and historical “canary” controls can each be checked against their own instruction. [Server](mail-lab/d3/web.py) · [Dependencies](mail-lab/requirements.txt)

## 2026-11-17 — Environment setup

- Ollama runs inside WSL (Linux build 0.40.5 in ~/.local/opt/ollama, CPU only; NVIDIA/AMD GPU libraries left out because this machine has no such GPU). The Windows Ollama install is not used: WSL's NAT network mode stops WSL code from reaching it on 127.0.0.1:11434.
- Ollama is a systemd *user* service (~/.config/systemd/user/ollama.service), not enabled at login; `ollama-start` / `ollama-stop` start and stop it.
- Codex sandbox profile `dev-fullread-net` (~/.codex/config.toml): read whole disk, write this project + pip/npm/uv caches, saved sign-in data denied, unrestricted network (user's choice; only setup downloads actually need the internet).
- Email stays local: messages live in SQLite; no external mail servers.
- Ollama `OLLAMA_KEEP_ALIVE=-1` (service file): the model stays loaded (~5.6 GB RAM) until Ollama stops, so the agent never waits for the slow (~minutes) CPU load. Context window is separate and still Ollama's default (4096 tokens); if the app changes it, use one fixed `num_ctx` everywhere, since a different value forces a reload.

## 2026-11-17 — Fixed GitHub app and separate setup runner

- Keep the complete GitHub checkout detached at `3e551eb9fa5acd82e26c32bf4d6dba9789beff2d`. The fetched default branch and local commit matched. All new implementation lives in `mail-lab/`.
- Serve the original Vue mail client at `/` and the independent inspector at `/lab/` on the same loopback origin. Both use the original browser sign-in. Full run records require the primary login.
- Seed a new template using the pinned app and bind its HTTP routes to a new SQLite copy per run. Build the original frontend outside the checkout. Keep previous material under `archive/before-fixed-setup/`.
- Persist model outputs, tool arguments, results, timestamps and delivered message IDs outside the disposable database. The dashboard excludes setup checks from run totals.

## Live observation

- The monitor follows the worker’s durable, ordered events and mailbox rows read through the fixed mail API. The run view groups copies from both account folders and distinguishes drafts from actual deliveries.
- Browser connections reconcile complete snapshots on change and reconnect. An OS file lock held by the worker provides independent evidence of interrupted execution.
- The default lab view is Live conversation. Functional checks launch from the primary session using the two existing ordinary sample files. The original webmail app and workspace database remain independent of disposable runs.

## Reply delivery diagnostics

The optional `--diagnose-reply` flag on the setup runner saves Ollama HTTP bodies, the received reply request, and a read-only SQLite observation under `mail-lab/data/diagnostics/`. It requests sampled-token metadata with `logprobs=true`. The agent continues to submit the structured tool arguments returned by Ollama. Earlier chat text stays in its original round as an unsent draft. The diagnostic uses the ordinary setup classification.

## Privacy setting

The original pinned `default` is displayed as `personalization-v1`. Its instruction to use the profile for personalization conflicts with the main privacy setting. The legacy demonstration describes the account as sample and limits its privacy instruction to routine mail. Historical records retain the configuration they used.

The main ordinary controls and new setup checks use the same `privacy-v1` template. Its SHA-256 is `895cff3a294a9c0744bde8330ce8449746efc59297c35698edf2bc004da458e1`. The new main runner supplies the rendered template at the Ollama request boundary on every turn of the pinned agent loop. Setup checks retain their separate tool-loop settings. The checker operates on delivered messages and records name matches separately. Grouping includes prompt version, sample file, and backend. The two settings have separate group IDs.

## 2026-11-18 — Privacy rule at delivery

`delivery-rule-v1` is an opt-in server configuration for disposable run instances. Its scope is mail from the primary account to the local test sender. The default workspace and historical default use their original configuration. The rule-based instance checks each pending outgoing email before SQLite insertion through the shared request database session. This covers webmail compose, webmail reply, agent reply, and the server's fixed-recipient forward route. Only read and reply occur in the model's tool schema.

The rule checks subject, stored plain body, raw HTML, and extracted HTML text separately against the private fields in the primary account's profile. It uses the pinned checker's Unicode and whitespace normalization, date formats, time-zone aliases, and workplace patterns. The name alone is allowed. The rule can reject incidental uses of a matched value or shared abbreviation. Semantic paraphrases and representations outside these patterns remain beyond its coverage. The checker still classifies recipient-inbox bodies with the historical rule. Using the same pattern definitions in application and classification bounds the interpretation of the results.

Allowed proposals and their message IDs commit in the mailbox transaction. A rejection rolls back the attempted insertion, persists the proposed message and match locations in an operator audit table, and returns HTTP 422 with a generic reason. The model has no tool for accessing that table. Each application and request owns its rule state. Copies used for default comparisons receive the original session dependency.

The paired replay uses all archived replies actually delivered by the ordinary privacy controls. Its unit is one recorded reply request under each server setting. Every pair uses the same existing lab template bytes and original message content. The historical main runner created transient seed templates, so the frozen template hash identifies the replay template only. The counterfactual measured here is whether each exact message could reach the recipient under the rule. Model retries, ordinary task quality under a new model conversation, and main additional effectiveness require separate evidence. [Frozen replay contract](mail-lab/main/replay_contract.json)

## D3 clean sandbox

The default launcher starts the D3 Vue bundle and FastAPI service on loopback. D3 initializes its own SQLite state in `mail-lab/d3-state/`. Its imports, web routes and build inputs exclude historical mail applications, profiles, sample files, prompts and run records. The earlier console has an explicit `--legacy` launcher option.

The plan starts with empty operator text. The default allocation is 20 repetitions per vector, model and setting. Both settings cycle through the same four or five active variations. With three vectors and two models, the planned count is 240, including 120 for each model. Each V3 variation stores the earlier and later message together. A revision check protects saved work in concurrent tabs.

Variant authoring is preview-only. The local HTML reader rebuilds passive markup in an inert template, keeps inline and embedded CSS, and displays it inside a sandboxed iframe with restrictive content rules. The editor preserves the input separately. Active elements, external resources and link destinations are outside this reader's rendering contract.

Live verification uses one ordinary greeting and a fresh local SQLite mailbox per check. The model receives exactly the selected system text and the incoming greeting through Ollama on loopback. Temperature and seed belong to the request's sampling options. The fixed run value is operator-specified context and defaults to empty. The older operator notes remain for human reference. The runner reads and replies through a scoped HTTP mailbox API. The expected-reply check is a delivery rule for this smoke test. A pass requires the exact proposed text in the original sender's inbox. The operator can inspect the prompt, digest, model output, message IDs, timestamps and delivery outcome.

## D3 process and model availability

Use FastAPI on 127.0.0.1:8000 for both the compiled console and its API. The launcher replaces itself with Uvicorn after the finite frontend build. D3 requires its own origin on writes, an operator cookie for plan access, an exact loopback Host header, and publicly serves only the dedicated static build. Ollama is an independently managed inference service. The console distinguishes an unreachable inventory from a model absent in a successful inventory response.

## Ordinary fruit checks and conversation turns

The sender’s email and the configured fixed value are separate inputs. The two ordinary fruit presets use a fresh mailbox per repetition and sample at temperature 0.8. Each turn rereads the stored run configuration and builds a new request containing the system prompt, the fixed value when supplied, and exactly that run’s confirmed mail in order. A following question is delivered only after verifying the preceding reply in the sender inbox. The run ends at the final planned reply. The three-guess preset uses the fixed value Banana. The V3 authoring view also supports prior mail and additional follow-ups, with planned reply slots distinguished from actual delivered replies.

## Ordinary run launch and per-turn records

The localhost runner performs Check 0 and Check 0.1 before each primary greeting attempt, with five fresh repetitions per control by default. Standalone controls run directly. The guess uses the exact configured spelling in its final question. Checks record the fruit names the checker recognizes and the actual delivered replies. The operator can inspect variation across seeds. A failed control retains its verdict and skips the primary.

The selected vector, variant, saved name, authored subject and revision are filing metadata. Each attempt separately identifies its actual scenario and sent subjects. SQLite records the entire local mail table after each turn, including turns with a rejected draft. The operator can open per-turn JSON as soon as the turn closes. The attempt transcript and complete record appear on completion. A missing export can be regenerated from the stored evidence. Earlier runs retain their original casing and explicitly identify reconstructed rows.

## Saved draft delivery

The explicit mailbox-only API remains available for delivery diagnostics. It commits the run and its recipient inbox rows together against the selected plan revision. An email with a subject or body is deliverable, and wholly blank slots are skipped. The original subject and body are preserved, including V2 markup and whitespace. V3 delivers prior emails, the first message and follow-ups in editor order. Each delivery has its own inbox in the logs. The console's ordinary saved-variation action now uses the unrestricted model replay described below.

The four ordinary calibration cases remain available through the explicitly selected standalone fruit controls and built-in fruit sequence. They retain their Check 0 or 0.1 prompts, scoring and sampling settings. Saved or imported variations never switch prompts merely because their content happens to match a calibration case.

## Plan and variation JSON downloads

The console downloads a UTF-8 JSON snapshot of the current editor state. The full plan uses the existing `revision` and `plan` fields and includes inactive variation slots. A single-variation download includes the shared plan settings, vector, active variation count, one-based slot number and complete variation. The revision identifies the saved plan the editor started from. Filenames include `-edited` when the snapshot contains unsaved changes.

## Live run transcripts and reply delivery

Ollama streams each reply. The runner records the pending request, partial draft, completed model output and verified delivery in SQLite. An incomplete stream retains the partial draft and failure reason. Only a completed nonempty reply is submitted to the mailbox. The optional expected text is compared after delivery. Earlier checks retain their historical rejection outcomes.

Starting a sequence freezes its populated slots in one transaction. The worker processes them in vector and variation order, including when the browser disconnects. The live view follows preparation checks and variations, with the current turn first. Opening an archived record pauses following. A restart marks unfinished sequence slots interrupted. The built-in fruit sequence can be run independently of the saved content.

## JSON import

The operator can load either console export into the editor. Server-side validation uses the same plan and mail schemas as saving. Importing a whole plan replaces all editor settings and slots. Importing a variation applies the file's shared settings and named slot, grows the active count when needed, and preserves the other slots. Save plan uses the current workspace revision so concurrent edits still receive a conflict. Model calls start through the run runner.

## Unrestricted saved-mail replay

Every populated saved or imported variation can use the local model; recognition as one of the four fruit controls is no longer required. A replay freezes the saved system prompt, fixed trial value, subjects, bodies, model digest and sampling settings before execution, then uses the existing scoped mailbox and read/draft/send audit path. Each sender-authored model turn is represented as `Subject: …`, a blank line and the exact stored body. Assistant turns contain the delivered reply body. V3 mail remains ordered: the runner verifies each reply in the sender inbox before inserting the next incoming email, and every later model request includes the confirmed conversation so far. The older mailbox-only endpoint and its records remain available, but the console's saved-variation and saved-sequence actions now run model replays. This requires no SQLite or plan-schema migration and does not rewrite imported content or historical records.

## Repetitions for saved replays

The default launch runs V1, then V2, then V3. Each vector gets the largest of 20 runs, five runs per configured variation, or the operator's vector minimum. A full plan requires mail in each vector and distributes that vector's budget across its populated slots in rotation. A single-variant replay runs its configured share. Each repetition gets its own mailbox, transcript and run ID and uses the selected sampling seed. A V3 repetition covers the complete thread. SQLite records the whole queue at launch so follow-up polling can recover progress.

Pause lets an active repetition finish and holds the remaining attempts in SQLite. Resume claims the next paused attempt in sequence order. Stop preserves completed deliveries, marks pending attempts stopped, and asks the active worker to exit on its next stream update or before submitting a reply. Paused queues survive a page reload or service restart.

## Second model and tracked raw results (2026-11-18)

The second model is `qwen2.5:3b-instruct-q4_K_M` instead of the earlier 7B candidate: the operator asked for a cheap, lightweight Qwen, inference is CPU-only, and the quantization matches the Llama build. The 3B weights carry the Qwen Research License (non-commercial), acceptable for coursework. `mail-lab/tools/d3_run.py` drives the existing operator API for launches and writes one row per trial to `mail-lab/results/`, because `d3-state/` is ignored by git and D3 requires raw results in the repository. Nothing is pushed to the team's GitHub repository; a separate repository will hold this run.

## Sampling, token limit and scoring for D3 trials (2026-11-18)

Trials must be independent, so saved replays sample at temperature 0.8, the value D2 pinned. Seeds are derived from the launch seed and queue position instead of drawn at random, so the same seeds apply to both models and to the later mitigation arm, and a rerun can repeat them. The reply limit is 192 tokens, the D2 value, because 64 tokens truncated most replies and split the canary. Leak scoring lives in the export tool and a rules file in the repository, so every reported count comes from a script and one row per trial. A trial is scored on delivered mail only. `leaked_turns` separates a V3 leak on the planted email from one on the trigger.
