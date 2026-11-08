"""スキル（backend/skills/<名前>/ の Markdown）の読み込み。内容のハッシュを版として返す。"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[3] / "skills"
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    text: str  # SKILL.md → 他の .md（名前順）の順につないだ指示文
    version: str  # 内容のハッシュ（点数・整理記事と一緒に DB に記録する）


def load_skill(name: str, skills_dir: Path = SKILLS_DIR, *, shared: tuple[str, ...] = ()) -> Skill:
    """shared: skills/ 直下の共通ファイル（例: _style.md）。スキルの後ろにつなぎ、版にも含める。"""
    folder = skills_dir / name
    main = folder / "SKILL.md"
    if not main.is_file():
        raise FileNotFoundError(f"スキルが見つかりません: {main}")
    others = sorted(p for p in folder.glob("*.md") if p.name != "SKILL.md")
    parts: list[str] = []
    digest = hashlib.sha256()
    for path in [main, *others, *(skills_dir / f for f in shared)]:
        raw = path.read_text(encoding="utf-8")
        digest.update(path.name.encode() + b"\0" + raw.encode() + b"\0")
        parts.append(_FRONTMATTER.sub("", raw, count=1).strip())
    return Skill(name=name, text="\n\n".join(parts), version=digest.hexdigest()[:12])
