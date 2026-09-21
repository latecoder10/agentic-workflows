/**
 * Synthesises a narration script as ONE continuous ElevenLabs take (or as few
 * chunks as possible) using the with-timestamps endpoint, and recovers each
 * scene's exact [start,end] time within the audio via character alignment.
 *
 * WHY ONE CONTINUOUS CALL, NOT ONE-PER-SCENE:
 * Synthesising each scene separately produces audible tone/energy jumps at
 * every cut - it sounds like independently-directed takes stitched together.
 * ElevenLabs has a request-stitching feature (previous_request_ids /
 * previous_text / next_text) meant to smooth exactly this, but NOT EVERY
 * MODEL SUPPORTS IT - eleven_v3 rejects those fields with a 400
 * "unsupported_model" error. This script always tries the whole script as
 * one call first; if the model/account can't handle that length, it falls
 * back to splitting into the fewest possible large chunks (still far better
 * than per-scene) rather than silently degrading to many small calls.
 *
 * Usage:
 *   node synthesize_narration.js <script.txt> <workdir> [--voice ID] [--model ID] [--stability 0.55]
 *
 * Reads ELEVENLABS_API_KEY (and optional ELEVENLABS_VOICE_ID/MODEL_ID) from
 * <workdir>/.env.local if present, else from the real environment.
 *
 * Writes:
 *   <workdir>/in/master_voiceover.mp3
 *   <workdir>/in/scenes_timed.json   - [{index, at, text, startTime, endTime, duration}, ...]
 *
 * Prints a JSON summary to stdout, including total narration length and
 * (if a scan happened) remaining ElevenLabs quota.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { loadEnv } from './lib/env.js';
import { parseSegments } from './lib/segments.js';
import { durationOf } from './lib/ffmpeg-paths.js';

function parseArgs(argv) {
    const args = { stability: 0.55, similarityBoost: 0.8 };
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--voice') args.voice = argv[++i];
        else if (a === '--model') args.model = argv[++i];
        else if (a === '--stability') args.stability = parseFloat(argv[++i]);
        else positional.push(a);
    }
    if (!positional[0] || !positional[1]) {
        console.error('Usage: node synthesize_narration.js <script.txt> <workdir> [--voice ID] [--model ID]');
        process.exit(1);
    }
    args.scriptFile = positional[0];
    args.workdir = positional[1];
    return args;
}

async function checkQuota(apiKey) {
    try {
        const res = await fetch('https://api.elevenlabs.io/v1/user/subscription', {
            headers: { 'xi-api-key': apiKey },
        });
        if (!res.ok) return null;
        const json = await res.json();
        return {
            characterLimit: json.character_limit,
            charactersUsed: json.character_count,
            remaining: json.character_limit - json.character_count,
        };
    } catch {
        return null;
    }
}

async function synthesiseWithTimestamps(text, { voice, model, stability, similarityBoost, apiKey }) {
    const url = `https://api.elevenlabs.io/v1/text-to-speech/${voice}/with-timestamps`;
    const res = await fetch(url, {
        method: 'POST',
        headers: { 'xi-api-key': apiKey, 'Content-Type': 'application/json' },
        body: JSON.stringify({
            text,
            model_id: model,
            voice_settings: { stability, similarity_boost: similarityBoost },
        }),
    });
    if (!res.ok) {
        const errText = await res.text();
        const err = new Error(`ElevenLabs API ${res.status}: ${errText}`);
        err.status = res.status;
        err.body = errText;
        throw err;
    }
    return res.json();
}

/** Splits scenes into as few contiguous chunks as possible under maxChars. */
function chunkScenes(segments, maxChars) {
    const chunks = [];
    let current = [];
    let currentLen = 0;
    for (const seg of segments) {
        const addLen = seg.text.length + 1;
        if (current.length && currentLen + addLen > maxChars) {
            chunks.push(current);
            current = [];
            currentLen = 0;
        }
        current.push(seg);
        currentLen += addLen;
    }
    if (current.length) chunks.push(current);
    return chunks;
}

function locate(haystack, needle, searchFrom, charStarts, charEnds) {
    const idx = haystack.indexOf(needle, searchFrom);
    if (idx === -1) {
        throw new Error(`Could not locate scene text in synthesised script starting at char ${searchFrom}: "${needle.slice(0, 60)}..."`);
    }
    const endIdx = idx + needle.length - 1;
    return {
        idx,
        endIdx,
        startTime: charStarts[idx],
        endTime: charEnds[Math.min(endIdx, charEnds.length - 1)],
    };
}

