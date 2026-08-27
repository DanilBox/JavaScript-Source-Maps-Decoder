import argparse
import re
import sys
from enum import StrEnum
from pathlib import Path
from re import Pattern
from urllib.parse import urlparse

import requests


class FileType(StrEnum):
    JS = "js"
    MAP = "map"
    AUTO = "auto"


def parse_array_urls_line(urls_line: str) -> list[str]:
    urls: list[str] = []

    urls_line = urls_line.removeprefix("[").removesuffix("]")
    for raw_url in urls_line.split(","):
        url = raw_url.strip().strip("'").strip('"')
        if url == "":
            continue

        urls.append(url)

    return urls


def get_urls_from_file(input_file: str) -> list[str]:
    file_path = Path(input_file)
    if not file_path.exists():
        sys.exit(f"Файл '{file_path.name}' не существует")

    urls: list[str] = []

    raw_urls_list = file_path.read_text(encoding="utf-8").splitlines()
    for raw_url in raw_urls_list:
        url = raw_url.strip()
        if url == "":
            continue

        if url.startswith("[") and url.endswith("]"):
            urls.extend(parse_array_urls_line(url))
            continue

        urls.append(url)

    return urls


def regexp_compile(regexp: str) -> Pattern[str] | None:
    try:
        return re.compile(regexp)
    except re.error:
        return None


def urls_filter(urls: list[str], filter_regexp: str) -> list[str]:
    _re = regexp_compile(filter_regexp)
    if _re is None:
        sys.exit("Ошибка в регулярном выражении")

    filtered_urls: list[str] = []
    for url in urls:
        if _re.search(url) is None:
            continue

        if url in filtered_urls:
            continue

        filtered_urls.append(url)

    return filtered_urls


def urls_modify(urls: list[str], file_type: FileType) -> list[str]:
    match file_type:
        case FileType.MAP:
            return urls
        case FileType.JS:
            return [f"{url}.map" for url in urls]
        case FileType.AUTO:
            return [f"{url}.map" for url in urls if url.endswith(".js")]


def download_by_url(url: str) -> str | None:
    try:
        _r = requests.get(url, timeout=30)
    except requests.exceptions.RequestException:
        return None

    content = _r.text
    if not content.startswith("{"):
        return None

    return content


def get_filename_from_url(url: str) -> str:
    url_path = urlparse(url).path
    return url_path.rsplit("/", 1)[1]


def urls_downloader(urls: list[str], output_folder: str) -> None:
    folder_path = Path(output_folder)
    if not folder_path.exists():
        folder_path.mkdir(parents=True)

    for url in urls:
        content = download_by_url(url)
        if content is None:
            print("[ERROR]", f"Произошла ошибка при скачивании файла '{url}'")
            continue

        filename = get_filename_from_url(url)

        save_file_path = folder_path / filename
        save_file_path.write_text(content, encoding="utf-8")
        print("[INFO]", f"Файл '{url}' успешно сохранён")


def downloader(input_file: str, filter_regexp: str, file_type: FileType, output_folder: str) -> None:
    urls = get_urls_from_file(input_file)
    urls = urls_filter(urls, filter_regexp)
    urls = urls_modify(urls, file_type)
    urls_downloader(urls, output_folder)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Source Maps Downloader")
    parser.add_argument(
        "-I",
        "--input",
        dest="input_file",
        type=str,
        required=True,
        help="Файл со списком ссылок для скачивания",
    )
    parser.add_argument(
        "-F",
        "--filter",
        dest="filter_regexp",
        type=str,
        default="",
        help="Регулярное выражение для фильтрации ссылок",
    )
    parser.add_argument(
        "-T",
        "--type",
        dest="file_type",
        type=FileType,
        default=FileType.AUTO,
        choices=list(FileType),
        help="Расширение файла в ссылках",
    )
    parser.add_argument(
        "-O",
        "--output",
        dest="output_folder",
        type=str,
        default="maps_files",
        help="Путь до папки для сохранения",
    )

    args = parser.parse_args(argv)
    downloader(**vars(args))


if __name__ == "__main__":
    main(sys.argv[1::])
