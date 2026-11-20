import re,html,csv,sys,os
src,out=sys.argv[1],sys.argv[2]
os.makedirs(out,exist_ok=True)
s=open(src).read().split('<template id="base">')[1].split('</template>')[0]
T=lambda x: html.unescape(re.sub(r'\s+',' ',re.sub(r'<[^>]+>',' ',x))).strip()
AREA={'linguagens':'LC','ciencias-humanas':'CH','ciencias-natureza':'CN','matematica':'MT'}
NOME={'Linguagens':'LC','Humanas':'CH','Natureza':'CN','Matemática':'MT'}
parts=re.split(r'<div class="sep" id="g\d+">',s)[1:]
Q={}; MAP=set(); PLANO={}
for b in parts:
  cad=re.search(r'No seu caderno (\w+)',b); cor=cad.group(1) if cad else ''
  for x in re.findall(r'<li class="q">.*?</li>',b,re.S):
    m=re.search(r'/(linguagens|ciencias-humanas|ciencias-natureza|matematica)/questao-(\d+)',x)
    area,qid=AREA[m.group(1)],int(m.group(2))
    num=int(re.search(r'class="qn"[^>]*>(\d+)',x).group(1))
    MAP.add((cor,area,num,qid))
    d=Q.setdefault(qid,{'questao_id':qid,'area':area,'tema':T(re.search(r'<b>(.*?)</b>',x,re.S).group(1)),
      'pct_acerto':int(re.search(r'<small>(\d+)%',x).group(1)),'gabarito':re.search(r'l ok">(\w)',x).group(1),
      'eh_facil_top15':1,'coelho':'','modelo_video':'','modelo_rotulo':''})
    for l,txt in re.findall(r'<p>Por que a (\w) engana:(.*?)</p>',x,re.S): d['por_que_engana_'+l]=T(txt)
    c=re.search(r'class="coelho"><strong>[^<]*</strong>(.*?)</p>',x,re.S)
    if c: d['coelho']=T(c.group(1))
    t=re.search(r'<a class="tag" href="([^"]*)">(.*?)</a>',x,re.S)
    if t: d['modelo_video']=html.unescape(t.group(1)); d['modelo_rotulo']=T(t.group(2))
  pm=re.search(r'card prova">(.*?)</section>',b,re.S)
  if pm:
    for num,qid in re.findall(r'<li><span class="qn">(\d+)</span>.*?/questao-(\d+)',pm.group(1),re.S):
      if cor: MAP.add((cor,'',int(num),int(qid)))
  # plano por área
  for blk in re.findall(r'<(?:div|details) class="area[^"]*">.*?(?=<(?:div|details) class="area|</section>)',b,re.S):
    n=re.search(r'class="pill">(\w+)<',blk); a=re.search(r'(\d+) de 45',blk)
    if not n or not a: continue
    tit=re.search(r'<h3>(.*?)</h3>|class="titulo-faixa">(.*?)</p>',blk,re.S); tit=T(tit.group(1) or tit.group(2))
    ps=[T(p) for p in re.findall(r'<p>(.*?)</p>',blk,re.S)]
    itens=[T(i) for i in re.findall(r'<ul class="faz">(.*?)</ul>',blk,re.S)[0].split('</li>') if T(i)] if 'class="faz"' in blk else []
    ch=re.search(r'class="chapeu">(?:<strong>[^<]*</strong>)?(.*?)</p>',blk,re.S)
    k=(NOME[n.group(1)],tit)
    e=PLANO.setdefault(k,{'area':k[0],'titulo':tit,'texto':ps[0] if ps else '','o_que_estudar':'|'.join(itens),'como_trabalhamos':T(ch.group(1)) if ch else '','acertos_vistos':set()})
    e['acertos_vistos'].add(int(a.group(1)))
# modelos (lista completa do grupo M, numeração Azul)
mods=[]; mb=parts[10]
for summ,ol in re.findall(r'<summary>(.*?)</summary><ol class="mods">(.*?)</ol>',mb,re.S):
  area=NOME[T(summ).split(':')[0]]
  for i,li in enumerate(re.findall(r'<li>(.*?)</li>',ol,re.S),1):
    p=re.search(r'<p><strong>(.*?):?</strong>(.*?)</p>',li,re.S)
    mods.append({'questao_id':int(re.search(r'questao-(\d+)',li).group(1)),'area':area,'ordem':i,
      'titulo':T(re.search(r'<b>(.*?)</b>',li,re.S).group(1)),'pct_acerto':int(re.search(r'<strong>(\d+)%',li).group(1)),
      'professor_data':T(p.group(1)).replace('Antes da prova, ','').rstrip(':'),'texto_aula':T(p.group(2)),
      'video_aula':html.unescape(re.search(r'href="(https://www.youtube[^"]*)"',li).group(1))})
def w(name,rows,cols):
  with open(os.path.join(out,name),'w',newline='',encoding='utf-8') as f:
    wr=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore'); wr.writeheader(); [wr.writerow(r) for r in rows]
qc=['questao_id','area','tema','pct_acerto','gabarito','eh_facil_top15']+['por_que_engana_'+l for l in 'ABCDE']+['coelho','modelo_rotulo','modelo_video']
w('ref_questoes_faceis.csv',sorted(Q.values(),key=lambda r:(r['area'],-r['pct_acerto'])),qc)
w('ref_questoes_modelo.csv',mods,['questao_id','area','ordem','titulo','pct_acerto','professor_data','texto_aula','video_aula'])
areaof={q:Q[q]['area'] for q in Q}; areaof.update({m['questao_id']:m['area'] for m in mods})
mp=sorted({(c,areaof.get(q,a),n,q) for c,a,n,q in MAP})
w('ref_caderno_numeracao.csv',[dict(cor_caderno=c,area=a,numero_no_caderno=n,questao_id=q) for c,a,n,q in mp],['cor_caderno','area','numero_no_caderno','questao_id'])
pl=[dict(v,acertos_vistos='|'.join(map(str,sorted(v['acertos_vistos'])))) for v in PLANO.values()]
w('ref_plano_faixas.csv',sorted(pl,key=lambda r:(r['area'],min(map(int,r['acertos_vistos'].split('|'))))),['area','acertos_min','acertos_max','titulo','texto','o_que_estudar','como_trabalhamos','acertos_vistos'])
print(len(Q),len(mods),len(mp),len(pl))
