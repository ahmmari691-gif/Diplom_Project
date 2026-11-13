import React from 'react';
import {language,useLanguage,setLanguage,Language} from './i18n';
export default function LanguageSwitcher(){useLanguage();return <nav className="site-language" aria-label="Язык / Тіл / Language">{([['ru','Рус'],['kk','Қаз'],['en','Eng']] as [Language,string][]).map(([value,label])=><button key={value} type="button" aria-pressed={language===value} onClick={()=>setLanguage(value)}>{label}</button>)}</nav>}
