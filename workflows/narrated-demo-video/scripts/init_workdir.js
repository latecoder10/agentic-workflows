/**
 * Sets up the per-project working directory for a narration job and does the
 * COARSE frame extraction pass for an initial overview.
 *
 * Usage:
 *   node init_workdir.js <source-video> [--workdir demo-narration] [--interval 2.5]
 *
 * Creates, under the CURRENT working directory (run this from the project
 * root you want the working folder in):
 *   <workdir>/in/frames_coarse/frame_%04d.jpg   - sampled frames for overview
 *   <workdir>/in/video_info.json                - duration/resolution/fps
 *   <workdir>/out/                               - (empty, final deliverables go here)
 *
 * Prints a JSON summary to stdout on success.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { execFileSync } from 'node:child_process';
import { getFfmpegPath, getFfprobePath } from './lib/ffmpeg-paths.js';

function parseArgs(argv) {
    const args = { workdir: 'demo-narration', interval: 2.5 };
    const positional = [];
    for (let i = 0; i < argv.length; i++) {
        const a = argv[i];
        if (a === '--workdir') args.workdir = argv[++i];
        else if (a === '--interval') args.interval = parseFloat(argv[++i]);
        else positional.push(a);
    }
    if (!positional[0]) {
        console.error('Usage: node init_workdir.js <source-video> [--workdir demo-narration] [--interval 2.5]');
        process.exit(1);
    }
    args.sourceVideo = path.resolve(positional[0]);
    return args;
}

function main() {
    const { sourceVideo, workdir, interval } = parseArgs(process.argv.slice(2));

    if (!fs.existsSync(sourceVideo)) {
        console.error(`Source video not found: ${sourceVideo}`);
        process.exit(1);
    }

    const ffmpeg = getFfmpegPath();
    const ffprobe = getFfprobePath();

    const inDir = path.join(workdir, 'in');
    const framesDir = path.join(inDir, 'frames_coarse');
    const outDir = path.join(workdir, 'out');
    fs.mkdirSync(framesDir, { recursive: true });
    fs.mkdirSync(outDir, { recursive: true });

    const probeOut = execFileSync(ffprobe, [
        '-v', 'error',
        '-show_entries', 'format=duration:stream=width,height,r_frame_rate,codec_type',
        '-of', 'json', sourceVideo,
    ], { encoding: 'utf8' });
    const probeJson = JSON.parse(probeOut);
    const duration = parseFloat(probeJson.format.duration);
    const videoStream = probeJson.streams.find((s) => s.codec_type === 'video');
    const hasAudio = probeJson.streams.some((s) => s.codec_type === 'audio');

    const videoInfo = {
        sourceVideo,
        duration,
        width: videoStream?.width,
        height: videoStream?.height,
        frameRate: videoStream?.r_frame_rate,
        hasExistingAudio: hasAudio,
        workdir: path.resolve(workdir),
    };
    fs.writeFileSync(path.join(inDir, 'video_info.json'), JSON.stringify(videoInfo, null, 2));

    // Coarse sample for an overview pass. Scale down to keep review cheap.
    execFileSync(ffmpeg, [
        '-y', '-i', sourceVideo,
        '-vf', `fps=1/${interval},scale=640:-1`,
        '-q:v', '4',
        path.join(framesDir, 'frame_%04d.jpg'),
    ], { stdio: ['ignore', 'ignore', 'pipe'] });

    const frameCount = fs.readdirSync(framesDir).filter((f) => f.endsWith('.jpg')).length;

    console.log(JSON.stringify({
        ok: true,
        videoInfo,
        framesDir: path.resolve(framesDir),
        frameCount,
        frameIntervalSeconds: interval,
        note: `frame_%04d.jpg -> timestamp = (index-1) * ${interval}s`,
        nextStep: 'Review these frames (delegate to a subagent) to build a scene list, then use probe_boundary.js to pin down exact cut times for each scene before finalizing.',
    }, null, 2));
}

main();
