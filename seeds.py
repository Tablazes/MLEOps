"""Sanity-zinnen voor het cloud-sentimentmodel: single source of truth.

Een klein setje evident positieve/negatieve zinnen om te checken dat het
getrainde model de duidelijke gevallen goed labelt. Staat hier zodat het
notebook (sectie 2) en eventuele hertraining exact dezelfde zinnen gebruiken.

LET OP: dit zijn geen trainingsdata en niet de held-out ASR-testzinnen; puur
een generalisatie-sanitycheck.
"""

# Sanity-zinnen: evident positieve/negatieve gevallen om de labeling te checken.
SANITY_TEXTS = [
    ('het gaat goed, stabiel, geen klachten',  1),
    ('ik voel me prima, helder en kalm',       1),
    ('ernstige pijn op de borst, bewusteloos', 0),
    ('hartaanval, ik kan niet ademen, help',   0),
]
