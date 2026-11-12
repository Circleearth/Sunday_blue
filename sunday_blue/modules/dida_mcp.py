"""Small allowlisted client for Dida's official Streamable HTTP MCP endpoint."""
import json
import requests

class DidaMCP:
    URL='https://mcp.dida365.com'
    ALLOWED={'list_projects','filter_tasks','get_task_by_id','complete_task','get_tool_details','create_task','update_task','delete_task'}
    def __init__(self,token,post=None):
        self.post=post or requests.post;self.counter=0
        self.headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
        result=self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'SundayBlue','version':'1.0'}})
        self.headers['MCP-Protocol-Version']=result.get('protocolVersion','2025-03-26')
        self.rpc('notifications/initialized',{},notification=True)
    def rpc(self,method,params,notification=False):
        self.counter+=1;payload={'jsonrpc':'2.0','method':method,'params':params}
        if not notification:payload['id']=self.counter
        try:
            with self.post(self.URL,headers=self.headers,json=payload,timeout=(5,25),allow_redirects=False,stream=True) as response:
                if response.status_code in (401,403):raise ValueError('滴答 API 口令无效或权限不足，请重新配置。')
                if not 200<=response.status_code<300:raise ValueError('滴答服务返回 HTTP '+str(response.status_code))
                session=response.headers.get('Mcp-Session-Id')
                if session:self.headers['Mcp-Session-Id']=session
                if notification:return {}
                if 'text/event-stream' in response.headers.get('Content-Type',''):
                    data=None;buffer=[];size=0
                    for line in response.iter_lines(decode_unicode=True):
                        if isinstance(line,bytes):line=line.decode('utf-8')
                        size+=len(line or '')
                        if size>10000000:raise ValueError('滴答响应过大')
                        if line and line.startswith('data:'):buffer.append(line[5:].strip())
                        elif not line and buffer:
                            item=json.loads('\n'.join(buffer));buffer=[]
                            if item.get('id')==payload['id']:data=item;break
                    if data is None:raise ValueError('滴答返回不完整响应')
                else:data=response.json()
                if data.get('id')!=payload['id'] or 'error' in data or 'result' not in data:raise ValueError('滴答请求未成功，请刷新后核对状态。')
                return data['result']
        except requests.RequestException:
            raise ValueError('滴答网络请求未确认成功，请同步核对后再操作。') from None
    def call(self,name,args):
        if name not in self.ALLOWED:raise PermissionError('此页面未开放该操作')
        result=self.rpc('tools/call',{'name':name,'arguments':args})
        if result.get('isError'):raise ValueError('滴答未接受操作，请同步核对任务或权限。')
        if result.get('structuredContent') is not None:value=result['structuredContent']
        else:
            texts=[c.get('text','') for c in result.get('content',[]) if c.get('type')=='text']
            try:value=json.loads('\n'.join(texts))
            except (ValueError,TypeError):
                if not texts:return None
                raise ValueError('滴答结果格式不符合预期') from None
        value=value.get('result',value) if isinstance(value,dict) else value
        if isinstance(value,dict) and value.get('error'):raise ValueError('滴答未接受操作或记录不可访问，请刷新核对。')
        return value
