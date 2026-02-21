import sqlite3
from pathlib import Path
from typing import Optional


def generate_index_markdown(db_path: str, local_root: str, limit: int = 200) -> str:
    """Generate a human-friendly index table for quick browsing.

    This is designed for Shiver to quickly inspect the library from cloud.
    Output is deterministic and safe to sync.
    """

    db = Path(db_path)
    if not db.exists():
        return "# 索引\n\n（数据库不存在）\n"

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # documents table schema uses storage_path as relative path.
    rows = cur.execute(
        """
        SELECT id,title,doc_type,category,tags,status,storage_path,source_url,updated_at
          FROM documents
         ORDER BY COALESCE(updated_at, created_at) DESC
         LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    con.close()

    lines = []
    lines.append("# 索引")
    lines.append("")
    lines.append(f"- 生成时间：自动更新")
    lines.append(f"- 数据源：`{db_path}`")
    lines.append("")

    if not rows:
        lines.append("（暂无记录）")
        lines.append("")
        return "\n".join(lines) + "\n"

    lines.append("| ID | 标题 | 类别 | 状态 | 路径 | 来源 | tags |")
    lines.append("|---:|---|---|---|---|---|---|")

    for r in rows:
        title = (r["title"] or "").replace("|", "\\|")
        category = (r["category"] or "").replace("|", "\\|")
        status = (r["status"] or "").replace("|", "\\|")
        tags = (r["tags"] or "").replace("|", "\\|")
        storage_path = (r["storage_path"] or "").lstrip("/")

        # Prefer relative link so it works both locally and on cloud.
        path_link = f"[{storage_path}]({storage_path})" if storage_path else ""

        src = (r["source_url"] or "").strip()
        if src:
            src_link = f"[link]({src})"
        else:
            src_link = ""

        lines.append(
            f"| {r['id']} | {title} | {category} | {status} | {path_link} | {src_link} | {tags} |"
        )

    lines.append("")
    lines.append("> 说明：该索引由同步服务自动生成并同步到云端，用于远程快速查看。")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_index_file(db_path: str, local_root: str, rel_path: str = "使用规范/云空间索引.md", limit: int = 200) -> Path:
    root = Path(local_root)
    out_path = root / rel_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(generate_index_markdown(db_path, local_root, limit=limit), encoding="utf-8")
    return out_path
