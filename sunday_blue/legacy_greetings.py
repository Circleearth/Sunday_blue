"""Read-only v1 display compatibility, even when the plugin is uninstalled."""
from pathlib import Path
import sqlite3
class LegacyGreetings:
    def __init__(self,data):self.path=Path(data)/'plugins/daypart-greetings/state.sqlite3'
    def for_session(self,sid):
        if not self.path.exists():return {}
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)
        try:return dict(db.execute('SELECT message,text FROM events WHERE session=?',(sid,)))
        except sqlite3.OperationalError:return {}
        finally:db.close()
