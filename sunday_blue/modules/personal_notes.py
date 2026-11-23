"""Local notebook. SQLite indexes plain-text Markdown files by stable note ID."""
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import uuid


class PersonalNotes:
    def __init__(self, db):
        self.db = db
        with db.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS personal_notes(id TEXT PRIMARY KEY,title TEXT,path TEXT,created TEXT)")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(personal_notes)")}
            for field in ("modified", "deleted"):
                if field not in columns:
                    conn.execute(f"ALTER TABLE personal_notes ADD COLUMN {field} TEXT")

    def directory(self):
        return Path(self.db.get("personal_notes_dir", str(self.db.root / "data/notebooks")))

    @staticmethod
    def _text(title, created, body):
        if not title or len(title) > 120 or not body.strip():
            raise ValueError("请填写标题（最多 120 字）和正文。")
        return f"# {title}\n\n记录时间：{created[:19]}\n\n{body}"

    def save(self, title, body):
        return self.create(title, body)["path"]

    def create(self, title, body):
        title = title.strip()
        now = datetime.now()
        created = now.isoformat()
        text = self._text(title, created, body)
        key = uuid.uuid4().hex
        folder = self.directory() / now.strftime("%Y/%m")
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:80] or "笔记"
        target = folder / (now.strftime("%d_%H%M%S_") + safe + "_" + key[:6] + ".md")
        with target.open("x", encoding="utf-8") as stream:
            stream.write(text)
        with self.db.connect() as conn:
            conn.execute("INSERT INTO personal_notes(id,title,path,created,modified) VALUES(?,?,?,?,?)",
                         (key, title, str(target), created, created))
        return self.row(key)

    def row(self, key):
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM personal_notes WHERE id=?", (key,)).fetchone()
        if row is None:
            raise ValueError("找不到这条笔记。")
        return dict(row)

    def rows(self, trash=False):
        where = "deleted IS NOT NULL" if trash else "deleted IS NULL"
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute(
                f"SELECT * FROM personal_notes WHERE {where} ORDER BY COALESCE(deleted,modified,created) DESC,id")]

    def read(self, key):
        return Path(self.row(key)["path"]).read_text(encoding="utf-8-sig")

    def document(self, key):
        raw = self.read(key)
        match = re.match(r"\A#[^\n]*\n\n记录时间：[^\n]*\n\n", raw)
        return (raw[match.end():] if match else raw), self.revision(raw)

    @staticmethod
    def revision(raw):
        return sha256(raw.encode("utf-8")).hexdigest()

    def update(self, key, title, body, expected):
        row = self.row(key)
        target = Path(row["path"])
        title = title.strip()
        text = self._text(title, row["created"], body)
        with self.db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if self.row(key)["deleted"] or self.revision(target.read_text(encoding="utf-8-sig")) != expected:
                raise ValueError("原文件已变更。当前草稿已保留，可另存为新笔记。")
            temp = None
            try:
                with NamedTemporaryFile("w", dir=target.parent, delete=False, encoding="utf-8") as stream:
                    temp = Path(stream.name)
                    stream.write(text)
                conn.execute("UPDATE personal_notes SET title=?,modified=? WHERE id=?",
                             (title, datetime.now().isoformat(), key))
                os.replace(temp, target)
            finally:
                if temp:
                    temp.unlink(missing_ok=True)

    def set_deleted(self, key, deleted):
        # Keep the original file and external links intact across delete and restore.
        with self.db.connect() as conn:
            conn.execute("UPDATE personal_notes SET deleted=? WHERE id=?",
                         (datetime.now().isoformat() if deleted else None, key))
