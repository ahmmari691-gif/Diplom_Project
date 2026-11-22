"""Generate ERD sources from Django metadata: python docs/erd/generate.py.

Rendering DOT to SVG/PNG is optional and can use Graphviz or @viz-js/viz.
No connection to a live database is needed.
"""
from pathlib import Path
import os, sys, re, json, html
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'delo-doma 2'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.apps import apps
OUT = Path(__file__).resolve().parent
models = list(apps.get_app_config('core').get_models())
def title(model):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', model.__name__).upper()
def typ(field):
    if field.is_relation:
        return typ(field.target_field)
    t = field.get_internal_type()
    return {'UUIDField':'uuid','CharField':'varchar','EmailField':'varchar','TextField':'text',
        'BooleanField':'boolean','DateTimeField':'datetime','DecimalField':'decimal',
        'JSONField':'json','BigAutoField':'bigint','PositiveIntegerField':'int'}.get(t,'int')
def keys(f):
    return ','.join(k for k, yes in [('PK',f.primary_key),('FK',f.is_relation),('UK',f.unique and not f.primary_key)] if yes)
lines=['erDiagram']
for m in models:
    for f in m._meta.fields:
        if f.is_relation and f.related_model in models:
            left='|o' if f.null else '||'
            right='o|' if f.one_to_one else 'o{'
            lines.append(f'    {title(f.related_model)} {left}--{right} {title(m)} : "{f.column} / {f.remote_field.on_delete.__name__}"')
for m in models:
    lines.append(f'    {title(m)} {{')
    for f in m._meta.fields:
        note=' "nullable"' if f.null else ''
        lines.append(f'        {typ(f)} {f.column} {keys(f)}{note}'.rstrip())
    lines.append('    }')
(OUT/'full-schema.mmd').write_text('\n'.join(lines)+'\n')
main={'Account','User','Business','Catalogue','Product','Order','OrderConsent','OrderStatusHistory','ProviderConsent','KnowledgeDocument','Invitation','AuditLog'}
account_fields={'id','email','password','role','name','platform_active','is_active','date_joined'}
# Reduce only display fields. The full Mermaid source above contains every scalar field.
omit={'Business':{'average_check','pickup_area','lead_hours','daily_capacity','business_type','currency','ai_provider','updated'},
      'KnowledgeDocument':{'columns','selected_columns','ignored_columns','formula_count'},
      'Order':{'channel','campaign','updated'},'Account':{f.name for f in apps.get_model('core.Account')._meta.fields}-account_fields}
dot=['digraph ERD {','graph [rankdir=LR, bgcolor="#faf8f3", pad=0.5, nodesep=0.6, ranksep=1.1, splines=polyline, fontname="Arial", fontsize=20, labelloc=t, label="DELO DOMA · ERD v4\nGuest buyer → Order ← Business\nSolid lines: foreign keys · Dashed lines: role permissions (not foreign keys)"];',
     'node [shape=plain, fontname="Arial", fontsize=12];',
     'edge [fontname="Arial", fontsize=10, color="#64748b", fontcolor="#475569", arrowsize=0.8];']
for m in models:
    if m.__name__ not in main:continue
    color='#176b65' if m.__name__ in ('User','Business','Order') else '#30375f'
    rows=[f'<TR><TD COLSPAN="3" BGCOLOR="{color}"><FONT COLOR="white"><B>{title(m)}</B></FONT></TD></TR>']
    rows.append(f'<TR><TD COLSPAN="3"><FONT COLOR="#64748b" POINT-SIZE="10">{m._meta.db_table}</FONT></TD></TR>')
    for f in m._meta.fields:
        if f.name in omit.get(m.__name__,set()):continue
        name=html.escape(f.column)
        if f.primary_key:name='<B>'+name+'</B>'
        rows.append(f'<TR><TD ALIGN="LEFT"><FONT COLOR="#64748b">{typ(f)}</FONT></TD><TD ALIGN="LEFT">{name}{" ?" if f.null else ""}</TD><TD ALIGN="RIGHT">{keys(f)}</TD></TR>')
    dot.append(f'{m.__name__} [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6" COLOR="{color}" BGCOLOR="white">'+''.join(rows)+'</TABLE>>];')
