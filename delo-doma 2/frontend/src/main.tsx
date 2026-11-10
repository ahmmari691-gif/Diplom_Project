import React from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import './style.css';
import LanguageSwitcher from './LanguageSwitcher';
import {language} from './i18n';
document.documentElement.lang=language;
document.title=language==='kk'?'Дело дома — микро және шағын бизнеске арналған':language==='en'?'Delo Doma — for micro and small businesses':'Дело дома — для микро- и малого бизнеса';
createRoot(document.getElementById('root')!).render(<><LanguageSwitcher/><App/></>);
