import json

import hjson
from pydantic import AliasChoices, ConfigDict, Field

from jsonc_sdict import NONE
from jsonc_sdict.jsonc import CommentIn
from jsonc_sdict.integrations.Pydantic import JsoncModel


def json_dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


class Model(JsoncModel):
    model_config = ConfigDict(serialize_by_alias=True)


class Meta(Model):
    title: str = ""


class Config(Model):
    schema_: str = Field(
        validation_alias=AliasChoices("$schema", "schema"),
        serialization_alias="$schema",
        default="file:///schema.json",
    )
    version: str = "1.0"
    meta: Meta = Field(
        default_factory=Meta,
        validation_alias=AliasChoices("meta_info", "meta"),
        serialization_alias="meta_info",
    )


RAW = """\
// header
{
  // schema comment
  "$schema": "file:///old.json",
  "version": "0.1", // version tail
  "meta_info": {
    // meta title
    "title": "before"
  }
}
// footer
"""


def test_from_jsonc_binds_comment_state():
    model = Config.from_jsonc(RAW, loads=hjson.loads, dumps=json_dumps)

    assert model.schema_ == "file:///old.json"
    assert model.version == "0.1"
    assert model.meta.title == "before"
    assert model.jsonc_state.header == "// header\n"
    assert model.jsonc_state.footer == "\n// footer\n"
    assert model.jsonc_state.comments_flat[()][CommentIn(NONE, "$schema")] == (
        "// schema comment"
    )
    assert model.jsonc_state.comments_flat[()][CommentIn("version", "meta_info")] == (
        "// version tail"
    )
    assert model.jsonc_state.comments_flat[("meta_info",)][
        CommentIn(NONE, "title")
    ] == ("// meta title")


def test_model_dump_jsonc_replays_comments_after_updates():
    model = Config.from_jsonc(RAW, loads=hjson.loads, dumps=json_dumps)
    model.version = "0.2"
    model.meta.title = "after"

    rendered = model.model_dump_jsonc(dumps=json_dumps)

    assert '// schema comment\n  "$schema": "file:///old.json"' in rendered
    assert '"version": "0.2",\n  // version tail\n  "meta_info"' in rendered
    assert '// meta title\n    "title": "after"' in rendered
    assert rendered.startswith("// header\n")
    assert rendered.endswith("\n// footer\n")


def test_to_jsonc_dict_keeps_comment_paths_in_new_tree():
    model = Config.from_jsonc(RAW, loads=hjson.loads, dumps=json_dumps)
    model.meta.title = "changed"

    jc = model.to_jsonc_dict(dumps=json_dumps)

    assert jc.comments[CommentIn(NONE, "$schema")] == "// schema comment"
    assert jc.comments[CommentIn("version", "meta_info")] == "// version tail"
    assert jc["meta_info"].comments[CommentIn(NONE, "title")] == "// meta title"
    assert jc["meta_info"]["title"] == "changed"
