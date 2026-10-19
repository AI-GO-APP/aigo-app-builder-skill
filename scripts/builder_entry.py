"""Expand the Builder knowledge template using only the standard library."""
import argparse
import sys
from pathlib import Path

BEGIN = '<!-- shared-rules:begin -->'
END = '<!-- shared-rules:end -->'
INCLUDE = '<!-- include: SKILL.md#shared-rules -->'


def extract_shared_rules(text: str) -> str:
    """Return the shared block without markers; reject ambiguous boundaries."""
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError('expected exactly one shared-rules marker pair')
    begin = text.index(BEGIN) + len(BEGIN)
    end = text.index(END)
    if end < begin:
        raise ValueError('shared-rules end marker precedes begin marker')
    return text[begin:end].strip()


def render_entry(root: Path) -> str:
    """Render ENTRY.md without changing any source files."""
    entry = (root / 'builder/ENTRY.md').read_text(encoding='utf-8')
    if entry.splitlines().count(INCLUDE) != 1 or entry.count(INCLUDE) != 1:
        raise ValueError('expected exactly one standalone shared-rules include line')
    block = extract_shared_rules((root / 'SKILL.md').read_text(encoding='utf-8'))
    return entry.replace(INCLUDE, block).rstrip() + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out', type=Path, help='Explicit output file; otherwise stdout')
    args = parser.parse_args(argv)
    try:
        rendered = render_entry(args.root)
        if args.out is not None:
            args.out.write_text(rendered, encoding='utf-8')
        else:
            sys.stdout.write(rendered)
    except (OSError, ValueError) as error:
        parser.exit(1, f'{parser.prog}: {error}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
