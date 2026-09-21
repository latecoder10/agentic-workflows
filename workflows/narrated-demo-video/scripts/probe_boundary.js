/**
 * Refines scene-cut timestamps. Coarse sampling (e.g. every 2.5s) is not
 * accurate enough to sync narration to visuals - real cuts have been found
 * up to 3-10s off from a coarse grid. Use this BEFORE finalizing a scene
 * list, for every boundary (especially ones that will need a large
 * freeze-frame extension - getting those right matters most).
 *
 * Two modes:
 *
 *   node probe_boundary.js scan <video> [--min 0.08] [--max 400]
 *     Runs ffmpeg scene-detection across the whole video (or a [min,max]
 *     window) and prints candidate cut timestamps. Good for an automated
 *     first pass, but noisy for single-page-app screen recordings where a
 *     nav change can have a smaller pixel delta than a mouse move - treat
 *     results as candidates, not ground truth.
 *
 *   node probe_boundary.js grid <video> <center> [--radius 3] [--step 0.5] [--out dir]
 *     Extracts one frame every <step> seconds in [center-radius, center+radius]
 *     to a directory, so you can look at them directly (Read tool) and find
 *     the exact second a cut happens. This is the reliable method - use it
 *     for every boundary that matters before locking in your scene list.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { getFfmpegPath } from './lib/ffmpeg-paths.js';

function scan(video, opts) {
    const ffmpeg = getFfmpegPath();
    const min = opts.min ?? 0.15;
    const trimArgs = [];
    if (opts.minTime !== undefined) trimArgs.push('-ss', String(opts.minTime));
    if (opts.maxTime !== undefined) trimArgs.push('-to', String(opts.maxTime));

    const logFile = path.join(opts.outDir || '.', 'scene_scan.log');
    fs.mkdirSync(path.dirname(logFile), { recursive: true });

    try {
        execFileSync(ffmpeg, [
            ...trimArgs, '-i', video,
            '-filter:v', `select='gt(scene,${min})',showinfo`,
            '-f', 'null', '-',
        ], { stdio: ['ignore', 'ignore', fs.openSync(logFile, 'w')] });
    } catch {
        // ffmpeg with -f null often exits non-zero on some builds even on success; log is what matters.
    }

    const log = fs.readFileSync(logFile, 'utf8');
    const times = [...log.matchAll(/pts_time:([0-9.]+)/g)].map((m) => parseFloat(m[1]));
    fs.unlinkSync(logFile);

    console.log(JSON.stringify({
        ok: true,
        mode: 'scan',
        threshold: min,
        candidateCutTimes: times,
        note: 'Candidates only - screen recordings of apps can produce false positives (scroll/cursor) and miss low-contrast nav changes. Cross-check with `grid` mode around each real boundary you care about.',
    }, null, 2));
}

function grid(video, center, opts) {
    const ffmpeg = getFfmpegPath();
    const radius = opts.radius ?? 3;
    const step = opts.step ?? 0.5;
    const outDir = opts.outDir || path.join('.', `boundary_${center}`);
    fs.mkdirSync(outDir, { recursive: true });

    const start = Math.max(0, center - radius);
    const timestamps = [];
    for (let t = start; t <= center + radius; t += step) timestamps.push(Math.round(t * 1000) / 1000);

    const files = [];
    for (const t of timestamps) {
        const file = path.join(outDir, `t_${t.toFixed(2)}.jpg`);
        execFileSync(ffmpeg, [
            '-y', '-ss', String(t), '-i', video,
            '-frames:v', '1', '-q:v', '4', file,
        ], { stdio: ['ignore', 'ignore', 'ignore'] });
        files.push({ t, file: path.resolve(file) });
    }

    console.log(JSON.stringify({
        ok: true,
        mode: 'grid',
        center,
        radius,
        step,
        frames: files,
        nextStep: 'Read these image files directly to find the exact timestamp where content changes.',
    }, null, 2));
}

function parseFlags(argv) {
    const flags = {};
    for (let i = 0; i < argv.length; i++) {
        if (argv[i].startsWith('--')) {
            flags[argv[i].slice(2)] = argv[i + 1];
            i++;
        }
    }
    return flags;
}

function main() {
    const [mode, video, arg3, ...rest] = process.argv.slice(2);
    if (!mode || !video) {
        console.error('Usage:\n  node probe_boundary.js scan <video> [--min 0.08] [--minTime S] [--maxTime S]\n  node probe_boundary.js grid <video> <center> [--radius 3] [--step 0.5] [--out dir]');
        process.exit(1);
    }
    const flags = parseFlags(mode === 'grid' ? rest : [arg3, ...rest]);

    if (mode === 'scan') {
        scan(video, {
            min: flags.min ? parseFloat(flags.min) : undefined,
            minTime: flags.minTime ? parseFloat(flags.minTime) : undefined,
            maxTime: flags.maxTime ? parseFloat(flags.maxTime) : undefined,
            outDir: flags.out,
        });
    } else if (mode === 'grid') {
        const center = parseFloat(arg3);
        if (Number.isNaN(center)) {
            console.error('grid mode requires a numeric <center> timestamp');
            process.exit(1);
        }
        grid(video, center, {
            radius: flags.radius ? parseFloat(flags.radius) : undefined,
            step: flags.step ? parseFloat(flags.step) : undefined,
            outDir: flags.out,
        });
    } else {
        console.error(`Unknown mode: ${mode} (expected "scan" or "grid")`);
        process.exit(1);
    }
}

main();
