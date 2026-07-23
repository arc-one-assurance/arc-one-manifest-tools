"""La versión que el CLI DICE tiene que ser la que el paquete ES.

🔴 En WS178 la Card 5 bumpeó ``pyproject.toml`` a 1.5.0 y dejó ``__version__.py`` en
1.4.0: ``arc-one-manifest --version`` decía 1.4.0 mientras el paquete se publicaba como
1.5.0. No rompía nada —el guard de compatibilidad del CI detecta el flag con
``audit --help``, no con la versión— pero el propio warning que ve el cliente dice
*"requiere v1.5.0+"*, y taggear un ``v1.5.0`` que se presenta como 1.4.0 es sellar la
mentira en el único lugar donde el cliente va a ir a mirar.

Dos fuentes para el mismo hecho necesitan quien las enfrente, o divergen en silencio —
la misma regla que ya cuida la paridad del resumen del manifiesto (``test_manifest_summary_parity``).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from arc_one_manifest.__version__ import __version__

_ROOT = Path(__file__).resolve().parent.parent


class VersionTest(unittest.TestCase):
    def test_pyproject_y_el_modulo_dicen_lo_mismo(self) -> None:
        texto = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', texto, flags=re.MULTILINE)
        self.assertIsNotNone(match, "pyproject.toml no declara `version`")
        assert match is not None  # narrowing
        self.assertEqual(
            match.group(1),
            __version__,
            "pyproject.toml y arc_one_manifest/__version__.py divergen: "
            "el CLI se presentaría con una versión que no es la suya.",
        )

    def test_es_semver(self) -> None:
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
