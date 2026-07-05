"""DBRD-ingest en -cleaning: single source of truth voor de datalagen.

De ruwe -> schone -> streaming-cleaning pijplijn op de 110kDBRD-recensies
(download, uitpakken, HTML strippen, dedupe, batch-gewijs schrijven) staat hier,
zodat het notebook (sectie 1) alleen nog importeert, aanroept en het resultaat
valideert/plot. Zo blijft de transformatie-logica op een plek en kan de
streaming-variant ook door de benchmark (bench.py) hergebruikt worden.
"""
import logging
import os
import tarfile

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

log = logging.getLogger('vitacall')

# Bron: https://github.com/benjaminvdb/110kDBRD - 110k Nederlandse boekenrecensies van Hebban.nl
DBRD_URL = 'https://github.com/benjaminvdb/110kDBRD/releases/download/v3.0/DBRD_v3.tgz'


def download_dbrd(base_dir):
    """Download+unpack de DBRD tar.gz naar base_dir/DBRD/. Idempotent."""
    out_dir = os.path.join(base_dir, 'DBRD')
    if os.path.exists(out_dir) and any(os.scandir(out_dir)):
        log.info('DBRD al uitgepakt in %s', out_dir)
        return out_dir
    tar_path = os.path.join(base_dir, 'DBRD_v3.tgz')
    if not os.path.exists(tar_path):
        log.info('DBRD downloaden (eenmalig, ~155 MB)...')
        with requests.get(DBRD_URL, stream=True, timeout=300) as r:
            r.raise_for_status()
            # In chunks schrijven zodat het grote bestand niet in één keer in geheugen komt
            with open(tar_path, 'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
    log.info('DBRD uitpakken...')
    with tarfile.open(tar_path, 'r:gz') as tar:
        tar.extractall(path=base_dir)
    return out_dir


def ingest_dbrd(dbrd_dir, out):
    """Ruwe laag: alle .txt-recensies uit train/test/{pos,neg} naar één Parquet."""
    rows = []
    # Mappenstructuur bepaalt het label: pos -> 1, neg -> 0
    for split in ['train', 'test']:
        for sentiment, label in [('pos', 1), ('neg', 0)]:
            sdir = os.path.join(dbrd_dir, split, sentiment)
            if not os.path.isdir(sdir):
                continue
            for fname in os.listdir(sdir):
                if not fname.endswith('.txt'):
                    continue
                with open(os.path.join(sdir, fname), encoding='utf-8') as f:
                    rows.append((f'{split}_{sentiment}_{fname[:-4]}', f.read(), label,
                                 f'{split}/{sentiment}/{fname}'))
    if not rows:
        raise RuntimeError(f'Geen recensies gevonden in {dbrd_dir} - dataset goed uitgepakt?')
    os.makedirs(out, exist_ok=True)
    df = pd.DataFrame(rows, columns=['review_id', 'text', 'label', 'source_file'])
    df.to_parquet(os.path.join(out, 'reviews.parquet'), index=False)
    log.info('Ruwe laag: %d recensies geschreven naar %s', len(df), out)


def ingest_sentiment(out, s140_cache='data/sentiment140_30k.parquet', s140_n=30_000, seed=42):
    """Ruwe laag op de opdracht-datasets: IMDb (Maas et al., 2011) + Sentiment140
    (Go et al., 2009) samengevoegd tot één Parquet met dezelfde kolommen als de
    DBRD-ingest (review_id, text, label, source_file). De pipeline erna (cleaning,
    Spark-split, validatie, manifest) blijft daardoor ongewijzigd werken."""
    from datasets import load_dataset

    imdb = load_dataset('imdb')
    imdb_df = pd.DataFrame({
        'text': list(imdb['train']['text']) + list(imdb['test']['text']),
        'label': list(imdb['train']['label']) + list(imdb['test']['label']),
        'source_file': 'imdb',
    })
    # Sentiment140: sample lokaal gecachet (1.6M is te groot voor een eindrun);
    # sentiment 0/4 -> label 0/1. Bij ontbrekende cache eenmalig van HF halen.
    if os.path.exists(s140_cache):
        s140 = pd.read_parquet(s140_cache)
    else:
        raw = pd.read_parquet('hf://datasets/stanfordnlp/sentiment140@refs/convert/'
                              'parquet/sentiment140/train/0000.parquet',
                              columns=['text', 'sentiment'])
        raw = raw[raw['sentiment'].isin([0, 4])].copy()
        raw['label'] = (raw['sentiment'] == 4).astype(int)
        s140 = raw.sample(s140_n, random_state=seed)[['text', 'label']]
        os.makedirs(os.path.dirname(s140_cache), exist_ok=True)
        s140.to_parquet(s140_cache, index=False)
    s140 = s140[['text', 'label']].copy()
    s140['source_file'] = 'sentiment140'

    # Stratified train/test-split (80/20) per bron, in het pad zodat _clean_df het oppikt.
    df = pd.concat([imdb_df, s140], ignore_index=True)
    df['review_id'] = range(len(df))
    rng = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    n_test = int(len(rng) * 0.2)
    rng['_split'] = ['test'] * n_test + ['train'] * (len(rng) - n_test)
    rng['source_file'] = rng['_split'] + '/' + rng['source_file']
    rng = rng[['review_id', 'text', 'label', 'source_file']]
    os.makedirs(out, exist_ok=True)
    rng.to_parquet(os.path.join(out, 'reviews.parquet'), index=False)
    log.info('Ruwe laag (IMDb+Sentiment140): %d reviews naar %s', len(rng), out)


def _clean_df(df):
    """Gedeelde cleaning: HTML-tags eruit, witruimte normaliseren, split uit pad."""
    df = df.copy()
    df['text_clean'] = (df['text']
                        .str.replace(r'<[^>]+>', ' ', regex=True)
                        .str.replace(r'\s+', ' ', regex=True)
                        .str.strip())
    # split halen we uit het pad (train/test) zodat we de oorspronkelijke verdeling houden
    df['split'] = df['source_file'].str.split('/').str[0]
    return df[df['label'].isin([0, 1])
              & df['text_clean'].notna()
              & (df['text_clean'] != '')]


def clean_reviews(raw_path, out):
    """Schone laag: duplicaten weg, anders traint het model op herhaling."""
    df = (_clean_df(pd.read_parquet(raw_path))
          .drop_duplicates(subset=['text_clean'])
          .reset_index(drop=True))
    os.makedirs(out, exist_ok=True)
    df.to_parquet(os.path.join(out, 'reviews.parquet'), index=False)
    log.info('Schone laag: %d unieke recensies (van %d ruw)',
             len(df), len(pd.read_parquet(raw_path)))


def clean_reviews_streaming(raw_path, out, chunk_size=5000):
    """Streaming-variant: zelfde _clean_df-transformaties, maar batch-gewijs."""
    pf = pq.ParquetFile(raw_path)
    os.makedirs(out, exist_ok=True)
    n_total = 0
    writer = None
    # Per batch verwerken houdt het geheugengebruik laag, ook bij miljoenen rijen
    try:
        for batch in pf.iter_batches(batch_size=chunk_size):
            df = _clean_df(batch.to_pandas())
            n_total += len(df)
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:   # writer pas bij eerste batch: schema klopt dan
                writer = pq.ParquetWriter(os.path.join(out, 'reviews.parquet'), table.schema)
            writer.write_table(table)
    finally:
        # Writer altijd sluiten, ook bij een fout, anders blijft het bestand corrupt
        if writer:
            writer.close()
    return n_total
