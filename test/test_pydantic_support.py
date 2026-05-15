import hjson
from jsonc_sdict.jsonc import jsoncDict
from pydantic import BaseModel, ConfigDict, AliasChoices, Field
from pydantic.json_schema import GenerateJsonSchema

from pathlib import Path
from importlib.metadata import version

_JSONC = "pydantic.config.jsonc"
"""为每个项目生成初始文件"""
SCHEMA = "schema.json"
"""自动更新schema校验文件"""

SELF = Path(__file__).resolve()
JSONC = SELF.parent / _JSONC


class Model(BaseModel):
    # python-re 支持负向断言
    model_config = ConfigDict(
        use_attribute_docstrings=True, serialize_by_alias=True, regex_engine="python-re"
    )


class Meta(Model):
    """用 "":{...} 空键名 记录父节点的元信息"""

    From: str | None = Field(
        validation_alias=AliasChoices("from", "From"),
        serialization_alias="from",
        default="",
    )
    """导入路径, 未使用的保留字段(TODO: 从后端哪个地方同步到前端)"""
    to: Path | None = Path()
    """导出路径"""
    title: str | None = ""
    """中文名(可随意填写，方便搜索/记忆)"""
    api: str | None = ""
    """/api/get...(可随意填写，方便搜索/记忆)"""


# NOTE: 暂时无法为 __extra__ 字段生成 json schema
class Node(Meta):
    """可嵌套节点. 用 "":{...} 空键名 记录父节点的元信息"""

    model_config = ConfigDict(extra="allow")
    __pydantic_extra__: dict[str, Meta] = Field(init=False)
    """子节点 id:{}"""
    meta: Meta = Field(
        validation_alias=AliasChoices("", "meta"),
        serialization_alias="",
    )


class Config(Model):
    """区分每个项目的配置"""

    model_config = ConfigDict(
        json_schema_extra={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "additionalProperties": False,
        }
    )

    schema_: str = Field(
        validation_alias=AliasChoices("$schema", "schema"),
        serialization_alias="$schema",
        default="file:///.../schema.json",
    )
    version: str = version("jsonc_sdict")

    api: dict[str, Meta | dict[str, Meta | dict[str, Meta | dict[str, Meta]]]] = {  # type: ignore
        "groupId": {
            "projectId_1": {
                "": {
                    "to": "api/gen/data",
                    "title": "XX项目",
                }
            }
        }
    }
    """可注释掉不需要同步的接口数据"""

    class Exp(Model):
        实验性选项: bool = True

    实验: Exp | None = Exp()


class MySchemaGen(GenerateJsonSchema):
    def generate(self, schema, mode="validation"):
        json_schema = super().generate(schema, mode=mode)
        # json_schema["$schema"] = "xxx"
        return json_schema


# def gen_jsonc(
#     From: Config, indent: int | None = 2, exclude_unset=True, exclude_none=True
# ):
#     jc_path = toDir / JSONC
#     From.schema_ = f"file:///{SELF.as_posix()}"
#     From.__pydantic_fields_set__.add("version")
#     if From.实验 is not None:
#         From.__pydantic_fields_set__.add("实验")
#     newDic = From.model_dump(exclude_none=exclude_none, exclude_unset=exclude_unset)
#     jc = jsoncDict(newDic)
#     if indent is not None and jc_path.exists() and jc_path.stat().st_size:
#         jc = jsoncDict(JSONC.read_text(), hjson.loads)  # 再读取一次old config
#         jc.merge(newDic)
#     print(jc.full)
#     return jc_path


def test_pydantic_merge_config():
    print(Config.model_json_schema())
    old = Config()  # user's config
    old.api = {}
    old.version = "0.1"

    old.schema_ = f"file://{SELF.as_posix()}"
    old.__pydantic_fields_set__.add("version")
    if old.实验 is not None:
        old.__pydantic_fields_set__.add("实验")
    oldDic = old.model_dump(exclude_none=True, exclude_unset=True)

    jc = jsoncDict(Config().model_dump(), hjson.loads)  # 再读取一次old config
    jc.merge(oldDic, unMergeable="new")

    print(jc.full)
    return jc.full


if __name__ == "__main__":
    test_pydantic_merge_config()
