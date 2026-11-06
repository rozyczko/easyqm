# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
"""Qt-free sample state: the molecule or crystal the calculations are run on (GENERAL_DESIGN.md, 3.2).

Structures are read from XYZ files (with a cell when extended XYZ gives one) by `read_xyz`
and from CIF files by `read_cif`. A crystal holds the full content of its unit cell (P1):
symmetry is expanded on reading, and the atoms are wrapped into the cell.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from typing import Union

from .elements import COVALENT_RADII
from .elements import DEFAULT_COVALENT_RADIUS
from .elements import SYMBOLS
from .elements import atomic_number
from .geometry import Vec
from .geometry import cross
from .geometry import distance
from .geometry import dot
from .geometry import norm

STRUCTURES_DIR = Path(__file__).resolve().parents[3] / 'Resources' / 'structures'
BENZENE = STRUCTURES_DIR / 'benzene.xyz'  # the sample at start-up and after a reset

_BOND_TOLERANCE = 1.2
MAX_FILE_BYTES = 20 * 1024 * 1024  # larger structure files are refused before reading
MULTIPLICITY_NAMES = ('singlet', 'doublet', 'triplet', 'quartet', 'quintet', 'sextet', 'septet')
_WRAP_TOLERANCE = 1e-6  # a fractional coordinate this close to 0 or 1 is 0
_OCCUPANCY_TOLERANCE = 1e-3
_SAME_POSITION = 1e-3  # Å; engines echo the input positions rounded
_FLAT_CELL = 1e-3  # a cell with less volume than this fraction of a·b·c is refused
_LATTICE = re.compile(r'Lattice\s*=\s*"([^"]*)"', re.IGNORECASE)
_PBC = re.compile(r'pbc\s*=\s*"([^"]*)"', re.IGNORECASE)


@dataclass
class Atom:
    label: str
    element: str
    x: float
    y: float
    z: float
    fixed: bool = False  # kept in place by the optimiser


@dataclass
class Cell:
    """A unit cell: the three lattice vectors a, b, c in Å, Cartesian, as read."""

    vectors: tuple[Vec, Vec, Vec]
    space_group: str = ''  # short Hermann-Mauguin symbol, 'Fm-3m'; '' when unknown

    @classmethod
    def from_parameters(cls, a, b, c, alpha, beta, gamma, space_group: str = '') -> 'Cell':
        """a along x, b in the xy plane: the setting gemmi uses for CIF coordinates."""
        cos_alpha, cos_beta, cos_gamma = (math.cos(math.radians(angle)) for angle in (alpha, beta, gamma))
        sin_gamma = math.sin(math.radians(gamma))
        cx = c * cos_beta
        cy = c * (cos_alpha - cos_beta * cos_gamma) / sin_gamma
        cz = math.sqrt(max(0.0, c * c - cx * cx - cy * cy))
        return cls(((a, 0.0, 0.0), (b * cos_gamma, b * sin_gamma, 0.0), (cx, cy, cz)), space_group)

    def with_parameters(self, a, b, c, alpha, beta, gamma) -> 'Cell':
        """A cell of these parameters, turned like this one: a keeps its direction and b stays in
        the plane of a and b. The space group goes, as the new cell may not have it.

        :raises ValueError: for a length that is not positive or angles that span no cell.
        """
        if min(a, b, c) <= 0:
            raise ValueError('Cell lengths must be positive.')
        if not all(0 < angle < 180 for angle in (alpha, beta, gamma)):
            raise ValueError('Cell angles must lie between 0° and 180°.')
        new = Cell.from_parameters(a, b, c, alpha, beta, gamma)
        if new.volume < _FLAT_CELL * a * b * c:
            raise ValueError('These angles do not form a cell.')
        # The rotation from the standard setting to this cell's, applied to the new cell.
        standard = Cell.from_parameters(*self.lengths, *self.angles)
        return Cell(tuple(self.cartesian(*standard.fractional(*vector)) for vector in new.vectors))

    @property
    def lengths(self) -> Vec:
        """a, b, c in Å."""
        return tuple(norm(vector) for vector in self.vectors)

    @property
    def angles(self) -> Vec:
        """alpha (b, c), beta (a, c), gamma (a, b) in degrees."""
        a, b, c = self.vectors
        return tuple(_angle_between(u, v) for u, v in ((b, c), (a, c), (a, b)))

    @property
    def volume(self) -> float:
        a, b, c = self.vectors
        return abs(dot(a, cross(b, c)))

    @property
    def reciprocal(self) -> tuple[Vec, Vec, Vec]:
        """Reciprocal vectors in Å⁻¹, without the 2π factor: a*·a = 1, a*·b = 0."""
        a, b, c = self.vectors
        volume = dot(a, cross(b, c))
        return tuple(tuple(x / volume for x in cross(u, v)) for u, v in ((b, c), (c, a), (a, b)))

    def fractional(self, x: float, y: float, z: float) -> Vec:
        return tuple(dot((x, y, z), vector) for vector in self.reciprocal)

    def cartesian(self, fa: float, fb: float, fc: float) -> Vec:
        return tuple(fa * a + fb * b + fc * c for a, b, c in zip(*self.vectors))


def _angle_between(u: Vec, v: Vec) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(u, v) / (norm(u) * norm(v))))))


class Sample:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.name = ''
        self.source = ''  # file the atoms came from, e.g. 'benzene.xyz'
        self.atoms: list[Atom] = []
        self.cell: Optional[Cell] = None  # None for a molecule
        self.charge = 0
        self.multiplicity = 1

    @classmethod
    def benzene(cls) -> 'Sample':
        sample = cls()
        sample.load(BENZENE)
        return sample

    # Derived

    @property
    def periodic(self) -> bool:
        return self.cell is not None

    @property
    def atom_count(self) -> int:
        return len(self.atoms)

    @property
    def formula_units(self) -> int:
        """Z: the formula units in the cell of a crystal (gcd of the element counts); 1 for a molecule."""
        if not self.periodic or not self.atoms:
            return 1
        return math.gcd(*self._element_counts().values())

    @property
    def formula(self) -> str:
        """Hill order: C, then H, then the rest alphabetically; count omitted when 1.

        A crystal's formula is that of one formula unit: NaCl's cell of 8 atoms gives 'ClNa'.
        """
        counts = self._element_counts()
        units = self.formula_units
        ordered = [element for element in ('C', 'H') if element in counts]
        ordered += sorted(element for element in counts if element not in ('C', 'H'))
        return ''.join(f'{element}{counts[element] // units if counts[element] > units else ""}' for element in ordered)

    @property
    def summary(self) -> str:
        """'benzene.xyz · C6H6 · 12 atoms'; 'NaCl.cif · ClNa · Z = 4 · 8 atoms · Fm-3m' for a crystal."""
        parts = [self.source, self.formula]
        if self.periodic:
            parts.append(f'Z = {self.formula_units}')
        parts.append(f'{self.atom_count} atoms')
        if self.periodic:
            parts.append(self.cell.space_group)
        return ' · '.join(part for part in parts if part)

    @property
    def fixed_count(self) -> int:
        return sum(atom.fixed for atom in self.atoms)

    def _element_counts(self) -> Counter:
        return Counter(atom.element for atom in self.atoms)

    def _electrons(self, charge: Optional[int] = None) -> int:
        return sum(atomic_number(atom.element) for atom in self.atoms) - (self.charge if charge is None else charge)

    # Electronic state

    def multiplicities(self, charge: Optional[int] = None) -> list[int]:
        """The multiplicities the electron count allows, lowest first, up to a septet."""
        electrons = self._electrons(charge)
        return list(range(1 + electrons % 2, min(electrons + 1, len(MULTIPLICITY_NAMES)) + 1, 2))

    def electronic_state_problem(self, charge: int, multiplicity: int) -> str:
        """Why the electron count does not allow this pair, or '' if it does."""
        if self._electrons(charge) < 0:
            return f'A charge of {charge:+d} leaves fewer than no electrons.'
        allowed = self.multiplicities(charge)
        if multiplicity not in allowed:
            return (f'With charge {charge:+d} the {self._electrons(charge)} electrons allow multiplicity '
                    + ', '.join(map(str, allowed)) + f', not {multiplicity}.')
        return ''

    def set_electronic_state(self, charge: int, multiplicity: int) -> None:
        """Set both together. :raises ValueError: for a pair the electron count does not allow;
        nothing changes then."""
        problem = self.electronic_state_problem(charge, multiplicity)
        if problem:
            raise ValueError(problem)
        self.charge, self.multiplicity = charge, multiplicity

    def set_charge(self, charge: int) -> None:
        """Set the charge; a multiplicity the new electron count does not allow goes to the
        lowest one it allows. :raises ValueError: as `set_electronic_state`."""
        allowed = self.multiplicities(charge)
        keep = self.multiplicity in allowed or not allowed
        self.set_electronic_state(charge, self.multiplicity if keep else allowed[0])

    # Input

    def load(self, path: Union[str, Path]) -> None:
        """Replace the structure with the one in a CIF or XYZ file. On an error the sample is unchanged.

        The files hold no charge or spin, so the charge goes back to 0 and the multiplicity to
        the lowest one the electron count allows (singlet or doublet).
        """
        path = Path(path)
        with path.open('rb') as file:
            content = file.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(f'The file is larger than {MAX_FILE_BYTES // 1024 // 1024} MB.')
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            raise ValueError('The file is not a text file.')
        read = read_cif if path.suffix.lower() == '.cif' else read_xyz
        atoms, cell = read(text)
        if cell is not None:
            _wrap(atoms, cell)
        self.atoms = atoms
        self.cell = cell
        self.source = path.name
        self.name = path.stem
        self.charge = 0
        self.multiplicity = 1 + self._electrons() % 2

    # Geometry from a calculation

    def at_positions(self, atoms: list[Atom]) -> bool:
        """Whether `atoms` are the sample's atoms, in the same order and at the same positions."""
        return len(atoms) == len(self.atoms) and all(
            new.element == atom.element and distance(new, atom) < _SAME_POSITION
            for atom, new in zip(self.atoms, atoms)
        )

    def move_atoms(self, atoms: list[Atom], cell: Optional[Cell] = None) -> None:
        """Move the atoms to the positions of `atoms`, the same atoms in the same order, and give
        a crystal the new `cell` if there is one. Labels and fixed flags are kept.

        :raises ValueError: if `atoms` are other atoms. The sample is unchanged in that case.
        """
        if [new.element for new in atoms] != [atom.element for atom in self.atoms]:
            raise ValueError('The new positions are for other atoms.')
        if cell is not None and self.cell is not None:
            self.cell = Cell(cell.vectors, self.cell.space_group)
        for atom, new in zip(self.atoms, atoms):
            atom.x, atom.y, atom.z = new.x, new.y, new.z
        if self.cell is not None:
            _wrap(self.atoms, self.cell)

    # Editing. The structure no longer has to have the symmetry of its file, so a crystal
    # loses its space group.

    def set_position(self, index: int, position: Vec, fractional: bool = False) -> None:
        """Put atom `index` at `position`: Cartesian in Å, or fractional in a crystal's cell.
        A crystal's atom is wrapped into the cell."""
        if fractional and self.cell is None:
            raise ValueError('A molecule has no fractional coordinates.')
        atom = self.atoms[index]
        atom.x, atom.y, atom.z = self.cell.cartesian(*position) if fractional else position
        if self.cell is not None:
            self.cell = Cell(self.cell.vectors)
            _wrap([atom], self.cell)

    def set_positions(self, positions: list[Vec]) -> None:
        """Put every atom at its Cartesian position in Å, given in atom order (e.g. from an
        edited Z-matrix). A crystal's atoms are wrapped into the cell."""
        if len(positions) != len(self.atoms):
            raise ValueError(f'{len(positions)} positions for {len(self.atoms)} atoms.')
        for atom, position in zip(self.atoms, positions):
            atom.x, atom.y, atom.z = position
        if self.cell is not None:
            self.cell = Cell(self.cell.vectors)
            _wrap(self.atoms, self.cell)

    def add_atom(self, element: str, position: Vec = (0.0, 0.0, 0.0), fractional: bool = False) -> int:
        """Add an atom of `element` at `position`, as in `set_position`, after the others; it
        is labelled with the next number ('C13' after 'H12'). Returns its index."""
        if element not in SYMBOLS:
            raise ValueError(f'"{element}" is not an element.')
        if fractional and self.cell is None:
            raise ValueError('A molecule has no fractional coordinates.')
        numbers = (re.search(r'\d+$', atom.label) for atom in self.atoms)
        number = 1 + max((int(match.group()) for match in numbers if match), default=0)
        self.atoms.append(Atom(f'{element}{number}', element, 0.0, 0.0, 0.0))
        self.set_position(len(self.atoms) - 1, position, fractional)
        self._electrons_changed()
        return len(self.atoms) - 1

    def remove_atoms(self, indices) -> None:
        """Remove the atoms at `indices`; the others keep their labels.

        :raises ValueError: for an index out of range, or if no atom would be left; nothing
            changes then.
        """
        removed = set(indices)
        if not all(0 <= index < len(self.atoms) for index in removed):
            raise ValueError('No such atom.')
        if len(removed) >= len(self.atoms):
            raise ValueError('A structure needs at least one atom.')
        if not removed:
            return
        self.atoms = [atom for index, atom in enumerate(self.atoms) if index not in removed]
        if self.cell is not None:
            self.cell = Cell(self.cell.vectors)
        self._electrons_changed()

    def _electrons_changed(self) -> None:
        """Atoms came or went: a charge that leaves fewer than no electrons goes back to 0, and a
        multiplicity the electron count no longer allows goes to the lowest one it allows."""
        if self._electrons() < 0:
            self.charge = 0
        allowed = self.multiplicities()
        if self.multiplicity not in allowed:
            self.multiplicity = allowed[0]

    def set_cell_parameters(self, a, b, c, alpha, beta, gamma) -> None:
        """Give a crystal a cell of these lengths (Å) and angles (°). The atoms keep their
        fractional coordinates; the cell keeps its orientation (`Cell.with_parameters`).

        :raises ValueError: for a molecule or parameters that make no cell; nothing changes then.
        """
        if self.cell is None:
            raise ValueError('A molecule has no unit cell.')
        cell = self.cell.with_parameters(a, b, c, alpha, beta, gamma)
        fractional = [self.cell.fractional(atom.x, atom.y, atom.z) for atom in self.atoms]
        self.cell = cell
        for atom, position in zip(self.atoms, fractional):
            atom.x, atom.y, atom.z = cell.cartesian(*position)


