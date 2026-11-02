"""Create a binary map for the S2 Mini's 20x10 canvas and 200 fixed slots."""
import argparse
import csv
from pathlib import Path
import struct


WIDTH, HEIGHT, SLOTS = 20, 10, 200


def encode_map(rows):
    if len(rows) != HEIGHT or any(len(row) != WIDTH for row in rows):
        raise ValueError('Expected 10 rows of 20 comma-separated indices.')
    indices = [index for row in rows for index in row]
    if any(index < -1 or index >= SLOTS for index in indices):
        raise ValueError('Use indices 0..199, or -1 for an empty position.')
    assigned = [index for index in indices if index >= 0]
    if len(assigned) != len(set(assigned)):
        raise ValueError('Each LED index may appear only once.')
    return b'\xa5\xa5' + bytes((WIDTH, HEIGHT)) + struct.pack('<200h', *indices)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, help='Top row first; indices 0..199; -1 for empty cells.')
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).resolve().parents[1] /
                        'firmware/LedPanelWiFi_v1.14/data/20x10.map')
    args = parser.parse_args()
    if args.csv:
        with args.csv.open(newline='') as source:
            rows = [[int(cell.strip()) for cell in row] for row in csv.reader(source) if row]
    else:
        # Existing parallel wiring starts at the lower left. Map files start
        # at the upper left, so the top row contains slots 180..199.
        rows = [[y * WIDTH + x for x in range(WIDTH)] for y in reversed(range(HEIGHT))]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode_map(rows))
    print(f'Wrote {args.output}: 20x10 positions, 200 fixed data slots.')


if __name__ == '__main__':
    main()
