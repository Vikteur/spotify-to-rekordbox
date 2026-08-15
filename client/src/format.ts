import type { ScoredCandidate } from './types';

/** Sentinel selection value meaning "leave this Spotify track out of the export". */
export const SKIP = '__skip__';

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '?:??';
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}

export function formatDelta(delta: number | null): string {
  if (delta == null) return '';
  const rounded = Math.round(delta);
  return ` (${rounded >= 0 ? '+' : '−'}${formatDuration(Math.abs(rounded))})`;
}

export function versionLabel(descriptors: string[], remixer: string | null): string {
  if (!descriptors.length) return '';
  const name = remixer ? `${remixer} ` : '';
  return `[${name}${descriptors.join('+')}]`;
}

export function candidateLabel(candidate: ScoredCandidate): string {
  const { track } = candidate;
  const version = versionLabel(candidate.version.descriptors, candidate.version.remixer);
  const analysis = [
    track.bpm ? `${Math.round(track.bpm)} BPM` : '',
    track.musical_key ?? '',
  ].filter(Boolean).join(' · ');
  const bits = [
    candidate.playlists.length ? `★ ${candidate.playlists.join(', ')}` : '',
    `${track.filename}.${track.ext}`,
    version,
    `${formatDuration(track.duration_sec)}${formatDelta(candidate.duration_delta_sec)}`,
    analysis,
    track.bitrate_kbps ? `${track.ext.toUpperCase()} ${track.bitrate_kbps}` : track.ext.toUpperCase(),
    `${Math.round(candidate.score * 100)}%`,
  ];
  return bits.filter(Boolean).join(' — ');
}

export const chipStyles: Record<string, string> = {
  auto: 'bg-green-100 text-green-800',
  remembered: 'bg-purple-100 text-purple-800',
  manual: 'bg-blue-100 text-blue-800',
  'pick one': 'bg-amber-100 text-amber-900',
  skipped: 'bg-gray-200 text-gray-600',
  'no match': 'bg-red-100 text-red-800',
};
