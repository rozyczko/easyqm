# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""pw.x ``bands`` and ``nscf`` runs written as pw.x 7.5 prints them, for the parser tests.

No Quantum ESPRESSO run made these: the levels are whatever a test gives. The layout follows
pw.x's output with ``verbosity = 'high'``, line for line where the parser reads it: the
lattice parameter, the electron count, the crystal axes, the k-point list with its weights
(Cartesian, then crystal coordinates), the tetrahedra header, and the levels under 'End of
band structure calculation'.
"""


def expand(vertices) -> list[tuple[float, float, float]]:
    """The k-points pw.x makes of ``K_POINTS crystal_b`` vertices: `count` points from each
    vertex towards the next, then the last vertex."""
    points = []
    for (start, count, _), (end, _, _) in zip(vertices, vertices[1:]):
        points += [tuple(a + (b - a) * j / count for a, b in zip(start, end)) for j in range(count)]
    points.append(tuple(vertices[-1][0]))
    return points


def pw_run(kpoints, levels, *, axes=((1, 0, 0), (0, 1, 0), (0, 0, 1)), alat=10.2629, electrons='32.00',
           weights=None, fermi=None, tetrahedra=False) -> str:
    """One pw.x non-SCF run. `kpoints` in Cartesian units of 2π/alat; `levels` per spin channel
    (one or two), per k-point; `electrons` as printed after '='."""
    weights = weights or [2 / len(kpoints)] * len(kpoints)
    lines = [
        '',
        '     Program PWSCF v.7.5 starts on  1Nov2026 at 18: 0: 0 ',
        '',
        f'     lattice parameter (alat)  = {alat:12.4f}  a.u.',
        '     number of atoms/cell      =            8',
        f'     number of electrons       =        {electrons}',
        f'     number of Kohn-Sham states=  {len(levels[0][0]):10d}',
        '',
        '     crystal axes: (cart. coord. in units of alat)',
        *(f'               a({i}) = ({x:11.6f}{y:11.6f}{z:11.6f} )  ' for i, (x, y, z) in enumerate(axes, 1)),
        '',
        '     reciprocal axes: (cart. coord. in units 2 pi/alat)',
        '               b(1) = (  1.000000  0.000000  0.000000 )  ',
        '',
        f'     number of k points={len(kpoints):6d}'
        + (' (tetrahedron method)' if tetrahedra else '  Marzari-Vanderbilt smearing, width (Ry)=  0.0100'),
        '                       cart. coord. in units 2pi/alat',
        *(f'        k({i:5d}) = ({x:12.7f}{y:12.7f}{z:12.7f}), wk ={w:12.7f}'
          for i, ((x, y, z), w) in enumerate(zip(kpoints, weights), 1)),
        '',
        '                       cryst. coord.',
        *(f'        k({i:5d}) = ({x:12.7f}{y:12.7f}{z:12.7f}), wk ={w:12.7f}'
          for i, ((x, y, z), w) in enumerate(zip(kpoints, weights), 1)),
        '',
        '     Band Structure Calculation',
        '     Davidson diagonalization with overlap',
        '',
        '     ethr =  3.13E-13,  avg # of iterations = 20.1',
        '',
        '     total cpu time spent up to now is        9.9 secs',
        '',
        '     End of band structure calculation',
    ]
    for channel, name in zip(levels, ('UP', 'DOWN') if len(levels) == 2 else ('',)):
        if name:
            lines += ['', f' ------ SPIN {name} {"-" * (12 if name == "UP" else 10)}', '']
        for (x, y, z), energies in zip(kpoints, channel):
            lines += ['', f'          k ={x:7.4f}{y:7.4f}{z:7.4f} (  2969 PWs)   bands (ev):', '']
            lines += ['  ' + ''.join(f'{e:9.4f}' for e in energies[i : i + 8]) for i in range(0, len(energies), 8)]
    if fermi is not None:
        lines += ['', f'     the Fermi energy is {fermi:10.4f} ev']
    lines += [
        '',
        '     Writing all to output data dir .\\tmp\\job.save\\ :',
        '     XML data file, pseudopotentials, collected wavefunctions',
        '',
        '     PWSCF        :      9.93s CPU      1.35s WALL',
        '',
        '   JOB DONE.',
        '',
    ]
    return '\n'.join(lines)
