import polars as pl, json, datetime as D, math, sys
W=sys.argv[1]; R=sys.argv[2]
p=pl.read_parquet(f'{W}/panel.parquet')
# --- séries BCB
cdi=pl.DataFrame([(D.datetime.strptime(x['data'],'%d/%m/%Y').date(),float(x['valor'])) for x in json.load(open(f'{W}/cdi.json'))],schema=['d','v'],orient='row').sort('d')
cdi=cdi.with_columns(((1+pl.col('v')/100).log().cum_sum()).alias('lc'))
usd=pl.DataFrame([(D.datetime.strptime(x['data'],'%d/%m/%Y').date(),float(x['valor'])) for x in json.load(open(f'{W}/usd.json'))],schema=['d','u'],orient='row').sort('d')
def idx_at(df,col,dates):
    # valor acumulado até a data (inclusive): join_asof backward
    t=pl.DataFrame({'d':dates}).with_row_index().sort('d')
    return t.join_asof(df.select('d',col),on='d',strategy='backward').sort('index')[col].to_list()
END=D.date(2026,11,19); START_M=D.date(2021,10,1)  # cota no fim de out/2021 -> ~5,05 anos
# --- metadados
c1=pl.read_csv(f'{R}/cad_fi.csv',separator=';',encoding='latin1',infer_schema_length=0,quote_char=None,truncate_ragged_lines=True).with_columns(pl.col('CNPJ_FUNDO').str.replace_all(r'\D','').alias('cnpj'))
c1=c1.select('cnpj',pl.col('DENOM_SOCIAL').alias('nome1'),pl.col('GESTOR').alias('gestor1'),pl.col('CLASSE').alias('classe1'),pl.col('CLASSE_ANBIMA').alias('anb1'),
   pl.col('INVEST_CEMPR_EXTER').alias('ext1'),pl.col('FUNDO_EXCLUSIVO').alias('excl1'),pl.col('DT_INI_ATIV').alias('ini1'),pl.col('SIT').alias('sit1'),pl.col('AUDITOR').alias('aud1'),pl.col('TP_FUNDO').alias('tp1'),pl.col('ADMIN').alias('adm1')).unique('cnpj',keep='last')
rc=pl.read_csv(f'{R}/reg/registro_classe.csv',separator=';',encoding='latin1',infer_schema_length=0,quote_char=None,truncate_ragged_lines=True)
rf=pl.read_csv(f'{R}/reg/registro_fundo.csv',separator=';',encoding='latin1',infer_schema_length=0,quote_char=None,truncate_ragged_lines=True).select('ID_Registro_Fundo','Gestor','Administrador','Data_Constituicao')
rc=rc.join(rf,on='ID_Registro_Fundo',how='left').select(pl.col('CNPJ_Classe').str.zfill(14).alias('cnpj'),pl.col('Denominacao_Social').alias('nome2'),pl.col('Gestor').alias('gestor2'),
   pl.col('Classificacao').alias('classe2'),pl.col('Classificacao_Anbima').alias('anb2'),pl.col('Permitido_Aplicacao_CemPorCento_Exterior').alias('ext2'),pl.col('Exclusivo').alias('excl2'),
   pl.col('Data_Inicio').alias('ini2'),pl.col('Situacao').alias('sit2'),pl.col('Auditor').alias('aud2'),pl.col('Tipo_Classe').alias('tp2'),pl.col('Publico_Alvo').alias('pub2'),pl.col('Administrador').alias('adm2')).unique('cnpj',keep='last')
meta=c1.join(rc,on='cnpj',how='full',coalesce=True)
meta=meta.select('cnpj',pl.coalesce('nome2','nome1').alias('nome'),pl.coalesce('gestor2','gestor1').alias('gestor'),pl.coalesce('adm2','adm1').alias('admin'),
   pl.coalesce('classe2','classe1').alias('classe'),pl.coalesce('anb2','anb1').alias('anbima'),pl.coalesce('ext2','ext1').alias('ext100'),
   pl.coalesce('excl2','excl1').alias('exclusivo'),pl.coalesce('ini1','ini2').alias('inicio'),pl.coalesce('sit2','sit1').alias('situacao'),pl.coalesce('aud2','aud1').alias('auditor'),
   pl.coalesce('tp2','tp1').alias('tipo'),'pub2')
