/**
 * Locates ffmpeg/ffprobe binaries. Tries, in order:
 *   1. FFMPEG_BIN / FFPROBE_BIN env vars (explicit override)
 *   2. The bare command (works if on PATH)
 *   3. Common per-OS install locations (probed, not assumed)
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const WINDOWS_GUESSES = [
    'C:\\Program Files\\ffmpeg\\bin',
    'C:\\ffmpeg\\bin',
];

function wingetGuess(binName) {
    // Winget installs ffmpeg under a versioned Gyan.FFmpeg package dir; glob for it.
    try {
        const base = 'C:\\Users\\' + (process.env.USERNAME || '') +
            '\\AppData\\Local\\Microsoft\\WinGet\\Packages';
        if (!fs.existsSync(base)) return null;
        const pkgDir = fs.readdirSync(base).find((d) => d.toLowerCase().startsWith('gyan.ffmpeg'));
        if (!pkgDir) return null;
        const versionDir = fs.readdirSync(path.join(base, pkgDir))
            .find((d) => d.toLowerCase().includes('ffmpeg'));
        if (!versionDir) return null;
        return path.join(base, pkgDir, versionDir, 'bin', binName);
    } catch {
        return null;
    }
}

function probe(bin) {
    try {
        execFileSync(bin, ['-version'], { stdio: 'ignore' });
        return true;
    } catch {
        return false;
    }
}

function resolve(name, envVar) {
    const explicit = process.env[envVar];
    if (explicit && probe(explicit)) return explicit;

    if (probe(name)) return name;

    if (process.platform === 'win32') {
        const guess = wingetGuess(`${name}.exe`);
        if (guess && probe(guess)) return guess;
        for (const dir of WINDOWS_GUESSES) {
            const candidate = `${dir}\\${name}.exe`;
            if (probe(candidate)) return candidate;
        }
    } else {
        for (const dir of ['/usr/local/bin', '/opt/homebrew/bin', '/usr/bin']) {
            const candidate = `${dir}/${name}`;
            if (probe(candidate)) return candidate;
        }
    }

    throw new Error(
        `Could not locate ${name}. Install it and ensure it's on PATH, or set ${envVar} to its full path.`
    );
}

export function getFfmpegPath() {
    return resolve('ffmpeg', 'FFMPEG_BIN');
}

export function getFfprobePath() {
    return resolve('ffprobe', 'FFPROBE_BIN');
}

export function durationOf(file) {
    const ffprobe = getFfprobePath();
    const out = execFileSync(ffprobe, [
        '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file,
    ], { encoding: 'utf8' });
    return parseFloat(out.trim());
}
