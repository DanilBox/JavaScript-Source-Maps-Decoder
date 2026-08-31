import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from common import source_maps
from common.error import Error
from common.safe_path import safe_path_join

FORBIDDEN_SYMBOL_LIST = ["|", "{", "}", "$", "^"]
RENAMED_SYMBOL_LIST = [" "]


class DecoderStatistic(TypedDict):
    forbiddenPaths: list[str]
    renamedPaths: dict[str, str]
    deduplicated: dict[str, str]
    originalPaths: list[str]


def check_in_forbidden_symbols(file_path: str) -> bool:
    for forbidden_symbol in FORBIDDEN_SYMBOL_LIST:
        if forbidden_symbol in file_path:
            return True

    return False


def remove_renamed_symbols(file_path: str) -> str:
    for symbol in RENAMED_SYMBOL_LIST:
        file_path = file_path.replace(symbol, "_")

    return file_path


def get_saved_folder(map_file: Path) -> str:
    suffixes = [".map", ".js", ".css"]

    file_name = map_file.name
    for suffix in suffixes:
        file_name = file_name.removesuffix(suffix)

    if any(file_name.endswith(suffix) for suffix in suffixes):
        raise RuntimeError("Не правильно удалились расширения")

    return file_name


def save_statistic_file(output_file_folder: Path, statistic: Any) -> None:
    output_file_folder.write_text(json.dumps(statistic, indent=2))


def remove_first_slash(file_path: str) -> str:
    while file_path.startswith("/"):
        file_path = file_path.removeprefix("/")

    return file_path


def is_generated_source_path(file_path: str) -> bool:
    return "/./" in file_path


def separate_generated_source_path(file_path: str) -> str:
    return file_path.replace("/./", "/__generated__/")


def get_available_file_path(file_path: Path, file_content: str) -> Path:
    content_hash = hashlib.sha256(file_content.encode()).hexdigest()
    hash_length = 4

    while hash_length <= len(content_hash):
        duplicate_file_path = Path(f"{file_path}?{content_hash[:hash_length]}")
        if not duplicate_file_path.exists() or duplicate_file_path.read_text() == file_content:
            return duplicate_file_path

        hash_length += 4

    raise RuntimeError(f"Не удалось подобрать уникальное имя для файла '{file_path}'")


def save_decode_result(output_folder: Path, bundle_name: str, decode_result: source_maps.DecodeResult) -> None:
    folder_path = output_folder / bundle_name
    if not folder_path.exists():
        folder_path.mkdir()

    files_folder_path = folder_path / "files"
    if not files_folder_path.exists():
        files_folder_path.mkdir()

    forbidden_paths: list[str] = []
    renamed_paths: dict[str, str] = {}
    deduplicated: dict[str, str] = {}
    original_paths: list[str] = []
    saved_file_contents: dict[Path, str] = {}

    # Папка в который лежит бандл, относительной данной папки, мы и будет сохранять файлы
    relative_folder_in_sm = Path(decode_result.sourceMapStatistic["sourceMapPath"]).parent

    # Сборщик по-разному обозначает путь исходника и путь сгенерированного модуля.
    # После нормализации они совпадают, поэтому сначала сохраняем исходник.
    # Тогда суффикс дубликата получает сгенерированная версия.
    file_paths_to_save = sorted(decode_result.files, key=is_generated_source_path)

    for original_file_path in file_paths_to_save:
        file_content = decode_result.files[original_file_path]
        file_path = original_file_path

        if check_in_forbidden_symbols(file_path):
            forbidden_paths.append(file_path)
            print("[INFO]", f"Файл '{file_path}' был убран для сохранения")
            continue

        if (new_value := remove_renamed_symbols(file_path)) != file_path:
            renamed_paths[file_path] = new_value
            print("[INFO]", f"Файл '{file_path}' был переименован")
            file_path = new_value

        # Убираем первый '/', что-бы не попасть в корень диска
        file_path = remove_first_slash(file_path)

        # Путь восстанавливаемого файла в Sources Map
        file_path_in_sm = relative_folder_in_sm / separate_generated_source_path(file_path)

        saved_file_path = safe_path_join(files_folder_path, file_path_in_sm)
        if not saved_file_path.parent.exists():
            saved_file_path.parent.mkdir(parents=True)

        if not is_generated_source_path(original_file_path):
            original_paths.append(file_path)

        saved_file_exists = False
        if saved_file_path in saved_file_contents:
            saved_file_exists = True
            if saved_file_contents[saved_file_path] == file_content:
                print(
                    "[INFO]",
                    f"Дубликат файла '{saved_file_path}' был убран, так как файл уже находится в памяти",
                )
                continue

        if not saved_file_exists and saved_file_path.exists():
            saved_file_exists = True
            if saved_file_path.read_text() == file_content:
                saved_file_contents[saved_file_path] = file_content
                print(
                    "[INFO]",
                    f"Дубликат файла '{saved_file_path}' был убран, так как файл уже находится в файловой системе",
                )
                continue

        if saved_file_exists:
            old_file_path = str(saved_file_path)
            print("[INFO]", f"Задублирование файла '{saved_file_path}'")

            saved_file_path = get_available_file_path(saved_file_path, file_content)
            deduplicated[old_file_path] = str(saved_file_path)

        saved_file_contents[saved_file_path] = file_content
        saved_file_path.write_text(file_content)

    decoder_statistic = DecoderStatistic(
        forbiddenPaths=forbidden_paths,
        renamedPaths=renamed_paths,
        deduplicated=deduplicated,
        originalPaths=original_paths,
    )

    save_statistic_file(folder_path / "statistic.json", decode_result.sourceMapStatistic)
    save_statistic_file(folder_path / "decoder.json", decoder_statistic)


def get_sources_maps_files(input_path: Path) -> list[Path]:
    if not input_path.exists():
        sys.exit(f"Файл или папки '{input_path}' не существует")

    if input_path.is_dir():
        return [file for file in input_path.glob("*.map") if file.is_file()]

    if input_path.is_file():
        return [input_path]

    sys.exit(f"Невозможно определить тип пути: {input_path}")


def decoder(input_path: str, output_folder: str, *, force: bool = False) -> None:
    output_path = Path(output_folder)
    if output_path.exists():
        if not force:
            sys.exit(f"Папка '{output_folder}' уже существует. Для продолжения используйте флаг '--force'")

        print("[WARNING]", f"Папка '{output_folder}' уже существует, возможны ошибки при работе программы")
    else:
        output_path.mkdir(parents=True)

    sm_files = get_sources_maps_files(Path(input_path))
    for sm_file in sm_files:
        result = source_maps.decode(sm_file.read_text(encoding="utf-8"))
        if isinstance(result, Error):
            print("[ERROR]", f"Произошла ошибка при декодировании файла '{sm_file}': {result.message}")
            continue

        bundle_name = get_saved_folder(sm_file)
        save_decode_result(output_path, bundle_name, result)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="JavaScript Source Maps Decoder")
    parser.add_argument(
        "-I",
        "--input",
        dest="input_path",
        type=str,
        required=True,
        help="Путь до файла или директории c Source Map",
    )
    parser.add_argument(
        "-O",
        "--output",
        dest="output_folder",
        type=str,
        default="output",
        help="Путь до папки для вывода",
    )
    parser.add_argument(
        "-F",
        "--force",
        action="store_true",
        help="Разрешить декодирование в уже существующую папку",
    )

    args = parser.parse_args(argv)
    decoder(**vars(args))


if __name__ == "__main__":
    main(sys.argv[1::])
