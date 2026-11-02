export interface LedPosition { id: number; x: number; y: number; }

export function parseLedPositions(text: string, width: number, height: number): LedPosition[] {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 8 || height < 8 ||
      width > 64 || height > 64 || width * height > 2048) {
    throw new Error('Canvas dimensions must be 8–64, with at most 2048 cells. Pad smaller shapes with empty cells.');
  }
  const ids = new Set<number>(), coordinates = new Set<string>();
  const entries: LedPosition[] = [];
  for (const [index, raw] of text.split(/\r?\n/).entries()) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const match = /^(\d+)\s*:\s*(\d+)\s*,\s*(\d+)$/.exec(line);
    if (!match) throw new Error(`Line ${index + 1}: use ID:x,y, for example 7:0,1.`);
    const [id, x, y] = match.slice(1).map(Number);
    if (id < 1 || id > 200 || x >= width || y >= height) throw new Error(`Line ${index + 1}: slot or coordinate is outside the allowed range.`);
    if (ids.has(id)) throw new Error(`Line ${index + 1}: slot ${id} is assigned twice.`);
    if (coordinates.has(`${x},${y}`)) throw new Error(`Line ${index + 1}: coordinate ${x},${y} is assigned twice.`);
    ids.add(id); coordinates.add(`${x},${y}`); entries.push({id, x, y});
  }
  return entries.sort((a, b) => a.id - b.id);
}

export function formatLedPositions(entries: LedPosition[]): string {
  return [...entries].sort((a, b) => a.id - b.id).map(({id, x, y}) => `${id}:${x},${y}`).join('\n');
}
