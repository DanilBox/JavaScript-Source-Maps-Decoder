import json
from pathlib import Path
from typing import Any, NamedTuple, TypedDict

from common.error import Error, error
from common.map_counter import MapCounter

SUPPORTED_SOURCE_MAP_VERSION = 3


class SourceMap(NamedTuple):
    version: int
    sources: list[str]
    names: list[str] | None
    mappings: str
    file: str
    sourcesContent: list[str]
    sourceRoot: str


class SourceMapStatistic(TypedDict):
    includesFiles: list[str]
    filesStatistics: dict[str, int]
    sourceMapPath: str


class DecodeResult(NamedTuple):
    files: dict[str, str]
    sourceMapStatistic: SourceMapStatistic


def remove_prefix(line: str) -> str:
    prefixes = ["webpack://"]
    for prefix in prefixes:
        line = line.removeprefix(prefix)

    return line


def parse_content(content: str) -> SourceMap:
    sm: dict[str, Any] = {
        "names": None,
    }
    sm |= json.loads(content)

    return SourceMap(**sm)


def parse_suffix(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix

    return suffix.split("?")[0]


def decode(content: str) -> Error | DecodeResult:
    sm = parse_content(content)

    if sm.version != SUPPORTED_SOURCE_MAP_VERSION:
        return error(f"Source Maps версии {sm.version} не поддерживается")

    files: dict[str, str] = {}
    suffix_stats = MapCounter()

    for idx, source_path in enumerate(sm.sources):
        file_path = remove_prefix(source_path)
        file_content = sm.sourcesContent[idx]

        suffix_stats.increment(parse_suffix(file_path))
        files[file_path] = file_content

    sm_stat = SourceMapStatistic(
        includesFiles=sm.sources,
        filesStatistics=suffix_stats.total,
        sourceMapPath=sm.file,
    )

    return DecodeResult(files, sm_stat)
