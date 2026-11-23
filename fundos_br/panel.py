import polars as pl, zipfile, io, glob, sys
raw=sys.argv[1]; out=[]
for z in sorted(glob.glob(raw+'/inf_diario_fi_*.zip')):
    zf=zipfile.ZipFile(z)
    for n in zf.namelist():
        df=pl.read_csv(io.BytesIO(zf.read(n)),separator=';',infer_schema_length=0,encoding='utf8-lossy',truncate_ragged_lines=True)
        cn='CNPJ_FUNDO_CLASSE' if 'CNPJ_FUNDO_CLASSE' in df.columns else 'CNPJ_FUNDO'
        if 'ID_SUBCLASSE' in df.columns: df=df.filter(pl.col('ID_SUBCLASSE').is_null()|(pl.col('ID_SUBCLASSE')==''))
        df=df.select(pl.col(cn).str.replace_all(r'\D','').alias('cnpj'),pl.col('DT_COMPTC').str.to_date().alias('dt'),
            pl.col('VL_QUOTA').cast(pl.Float64).alias('q'),pl.col('VL_PATRIM_LIQ').cast(pl.Float64).alias('pl'),pl.col('NR_COTST').cast(pl.Float64,strict=False).alias('cot'))
        df=df.filter(pl.col('q')>0).with_columns(pl.col('dt').dt.truncate('1mo').alias('m')).sort('dt').group_by(['cnpj','m']).last()
        out.append(df); print(n,df.height,flush=True)
p=pl.concat(out).sort('dt').group_by(['cnpj','m']).last().sort(['cnpj','m'])
p.write_parquet(sys.argv[2])
