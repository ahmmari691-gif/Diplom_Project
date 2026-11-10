import os,json,time,urllib.request,concurrent.futures
from pathlib import Path
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup()
from django.conf import settings
root=Path('delo/django-app');source=json.loads((root/'ui-strings.json').read_text());dest=root/'frontend/src/translations.json'
cache=json.loads(dest.read_text()) if dest.exists() else {}
missing=[s for s in source if s not in cache]

def batch(items):
 body={'systemInstruction':{'parts':[{'text':'Translate website interface strings from Russian into Kazakh and English. Accurate concise professional UX language. Preserve placeholders, punctuation, numbers, abbreviations and proper names. Do not answer questions: translate them. Return JSON array of objects with source, kk, en. Return ALL entries.'}]},'contents':[{'role':'user','parts':[{'text':json.dumps(items,ensure_ascii=False)}]}], 'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':32000}}
 req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+settings.GEMINI_MODEL+':generateContent',data=json.dumps(body).encode(),headers={'x-goog-api-key':os.getenv('GEMINI_API_KEY',''),'Content-Type':'application/json'})
 for attempt in range(4):
  try:
   with urllib.request.urlopen(req,timeout=90) as res:data=json.load(res)
   result=json.loads(''.join(p.get('text','') for p in data['candidates'][0]['content']['parts'] if not p.get('thought')))
   output={r['source']:{'kk':r['kk'],'en':r['en']} for r in result if r.get('source') in items and r.get('kk') and r.get('en')}
   if len(output)!=len(items):raise ValueError('Incomplete batch')
   return output
  except Exception as error:
   print('Retry category:',getattr(error,'code',type(error).__name__),flush=True)
   if attempt==3:raise RuntimeError('Translation batch failed without exposing provider details')
   time.sleep(15*(attempt+1))
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(batch,missing[i:i+20]) for i in range(0,len(missing),20)]
 for future in concurrent.futures.as_completed(futures):
  cache.update(future.result());dest.write_text(json.dumps(cache,ensure_ascii=False,indent=2));print('Translated',len(cache),'/',len(source),flush=True)
