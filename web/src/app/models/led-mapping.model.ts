export interface LedPosition { string: number; id: number; x: number; y: number; }

export function parseLedPositions(text: string, width: number, height: number): LedPosition[] {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 8 || height < 8 ||
      width > 64 || height > 64 || width * height > 2048) {
    throw new Error('Canvas dimensions must be 8–64, with at most 2048 cells. Pad smaller shapes with empty cells.');
  }
  const ids = new Set<string>(), coordinates = new Set<string>();
  const entries: LedPosition[] = [];
  for (const [index, raw] of text.split(/\r?\n/).entries()) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const match = /^([AB])?(\d+)\s*:\s*(\d+)\s*,\s*(\d+)$/i.exec(line);
    if (!match) throw new Error(`Line ${index + 1}: use A7:0,1 or B7:0,1. Plain IDs belong to A.`);
    const string = match[1]?.toUpperCase() === 'B' ? 1 : 0;
    const [id, x, y] = match.slice(2).map(Number);
    if (id < 1 || id > 200 || x >= width || y >= height) throw new Error(`Line ${index + 1}: slot or coordinate is outside the allowed range.`);
    const key = `${string}:${id}`;
    if (ids.has(key)) throw new Error(`Line ${index + 1}: slot ${string ? 'B' : 'A'}${id} is assigned twice.`);
    if (coordinates.has(`${x},${y}`)) throw new Error(`Line ${index + 1}: coordinate ${x},${y} is assigned twice.`);
    ids.add(key); coordinates.add(`${x},${y}`); entries.push({string, id, x, y});
  }
  return entries.sort((a, b) => a.string - b.string || a.id - b.id);
}

export function formatLedPositions(entries: LedPosition[]): string {
  return [...entries].sort((a, b) => a.string - b.string || a.id - b.id)
    .map(({string, id, x, y}) => `${string ? 'B' : 'A'}${id}:${x},${y}`).join('\n');
}
