# test_director_helpers.py
import os
from app.templates_engine.context import (
    _to_director_position_nominative_ru,
    _to_director_position_es,
    _short_latin_from_full,
)

print("=" * 70)
print("KAYTUKTI (РЕНКОНС, id=18):")
print("=" * 70)
print(f"  _to_director_position_nominative_ru('Генерального директора'):")
print(f"    → {_to_director_position_nominative_ru('Генерального директора')!r}")
print(f"  _to_director_position_es('Генерального директора'):")
print(f"    → {_to_director_position_es('Генерального директора')!r}")
print(f"  _short_latin_from_full('KAYTUKTI KONSTANTIN PETROVICH'):")
print(f"    → {_short_latin_from_full('KAYTUKTI KONSTANTIN PETROVICH')!r}")

print()
print("=" * 70)
print("VASILEVSKAYA (АГАЛАРОВ, id=16):")
print("=" * 70)
print(f"  _short_latin_from_full('Vasilevskaia Anna Vadimovna'):")
print(f"    → {_short_latin_from_full('Vasilevskaia Anna Vadimovna')!r}")