for m in models:
    if m.__name__ not in main:continue
    for f in m._meta.fields:
        if not f.is_relation or f.related_model.__name__ not in main:continue
        parent=f.related_model.__name__
        cardinality=('0..1' if f.null else '1')+' : '+('0..1' if f.one_to_one else '0..N')
        dot.append(f'{parent} -> {m.__name__} [dir=both, arrowtail="{ "teeodot" if f.null else "teetee"}", arrowhead="{ "teeodot" if f.one_to_one else "crowodot"}", label="{f.column}\n{cardinality}"];')
dot+=['subgraph cluster_roles { label="ACCOUNT roles — access rules, not additional tables"; color="#c4b5a0"; style="rounded,dashed";',
'Manager [shape=box, style="rounded,filled,dashed", fillcolor="#e9f3ef", label="PLATFORM MANAGER\nACCOUNT.role = manager\nname · email · active access\nAggregate statistics · campaigns · tasks\nNo business profiles or documents\nNo private orders · no business suspension"];',
'Administrator [shape=box, style="rounded,filled,dashed", fillcolor="#fff0d7", label="PLATFORM ADMINISTRATOR\nACCOUNT.role = admin\nname · email · active account\nAll manager operations\nSuspends / resumes businesses\nInvites / revokes managers\nReads platform audit log\nNo customer order contents"];','}',
'PlatformOperations [shape=box, style="rounded,filled", fillcolor="#e9f3ef", label="Aggregate statistics\nCAMPAIGN (platform only)\nPLATFORM_TASK"];',
'Manager -> PlatformOperations [style=dashed, color="#238577", label="view / manage"];',

'Administrator -> Business [style=dashed, color="#b77924", label="edit / suspend / resume", constraint=false];',
'Administrator -> KnowledgeDocument [style=dashed, color="#b77924", label="manage documents", constraint=false];',
'Administrator -> Invitation [style=dashed, color="#b77924", label="invite manager", constraint=false];',
'Administrator -> AuditLog [style=dashed, color="#b77924", label="read audit", constraint=false];',
'Administrator -> Account [style=dashed, color="#b77924", label="revoke manager access", constraint=false];',
'Legend [shape=box, style="rounded,filled", fillcolor="#f1eee7", label="PK primary key · FK foreign key · UK unique · ? nullable\nUSER is a guest buyer: no password and no direct business FK\nCustomer contacts and notes remain encrypted in ORDER\nACCOUNT is an owner/staff login, not a customer\nSome scalar fields omitted; full-schema.mmd contains all 21 core tables\nStandard Django authentication/session tables omitted"];','}']
(OUT/'delo-doma-erd.dot').write_text('\n'.join(dot)+'\n')
# A second, compact role view is intentionally not an ERD.
(OUT/'roles.mmd').write_text('''flowchart LR
  Customer["USER · покупатель без регистрации"] -->|оформляет и отслеживает| Order["ORDER · заказ"]
  Owner["ACCOUNT · владелец бизнеса"] -->|управляет| Business["BUSINESS · клиент платформы"]
  Business -->|получает и выполняет| Order
  Owner -->|ведёт| Catalogue["CATALOGUE → PRODUCT"]
  Owner -->|загружает и активирует| Docs["KNOWLEDGE_DOCUMENT"]
  Manager["ACCOUNT.role = manager<br/>Менеджер платформы"] -->|просматривает / ведёт| Ops["Статистика · CAMPAIGN · PLATFORM_TASK"]
  Admin["ACCOUNT.role = admin<br/>Администратор"] -->|все полномочия менеджера| Manager
  Admin -->|редактирует / приостанавливает / возобновляет| Business
  Admin -->|управляет документами| Docs
  Admin -->|создаёт| Invite["INVITATION · приглашение менеджера"]
  Admin -->|отзывает доступ| Staff["ACCOUNT · аккаунт менеджера"]
  Admin -->|просматривает| Audit["AUDIT_LOG · журнал действий"]
''')
print(f'Generated {len(models)} core models in {OUT}')
