"""Pydantic integration that keeps jsonc comments as sidecar metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from pydantic import BaseModel, PrivateAttr

from jsonc_sdict.jsonc import jsoncDict


def _normalize_comment_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _normalize_comment_value(item) for key, item in value.items()}
    if isinstance(value, str):
        return value.strip()
    return value


def _copy_comments_flat(
    comments_flat: Mapping[tuple[Any, ...], Mapping[Any, Any]],
) -> dict[tuple[Any, ...], dict[Any, Any]]:
    return {
        tuple(path): {
            key: _normalize_comment_value(value) for key, value in comments.items()
        }
        for path, comments in comments_flat.items()
    }


@dataclass(slots=True)
class JsoncState:
    """Round-trip metadata that should stay outside pydantic validation."""

    comments_flat: dict[tuple[Any, ...], dict[Any, Any]] = field(default_factory=dict)
    header: str = ""
    footer: str = ""

    @classmethod
    def from_jsonc_dict(cls, jc: jsoncDict) -> Self:
        return cls(
            comments_flat=_copy_comments_flat(jc.comments_flat),
            header=jc.header,
            footer=jc.footer,
        )


def replay_comments(
    jc: jsoncDict,
    comments_flat: Mapping[tuple[Any, ...], Mapping[Any, Any]],
) -> jsoncDict:
    """Apply flattened comment metadata to a freshly dumped jsoncDict."""
    for path, comments in comments_flat.items():
        try:
            owner = jc if not path else jc[path]
        except (KeyError, IndexError, TypeError):
            continue
        if not isinstance(owner, jsoncDict):
            continue
        owner.comments.update(
            {key: _normalize_comment_value(value) for key, value in comments.items()}
        )
    return jc


class JsoncModel(BaseModel):
    """BaseModel mixin that round-trips jsonc comments beside validated data."""

    _jsonc_state: JsoncState = PrivateAttr(default_factory=JsoncState)

    @property
    def jsonc_state(self) -> JsoncState:
        return self._jsonc_state

    def bind_jsonc(self, jc: jsoncDict) -> Self:
        self._jsonc_state = JsoncState.from_jsonc_dict(jc)
        return self

    @classmethod
    def from_jsonc_dict(cls, jc: jsoncDict, **kwargs) -> Self:
        model = cls.model_validate(jc.mixed(comments=False), **kwargs)
        model.bind_jsonc(jc)
        return model

    @classmethod
    def from_jsonc(
        cls,
        raw: str,
        *,
        loads: Callable[[str], Any],
        dumps: Callable[[Any], str] | None = None,
        slash_dash: bool | None = None,
        auto_indent: bool | None = None,
        **kwargs,
    ) -> Self:
        jsonc_kwargs: dict[str, Any] = {"loads": loads}
        if dumps is not None:
            jsonc_kwargs["dumps"] = dumps
        if slash_dash is not None:
            jsonc_kwargs["slash_dash"] = slash_dash
        if auto_indent is not None:
            jsonc_kwargs["auto_indent"] = auto_indent
        jc = jsoncDict(raw, **jsonc_kwargs)
        return cls.from_jsonc_dict(jc, **kwargs)

    def to_jsonc_dict(
        self,
        *,
        by_alias: bool = True,
        exclude_none: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        dumps: Callable[[Any], str] | None = None,
        slash_dash: bool | None = None,
        auto_indent: bool | None = None,
        **kwargs,
    ) -> jsoncDict:
        data = self.model_dump(
            by_alias=by_alias,
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            **kwargs,
        )
        jsonc_kwargs: dict[str, Any] = {}
        if dumps is not None:
            jsonc_kwargs["dumps"] = dumps
        if slash_dash is not None:
            jsonc_kwargs["slash_dash"] = slash_dash
        if auto_indent is not None:
            jsonc_kwargs["auto_indent"] = auto_indent
        jc = jsoncDict(data, **jsonc_kwargs)
        jc.header = self._jsonc_state.header
        jc.footer = self._jsonc_state.footer
        return replay_comments(jc, self._jsonc_state.comments_flat)

    def model_dump_jsonc(self, **kwargs) -> str:
        return self.to_jsonc_dict(**kwargs).full
