"""Build an image with ephemeral BuildKit credentials and redacted output."""
import argparse
import os
import subprocess
from pathlib import Path


def build(dockerfile: str, tag: str, log_path: Path) -> int:
    """Use environment secrets without copying them into build args or files."""
    command = ['docker', 'build', '--progress=plain', '-f', dockerfile, '-t', tag]
    for short, key in [('prodigy_username', 'UV_INDEX_PRODIGY_USERNAME'), ('ysz_username', 'UV_INDEX_YSZ_USERNAME'), ('ysz_password', 'UV_INDEX_YSZ_PASSWORD')]:
        if os.environ.get(key):
            command += ['--secret', f'id={short},env={key}']
    if os.environ.get('SSH_AUTH_SOCK'):
        command += ['--ssh', 'default']
    command += ['.']
    private_values = [value for key, value in os.environ.items()
                      if any(word in key for word in ('PASSWORD', 'SECRET', 'TOKEN', 'UV_INDEX_')) and value]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('w', encoding='utf-8') as log:
        os.chmod(log_path, 0o600)
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
            for line in process.stdout:
                for value in private_values:
                    line = line.replace(value, '[redacted]')
                log.write(line)
                log.flush()
            code = process.wait()
    print(f'Build exited with status {code}; log: {log_path}')
    print('\n'.join(log_path.read_text().splitlines()[-20:]))
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dockerfile', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(build(args.dockerfile, args.tag, args.log))
