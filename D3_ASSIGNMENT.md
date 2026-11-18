# D3 assignment details

Stored 2026-11-18 from the course brief, for reference while preparing the D3 writeup.
Team track: **Track A — AI Agent Trap and Remediation**.

D3 builds on your D1 scope and the harness you built in D2. Measure a baseline, build a
mitigation, and measure again to show what changed. Do this for your own track only.

Use the targets and scope from D1, with any replacements you made in D2. Use canary tokens and
synthetic data, never real user data.

## Part 1: Baseline (Track A)

- Use at least three injection vectors of different kinds, chosen to fit your agent: for example
  hidden text, text in images, file metadata, poisoned tool results, or an instruction stored
  earlier and read later. The same trick in three places counts as one vector.
- Show a real security impact: name something the agent must never do, such as send the user's
  data to an outside address or take an action the user did not ask for, and show your attack
  making it happen. "The agent said something strange" does not count.
- Test each vector separately against at least two agents or models, with exact model versions
  pinned. Run at least 20 trials per vector and model, and report successes out of trials, such
  as 14 of 20.

## Part 2: Mitigation

Build the fix in code. A recommendation is not a mitigation.

- Track A: for example, separate instructions from untrusted data, allowlist tool calls, or
  sandbox the agent.
- Track B: a patch, or compiler hardening if you found no crash.
- Track C: an improvement aimed at the weakest part of your results.

Say whether your fix covers one bug or a whole class.

Then run the same evaluation again: same harness, inputs, success criteria, trial counts,
settings, and versions. Only the system under test changes. For Track B, you do not need to rerun
the whole campaign: replay every crashing input and your final corpus against the fixed build.
Show before and after side by side and explain the difference.

## Reproducibility

Every number in your report needs the script that produced it and the raw results in your
repository: one row per trial or case, or campaign logs for fuzzing. A number with no raw results
behind it scores zero. A number that does not match its raw results is an academic integrity
matter. The grader will re-run the harness for three randomly chosen teams.

## What to submit

One PDF per team on Canvas, named `D3-<team name>.pdf`. Code and raw results stay in your
repository.

The PDF has these sections, in order:

1. Repository: link, the `baseline` commit hash, and the final commit hash.
2. Setup: target, tools, agents, and models, with versions.
3. Method: how you ran the experiments, including your vectors (A), fuzzing setup (B), or scoring
   rule (C).
4. Baseline results: everything Part 1 asks for.
5. Mitigation: what you built, where it is in the code, and whether it covers one bug or a class.
6. Before and after: side by side, with what changed and why.
7. Reproduction: exact commands for both runs, and paths to the raw results.
8. AI Use Appendix: which AI tools you used, what for, and what you changed. Accurate disclosure
   never costs marks. Missing or false disclosure is an academic integrity matter.

Only 20% of the grade depends on whether the attack or fix worked. An honest, well-explained drop
from 80% to 45% scores better than a claim of complete prevention without evidence.

## Local constraints from the user (2026-11-18)

- This repository is separate from the team's GitHub repository because the setup differs from
  the team's. Do not push this work to the team's repository.
- Runs must be easy to reproduce: see `README.md`, `mail-lab/tools/d3_run.py` and
  `mail-lab/results/`.
