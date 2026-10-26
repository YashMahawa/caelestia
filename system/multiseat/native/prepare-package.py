#!/usr/bin/env python3
"""Package the exact locally validated optimized binary; never rebuild as root."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
REPO = Path.home()/'caelestia-repo-work/hyprland-multiseat'
BINARY = REPO/'build-native/Hyprland'
ABI_PACKAGES = ['aquamarine','hyprutils','hyprgraphics','hyprcursor','hyprlang']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source, target, mode=0o644):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    target.chmod(mode)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=json.loads(args.report.read_text())
    if not report.get('passed') or report.get('binarySha256') != sha(BINARY):
        raise SystemExit('The current binary must pass the integration test before packaging')
    version=json.loads(subprocess.run([str(BINARY),'--version-json'],check=True,capture_output=True,text=True).stdout)
    cache=(REPO/'build-native/CMakeCache.txt').read_text()
    if 'CMAKE_BUILD_TYPE:STRING=Release' not in cache or not re.search(r'^WITH_TESTS:[^=]+=OFF$',cache,re.M):
        raise SystemExit('Expected an optimized build without test coverage')
    if version.get('commit') != report['version'].get('commit'):
        raise SystemExit('The validated build version does not match')
    commit=version['commit']
    head=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True,check=True).stdout.strip()
    dirty=subprocess.run(['git','status','--porcelain'],cwd=REPO,capture_output=True,text=True,check=True).stdout.strip()
    if commit != head or dirty or version.get('dirty') or 'debug' in version.get('flags',[]):
        raise SystemExit('Only a clean, committed, optimized build can be packaged')
    if not re.fullmatch(r'[0-9a-f]{40}',commit):
        raise SystemExit('Expected a unique source commit')
    packages={}
    for name in ABI_PACKAGES:
        packages[name]=subprocess.run(['pacman','-Q',name],capture_output=True,text=True,check=True).stdout.split(maxsplit=1)[1].strip()
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    payload=output/'payload'
    if payload.exists():
        shutil.rmtree(payload)
    prefix=payload/'usr/lib/caelestia-hyprland-native'
    copy(BINARY,prefix/'bin/Hyprland',0o755)
    for asset in (REPO/'assets/install').rglob('*'):
        if asset.is_file():
            copy(asset,prefix/'share/hypr'/asset.name)
    copy(REPO/'example/hyprland.lua',prefix/'share/hypr/hyprland.lua')
    copy(REPO/'meta/hl.meta.lua',prefix/'share/hypr/stubs/hl.meta.lua')
    manifest={'commit':commit,'binarySha256':report['binarySha256'],'abiPackages':packages,'builtAt':time.time(),
              'validation':report['checks'],'source':str(REPO)}
    (prefix/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    copy(HERE/'start-caelestia-native',payload/'usr/bin/start-caelestia-native',0o755)
    copy(HERE/'caelestia-native.desktop',payload/'usr/share/wayland-sessions/caelestia-native.desktop')
    copy(REPO/'LICENSE',payload/'usr/share/licenses/caelestia-hyprland-native/LICENSE')
    copy(HERE/'README.md',payload/'usr/share/doc/caelestia-hyprland-native/README.md')
    copy(REPO/'docs/native-multiseat.md',payload/'usr/share/doc/caelestia-hyprland-native/implementation.md')
    with tarfile.open(output/'payload.tar','w') as archive:
        archive.add(payload,arcname='payload')
    pkgver=f"0.56.2.r{int(version['commits'])}.g{commit[:8]}"
    (output/'PKGBUILD').write_text(f'''pkgname=caelestia-hyprland-native
pkgver={pkgver}
pkgrel=1
pkgdesc='Locally validated Hyprland native logical multiseat, installed beside stock'
arch=('x86_64')
license=('BSD-3-Clause')
depends=('hyprland' 'python' 'xcb-util-errors' 'libinput' 'libxcb' 'wayland>=1.26.0')
options=('!strip' '!debug')
source=('payload.tar')
sha256sums=('{sha(output/'payload.tar')}')
package() {{
    cp -a "$srcdir/payload/." "$pkgdir/"
}}
''')
    print(json.dumps({'directory':str(output),'pkgver':pkgver,'binarySha256':manifest['binarySha256']},indent=2))


if __name__=='__main__':
    main()
