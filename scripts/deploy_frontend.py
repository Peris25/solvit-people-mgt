"""Publish a CRA build to a directory-restricted FTPS account; never delete files."""
import ftplib
import hashlib
import os
from pathlib import Path
import re
import ssl
import sys
import time
from urllib.request import Request, urlopen


SITE = 'https://people.solvit.co.ke'


def build_files(root):
    root = Path(root).resolve()
    files = sorted(path for path in root.rglob('*') if path.is_file())
    if not (root / 'index.html').is_file() or not files:
        raise ValueError('Missing frontend build/index.html')
    for path in files:
        relative = path.relative_to(root)
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Build contains a symlink or external file')
        if any(part.startswith('.') for part in relative.parts) or path.suffix.lower() in {
            '.map', '.pem', '.key', '.env', '.py', '.zip', '.php', '.sql', '.xlsx', '.csv',
        }:
            raise ValueError('Build contains a forbidden file')
    # Publish index last so browsers see the old entry point until assets exist.
    return [path for path in files if path != root / 'index.html'] + [root / 'index.html']


def publish(ftp, root):
    root = Path(root).resolve()
    files = build_files(root)
    for path in files:
        parts = path.relative_to(root).parts
        ftp.cwd('/')  # FTP account MUST be jailed to public_html/people.
        for part in parts[:-1]:
            try:
                ftp.cwd(part)
            except ftplib.error_perm:
                ftp.mkd(part)
                ftp.cwd(part)
        temporary = parts[-1] + '.uploading'
        with path.open('rb') as stream:
            ftp.storbinary('STOR ' + temporary, stream)
        ftp.rename(temporary, parts[-1])
    return len(files)


def fetch(url):
    return urlopen(Request(url, headers={'Cache-Control': 'no-cache'}), timeout=30).read()


def verify(root):
    root = Path(root)
    local = (root / 'index.html').read_bytes()
    assets = re.findall(r'(?:src|href)="(/static/[^"?]+\.(?:js|css))"', local.decode('utf-8'))
    if not assets:
        raise ValueError('Build has no static JS/CSS references')
    for attempt in range(6):
        try:
            live = fetch(SITE + '/?release=' + str(time.time_ns()))
            if live != local:
                raise ValueError('Live index does not match this release')
            for asset in assets:
                expected = (root / asset.lstrip('/')).read_bytes()
                actual = fetch(SITE + asset)
                if hashlib.sha256(expected).digest() != hashlib.sha256(actual).digest():
                    raise ValueError('Live asset does not match this release')
            return
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5)


def main():
    root = Path('frontend/build')
    build_files(root)  # Validate before connecting.
    config = {key: os.environ.get(key) for key in ('FTP_HOST', 'FTP_USER', 'FTP_PASSWORD')}
    if not all(config.values()):
        raise ValueError('Missing FTPS configuration')
    context = ssl.create_default_context()
    with ftplib.FTP_TLS(context=context, timeout=60) as ftp:
        ftp.connect(config['FTP_HOST'], 21)
        ftp.login(config['FTP_USER'], config['FTP_PASSWORD'])
        ftp.prot_p()  # Encrypt data transfers as well as credentials.
        count = publish(ftp, root)
    verify(root)
    print(f'Published {count} build files; live HTML and JS/CSS verified.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Server exceptions can include host/user details. Keep CI logs generic.
        print(f'Deployment failed ({type(error).__name__}). Check configuration and hosting connectivity.', file=sys.stderr)
        sys.exit(1)
