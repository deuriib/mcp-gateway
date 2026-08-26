"""Parsing helpers for headers and environment variables."""

from __future__ import annotations


def parse_headers(headers: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in headers:
        key, _, value = item.partition("=")
        result[key.strip()] = value.strip()
    return result


def parse_envs(envs: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in envs:
        key, _, value = item.partition("=")
        result[key] = value
    return result
