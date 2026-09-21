# Narrated Demo Video

Turns a silent screen-recording (a product demo `.mp4`, no usable audio track)
into a narrated one where:

- the voiceover is **one continuous take** — no audible tone/energy jump
  between cuts, because it's not stitched together from separate synthesis
  calls;
- every scene's **video length is built to match its narration**, not the
  other way around — footage is trimmed if it naturally runs longer than the
  narration needs, or extended with a frozen last frame if the narration
  needs more time than the raw recording gives it. The result: no rushed
  scenes, no awkward silent gaps, and narration that's actually talking about
  what's on screen at that moment.

It works with **any coding agent that can run shell commands and read text
output** — Claude Code, Cursor, OpenCode, Antigravity, Aider, Windsurf, a
plain terminal session, whatever. Nothing here depends on a specific agent
vendor's tool-calling format. The only two moving pieces are:

1. Deterministic Node.js + ffmpeg scripts (`scripts/`) that do the actual
   audio/video work.
2. This document, which tells whichever agent is running the show what order
   to call them in and what to watch out for.

If your agent framework supports delegating a sub-task to an isolated
context (a "subagent," "sub-task," or similar), use that for step 2 below —
it's the one step that requires looking at images, and doing it in an
isolated context keeps dozens of screenshot tokens out of your main
conversation. If your agent doesn't support that, just do it inline; it
still works, it's just costlier in context.

See [`references/LESSONS.md`](references/LESSONS.md) if a build comes out
with sync problems, tone problems, or odd pacing. It documents the actual
failure modes hit while building this (not hypothetical ones) and the fix
for each. Read it before re-running the same thing and hoping for a
different result.

## When to use this

The user has a silent screen recording and wants it narrated — phrases like
"add a voiceover to this demo," "turn this recording into a presentation
video," "the narration timing is off, fix it," "the voice sounds different
between cuts," or "there are long silent gaps in the narration." Also
applies if they just want a polished walkthrough video ready for a
client/stakeholder meeting from raw screen-capture footage.

Not a fit for: videos that already have usable narration/dialogue audio,
adding subtitles/captions only (no voice), or purely visual edits (color
grading, trimming for length) with no narration involved.

## Prerequisites

- `ffmpeg` and `ffprobe` available (the scripts auto-discover common install
  locations on Windows/macOS/Linux, or set `FFMPEG_BIN`/`FFPROBE_BIN` env
  vars to point at them explicitly).
- Node.js (any reasonably recent version — the scripts use only built-in
  modules plus global `fetch`).
- An ElevenLabs account + API key. (The synthesis script is ElevenLabs-
  specific today; see "Swapping the TTS provider" below if you need a
  different one.)

## Step-by-step

### 0. Get the essentials

