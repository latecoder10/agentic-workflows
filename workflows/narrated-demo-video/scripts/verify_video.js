/**
 * Automated sanity checks for a narrated video - run this instead of
 * eyeballing waveforms. Checks:
 *   1. Video and audio stream durations match (within tolerance).
 *   2. No silence gap in the audio exceeds --max-gap seconds (default 2).
 *
 * Usage:
 *   node verify_video.js <narrated-video.mp4> [--max-gap 2] [--noise -35dB]
 *
 * Exits non-zero and prints a JSON report with ok:false if either check
 * fails, so this can gate whether the build is actually done.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { getFfmpegPath, getFfprobePath, durationOf } from './lib/ffmpeg-paths.js';

function parseArgs(argv) {
    const args = { maxGap: 2, noise: '-35dB' };
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--max-gap') args.maxGap = parseFloat(argv[++i]);
        else if (a === '--noise') args.noise = argv[++i];
        else positional.push(a);
    }
    if (!positional[0]) {
        console.error('Usage: node verify_video.js <narrated-video.mp4> [--max-gap 2] [--noise -35dB]');
        process.exit(1);
    }
    args.video = path.resolve(positional[0]);
    return args;
}

function streamDurations(video) {
    const ffprobe = getFfprobePath();
    const out = execFileSync(ffprobe, [
        '-v', 'error',
        '-show_entries', 'stream=codec_type,duration',
        '-of', 'json', video,
    ], { encoding: 'utf8' });
    const json = JSON.parse(out);
    const video_ = json.streams.find((s) => s.codec_type === 'video');
    const audio_ = json.streams.find((s) => s.codec_type === 'audio');
    return {
        video: video_ ? parseFloat(video_.duration) : null,
        audio: audio_ ? parseFloat(audio_.duration) : null,
    };
}

function findSilenceGaps(video, noise, minSilence) {
    const ffmpeg = getFfmpegPath();
    const logFile = `${video}.silence_check.log`;
    try {
        execFileSync(ffmpeg, [
            '-i', video,
            '-af', `silencedetect=noise=${noise}:d=${minSilence}`,
            '-f', 'null', '-',
        ], { stdio: ['ignore', 'ignore', fs.openSync(logFile, 'w')] });
    } catch {
        // ffmpeg -f null can exit non-zero even on success in some builds.
    }
    const log = fs.readFileSync(logFile, 'utf8');
    fs.unlinkSync(logFile);

    const gaps = [];
    const starts = [...log.matchAll(/silence_start: ([0-9.]+)/g)].map((m) => parseFloat(m[1]));
    const ends = [...log.matchAll(/silence_end: ([0-9.]+) \| silence_duration: ([0-9.]+)/g)]
        .map((m) => ({ end: parseFloat(m[1]), duration: parseFloat(m[2]) }));
    for (let i = 0; i < starts.length && i < ends.length; i++) {
        gaps.push({ start: starts[i], end: ends[i].end, duration: ends[i].duration });
    }
    return gaps;
}

function main() {
    const { video, maxGap, noise } = parseArgs(process.argv.slice(2));

    if (!fs.existsSync(video)) {
        console.error(JSON.stringify({ ok: false, error: `File not found: ${video}` }, null, 2));
        process.exit(1);
    }

    const durations = streamDurations(video);
    const durationDelta = durations.video != null && durations.audio != null
        ? Math.abs(durations.video - durations.audio)
        : null;
    const durationsMatch = durationDelta !== null && durationDelta < 0.5;

    // Scan for gaps down to a small floor (0.2s) so we can report the real
    // max, then separately flag which (if any) exceed the caller's threshold.
    const gaps = findSilenceGaps(video, noise, 0.2);
    const violations = gaps.filter((g) => g.duration > maxGap);
    const maxGapFound = gaps.reduce((m, g) => Math.max(m, g.duration), 0);

    const ok = durationsMatch && violations.length === 0;

    const report = {
        ok,
        video,
        durations,
        durationDeltaSeconds: durationDelta !== null ? Math.round(durationDelta * 1000) / 1000 : null,
        durationsMatch,
        maxAllowedGapSeconds: maxGap,
        maxGapFoundSeconds: Math.round(maxGapFound * 1000) / 1000,
        gapCount: gaps.length,
        violatingGaps: violations,
    };

    console.log(JSON.stringify(report, null, 2));
    process.exit(ok ? 0 : 1);
}

main();
