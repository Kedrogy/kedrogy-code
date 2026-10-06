"""Inspect every image layer for private files and known secret values.

Load secret environment variables before invoking this script. Findings contain
paths only; matched values are never printed. Generic short passwords cannot be
reliably detected by byte matching and are covered by configuration checks.
"""
import argparse
import ast
import gzip
import io
import json
import os
import subprocess
import tarfile


def secrets_to_check() -> list[bytes]:
    values = {value for key, value in os.environ.items()
              if any(word in key for word in ('PASSWORD', 'SECRET', 'TOKEN', 'UV_INDEX_')) and len(value) >= 16}
    original = subprocess.check_output(['git', 'show', 'HEAD:mysite/src/mysite/settings.py'], text=True)
    for node in ast.walk(ast.parse(original)):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SECRET_KEY' for t in node.targets):
            values.add(ast.literal_eval(node.value))
    import re
    original = subprocess.check_output(['git', 'show', 'HEAD:kedrogy/src/kedrogy/templates_k8s/prodigy.yaml.jinja'], text=True)
    values.update(re.findall(r'\b[a-f0-9]{56,64}\b', original))
    return [value.encode() for value in values if value]


def contains_secret(file, needles) -> bool:
    tail = b''
    overlap = max(map(len, needles), default=1) - 1
    found = False
    while chunk := file.read(1024 * 1024):
        content = tail + chunk
        found = found or any(needle in content for needle in needles)
        tail = content[-overlap:] if overlap else b''
    return found


def audit(image: str) -> dict:
    """Stream Docker's OCI archive and inspect layer tars, history and config."""
    needles = secrets_to_check()
    findings = []
    layers = 0
    files = 0
    process = subprocess.Popen(['docker', 'image', 'save', image], stdout=subprocess.PIPE)
    with process, tarfile.open(fileobj=process.stdout, mode='r|*') as archive:
        for member in archive:
            if not member.isfile():
                continue
            source = archive.extractfile(member)
            # Docker exports OCI blobs; compressed tar blobs are filesystem layers.
            buffer = io.BufferedReader(source)
            first = buffer.peek(512)
            is_gzip = first[:2] == b'\x1f\x8b'
            is_tar = len(first) > 265 and first[257:262] == b'ustar'
            if is_gzip or is_tar or member.name.endswith('/layer.tar'):
                layers += 1
                reader = gzip.GzipFile(fileobj=buffer) if is_gzip else buffer
                with tarfile.open(fileobj=reader, mode='r|') as layer:
                    for item in layer:
                        path = item.name
                        components = path.split('/')
                        if '.git' in components or any(p == '.env' or (p.startswith('.env.') and p != '.env.example') for p in components):
                            findings.append({'kind': 'private-path', 'path': path})
                        if item.isfile():
                            files += 1
                            if contains_secret(layer.extractfile(item), needles):
                                findings.append({'kind': 'secret-value', 'path': path})
            elif contains_secret(buffer, needles):
                findings.append({'kind': 'secret-in-metadata', 'path': member.name})
    if process.returncode:
        raise RuntimeError('docker image save failed')
    return {'image': image, 'layers': layers, 'files': files, 'checked_secret_values': len(needles), 'findings': findings}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image')
    args = parser.parse_args()
    result = audit(args.image)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['findings']))
