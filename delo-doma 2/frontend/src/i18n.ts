import {useSyncExternalStore} from 'react';
import dictionary from './translations.json';
export type Language='ru'|'kk'|'en';
export let language:Language=(()=>{try{const v=localStorage.getItem('delo-language');return v==='kk'||v==='en'?v:'ru'}catch{return 'ru'}})();
export let locale=language==='kk'?'kk-KZ':language==='en'?'en-GB':'ru-RU';
const listeners=new Set<()=>void>();
export function useLanguage(){return useSyncExternalStore(callback=>{listeners.add(callback);return()=>{listeners.delete(callback)}},()=>language)}
export function t(value:string):string{return language==='ru'?value:((dictionary as any)[value]?.[language]||value)}
export function translateExperience(value:any):any{if(typeof value==='string')return t(value);if(Array.isArray(value))return value.map(translateExperience);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,translateExperience(v)]));return value}
// Keep module-level UI catalogues reactive without changing underlying values.
const proxies=new WeakMap<object,any>();
export function localized<T extends object>(value:T):T{if(proxies.has(value))return proxies.get(value);const proxy=new Proxy(value,{get(target,key,receiver){const item=Reflect.get(target,key,receiver);return typeof item==='string'?t(item):item&&typeof item==='object'?localized(item):item}});proxies.set(value,proxy);return proxy}
export function setLanguage(value:Language){if(value===language)return;language=value;locale=value==='kk'?'kk-KZ':value==='en'?'en-GB':'ru-RU';try{localStorage.setItem('delo-language',value)}catch{}document.documentElement.lang=value;document.title=value==='kk'?'Дело дома — микро және шағын бизнеске арналған':value==='en'?'Delo Doma — for micro and small businesses':'Дело дома — для микро- и малого бизнеса';listeners.forEach(callback=>callback())}
