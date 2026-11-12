"""Narrow per-duty tools; current assignments are rechecked at execution time."""
import json
from datetime import date,timedelta
from .database import ModuleDB,day
from .duties import Duties,assigned
from ..roles import require_role

ACTIONS={'director':{'summary','work_list','work_create','work_update'},'exercise':{'summary','exercise_record'},'diet':{'summary','daily_record'},'recovery':{'summary','daily_record'},'study':{'summary'},'recorder':{'summary','capture','handoffs','file_revision'},'organizer':{'summary','handoffs','organize','fail','file_revision'}}
WRITE={'work_create','work_update','exercise_record','daily_record'}
GUIDE='只记录用户实际报告的事实；写入需要确认。记录员快速收原文，整理员查交接、复用分类、完成后清出待办；分类不明问用户。'

def permitted(root,role):return set().union(*(ACTIONS.get(s,set()) for s in assigned(root,role)))

def schema(root,role):
    actions=sorted(permitted(root,role))
    if not actions:return []
    description=('按当前职责操作共享真实数据。'+GUIDE+' action参数：summary 可给 day；work_create: title,parent_id?,estimate_minutes?,due?,priority?,dida_id?；work_update: id,fields对象；exercise_record: kind,minutes,intensity(light/moderate/high),day?,record_id?,muscles?（胸/背/肩/二头肌/三头肌/核心）; daily_record: day默认昨天，饮食meal/睡眠sleep_start,sleep_end(HH:mm，起床早于入睡视为次日)/手机分钟phone_total,phone_fun/note。旧sleep_hours,screen_hours,energy仅兼容旧数据；capture: title,body(用户本次原文),request?,files?；organize: id,category,title?,note?；fail: id,error；file_revision: id（交接中的修订 ID，读取改前改后与差异）。未提供的值不要编造。')
    return [{'name':'duty_action','description':description,'input_schema':{'type':'object','properties':{'action':{'type':'string','enum':actions},'args':{'type':'object'}},'required':['action','args'],'additionalProperties':False}}]

def summary(db,slots,target):
    from .life import Life
    from .work import Work
    life=Life(db);daily=life.daily(target);result={'day':target}
    if 'director' in slots:result.update(energy=life.energy(target),life=daily,exercise=[r for r in life.exercises() if r['day']==target],work=Work(db).tasks()[:100])
    else:
        if 'diet' in slots:result['diet']={k:daily.get(k) for k in ('day','meal')}
        if 'recovery' in slots:result.update(energy=life.energy(target),recovery={k:daily.get(k) for k in ('day','sleep_hours','phone_total','phone_fun','screen_hours','energy','note')})
        if 'exercise' in slots:result['exercise']=[r for r in life.exercises() if r['day']==target]
    if slots & {'director','study'}:
        with db.connect() as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='activity_records'").fetchone():
                result['focus']=[dict(r) for r in c.execute("SELECT category,label,seconds,day FROM activity_records WHERE day=? AND (? OR category='学习') ORDER BY finished DESC LIMIT 100",(target,'director' in slots))]
    if 'director' in slots:
        from .recovery import Recovery
        result['recovery']=Recovery(db).status()
        with db.connect() as c:result['deferred_reviews']=[json.loads(r[0]) for r in c.execute("SELECT payload FROM module_events WHERE kind='activity.review_deferred' ORDER BY seq DESC LIMIT 20")]
    if slots & {'recorder','organizer'}:
        with db.connect() as c:result['handoff_counts']={r[0]:r[1] for r in c.execute('SELECT status,count(*) FROM duty_handoffs GROUP BY status')}
    return result

def dispatch(root,role,action,args,approve=None,actual_text=''):
    require_role(root,role)
    if not isinstance(args,dict):raise ValueError('工具参数必须为对象')
    if action not in permitted(root,role):raise PermissionError('当前人格未承担对应职责，不能执行此操作')
    db=ModuleDB(root);duties=Duties(db);slots=set(assigned(root,role));args=dict(args)
    if action in WRITE:
        if not actual_text.strip():raise ValueError('没有本次用户报告可作为写入来源')
        if action=='daily_record':
            allowed={'day'}
            if 'diet' in slots:allowed.add('meal')
            if 'recovery' in slots:allowed.update(('sleep_hours','sleep_start','sleep_end','phone_total','phone_fun','screen_hours','energy','note'))
            if set(args)-allowed:raise PermissionError('本职责无权修改这些生活字段')
        if approve is None or not approve('确认职责数据写入',action,json.dumps(args,ensure_ascii=False,indent=2)):
            return {'status':'denied'}
        # Assignment can change while the user is reviewing the proposed mutation.
        if action not in permitted(root,role) or set(assigned(root,role))!=slots:raise PermissionError('职责分配已变化，请重新发起操作')
    if action=='summary':
        target=args.get('day') or day();date.fromisoformat(target);return summary(db,slots,target)
    if action.startswith('work_'):
        from .work import Work
        work=Work(db)
        if action=='work_list':return {'tasks':work.tasks()[:100],'suggested':work.suggest()[:30]}
        if action=='work_create':return {'id':work.create(**args)}
        work.update(args['id'],**args.get('fields',{}));return work.task(args['id'])
    if action=='exercise_record':
        from .life import Life
        return Life(db).exercise(**args)
    if action=='daily_record':
        from .life import Life
        life=Life(db);target=args.pop('day',(date.fromisoformat(day())-timedelta(days=1)).isoformat());current=life.daily(target)
        base={k:current.get(k) for k in ('meal','sleep_hours','phone_total','phone_fun','screen_hours','energy','note')};base['meal']=base['meal'] or '';base['note']=base['note'] or '';base.update(args)
        saved=life.save_daily(target,**base)
        visible={'day','revision','updated'}
        if 'diet' in slots:visible.add('meal')
        if 'recovery' in slots:visible.update(('sleep_hours','sleep_start','sleep_end','phone_total','phone_fun','screen_hours','energy','note'))
        return {k:v for k,v in saved.items() if k in visible}
    if action=='capture':
        body=str(args.get('body','')).strip()
        if not actual_text.strip() or body!=actual_text.strip():raise ValueError('快速记录必须保留本次用户原文，提炼或推断请先由用户确认')
        return duties.capture(**args)
    if action=='handoffs':
        from .organizer import Organizer
        return {'categories':Organizer(db).categories(),'items':duties.handoffs(bool(args.get('include_done',False)))}
    if action=='file_revision':
        from .document_changes import DocumentChanges
        changes=DocumentChanges(db);row=changes.get(args['id'])
        return {k:row[k] for k in ('id','path','actor','state','created','handoff_id')}|{'before':row['before_text'][:12000],'after':row['after_text'][:12000],'diff':changes.difference(row['before_text'],row['after_text']),'truncated':max(len(row['before_text']),len(row['after_text']))>12000}
    if action=='organize':return duties.complete_handoff(**args)
    if action=='fail':return duties.fail_handoff(**args)
    raise ValueError('未知职责动作')
