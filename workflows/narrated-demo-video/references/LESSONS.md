# Lessons learned (read this if something looks wrong)

These came from building and debugging this pipeline end-to-end on a real
multi-minute product demo video, including two full redo cycles after the
first two attempts had real, user-visible defects. If a build's output has
sync problems, tone problems, or awkward pacing, the cause is almost always
one of these.

## 1. Coarse frame sampling is not enough to place cuts

A 2-3 second sampling grid gives a good *overview* of what's in the video,
but real UI transitions (a nav click, a modal closing, a tab switching) can
land anywhere inside that gap. On a real run, boundaries estimated from a
2.5s grid were later found to be off by 3-10 seconds from the true cut -
enough that narration about one screen was playing over a frozen frame of a
*different* screen after the video-build step extended that scene.

**Fix:** after drafting a scene list from the coarse pass, run
`probe_boundary.js grid <video> <estimated-boundary>` for every boundary that
matters (definitely for any scene likely to need a large freeze-hold
extension - those are the highest-risk ones) and look at the actual frames
before locking in `naturalStarts` values in `boundaries.json`. This costs a
handful of extra frame reads per boundary; it is much cheaper than shipping
a video with visibly wrong sync and redoing the whole build.

`probe_boundary.js scan` (ffmpeg scene-detection) can suggest candidates
automatically, but for single-page-app screen recordings it's noisy: a
cursor move or scroll can register as a bigger pixel delta than a low-contrast
content swap, so treat its output as candidates to check with `grid` mode,
not ground truth.

## 2. Scenes are not always a clean partition of the timeline

Don't assume the video's scenes are strictly back-to-back. A short "proof"
cutaway (e.g. briefly switching to an email client to show a real
notification arrived, then switching back to the main app) can be *nested*
inside a longer scene rather than being cleanly between two others. If you
build `naturalStarts` assuming clean partitioning, a nested cutaway either
gets skipped entirely or - worse - gets picked up as a boundary's "natural
footage" when it's actually a two-second aside in the middle of something
else. Verify actual scene order by looking at real frames around anything
that seems like it might be a cutaway, don't infer it from earlier context.

## 3. Per-scene TTS calls produce audible tone jumps

Splitting narration into one ElevenLabs call per scene is tempting because
it maps cleanly onto the video-build step, but it sounds wrong: each call is
an independently-directed take, so pacing/energy/emphasis shift at every
cut, especially with expressive voices. ElevenLabs' request-stitching
(`previous_request_ids`, `previous_text`, `next_text`) exists to smooth
exactly this - but **not every model supports it**. `eleven_v3` rejects
those fields outright with a 400 `unsupported_model` error. Don't silently
retry per-segment on that error; treat it as confirmation to synthesize the
whole script as one continuous take (or as few large chunks as the account's
quota/model length limit allows) and use the with-timestamps endpoint's
character alignment to recover per-scene timing after the fact. This is what
`synthesize_narration.js` does automatically.

## 4. Gaps come from the video-build step, not from padding

Don't try to solve "narration shouldn't pause" by inserting silence of a
fixed length between segments - that's solving the wrong side of the sync
problem. If every scene's video clip is sized to *exactly* match that
scene's real narration duration (trim if the footage is longer than needed,
freeze-hold the last frame if it's shorter), and scenes are then
concatenated with the one continuous voiceover laid on top unmodified, gaps
between narrated beats end up bounded by nothing but the natural pauses
already in the recording - typically well under a second, always well under
a "2 second max" kind of requirement, with no separate gap-management logic
needed. `verify_video.js` should confirm this with `silencedetect`, not a
visual/audio spot-check by the model.

## 5. ElevenLabs is billed per character - check quota before a big call

A several-minute video's narration script can be several thousand
characters. `synthesize_narration.js` checks `/v1/user/subscription` before
attempting synthesis and refuses with a clear `quota_exceeded` report rather
than burning a partial call. If quota is short, the options are: top up
credits, trim the script, or accept chunked synthesis (still far better than
per-scene: fewest possible large chunks, not one-per-scene).

## 6. ffmpeg/ffprobe binary discovery on Windows

`ffmpeg`/`ffprobe` are often not on `PATH` on Windows even when installed
(e.g. via winget). `lib/ffmpeg-paths.js` tries, in order: an explicit
`FFMPEG_BIN`/`FFPROBE_BIN` env var, the bare command, then probes common
install locations (including winget's versioned package directory, which it
globs for rather than hardcoding a version). If binary discovery still
fails on someone's machine, the fix is to add their install pattern to that
file, not to hardcode a path in one script.

## 7. How the video-build math works (for debugging a `build_video.js` report)

For scene `i`: `naturalAvailable = naturalStarts[i+1] - naturalStarts[i]`
(or `sourceDuration - naturalStarts[i]` for the last scene). `target` is how
long that scene's narration actually took, read from
`scenes_timed.json` (which came from the TTS alignment - real measured time,
not an estimate). If `target > naturalAvailable`, the scene gets a
freeze-frame extension of `target - naturalAvailable` seconds. If
`target < naturalAvailable`, the clip is trimmed down to `target` (from the
start of its natural window - the "extra" natural footage at the tail is
simply not used, on the assumption it was dead/idle time; if that assumption
is wrong for a given scene - i.e. important content sits *late* in the
natural window - narrow `naturalStarts[i]` for that scene to start right
before the important part rather than at the scene's earliest possible
frame).

A scene with a very large `extended` value is a sign either the narration
for that beat is too rich for how little screen time it naturally got (fine
- that's what the freeze-hold is for), or that the boundary estimate is
wrong and the scene's *real* natural window is bigger than assumed (go
re-check with `probe_boundary.js grid`).
