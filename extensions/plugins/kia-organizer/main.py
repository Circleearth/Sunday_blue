from pathlib import Path
from sunday_blue.modules.database import ModuleDB
from sunday_blue.modules.organizer import Organizer,CATEGORIES

def system_context(config):return Path(__file__).with_name('SKILL.md').read_text(encoding='utf-8')
def tools():
    def schema(name,description,properties,required=()):return {'name':name,'description':description,'input_schema':{'type':'object','properties':properties,'required':list(required)}}
    string={'type':'string'}
    return [schema('search','先检索共享整理记录；不读私人记忆',{'query':string,'day':string}),
        schema('capture','收录原文或提炼内容，始终待用户确认；同源内容自动去重',{'title':string,'body':string,'category':{'type':'string','description':'必须为宿主已有分类；未知时先询问用户'},'day':string},('title','body')),
        schema('organize','将已有记录归入已有分类，保留原文与可撤销版本',{'id':string,'category':{'type':'string','description':'必须为宿主已有分类；未知时先询问用户'},'title':string},('id','category'))]
def plugin(config,role,name,args):
    if role!='kia':raise PermissionError('仅 Kia 可使用整理工具')
    service=Organizer(ModuleDB(Path(config['_plugin_root'])))
    if name=='search':return {'categories':service.categories(),'records':service.search(args.get('query',''),args.get('day'))}
    if name=='capture':return service.capture(args['title'],args['body'],args.get('category','收件箱'),args.get('day'),origin='kia',confirmed=False)
    if name=='organize':service.organize(args['id'],args['category'],args.get('title'));return {'status':'organized','reversible':True}
    raise ValueError('未知整理操作')

dispatch = plugin
