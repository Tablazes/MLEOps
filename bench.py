"""Throughput- + piek-geheugen-benchmark: single source of truth.

De streaming-cleaner moet geheugen-begrensd zijn (piek-RSS vlak over batch-sizes,
ongeacht datavolume). Die meet-plumbing -- een achtergrond-sampler voor de RSS-piek
plus de benchmark-lus -- staat hier zodat het notebook alleen nog aanroept en de
tabel/plot toont. De cleaning-functie wordt als argument doorgegeven, zodat deze
module niets uit het notebook hoeft te importeren.
"""
import gc
import os
import tempfile
import threading
import time


def _rss_mb() -> float:
    """Huidige resident-set-size van dit proces in MB."""
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


class _PeakSampler:
    """Bemonstert RSS in een achtergrond-thread en houdt de piek bij.

    Meet zo het piek-geheugen TIJDENS het streamen, niet alleen het verschil
    ervoor/erna (dat de tussentijdse piek zou missen).
    """
    def __init__(self, interval: float = 0.02):
        self.interval = interval
        self.peak = _rss_mb()
        self._stop = threading.Event()
        self._t = None

    def _run(self):
        while not self._stop.is_set():
            cur = _rss_mb()
            if cur > self.peak:
                self.peak = cur
            self._stop.wait(self.interval)

    def __enter__(self):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=1)


def benchmark_cleaning(clean_fn, raw_path, batch_sizes=(1000, 5000, 20000)):
    """Meet per batch-size tijd, doorvoer en piek-geheugen van `clean_fn`.

    `clean_fn(raw_path, out_dir, chunk_size=...)` schrijft de schone laag weg;
    de output gaat naar een tijdelijke map die per run wordt opgeruimd.
    """
    results = []
    for bs in batch_sizes:
        gc.collect()                 # eerlijke basislijn vlak voor de run
        rss_before = _rss_mb()
        with _PeakSampler() as sampler:
            with tempfile.TemporaryDirectory() as tmp:
                t0 = time.perf_counter()
                n = clean_fn(raw_path, tmp, chunk_size=bs)
                elapsed = time.perf_counter() - t0
        results.append({
            'batch_size': bs, 'rows': n, 'elapsed_s': round(elapsed, 2),
            'throughput_rps': int(n / max(elapsed, 1e-9)),
            'peak_rss_mb': round(sampler.peak, 1),
            'rss_before_mb': round(rss_before, 1),
        })
    return results
