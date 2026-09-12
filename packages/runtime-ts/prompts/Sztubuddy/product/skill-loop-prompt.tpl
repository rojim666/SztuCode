# /loop — schedule a recurring prompt

Parse the input below into `[interval] <prompt…>` and schedule it with CronCreate.

## Parsing (in priority order)

1. **Leading token**: if the first whitespace-delimited token matches `^\d+[smhd]$` (e.g. `5m`, `2h`), that's the interval; the rest is the prompt.
2. **Trailing "every" clause**: otherwise, if the input ends with `every <N><unit>` or `every <N> <unit-word>` (e.g. `every 20m`, `every 5 minutes`, `every 2 hours`), extract that as the interval and strip it from the prompt. Only match when what follows "every" is a time expression — `check every PR` has no interval.
3. **Default**: otherwise, interval is `10m` and the entire input is the prompt.

If the resulting prompt is empty, show usage `/loop [interval] <prompt>` and stop — do not call CronCreate.

Examples:
- `5m /babysit-prs` → interval `5m`, prompt `/babysit-prs` (rule 1)
- `check the deploy every 20m` → interval `20m`, prompt `check the deploy` (rule 2)
- `run tests every 5 minutes` → interval `5m`, prompt `run tests` (rule 2)
- `check the deploy` → interval `10m`, prompt `check the deploy` (rule 3)
- `check every PR` → interval `10m`, prompt `check every PR` (rule 3 — "every" not followed by time)
- `5m` → empty prompt → show usage

## Interval → cron

Supported suffixes: `s` (seconds, rounded up to nearest minute, min 1), `m` (minutes), `h` (hours), `d` (days). Convert:

| Interval pattern      | Cron expression     | Notes                                    |
|-----------------------|---------------------|------------------------------------------|
| `Nm` where N ≤ 59   | `*/N * * * *`     | every N minutes                          |
| `Nm` where N ≥ 60   | `0 */H * * *`     | round to hours (H = N/60, must divide 24)|
| `Nh` where N ≤ 23   | `0 */N * * *`     | every N hours                            |
| `Nd`                | `0 0 */N * *`     | every N days at midnight local           |
| `Ns`                | treat as `ceil(N/60)m` | cron minimum granularity is 1 minute  |

**If the interval doesn't cleanly divide its unit** (e.g. `7m` → `*/7 * * * *` gives uneven gaps at :56→:00; `90m` → 1.5h which cron can't express), pick the nearest clean interval and tell the user what you rounded to before scheduling.

## Action

First pick a `<LOOP_ID>`: a short unique token you make up right now (e.g. 6–8 random lowercase-alphanumeric characters like `k3f9x2`). **Do not call any tool (e.g. Bash `date`) to build it** — just invent it inline. It only has to be unique per loop and stay identical across every reschedule of this loop. Also note today's date from the `<env>` block above as `<STARTED_DATE>` (a plain date is enough for the safety cap; you do not need a precise time).

Build the scheduled prompt by wrapping the parsed prompt with a self-adjustment block. Substitute `<LOOP_ID>` and `<STARTED_DATE>` with the values you just chose (set once here; never change them on later reschedules) and `<PROMPT>` with the parsed prompt. The `[/loop:<LOOP_ID>]` marker must stay at the very front so it survives CronList's truncated preview:

```
[/loop:<LOOP_ID>] <PROMPT>

---
[/loop self-adjustment] This prompt is fired by a /loop job (marker `[/loop:<LOOP_ID>]`, started <STARTED_DATE>). **Every single time this prompt fires**, after finishing the task above you must end the turn with one of:
- **Continue looping** (default — same interval as before, or a new one you decide is better):
  1. Find this job's id: check your conversation history for the CronCreate/CronDelete result that scheduled this exact firing; if not visible — e.g. after context compaction — call CronList and match the `[/loop:<LOOP_ID>]` marker at the start of a job's prompt preview.
  2. If CronList matches more than one job with this exact marker (can happen if a previous CronDelete failed), delete all of them before creating the replacement — never leave duplicates running.
  3. If CronDelete errors (e.g. job already gone), do not skip it silently — still proceed to CronCreate the replacement so the loop doesn't die.
  4. Call CronCreate with `recurring: false` and this exact wrapped prompt (marker + self-adjustment block unchanged) at whatever time you decide the next iteration should run.
- **Stop the loop**: call CronDelete with the job id (and any duplicates found via CronList) and do not create a replacement. Tell the user the loop stopped and why.

Do not assume the job re-fires on its own — once this switches to a `recurring: false` job, nothing fires automatically; you must explicitly recreate it every time or the loop silently ends.

**Safety cap**: if today's date is more than 3 days after <STARTED_DATE>, stop instead of continuing — this mirrors the built-in recurring task expiry, which only auto-enforces on the initial `recurring: true` job below, not on the one-shot jobs you create afterward.
```

Call CronCreate with:
- `cron`: the expression from the table above
- `prompt`: the wrapped prompt built above (not the bare parsed prompt)
- `recurring`: `true`

Then confirm to the user: what's scheduled, the cron expression, the human-readable cadence, that after the first firing it switches to self-managed rescheduling each round (so it keeps running only as long as it keeps recreating itself, and can stop itself early), that it's capped at 3 days either way, and that they can cancel sooner with CronDelete (include the job ID).

## Input

$ARGUMENTS
