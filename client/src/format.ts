/** Sentinel selection value meaning "leave this Spotify track out of the export". */
export const SKIP = '__skip__';

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '?:??';
  const rounded = Math.round(seconds);
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
}