def read_xyz(text: str) -> tuple[list[Atom], Optional[Cell]]:
    """Atoms of the first frame of an XYZ file, Cartesian coordinates in Å, and its cell.

    The format: the atom count, a comment line, then one `element x y z` line per atom.
    The element may also be an atomic number or a label starting with the symbol ('C12',
    'Cl_a'); columns after z (extended XYZ: forces, charges, ...) are ignored, and so are
    any further frames. Labels are numbered in file order: C1, H2, ...

    The cell comes from an extended XYZ comment line, `Lattice="ax ay az bx by bz cx cy cz"`;
    it is None without one, or when `pbc="F F F"` says the box is not periodic.
    """
    lines = text.splitlines()
    try:
        count = int(lines[0].split()[0])
    except (IndexError, ValueError):
        raise ValueError('The first line must be the number of atoms.')
    if count < 1:
        raise ValueError('The file declares no atoms.')
    body = lines[2 : 2 + count]
    if len(body) < count or not all(line.strip() for line in body):
        found = sum(1 for line in body if line.strip())
        raise ValueError(f'The file declares {count} atoms but holds {found}.')
    atoms = []
    for number, line in enumerate(body, start=1):
        fields = line.split()
        element = _element(fields[0])
        if element is None:
            raise ValueError(f'Atom {number}: "{fields[0]}" is not an element.')
        try:
            x, y, z = (float(field) for field in fields[1:4])
        except ValueError:
            raise ValueError(f'Atom {number}: expected "element x y z", got "{line.strip()}".')
        atoms.append(Atom(f'{element}{number}', element, x, y, z))
    return atoms, _xyz_cell(lines[1])


