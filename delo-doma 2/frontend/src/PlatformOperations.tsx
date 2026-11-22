import React, {useEffect, useState} from 'react';
import {t as tx} from './i18n';

export function PlatformOperations({request, notify}: any) {
  const [businesses, setBusinesses] = useState<any[]>([]);
  const [selected, setSelected] = useState('');
  const [profile, setProfile] = useState<any>(null);
  const [documents, setDocuments] = useState<any[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [rights, setRights] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  async function loadBusinesses() {
    const r = await request('operations');
    setBusinesses(r.businesses);
    return r.businesses;
  }
  useEffect(() => {loadBusinesses().catch((e: any) => notify(e.message));}, []);
  useEffect(() => {
    let active = true;
    setProfile(businesses.find(b => b.id === selected) || null);
    setPreview(null); setDocuments([]); setRights(false); setReviewed(false);
    if (selected) request('platform_knowledge?business=' + encodeURIComponent(selected))
      .then((r: any) => {if (active) setDocuments(r.documents);})
      .catch((e: any) => {if (active) notify(e.message);});
    return () => {active = false;};
  }, [selected, businesses]);
  async function action(task: () => Promise<void>) {
    setBusy(true);
    try {await task();} catch (e: any) {notify(e.message);} finally {setBusy(false);}
  }
  async function refreshDocs() {
    const r = await request('platform_knowledge?business=' + encodeURIComponent(selected));
    setDocuments(r.documents); setPreview(null); setReviewed(false);
  }
  return <section className="card stock-panel">
    <h2>{tx('Бизнесы и документы')}</h2>
    <p>{tx('Управляйте профилями бизнесов и проверяйте документы для помощника. Частные заказы и контакты покупателей здесь недоступны.')}</p>
    <label>{tx('Бизнес')}<select value={selected} disabled={busy} onChange={e => setSelected(e.target.value)}>
      <option value="">{tx('Выберите бизнес')}</option>
      {businesses.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
    </select></label>
    {!businesses.length && <p>{tx('Бизнесов пока нет.')}</p>}
    {profile && <>
      <form className="stack-form" onSubmit={e => {e.preventDefault();action(async () => {
        await request('operations', {action:'update_business', business:selected, name:profile.name,
          category:profile.category, description:profile.description,
          orderingConditions:profile.orderingConditions, contactPhone:profile.contactPhone,
          businessLanguage:profile.language});
        await loadBusinesses(); notify(tx('Профиль сохранён'));
      });}}>
        {['name','category','description','orderingConditions','contactPhone'].map((field, i) =>
          <label key={field}>{tx(['Название','Категория','Описание','Условия заказа','Публичный телефон бизнеса'][i])}
            <input required={field==='name'} disabled={busy} value={profile[field] || ''}
              maxLength={field==='name'?120:field==='category'||field==='contactPhone'?100:3000}
              onChange={e => setProfile({...profile,[field]:e.target.value})}/>
          </label>)}
        <label>{tx('Язык бизнеса')}<select disabled={busy} value={profile.language} onChange={e => setProfile({...profile,language:e.target.value})}>
          <option value="ru">Русский</option><option value="kk">Қазақша</option><option value="en">English</option>
        </select></label>
        <p>{tx('Статус')}: {profile.status === 'active' ? tx('Активен') : tx('Приостановлен')}. {tx('Статус меняет администратор в реестре бизнесов.')}</p>
        <button className="btn btn-primary" disabled={busy}>{tx('Сохранить профиль')}</button>
      </form>
      <h3>{tx('Документы бизнеса')}</h3>
      <label className="check-label"><input type="checkbox" checked={rights} disabled={busy} onChange={e => setRights(e.target.checked)}/>
        {tx('Подтверждаю право использовать файл и отсутствие персональных данных покупателей.')}</label>
      <label>{tx('Загрузить TXT, CSV или XLSX')}<input type="file" accept=".txt,.csv,.xlsx" disabled={busy || !rights}
        onChange={e => {const file=e.target.files?.[0];e.target.value='';if(!file)return;
          action(async () => {
            if(file.size>2*1024*1024)throw new Error(tx('Размер файла — не больше 2 МБ.'));
            const base64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();
              reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error(tx('Не удалось прочитать файл.')));reader.readAsDataURL(file);});
            await request('platform_knowledge',{action:'upload',business:selected,name:file.name,base64,rightsConfirmed:rights});
            await refreshDocs();setRights(false);notify(tx('Документ загружен'));
          });
        }}/></label>
      {!documents.length && <p>{tx('Документов пока нет.')}</p>}
      {documents.map(d => <div className="platform-count-row" key={d.id}>
        <span>{d.name} · {d.status}</span>
        <button className="text-link" disabled={busy} onClick={()=>action(async()=>{
          const r=await request('platform_knowledge?business='+encodeURIComponent(selected)+'&id='+encodeURIComponent(d.id));
          setPreview(r);setColumns(r.selectedColumns || r.columns);setReviewed(false);
        })}>{tx('Проверить')}</button>
        <button className="text-link" disabled={busy} onClick={()=>{if(window.confirm(tx('Удалить документ?')))action(async()=>{
          await request('platform_knowledge',{action:'delete',business:selected,id:d.id});await refreshDocs();notify(tx('Документ удалён'));
        });}}>{tx('Удалить')}</button>
      </div>)}
      {preview && <section className="card">
        <h3>{preview.name}</h3><p>{tx('Предпросмотр первых пяти строк')}</p>
        <div style={{overflowX:'auto'}}><table><thead><tr>{preview.columns.map((c:string)=><th key={c}>{c}</th>)}</tr></thead>
          <tbody>{preview.preview.map((r:any,i:number)=><tr key={i}>{preview.columns.map((c:string)=><td key={c}>{r[c]}</td>)}</tr>)}</tbody></table></div>
        <p>{tx('Столбцы, разрешённые для помощника:')}</p>
        {preview.columns.map((c:string)=><label key={c} style={{display:'block'}}><input type="checkbox" disabled={busy} checked={columns.includes(c)}
          onChange={e=>setColumns(e.target.checked?[...columns,c]:columns.filter(x=>x!==c))}/>{c}</label>)}
        <label style={{display:'block'}}><input type="checkbox" disabled={busy} checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/>{tx('Я проверил документ и выбранные столбцы.')}</label>
        <button className="btn btn-primary" disabled={busy||!reviewed||!columns.length} onClick={()=>action(async()=>{
          await request('platform_knowledge',{action:'activate',business:selected,id:preview.id,columns,confirmed:reviewed});
          await refreshDocs();notify(tx('Документ активирован'));
        })}>{tx('Разрешить для помощника')}</button>
      </section>}
    </>}
  </section>;
}
