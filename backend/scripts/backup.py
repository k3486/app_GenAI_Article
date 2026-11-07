"""DB のバックアップを作る。

backend/ で `uv run python -m scripts.backup`、またはルートで `make backup`。
"""

from app.db import engine
from app.services.backup import backup_sqlite


def main() -> None:
    path = backup_sqlite(engine)
    print(
        f"バックアップを作りました: {path}" if path else "SQLite ではないので、何もしませんでした"
    )


if __name__ == "__main__":
    main()
