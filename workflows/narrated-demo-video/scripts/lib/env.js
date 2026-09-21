/**
 * Minimal .env-style loader (no dotenv dependency). Reads KEY=VALUE lines,
 * ignores blank lines and #comments, and never overwrites a variable that's
 * already set in the real environment (so an explicit `FOO=x node script.js`
 * always wins over the file).
 */
import fs from 'node:fs';

export function loadEnv(envPath) {
    if (!fs.existsSync(envPath)) return;
    for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eq = trimmed.indexOf('=');
        if (eq === -1) continue;
        const key = trimmed.slice(0, eq).trim();
        const value = trimmed.slice(eq + 1).trim();
        if (!process.env[key]) process.env[key] = value;
    }
}
