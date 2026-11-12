"""Real provider counts only: never turn character counts into fictitious tokens."""
def used(usage):
 if 'prompt_tokens' in usage:return int(usage['prompt_tokens'])+int(usage.get('completion_tokens',0))
 if 'input_tokens' in usage:return sum(int(usage.get(k,0)) for k in ('input_tokens','cache_read_input_tokens','cache_creation_input_tokens','output_tokens'))
 return None

def threshold(api):
 limit=max(4096,int(api.get('context_limit',200000)));output=int(api.get('max_tokens',4096))
 return max(1024,min(300000,int(limit*.75),limit-output-2048))

def prefix(messages,keep=4):
 starts=[i for i,m in enumerate(messages) if m['role']=='user' and isinstance(m['content'],str)]
 if len(starts)<=keep:return messages
 return messages[:starts[-keep]]