def _xyz_cell(comment: str) -> Optional[Cell]:
    lattice = _LATTICE.search(comment)
    if lattice is None:
        return None
    pbc = _PBC.search(comment)
    flags = {field.upper() in ('T', 'TRUE', '1') for field in pbc.group(1).split()} if pbc else set()
    if flags == {False}:
        return None  # a molecule in a box
    if flags - {True}:
        raise ValueError('Partially periodic structures are not supported.')
    try:
        numbers = [float(field) for field in lattice.group(1).split()]
    except ValueError:
        numbers = []
    if len(numbers) != 9:
        raise ValueError('Lattice= must hold nine numbers.')
    cell = Cell((tuple(numbers[0:3]), tuple(numbers[3:6]), tuple(numbers[6:9])))
    if cell.volume < 1e-6:
        raise ValueError('The lattice vectors span no volume.')
    return cell


def read_cif(text: str) -> tuple[list[Atom], Cell]:
    """Atoms of the whole unit cell, Cartesian in Å, and the cell, from the first data block
    of a CIF file that has atoms.

    gemmi expands the symmetry; the element comes from gemmi's reading of the type symbol
    ('Na+' is Na). Labels are numbered in cell order, as for XYZ. Partially occupied sites
    are refused: an engine cannot put two atoms on one position.
    """
    try:
        import gemmi
    except ImportError:
        raise ValueError('Reading CIF needs the gemmi package.')
    try:
        document = gemmi.cif.read_string(text)
    except ValueError as error:
        raise ValueError(f'The file is not a CIF file: {error}')
    structures = (gemmi.make_small_structure_from_block(block) for block in document)
    structure = next((structure for structure in structures if structure.sites), None)
    if structure is None:
        raise ValueError('The file has no atoms.')
    if not structure.cell.is_crystal():
        raise ValueError('The file has no unit cell.')
    for site in structure.sites:
        if site.element.name not in SYMBOLS:  # gemmi reads an unknown type as 'X'
            raise ValueError(f'Site {site.label}: "{site.type_symbol}" is not an element.')
        if site.occ < 1 - _OCCUPANCY_TOLERANCE:
            raise ValueError('The file has partially occupied sites.')
    cell = Cell.from_parameters(*structure.cell.parameters, space_group=_space_group(gemmi, structure))
    atoms = []
    for number, site in enumerate(structure.get_all_unit_cell_sites(), start=1):
        element = site.element.name
        atoms.append(Atom(f'{element}{number}', element, *cell.cartesian(*site.fract.tolist())))
    return atoms, cell


