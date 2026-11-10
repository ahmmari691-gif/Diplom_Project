const ts=require('../frontend/node_modules/typescript');
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'../frontend/src'), words=new Set();
for(const file of fs.readdirSync(root).filter(x=>x.endsWith('.tsx')&&!['SiteHelp.tsx','main.tsx'].includes(x))){
 const p=path.join(root,file),s=fs.readFileSync(p,'utf8'),sf=ts.createSourceFile(file,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),edits=[];
 const add=x=>{if(/[А-Яа-яЁё]/.test(x))words.add(x)};
 function visit(n){
  if(ts.isJsxText(n)){
   const raw=n.getText(sf),v=raw.trim();if(/[А-Яа-яЁё]/.test(v)){add(v);edits.push([n.getStart(sf),n.end,raw.replace(v,'{t('+JSON.stringify(v)+')}')]);}return;
  }
  if(ts.isStringLiteral(n)||ts.isNoSubstitutionTemplateLiteral(n)){
   const v=n.text;if(!/[А-Яа-яЁё]/.test(v))return;add(v);
   if((ts.isPropertyAssignment(n.parent)&&n.parent.name===n)||ts.isImportDeclaration(n.parent)||ts.isLiteralTypeNode(n.parent))return;
   const val='t('+JSON.stringify(v)+')';edits.push([n.getStart(sf),n.end,ts.isJsxAttribute(n.parent)?'{'+val+'}':val]);return;
  }
  ts.forEachChild(n,visit);
 }
 visit(sf);let out=s;for(const [a,b,c] of edits.sort((a,b)=>b[0]-a[0]))out=out.slice(0,a)+c+out.slice(b);
 fs.writeFileSync(p,"import {t,locale} from './i18n';\n"+out);
}
fs.writeFileSync(path.resolve(__dirname,'../ui-strings.json'),JSON.stringify([...words],null,2));
console.log('UI strings:',words.size);
