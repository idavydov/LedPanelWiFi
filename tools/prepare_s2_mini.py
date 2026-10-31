"""Unpack the repository's pinned libraries for the S2 build (no downloads)."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
source = root / 'libraries' / 'для esp8266 core 3.1.2 FastLed 3.6.0'
destination = root / '.pio' / 'vendor' / 's2_mini'
destination.mkdir(parents=True, exist_ok=True)
for filename in ('FastLED.zip', 'ESPAsyncWebServer.zip'):
    with zipfile.ZipFile(source / filename) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError(f'Unsafe archive path: {member.filename}')
        archive.extractall(destination)
    print(f'Prepared {filename} in {destination.relative_to(root)}')
