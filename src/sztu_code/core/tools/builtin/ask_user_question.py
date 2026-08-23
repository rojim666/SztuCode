from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sztu_code.core.bus.commands import UserQuestionItem
from sztu_code.core.interaction.user_questions import UserQuestionManager
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult


class AskUserQuestionParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    questions: list[UserQuestionItem] = Field(min_length=1, max_length=3)

    # 拒绝重复问题 ID，确保回答可以稳定关联到原问题
    @model_validator(mode="after")
    def validate_unique_ids(self) -> AskUserQuestionParams:
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
        return self


class AskUserQuestionTool(BaseTool):
    name = "ask_user_question"
    description = (
        "Ask the user one to three concise questions when a decision or missing "
        "information is required before continuing. The tool waits for the user's "
        "structured answer and then returns it to the agent."
    )
    required_permission = ToolPermission.READ_ONLY
    is_interactive = True
    allows_indefinite_wait = True
    params_model = AskUserQuestionParams
    input_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "description": "Questions to ask before continuing.",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Stable question id echoed in the answer.",
                        },
                        "header": {
                            "type": "string",
                            "description": "Optional short heading, up to 40 characters.",
                        },
                        "question": {
                            "type": "string",
                            "description": "The specific user-facing question.",
                        },
                        "options": {
                            "type": "array",
                            "maxItems": 8,
                            "description": (
                                "Optional choices. Put a recommended choice first and append "
                                "'(Recommended)' to its label."
                            ),
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["label"],
                            },
                        },
                        "multi_select": {
                            "type": "boolean",
                            "description": "Allow more than one option. Defaults to false.",
                        },
                    },
                    "required": ["id", "question"],
                },
            },
        },
        "required": ["questions"],
    }

    # 绑定当前 session/run，使挂起问题可以精确恢复到对应会话
    def __init__(
        self,
        manager: UserQuestionManager,
        session_id: str,
        run_id: str,
    ) -> None:
        self._manager = manager
        self._session_id = session_id
        self._run_id = run_id

    # 发布问题并等待回答，将结构化结果编码为普通工具文本结果
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        parsed = AskUserQuestionParams.model_validate(params)
        answers = await self._manager.ask(
            session_id=self._session_id,
            run_id=self._run_id,
            questions=parsed.questions,
        )
        payload = {
            "answers": [answer.model_dump(exclude_none=True) for answer in answers]
        }
        return ToolResult(content=json.dumps(payload, ensure_ascii=False))
