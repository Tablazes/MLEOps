"""Domein-seedzinnen voor het cloud-sentimentmodel: single source of truth.

De DBRD-boekenrecensies dekken alarmcentrale-taal niet af, dus oversamplen we
een handvol zorg-/spoedzinnen mee bij de training. Die letterlijke lijsten staan
hier zodat het notebook (sectie 2) en eventuele hertraining exact dezelfde
seeds gebruiken; geen kopie die uit de pas kan lopen.

LET OP: dit zijn TRAININGS-seeds, niet de 20 held-out ASR-testzinnen. Die
laatste blijven bewust zichtbaar in het notebook (dat is de testset).
"""

# Domein-zinnen, oversampled zodat de logreg ook spoed-vocabulaire gewicht geeft
# (niet enkel boekentaal). Label 1 = rustig/positief, 0 = spoed/negatief.
DOMAIN_SEEDS = [
    # Positief: rustige, stabiele situaties.
    ('het gaat goed met me', 1),
    ('ik voel me prima',     1),
    ('alles is rustig',      1),
    ('stabiel, geen pijn',   1),
    ('het gaat beter, kalm', 1),
    ('geen klachten',        1),
    ('helder en wakker',     1),
    ('dank voor het luisteren', 1),
    ('ik begrijp het, fijn', 1),
    ('alles goed, normaal',  1),
    # Negatief: spoed-zinnen.
    ('pijn op de borst',                        0),
    ('ernstige pijn op de borst, bewusteloos',  0),
    ('ik kan niet ademen, benauwd',             0),
    ('hartaanval, help',                        0),
    ('mijn moeder is gevallen, bewusteloos',    0),
    ('overdosis pillen',                        0),
    ('hoge koorts en stuipen',                  0),
    ('bloeding, veel bloed',                    0),
    ('beroerte, halve gezicht hangt',           0),
    ('flauwgevallen, niet aanspreekbaar',       0),
]

# Sanity-zinnen: kleine variaties op bovenstaande om generalisatie te checken.
SANITY_TEXTS = [
    ('het gaat goed, stabiel, geen klachten',  1),
    ('ik voel me prima, helder en kalm',       1),
    ('ernstige pijn op de borst, bewusteloos', 0),
    ('hartaanval, ik kan niet ademen, help',   0),
]
