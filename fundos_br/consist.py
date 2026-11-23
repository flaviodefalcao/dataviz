# Consistência: volatilidade mensal, concentração do ganho no melhor ano, anos acima do CDI
import polars as pl, datetime as D, math, sys
W=sys.argv[1]
u=pl.read_parquet(f'{W}/universo.parquet').filter((pl.col('nmeses')>=55)&(pl.col('exclusivo')!='S')&(pl.col('pl')>=3e7)&(pl.col('cot')>=50))
p=pl.read_parquet(f'{W}/panel.parquet').join(u.select('cnpj'),on='cnpj',how='semi').filter(pl.col('m')>=D.date(2021,10,1)).sort(['cnpj','m'])
r=p.with_columns((pl.col('q')/pl.col('q').shift(1).over('cnpj')-1).alias('r')).drop_nulls('r')
v=r.group_by('cnpj').agg((pl.col('r').std()*math.sqrt(12)).alias('vol'),(pl.col('r')>0).mean().alias('meses_pos'),pl.col('r').min().alias('pior_mes'))
CDI={2022:.1239,2023:.1304,2024:.1088,2025:.1432,2026:.1237}
Y=list(CDI)
df=u.join(v,on='cnpj').with_columns(
  pl.max_horizontal([(1+pl.col(f'a{y}')).log() for y in Y]).alias('lmax'),
  pl.sum_horizontal([(1+pl.col(f'a{y}')).log() for y in Y]).alias('lsum'),
  pl.sum_horizontal([(pl.col(f'a{y}')>=CDI[y]).cast(pl.Int8) for y in Y]).alias('anos_acima_cdi'),
  pl.min_horizontal([pl.col(f'a{y}') for y in Y]).alias('pior_ano2'))
df=df.with_columns((pl.col('lmax')/pl.col('lsum')).alias('conc_melhor_ano'),((pl.col('ret_aa')-0.1288)/pl.col('vol')).alias('sharpe'))
df.write_parquet(f'{W}/consist.parquet')
pl.Config.set_tbl_rows(80); pl.Config.set_fmt_str_lengths(42); pl.Config.set_tbl_width_chars(300)
base=df.filter(pl.col('a2022').is_not_null()&(pl.col('lsum')>0))
for lim in [1.5,1.3,1.2]:
  f=base.filter((pl.col('pct_cdi')>=lim)&(pl.col('conc_melhor_ano')<=0.35)&(pl.col('pior_ano2')>=0)&(pl.col('vol')<=0.08)&(pl.col('anos_acima_cdi')>=4))
  print(lim,f.height)
f=base.filter((pl.col('pct_cdi')>=1.2)&(pl.col('conc_melhor_ano')<=0.35)&(pl.col('pior_ano2')>=0)&(pl.col('vol')<=0.08)&(pl.col('anos_acima_cdi')>=4)).sort('sharpe',descending=True)
print(f.select('cnpj',pl.col('nome').str.slice(0,42),pl.col('gestor').str.slice(0,22),(pl.col('ret5')*100).round(0),(pl.col('pct_cdi')*100).round(0),(pl.col('vol')*100).round(1),(pl.col('conc_melhor_ano')*100).round(0),'anos_acima_cdi',*[(pl.col(f'a{y}')*100).round(1) for y in Y],(pl.col('max_dd_mensal')*100).round(1),(pl.col('pl')/1e6).round(0),'cot',pl.col('anbima').str.slice(0,26)))