# --- painel: apenas fundos vivos com cota no início e no fim
p=p.with_columns(pl.col('m').dt.year().alias('y'))
alive=p.filter(pl.col('m')==D.date(2026,11,1)).filter(pl.col('dt')>=D.date(2026,11,14)).select('cnpj')
p=p.join(alive,on='cnpj',how='semi')
st=p.filter(pl.col('m')==START_M).select('cnpj',pl.col('q').alias('q0'),pl.col('dt').alias('d0'))
p=p.join(st,on='cnpj',how='semi')
# cobertura mensal desde out/2021
w=p.filter(pl.col('m')>=START_M)
cov=w.group_by('cnpj').agg(pl.len().alias('nmeses'))
# retorno anual (cota de fim de ano)
ye=p.sort('m').group_by(['cnpj','y']).last().sort(['cnpj','y'])
ye=ye.with_columns((pl.col('q')/pl.col('q').shift(1).over('cnpj')-1).alias('ret'), pl.col('y').shift(1).over('cnpj').alias('yprev'))
ye=ye.filter(pl.col('yprev')==pl.col('y')-1)
annual=ye.pivot(on='y',index='cnpj',values='ret').rename(lambda c: c if c=='cnpj' else f'a{c}')
worst=ye.group_by('cnpj').agg(pl.col('ret').min().alias('pior_ano'),pl.len().alias('nanos'))
# retorno mensal p/ drawdown e beta-dólar
mm=w.sort(['cnpj','m']).with_columns((pl.col('q')/pl.col('q').shift(1).over('cnpj')-1).alias('r')).drop_nulls('r')
u_dates=sorted(set(mm['dt'].to_list()))
umap=dict(zip(u_dates,idx_at(usd,'u',u_dates)))
mm=mm.with_columns(pl.col('dt').replace_strict(umap,return_dtype=pl.Float64).alias('ux'))
mm=mm.with_columns((pl.col('ux')/pl.col('ux').shift(1).over('cnpj')-1).alias('du'))
beta=mm.drop_nulls('du').group_by('cnpj').agg(pl.corr('r','du').alias('corr_usd'),(pl.cov('r','du')/pl.col('du').var()).alias('beta_usd'))
dd=w.sort(['cnpj','m']).with_columns((pl.col('q')/pl.col('q').cum_max().over('cnpj')-1).alias('dd')).group_by('cnpj').agg(pl.col('dd').min().alias('max_dd_mensal'))
# retorno 5a vs CDI no mesmo intervalo exato
last=p.filter(pl.col('m')==D.date(2026,11,1)).select('cnpj',pl.col('q').alias('q1'),pl.col('dt').alias('d1'),'pl','cot')
r=st.join(last,on='cnpj')
ds=sorted(set(r['d0'].to_list()+r['d1'].to_list())); lmap=dict(zip(ds,idx_at(cdi,'lc',ds)))
r=r.with_columns((pl.col('q1')/pl.col('q0')-1).alias('ret5'),
   ((pl.col('d1').replace_strict(lmap,return_dtype=pl.Float64)-pl.col('d0').replace_strict(lmap,return_dtype=pl.Float64)).exp()-1).alias('cdi5'))
r=r.with_columns((pl.col('ret5')/pl.col('cdi5')).alias('pct_cdi'),((pl.col('d1')-pl.col('d0')).dt.total_days()/365.25).alias('anos'))
r=r.with_columns(((1+pl.col('ret5'))**(1/pl.col('anos'))-1).alias('ret_aa'))
df=r.join(cov,on='cnpj').join(worst,on='cnpj').join(annual,on='cnpj',how='left').join(beta,on='cnpj',how='left').join(dd,on='cnpj',how='left').join(meta,on='cnpj',how='left')
df.write_parquet(f'{W}/universo.parquet')
print('fundos vivos com 5a de histórico:',df.height)
f=df.filter(pl.col('nmeses')>=55)
print('cobertura ok:',f.height)
f=f.filter(pl.col('pior_ano')>-0.10); print('sem ano < -10%:',f.height)
f=f.filter(pl.col('pct_cdi')>=1.5); print('>=150% CDI:',f.height)
f.write_parquet(f'{W}/filtrado.parquet')
print('CDI 5a médio:',r['cdi5'].median())
