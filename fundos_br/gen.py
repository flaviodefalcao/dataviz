# Gera os arquivos do painel a partir das cotas da CVM (panel.parquet) e do CDI (BCB série 12)
import polars as pl, json, math, datetime as D, sys
W=sys.argv[1]; O=sys.argv[2]; CODE=open(__file__).read()
F={'34081680000137':('XP Special Situations I','XP Vista','Brasil','Crédito estruturado'),
   '24215286000190':('SPX Falcon','SPX','Brasil','Ações Brasil'),
   '24623392000103':('Guepardo Long Bias','Guepardo','Brasil','Ações Brasil'),
   '40826574000138':('Carbyne Mercados Privados','Carbyne','Brasil','Crédito privado'),
   '15334585000153':('SPX Patriot','SPX','Brasil','Ações Brasil'),
   '32892827000143':('Absolute Pace Long Biased','Absolute','Brasil','Ações Brasil'),
   '22963439000152':('Trend Ouro','XP Allocation','Exterior/dólar','Ouro sem hedge'),
   '35002927000145':('BTGP AQR Long-Biased','BTG / AQR','Exterior/dólar','Ações globais com hedge'),
   '35769107000183':('Schroder Contour Tech L&S BRL','Gama / Schroders','Exterior/dólar','Tech global long-short com hedge'),
   '36499594000174':('BTG S&P 500 BRL','BTG','Exterior/dólar','S&P 500 com hedge')}
PESOS={'24215286000190':0.30,'35002927000145':0.25,'35769107000183':0.20,'40826574000138':0.15,'22963439000152':0.10}
p=pl.read_parquet(f'{W}/panel.parquet').filter(pl.col('cnpj').is_in(list(F))&(pl.col('m')>=D.date(2021,10,1))).sort(['cnpj','m'])
cdi=sorted((D.datetime.strptime(x['data'],'%d/%m/%Y').date(),float(x['valor'])) for x in json.load(open(f'{W}/cdi.json')))
def cdi_idx(d):  # índice acumulado do CDI até a data d (inclusive), base 1 em 29/10/2021
    v=1.0
    for dd,r in cdi:
        if dd>D.date(2021,10,29) and dd<=d: v*=1+r/100
    return v
meses=sorted(set(p['m'].to_list()))
datas={m:p.filter(pl.col('m')==m)['dt'].max() for m in meses}
q={(c,m):v for c,m,v in p.select('cnpj','m','q').iter_rows()}
curvas=[]
for c in F:
    q0=q[(c,meses[0])]
    for m in meses:
        if (c,m) in q: curvas.append({'mes':m.isoformat(),'serie':F[c][0],'indice':round(q[(c,m)]/q0,5)})
ci={m:cdi_idx(datas[m]) for m in meses}
for m in meses: curvas.append({'mes':m.isoformat(),'serie':'CDI','indice':round(ci[m],5)})
# carteira sugerida com rebalanceamento mensal
cart=[1.0]
for a,b in zip(meses,meses[1:]):
    r=sum(w*(q[(c,b)]/q[(c,a)]-1) for c,w in PESOS.items()); cart.append(cart[-1]*(1+r))
for m,v in zip(meses,cart): curvas.append({'mes':m.isoformat(),'serie':'Carteira sugerida','indice':round(v,5)})
def stats(serie):  # serie: lista (mes, indice); anos = retorno por ano-calendário (2026 até nov)
    idx=[v for _,v in serie]; rr=[b/a-1 for a,b in zip(idx,idx[1:])]
    mu=sum(rr)/len(rr); vol=math.sqrt(sum((x-mu)**2 for x in rr)/(len(rr)-1)*12)
    pk=idx[0]; dd=0
    for v in idx: pk=max(pk,v); dd=min(dd,v/pk-1)
    ye={}
    for m,v in serie: ye[m.year]=v
    anos={}; prev=None
    for y in sorted(ye):
        if prev is not None: anos[y]=ye[y]/ye[prev]-1
        prev=y
    return idx[-1]-1, vol, dd, anos
cdi5=ci[meses[-1]]-1
def linha(ret,vol,dd,anos):
    return {'ret_5a':round(ret,4),'pct_cdi':round(ret/cdi5,3),'vol_anual':round(vol,4),'queda_max':round(dd,4),
            'pior_ano':round(min(anos[y] for y in range(2022,2027)),4),**{f'ano_{y}':round(anos[y],4) for y in range(2022,2027)}}
fundos=[]
for c,(nome,gest,grupo,estr) in F.items():
    s=[(m,q[(c,m)]/q[(c,meses[0])]) for m in meses if (c,m) in q]
    ult=p.filter((pl.col('cnpj')==c)&(pl.col('m')==meses[-1])).row(0,named=True)
    fundos.append({'fundo':nome,'gestora':gest,'grupo':grupo,'estrategia':estr,'cnpj':c,**linha(*stats(s)),
      'pl_milhoes':round(ult['pl']/1e6),'cotistas':int(ult['cot']),'peso_sugerido':PESOS.get(c,0)})
resumo=[{'serie':'Carteira sugerida',**linha(*stats(list(zip(meses,cart))))},{'serie':'CDI',**linha(*stats([(m,ci[m]) for m in meses]))}]
rm={c:{b:q[(c,b)]/q[(c,a)]-1 for a,b in zip(meses,meses[1:]) if (c,a) in q and (c,b) in q} for c in F}
def corr(x,y):
    k=sorted(set(x)&set(y)); a=[x[i] for i in k]; b=[y[i] for i in k]; ma=sum(a)/len(a); mb=sum(b)/len(b)
    return sum((u-ma)*(v-mb) for u,v in zip(a,b))/math.sqrt(sum((u-ma)**2 for u in a)*sum((v-mb)**2 for v in b))
correl=[{'fundo_a':F[a][0],'fundo_b':F[b][0],'correlacao':round(corr(rm[a],rm[b]),2)} for a in F for b in F]
meta=[{'label':'gen.py','value':CODE,'type':'code','lang':'python'},{'label':'Entrada','value':'Informe diário CVM (dados.cvm.gov.br) e CDI série 12 do BCB'},
      {'label':'Janela','value':f'{datas[meses[0]]} a {datas[meses[-1]]}'}]
for n,rows in [('fundos',fundos),('curvas',curvas),('resumo',resumo),('correl',correl)]:
    json.dump({'rows':rows,'meta':meta},open(f'{O}/{n}.json','w'),ensure_ascii=False)
print(json.dumps(resumo,indent=0)); print(len(curvas))