Ask the user for (don't assume):
- **Source video path.**
- **Working folder name** — default `demo-narration`, created inside the
  **project this video belongs to** (not inside this workflow's own
  directory). It gets an `in/` subfolder for working data (frames, scripts,
  raw audio, scene JSON) and an `out/` subfolder for the finished video.
- **ElevenLabs API key.** Check `<workdir>/.env.local` first
  (`ELEVENLABS_API_KEY=...`, one per line, `#` comments allowed). If
  missing, ask for a key + voice ID and write it there yourself — then make
  sure it's gitignored, it's a secret.
- **Voice ID + model.** Ask if the user has a preferred ElevenLabs voice; if
  not, point them at https://elevenlabs.io/app/voice-library. Don't invent
  one.

### 1. Set up the working directory + a coarse frame pass

```bash
cd <project-root>
node <this-workflow-path>/scripts/init_workdir.js "<source-video>" --workdir demo-narration --interval 2.5
```

Prints `video_info.json` (duration, resolution, fps, whether the source
already has audio) and the coarse frame count. If the source already has an
audio track, ask the user whether to replace it fully or mix under it — the
rest of this workflow assumes silent source + full replacement.

### 2. Build a shot list, then verify boundaries with real frames

Look through the coarse frames (`<workdir>/in/frames_coarse/frame_%04d.jpg`,
timestamp = `(index-1) * interval`) and build a shot list: for each distinct
screen/action, a rough start time and a one-line description of what's shown
— include real numbers/labels/names visible, the narration script will need
them.

**Then refine every boundary you're not confident about** — especially any
scene that looks like it'll need a lot of "extra" narration relative to its
natural screen time — with:

```bash
node <this-workflow-path>/scripts/probe_boundary.js grid "<source-video>" <estimated-boundary-seconds> --out <workdir>/in/boundary_check --radius 3 --step 0.5
```

then look at the resulting frames to find the exact second content changes.
**This is the highest-value accuracy step in the whole workflow** — a coarse
sampling grid alone has been found to be wrong by 3-10 seconds on real
recordings, which causes narration to play over the wrong visual once a
scene gets extended. See `references/LESSONS.md` #1.

Also watch for **nested cutaways** — a brief aside inside a longer scene
(e.g. switching to an email client to show a real notification, then
switching back) rather than a clean scene boundary. Don't assume scenes
partition the timeline cleanly; verify with real frames (`LESSONS.md` #2).

Write the result to `<workdir>/in/shot_list.json`:

```json
{
  "scenes": [
    { "naturalStart": 0, "description": "Empty dashboard, all-zero stats, sidebar nav visible" },
    { "naturalStart": 7.5, "description": "Upload screen, drag-drop zone, supported format badges" }
  ]
}
```

### 3. Write the narration script

Using the shot list's descriptions, write `<workdir>/in/narration.txt`. See
[`examples/example-narration.txt`](examples/example-narration.txt) for the
exact format (content is illustrative only — write fresh from the actual
shot list every time). Format:

```
[<naturalStart>]
Prose for this scene — can be multiple sentences, wraps across lines.

[<next naturalStart>]
Next scene's prose.
```

Guidance, not rigid rules:
- Write at a pace a demo voiceover actually sounds good at (~2-2.3
  words/sec is typical for clear, unhurried narration) — don't pad or
  compress to hit a time budget per scene. The video-build step adapts
  footage to match what you write, so there's no need to force word counts.
- Use real specifics from the shot list (actual numbers, labels, names) —
  reads far more credible than generic language, and makes sync *feel*
  right even if a cut lands a second or two off.
- Fine to narrate real "under the hood" context that isn't visible on screen
  (e.g. how a backend job queue works, while a processing/log screen is
  showing) — just don't claim a specific on-screen action is happening if it
  isn't.
- One shot-list line per narration scene is a reasonable default; merge
  trivial back-to-back UI beats into one scene if there's not enough
  distinct content to say about each separately.

### 4. Synthesize the narration as one continuous take

```bash
cd <workdir>
node <this-workflow-path>/scripts/synthesize_narration.js in/narration.txt . --voice <VOICE_ID> --model <MODEL_ID>
```

Checks ElevenLabs quota first and fails clearly with `quota_exceeded` rather
than burning a partial call if the script is too long for what's left (see
`LESSONS.md` #5 for what to do about that). Falls back automatically to
chunked synthesis (fewest possible large chunks, not per-scene) if the model
rejects one big call — see `LESSONS.md` #3 for why per-scene calls should be
avoided in the first place (they produce audible tone jumps; some models,
confirmed for `eleven_v3`, don't support the stitching fields that would fix
that).

Output: `in/master_voiceover.mp3` + `in/scenes_timed.json` — real measured
per-scene timing from TTS character alignment. This is what actually drives
the video build in the next step, not the nominal cue times in the script.

### 5. Build `boundaries.json` and build the video

From the shot list's `naturalStart` values (refined in step 2), write
`<workdir>/in/boundaries.json` — see
[`examples/example-boundaries.json`](examples/example-boundaries.json):

```json
{ "naturalStarts": [0, 7.5, 15, 24.5, "..."] }
```

One entry per scene, same order as the narration script. Then:

```bash
node <this-workflow-path>/scripts/build_video.js "<source-video>" <workdir> <workdir>/in/boundaries.json
```

Add `--crossfade 0.35` for a short dissolve between every cut instead of
hard cuts, if the user wants smoother-feeling transitions — optional, hard
cuts are fine for UI demos.

Prints a per-scene report (`extended`/`trimmed` seconds). Scan it for any
scene with a surprisingly large `extended` value — that often means the
boundary estimate was actually wrong, not that the scene genuinely needed
that much held time (`LESSONS.md` #7).

### 6. Verify automatically — don't eyeball it

```bash
node <this-workflow-path>/scripts/verify_video.js <workdir>/out/<name>-narrated.mp4 --max-gap 2
```

Hard gate, not a suggestion: if `ok: false`, look at `violatingGaps` or
`durationsMatch` and go fix the actual cause (usually a boundary that needs
re-checking, or a scene whose narration doesn't fit its screen time well)
rather than re-running the same build. Only report the video as done once
this passes.

Optional extra insurance: extract single frames
(`ffmpeg -ss T -i out.mp4 -frames:v 1 check.jpg`) at scene boundaries that
got extended a lot and look at them — cheap protection against the "held
frame shows the wrong scene" failure mode.

### 7. Report back

Give the user the output path, final duration vs. source duration (the
video usually gets *longer* — scenes get extended to fit narration, that's
expected, not a bug), and the verify report's summary.

## Swapping the TTS provider

`scripts/synthesize_narration.js` is written against ElevenLabs' API
specifically (its with-timestamps endpoint + character alignment is what
makes precise scene timing possible without per-scene calls). To use a
different provider, the contract to preserve is:

1. Synthesize the *entire* script as few calls as possible (ideally one).
2. Get back, or derive, character- or word-level timing so you can compute
   each scene's `[startTime, endTime]` within that audio.
3. Write `<workdir>/in/master_voiceover.<ext>` +
   `<workdir>/in/scenes_timed.json` in the same shape this script produces —
   `build_video.js` and `verify_video.js` don't care which provider made
   them.

## File reference

```
scripts/
  init_workdir.js          - sets up in/ and out/, coarse frame extraction
  probe_boundary.js        - fine-grained scene-cut timestamp verification
  synthesize_narration.js  - ElevenLabs TTS, one continuous take + alignment
  build_video.js           - trim/freeze-extend/concat/mux to match audio
  verify_video.js          - automated duration + silence-gap check
  lib/
    ffmpeg-paths.js        - cross-platform ffmpeg/ffprobe discovery
    env.js                 - minimal .env-style loader (no dependency)
    segments.js            - parses the [cue] narration script format
references/
  LESSONS.md                - failure modes hit building this, and the fix
examples/
  example-narration.txt     - illustrative narration script format
  example-boundaries.json   - matching illustrative boundaries.json
```
