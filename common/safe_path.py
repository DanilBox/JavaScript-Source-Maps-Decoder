from pathlib import Path
from typing import Self

PyPath = Path | str


class SafePath:
    """Класс надстройка над [pathlib.Path], который не позволяет выйти за пределы указанного "базового" пути.

    Оригинальный путь вычисляется при создании первого экземпляра данного класса.
    При последующем join путей, "базовый" путь берётся от родительского пути.

    >>> safe = SafePath("base")  # path: base, original_absolute: base
    >>> safe2 = safe / "folder"  # path: base/folder, original_absolute: base
    """

    def __init__(self, path: PyPath) -> None:
        save_path = Path(path)
        self._safe_path = save_path
        self._original_absolute: str = str(save_path.resolve().absolute())

    def __truediv__(self, path_part: PyPath | Self) -> Self:
        if isinstance(path_part, SafePath):
            add_path_part = path_part.path
        else:
            add_path_part = Path(path_part)

        new_path = self._safe_path / add_path_part

        new_absolute = str(new_path.resolve().absolute())
        if not new_absolute.startswith(self._original_absolute):
            raise RuntimeError(f"Путь '{new_absolute}' вышел из оригинального пути '{self._original_absolute}'")

        save_path = SafePath(new_path)
        save_path._set_absolute(self._original_absolute)
        return save_path  # type: ignore [return-value]

    def _set_absolute(self, absolute_path: str) -> None:
        self._original_absolute = absolute_path

    @property
    def path(self) -> Path:
        return self._safe_path


def safe_path_join(original_path: PyPath, path_part: PyPath) -> Path:
    new_path = SafePath(original_path) / path_part
    return new_path.path