async function main() {
    const { scriptFile, workdir, voice: voiceArg, model: modelArg, stability, similarityBoost } = parseArgs(process.argv.slice(2));

    loadEnv(path.join(workdir, '.env.local'));
    loadEnv('.env.local');

    const apiKey = process.env.ELEVENLABS_API_KEY;
    if (!apiKey) {
        console.error('ELEVENLABS_API_KEY not set (checked <workdir>/.env.local and ./.env.local, and the real environment).');
        process.exit(1);
    }
    const voice = voiceArg || process.env.ELEVENLABS_VOICE_ID;
    const model = modelArg || process.env.ELEVENLABS_MODEL_ID || 'eleven_v3';
    if (!voice) {
        console.error('No voice ID given. Pass --voice <id> or set ELEVENLABS_VOICE_ID.');
        process.exit(1);
    }

    const segments = parseSegments(fs.readFileSync(scriptFile, 'utf8'));
    const fullScript = segments.map((s) => s.text).join(' ');

    const quota = await checkQuota(apiKey);
    if (quota && quota.remaining < fullScript.length) {
        console.error(JSON.stringify({
            ok: false,
            error: 'quota_exceeded',
            scriptLength: fullScript.length,
            quota,
            suggestion: 'Script needs more characters than the account has left. Either top up ElevenLabs credits, or trim the script, or accept chunked synthesis by re-running with a shorter script per chunk (this script auto-chunks on a 400, but not on quota errors, since quota errors need a human decision).',
        }, null, 2));
        process.exit(1);
    }

    const inDir = path.join(workdir, 'in');
    fs.mkdirSync(inDir, { recursive: true });
    const masterAudioPath = path.join(inDir, 'master_voiceover.mp3');
    const scenesTimedPath = path.join(inDir, 'scenes_timed.json');

    const synthOpts = { voice, model, stability, similarityBoost, apiKey };

    let audioBuf;
    let alignment;
    let chunked = false;

    try {
        const result = await synthesiseWithTimestamps(fullScript, synthOpts);
        audioBuf = Buffer.from(result.audio_base64, 'base64');
        alignment = result.alignment || result.normalized_alignment;
    } catch (err) {
        // Model/account rejected one big call (e.g. max length) - fall back to
        // the fewest chunks that fit, still far better than per-scene calls.
        console.error(`Single continuous call failed (${err.status || 'error'}), falling back to chunked synthesis: ${(err.body || err.message || '').slice(0, 200)}`);
        chunked = true;
        const chunks = chunkScenes(segments, 2500);
        const buffers = [];
        alignment = { characters: [], character_start_times_seconds: [], character_end_times_seconds: [] };
        let timeOffset = 0;
        let charOffset = 0;

        for (const chunk of chunks) {
            const chunkText = chunk.map((s) => s.text).join(' ');
            const result = await synthesiseWithTimestamps(chunkText, synthOpts);
            const buf = Buffer.from(result.audio_base64, 'base64');
            buffers.push(buf);

            const align = result.alignment || result.normalized_alignment;
            for (let i = 0; i < align.characters.length; i++) {
                alignment.characters.push(align.characters[i]);
                alignment.character_start_times_seconds.push(align.character_start_times_seconds[i] + timeOffset);
                alignment.character_end_times_seconds.push(align.character_end_times_seconds[i] + timeOffset);
            }
            charOffset += chunkText.length + 1;

            // Write chunk to a temp file to get its real duration (mp3 frame
            // padding means byte-length isn't a reliable time proxy).
            const tmpFile = path.join(inDir, `_chunk_tmp.mp3`);
            fs.writeFileSync(tmpFile, buf);
            timeOffset += durationOf(tmpFile);
            fs.unlinkSync(tmpFile);
        }
        audioBuf = Buffer.concat(buffers);
    }

    fs.writeFileSync(masterAudioPath, audioBuf);

    if (!alignment || !alignment.characters) {
        throw new Error('No character alignment returned - cannot compute scene timing.');
    }
    const charStarts = alignment.character_start_times_seconds;
    const charEnds = alignment.character_end_times_seconds;

    let searchFrom = 0;
    const scenes = [];
    for (let i = 0; i < segments.length; i++) {
        const seg = segments[i];
        const { idx, endIdx, startTime, endTime } = locate(fullScript, seg.text, searchFrom, charStarts, charEnds);
        scenes.push({ index: i, at: seg.at, text: seg.text, startTime, endTime, duration: endTime - startTime });
        searchFrom = endIdx + 1;
    }

    fs.writeFileSync(scenesTimedPath, JSON.stringify({ masterAudio: path.resolve(masterAudioPath), scenes }, null, 2));

    const totalAudioDuration = durationOf(masterAudioPath);

    console.log(JSON.stringify({
        ok: true,
        chunkedSynthesis: chunked,
        scriptCharacters: fullScript.length,
        scriptWords: fullScript.split(/\s+/).length,
        sceneCount: scenes.length,
        totalNarrationSeconds: totalAudioDuration,
        masterAudio: path.resolve(masterAudioPath),
        scenesTimed: path.resolve(scenesTimedPath),
        scenes: scenes.map((s) => ({ index: s.index, startTime: Math.round(s.startTime * 100) / 100, duration: Math.round(s.duration * 100) / 100, preview: s.text.slice(0, 50) })),
        nextStep: 'Run build_video.js with a scene-boundaries file mapping each scene to its natural source-footage window.',
    }, null, 2));
}

main().catch((err) => {
    console.error(JSON.stringify({ ok: false, error: err.message }, null, 2));
    process.exit(1);
});
