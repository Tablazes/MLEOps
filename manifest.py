"""SHA256-dataset-manifest: single source of truth.

Legt per datalaag (ruw -> schoon -> trainklaar) de vingerafdruk vast: rij-count,
kolommen, SHA256 over de parquet-bytes, grootte en label-verdeling, plus de
omgeving (versies/seed/platform/git-sha). Zo kan een reviewer of CI verifieren
dat exact deze data + code de resultaten produceerde. Het notebook geeft de
laag-paden door en toont het resultaat; de hash-plumbing zit hier.
"""
import glob
import hashlib
import os
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import sklearn


def hash_files(paths) -> str:
    """SHA256 over een of meer files in vaste volgorde, in 1MB-blokken."""
    h = hashlib.sha256()
    for p in paths:
        with open(p, 'rb') as f:
            for blk in iter(lambda: f.read(1 << 20), b''):
                h.update(blk)
    return h.hexdigest()


def _layer_parts(path):
    """Laag = los reviews.parquet OF Spark-map met part-*.parquet."""
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, '*.parquet')))
    return [path] if os.path.exists(path) else []


def _git_sha() -> str:
    """Korte git-HEAD zodat het manifest aan een code-versie hangt."""
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return 'unknown'


def build_manifest(layers, seed):
    """Bouw het manifest-dict voor de gegeven (laag-naam, pad)-paren.

    `layers` is een lijst van (laag-naam, pad); een pad is een los parquet-bestand
    of een Spark-map met part-files.
    """
    entries = []
    for layer, path in layers:
        parts = _layer_parts(path)
        if not parts:   # ontbrekende laag noteren zodat gaten zichtbaar blijven
            entries.append({'layer': layer, 'path': path, 'status': 'missing'})
            continue
        df = pd.read_parquet(path)
        size = round(sum(os.path.getsize(p) for p in parts) / 1024 / 1024, 2)
        entries.append({
            'layer': layer, 'path': path, 'rows': int(len(df)),
            'n_files': len(parts), 'cols': list(df.columns),
            'sha256': hash_files(parts), 'size_mb': size,
            'label_dist': (df['label'].value_counts().to_dict()
                           if 'label' in df.columns else None),
        })
    # Omgeving (versies/seed/platform) toevoegen zodat resultaten herhaalbaar zijn.
    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'git_sha': _git_sha(), 'python': sys.version.split()[0],
        'platform': platform.platform(), 'seed': seed,
        'sklearn': sklearn.__version__, 'pandas': pd.__version__,
        'numpy': np.__version__, 'layers': entries,
    }
