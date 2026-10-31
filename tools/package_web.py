"""Package an Angular production build for LittleFS, preserving custom data files."""
import gzip
from pathlib import Path
import re
import shutil

root = Path(__file__).resolve().parents[1]
source = root / 'web/dist/browser'
destination = root / 'firmware/LedPanelWiFi_v1.14/data/web'
if not (source / 'index.html').is_file():
    raise SystemExit('Run npm run build in web/ first.')

# Delete only old generated bundles; leave maps, backups, and custom data alone.
bundles = {path.name + '.gz' for path in source.iterdir() if path.suffix in {'.js', '.css'}}
for path in destination.iterdir():
    if re.fullmatch(r'(chunk|main|polyfills|styles)-[\w-]+\.(js|css)\.gz', path.name) and path.name not in bundles:
        path.unlink()

count = 0
for path in source.rglob('*'):
    if not path.is_file() or path.suffix == '.map':
        continue
    target = destination / path.relative_to(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix in {'.html', '.js', '.css', '.json', '.svg', '.ico', '.txt'}:
        target = target.with_name(target.name + '.gz')
        content = path.read_bytes()
        if not target.exists() or gzip.decompress(target.read_bytes()) != content:
            target.write_bytes(gzip.compress(content, compresslevel=9, mtime=0))
    else:
        if not target.exists() or target.read_bytes() != path.read_bytes():
            shutil.copyfile(path, target)
    count += 1
print(f'Packaged {count} web assets for LittleFS.')
