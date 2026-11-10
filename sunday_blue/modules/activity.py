"""Authoritative reality records: read by capability, never duplicated as facts."""
from datetime import date,timedelta
from .database import ModuleDB,day

SCHEMA={'name':'activity_recent','description':'读取已实际记录的专注活动和时长。没有记录不代表用户没完成；这是模块事实源，不要重复创建任务或当作 AI 推断。',
        'input_schema':{'type':'object','properties':{'days':{'type':'integer','minimum':1,'maximum':30},'category':{'type':'string'}}}}


def recent(root,days=7,category=None):
    days=max(1,min(30,int(days)));database=ModuleDB(root)
    with database.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='activity_records'").fetchone():return []
        after=(date.fromisoformat(day())-timedelta(days=days-1)).isoformat()
        return [dict(r) for r in db.execute('''SELECT * FROM activity_records WHERE day>=?
            AND (? IS NULL OR category=?) ORDER BY finished DESC,rowid DESC LIMIT 50''',(after,category,category))]


def context(root):
    records=recent(root,1)[:3]
    if not records:return ''
    return '最近真实记录（模块原始数据，不是推断；勿重复归档）：\n'+'\n'.join(
        f"来源 {r['id']}：{r['day']} {r['category']} {int(r['seconds']//60)} 分钟，{r['label'][:100]}" for r in records)
