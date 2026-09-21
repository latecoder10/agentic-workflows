/**
 * Builds the final narrated video: sizes every scene's video clip to exactly
 * match its narration's real duration (trimming footage that runs long,
 * freeze-holding the last frame for footage that runs short), concatenates
 * them, and lays the single continuous voiceover (from synthesize_narration.js)
 * on top unmodified.
 *
 * This is what makes sync and "no dead air" hold simultaneously: there's no
 * separate silence-padding step because the video is built to match the
 * audio's real timing, not the other way around. Gaps between narrated beats
 * are then bounded only by natural sentence pauses already baked into one
 * continuous take.
 *
 * Usage:
 *   node build_video.js <source-video> <workdir> <boundaries.json> [--crossfade 0]
 *
 * boundaries.json format (one entry per scene, SAME ORDER as the narration
 * script / scenes_timed.json):
 *   { "naturalStarts": [0, 7.5, 15, 24.5, ...] }
 * naturalStarts[i] is where scene i's footage begins in the SOURCE video;
 * naturalStarts[i+1] (or the source video's total duration, for the last
 * scene) is where it ends. Get these from frame review + probe_boundary.js -
 * do not guess from a coarse sampling grid alone (see references/LESSONS.md).
 *
 * --crossfade N adds an N-second crossfade dissolve between every cut
 * (default 0 = hard cuts, which is fine and often preferable for UI demos).
 *
 * Writes <workdir>/out/<source-video-basename>-narrated.mp4 and prints a
 * JSON build report (per-scene trim/extend amounts) to stdout.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { getFfmpegPath, durationOf } from './lib/ffmpeg-paths.js';

function parseArgs(argv) {
    const args = { crossfade: 0 };
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--crossfade') args.crossfade = parseFloat(argv[++i]);
        else if (a === '--out') args.outFile = argv[++i];
        else positional.push(a);
    }
    if (!positional[0] || !positional[1] || !positional[2]) {
        console.error('Usage: node build_video.js <source-video> <workdir> <boundaries.json> [--crossfade 0] [--out path]');
        process.exit(1);
    }
    args.sourceVideo = path.resolve(positional[0]);
    args.workdir = positional[1];
    args.boundariesFile = positional[2];
    return args;
}

function buildTrimHoldFilter(scenes, naturalStarts, sourceDuration) {
    const filterParts = [];
    const labels = [];
    const report = [];

    for (let i = 0; i < scenes.length; i++) {
        const srcStart = naturalStarts[i];
        const srcEndNatural = i + 1 < naturalStarts.length ? naturalStarts[i + 1] : sourceDuration;
        const naturalAvailable = srcEndNatural - srcStart;
        const target = scenes[i].target;
        const useFromSource = Math.min(naturalAvailable, target);
        const extend = Math.max(0, target - naturalAvailable);

        const label = `s${i}`;
        labels.push(label);
        let chain = `[0:v]trim=start=${srcStart.toFixed(3)}:duration=${useFromSource.toFixed(3)},setpts=PTS-STARTPTS`;
        if (extend > 0) chain += `,tpad=stop_mode=clone:stop_duration=${extend.toFixed(3)}`;
        chain += `[${label}]`;
        filterParts.push(chain);

        report.push({
            scene: i,
            naturalAvailable: Math.round(naturalAvailable * 10) / 10,
            target: Math.round(target * 10) / 10,
            extended: extend > 0 ? Math.round(extend * 10) / 10 : 0,
            trimmed: extend === 0 ? Math.round((naturalAvailable - target) * 10) / 10 : 0,
        });
    }

    return { filterParts, labels, report };
}

function buildConcatOrCrossfade(labels, report, crossfade) {
    if (!crossfade || crossfade <= 0) {
        const inputs = labels.map((l) => `[${l}]`).join('');
        return `${inputs}concat=n=${labels.length}:v=1:a=0[vout]`;
    }

    // Chain xfade between consecutive labeled clips. Each xfade shortens the
    // running total by `crossfade` seconds, so offsets must account for that.
    let chain = '';
    let prev = labels[0];
    let cumulative = report[0].target; // duration of the plain first clip
    for (let i = 1; i < labels.length; i++) {
        const outLabel = i === labels.length - 1 ? 'vout' : `x${i}`;
        const offset = Math.max(0, cumulative - crossfade);
        chain += `[${prev}][${labels[i]}]xfade=transition=fade:duration=${crossfade}:offset=${offset.toFixed(3)}[${outLabel}];`;
        cumulative = offset + report[i].target; // next clip's own duration
        prev = outLabel;
    }
    return chain.replace(/;$/, '');
}

function main() {
    const { sourceVideo, workdir, boundariesFile, crossfade, outFile } = parseArgs(process.argv.slice(2));

    const scenesTimedPath = path.join(workdir, 'in', 'scenes_timed.json');
    if (!fs.existsSync(scenesTimedPath)) {
        console.error(`Missing ${scenesTimedPath}. Run synthesize_narration.js first.`);
        process.exit(1);
    }
    const { masterAudio, scenes: timedScenes } = JSON.parse(fs.readFileSync(scenesTimedPath, 'utf8'));
    const { naturalStarts } = JSON.parse(fs.readFileSync(boundariesFile, 'utf8'));

    if (naturalStarts.length !== timedScenes.length) {
        console.error(`Scene count mismatch: narration has ${timedScenes.length} scenes, boundaries.json has ${naturalStarts.length}.`);
        process.exit(1);
    }

    const sourceDuration = durationOf(sourceVideo);
    const totalAudioDuration = durationOf(masterAudio);

    // Target duration per scene = time until the next scene starts in the
    // continuous audio timeline (keeps cuts locked to the audio's real
    // cadence, including its natural inter-sentence pauses).
    const scenes = timedScenes.map((s, i) => {
        const nextStart = i + 1 < timedScenes.length ? timedScenes[i + 1].startTime : totalAudioDuration;
        return { ...s, target: nextStart - s.startTime };
    });

    const { filterParts, labels, report } = buildTrimHoldFilter(scenes, naturalStarts, sourceDuration);
    filterParts.push(buildConcatOrCrossfade(labels, report, crossfade));
    const filterComplex = filterParts.join(';\n');

    const outDir = path.join(workdir, 'out');
    fs.mkdirSync(outDir, { recursive: true });
    const videoOut = outFile
        ? path.resolve(outFile)
        : path.join(outDir, `${path.basename(sourceVideo, path.extname(sourceVideo))}-narrated.mp4`);

    const ffmpeg = getFfmpegPath();
    const args = [
        '-y',
        '-i', sourceVideo,
        '-i', masterAudio,
        '-filter_complex', filterComplex,
        '-map', '[vout]',
        '-map', '1:a:0',
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest',
        videoOut,
    ];

    execFileSync(ffmpeg, args, { stdio: ['ignore', 'ignore', 'pipe'] });

    console.log(JSON.stringify({
        ok: true,
        output: path.resolve(videoOut),
        sourceDuration: Math.round(sourceDuration * 10) / 10,
        finalDuration: Math.round(totalAudioDuration * 10) / 10,
        crossfade,
        perScene: report,
        nextStep: 'Run verify_video.js to confirm sync + gap thresholds automatically before considering this done.',
    }, null, 2));
}

main();
