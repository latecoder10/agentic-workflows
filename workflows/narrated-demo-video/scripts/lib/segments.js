/**
 * Parses a narration script of the form:
 *
 *   # comment
 *   [12.5] Some narration text that can
 *   wrap across multiple lines until the
 *   next [cue] marker.
 *
 *   [30.0] Next scene's line.
 *
 * The bracketed number is a NOMINAL cue time (roughly where this beat starts
 * in the source video, for human reference / ordering) - it is not used as
 * an exact playback timestamp. Real timing comes from the TTS alignment
 * (see synthesize_narration.js), which is what actually drives the video build.
 */
export function parseSegments(raw) {
    const segments = [];
    let current = null;

    for (const line of raw.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;

        const marker = trimmed.match(/^\[(\d+(?:\.\d+)?)\]\s*(.*)$/);
        if (marker) {
            if (current) segments.push(current);
            current = { at: parseFloat(marker[1]), text: marker[2] ? marker[2].trim() : '' };
        } else if (current) {
            current.text = current.text ? `${current.text} ${trimmed}` : trimmed;
        }
    }
    if (current) segments.push(current);

    const empty = segments.find((s) => !s.text);
    if (empty) throw new Error(`Segment at [${empty.at}] has no text`);

    for (let i = 1; i < segments.length; i++) {
        if (segments[i].at <= segments[i - 1].at) {
            throw new Error(`Cue times must increase: [${segments[i - 1].at}] then [${segments[i].at}]`);
        }
    }
    return segments;
}
