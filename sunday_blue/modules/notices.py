"""Idempotent notifications via the shared planner/delivery outbox."""
from .database import stamp

def notify(c,key,title,qq=False,urgent=False,when=None):
 when=when or stamp()
 c.execute('INSERT OR IGNORE INTO reminder_occurrences VALUES(?,?,?,?,?,?)',(key,key,when,title,'pending','pending' if qq else 'off'))
 c.execute('INSERT OR IGNORE INTO reminder_priority VALUES(?,?)',(key,int(urgent)))