def _space_group(gemmi, structure) -> str:
    """'Fm-3m' from the Hermann-Mauguin symbol, else from the symmetry operations; '' if neither."""
    if structure.spacegroup_hm:
        group = gemmi.find_spacegroup_by_name(structure.spacegroup_hm)
        return group.short_name() if group else structure.spacegroup_hm.replace(' ', '')
    structure.determine_and_set_spacegroup('S')
    return structure.spacegroup.short_name() if structure.spacegroup else ''


def _wrap(atoms: list[Atom], cell: Cell) -> None:
    """Move every atom into the cell: fractional coordinates in [0, 1)."""
    for atom in atoms:
        wrapped = []
        for value in cell.fractional(atom.x, atom.y, atom.z):
            value -= math.floor(value)
            wrapped.append(0.0 if value < _WRAP_TOLERANCE or value > 1 - _WRAP_TOLERANCE else value)
        atom.x, atom.y, atom.z = cell.cartesian(*wrapped)


def _element(field: str) -> Union[str, None]:
    """'C', 'cl', 'CL', '6', 'C12', 'Cl_a' -> the element symbol, or None."""
    if field.isdigit():
        number = int(field)
        return SYMBOLS[number - 1] if 1 <= number <= len(SYMBOLS) else None
    letters = re.match(r'[A-Za-z]{1,2}', field)
    if letters is None:
        return None
    # Two letters first ('Cl' before 'C'), then one; a symbol is a capital and a small letter.
    for candidate in (letters.group(), letters.group()[0]):
        symbol = candidate.capitalize()
        if symbol in SYMBOLS:
            return symbol
    return None


def find_bonds(atoms: list[Atom]) -> list[tuple[int, int]]:
    """Atom index pairs closer than the scaled sum of their covalent radii."""
    pairs = []
    for i, first in enumerate(atoms):
        for j in range(i + 1, len(atoms)):
            second = atoms[j]
            cutoff = _BOND_TOLERANCE * (_radius(first.element) + _radius(second.element))
            if distance(first, second) < cutoff:
                pairs.append((i, j))
    return pairs


def _radius(element: str) -> float:
    return COVALENT_RADII.get(element, DEFAULT_COVALENT_RADIUS)
