# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Element symbols and covalent radii, for reading structures and finding bonds."""

# Index + 1 is the atomic number.
SYMBOLS = (
    'H He '
    'Li Be B C N O F Ne '
    'Na Mg Al Si P S Cl Ar '
    'K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr '
    'Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe '
    'Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn '
    'Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'
).split()

# Covalent radii in Å, H to Cm (Cordero et al., Dalton Trans. 2008, 2832); low-spin values
# for Mn, Fe, Co, sp3 for C.
_RADII = (
    '0.31 0.28 '
    '1.28 0.96 0.84 0.76 0.71 0.66 0.57 0.58 '
    '1.66 1.41 1.21 1.11 1.07 1.05 1.02 1.06 '
    '2.03 1.76 1.70 1.60 1.53 1.39 1.39 1.32 1.26 1.24 1.32 1.22 1.22 1.20 1.19 1.20 1.20 1.16 '
    '2.20 1.95 1.90 1.75 1.64 1.54 1.47 1.46 1.42 1.39 1.45 1.44 1.42 1.39 1.39 1.38 1.39 1.40 '
    '2.44 2.15 2.07 2.04 2.03 2.01 1.99 1.98 1.98 1.96 1.94 1.92 1.92 1.89 1.90 1.87 1.87 '
    '1.75 1.70 1.62 1.51 1.44 1.41 1.36 1.36 1.32 1.45 1.46 1.48 1.40 1.50 1.50 '
    '2.60 2.21 2.15 2.06 2.00 1.96 1.90 1.87 1.80 1.69'
).split()
COVALENT_RADII = dict(zip(SYMBOLS, map(float, _RADII)))
DEFAULT_COVALENT_RADIUS = 1.5


def atomic_number(symbol: str) -> int:
    return SYMBOLS.index(symbol) + 1
