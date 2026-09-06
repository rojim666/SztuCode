// Generated from sztu_code.core.office.office_contract; do not edit by hand.
export const officeToolContracts = [
  {
    "name": "read_document",
    "description": "读取 PDF、Word(DOCX)、Excel(XLSX)、PPT(PPTX) 的结构化内容，返回可引用的页码、段落、工作表/单元格、幻灯片和备注位置。长资料用 next_offset 翻页；不要把第一页当成全文。",
    "permission": "read_only",
    "schema": {
      "additionalProperties": false,
      "properties": {
        "path": {
          "description": "Output or input path relative to the workspace",
          "minLength": 1,
          "title": "Path",
          "type": "string"
        },
        "offset": {
          "default": 0,
          "description": "Block offset; use next_offset",
          "maximum": 1000000,
          "minimum": 0,
          "title": "Offset",
          "type": "integer"
        },
        "limit": {
          "default": 40,
          "maximum": 100,
          "minimum": 1,
          "title": "Limit",
          "type": "integer"
        },
        "sheet": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "description": "XLSX: exact worksheet name",
          "title": "Sheet"
        }
      },
      "required": [
        "path"
      ],
      "title": "ReadDocumentParams",
      "type": "object"
    }
  },
  {
    "name": "create_document",
    "description": "生成真正可编辑的 DOCX、XLSX 或 PPTX 文件。分别提供 blocks、sheets 或 slides；默认不覆盖文件。XLSX 保留公式表达式但不计算。保存后重开校验结构，未进行视觉排版校验。",
    "permission": "workspace_write",
    "schema": {
      "$defs": {
        "SheetSpec": {
          "additionalProperties": false,
          "properties": {
            "name": {
              "maxLength": 31,
              "minLength": 1,
              "title": "Name",
              "type": "string"
            },
            "rows": {
              "items": {
                "items": {
                  "anyOf": [
                    {
                      "type": "string"
                    },
                    {
                      "type": "integer"
                    },
                    {
                      "type": "number"
                    },
                    {
                      "type": "boolean"
                    },
                    {
                      "type": "null"
                    }
                  ]
                },
                "type": "array"
              },
              "maxItems": 10000,
              "minItems": 1,
              "title": "Rows",
              "type": "array"
            }
          },
          "required": [
            "name",
            "rows"
          ],
          "title": "SheetSpec",
          "type": "object"
        },
        "SlideSpec": {
          "additionalProperties": false,
          "properties": {
            "title": {
              "maxLength": 120,
              "title": "Title",
              "type": "string"
            },
            "bullets": {
              "items": {
                "type": "string"
              },
              "maxItems": 8,
              "title": "Bullets",
              "type": "array"
            },
            "notes": {
              "default": "",
              "maxLength": 20000,
              "title": "Notes",
              "type": "string"
            }
          },
          "required": [
            "title"
          ],
          "title": "SlideSpec",
          "type": "object"
        },
        "WordBlock": {
          "additionalProperties": false,
          "properties": {
            "kind": {
              "enum": [
                "heading",
                "paragraph",
                "bullet",
                "table"
              ],
              "title": "Kind",
              "type": "string"
            },
            "text": {
              "default": "",
              "maxLength": 50000,
              "title": "Text",
              "type": "string"
            },
            "level": {
              "default": 1,
              "maximum": 6,
              "minimum": 1,
              "title": "Level",
              "type": "integer"
            },
            "rows": {
              "items": {
                "items": {
                  "type": "string"
                },
                "type": "array"
              },
              "maxItems": 1000,
              "title": "Rows",
              "type": "array"
            }
          },
          "required": [
            "kind"
          ],
          "title": "WordBlock",
          "type": "object"
        }
      },
      "additionalProperties": false,
      "properties": {
        "path": {
          "description": "Output or input path relative to the workspace",
          "minLength": 1,
          "title": "Path",
          "type": "string"
        },
        "title": {
          "default": "",
          "maxLength": 200,
          "title": "Title",
          "type": "string"
        },
        "blocks": {
          "description": "DOCX body in document order",
          "items": {
            "$ref": "#/$defs/WordBlock"
          },
          "maxItems": 1000,
          "title": "Blocks",
          "type": "array"
        },
        "sheets": {
          "description": "XLSX sheets; strings starting with = are formulas",
          "items": {
            "$ref": "#/$defs/SheetSpec"
          },
          "maxItems": 100,
          "title": "Sheets",
          "type": "array"
        },
        "slides": {
          "description": "PPTX title and bullet slides, with speaker notes",
          "items": {
            "$ref": "#/$defs/SlideSpec"
          },
          "maxItems": 100,
          "title": "Slides",
          "type": "array"
        },
        "overwrite": {
          "default": false,
          "title": "Overwrite",
          "type": "boolean"
        }
      },
      "required": [
        "path"
      ],
      "title": "CreateDocumentParams",
      "type": "object"
    }
  },
  {
    "name": "edit_document",
    "description": "修改办公文件并另存副本：DOCX/PPTX 支持跨文本运行的精确替换，XLSX 支持按工作表和单元格写值/公式。先 read_document，再使用 source_sha256 防止修改过期内容；替换次数须匹配 expected_matches。",
    "permission": "workspace_write",
    "schema": {
      "$defs": {
        "EditOperation": {
          "additionalProperties": false,
          "properties": {
            "kind": {
              "enum": [
                "replace_text",
                "set_cell"
              ],
              "title": "Kind",
              "type": "string"
            },
            "find": {
              "default": "",
              "maxLength": 10000,
              "title": "Find",
              "type": "string"
            },
            "replace": {
              "default": "",
              "maxLength": 50000,
              "title": "Replace",
              "type": "string"
            },
            "expected_matches": {
              "default": 1,
              "description": "replace_text: exact expected count across source",
              "maximum": 10000,
              "minimum": 1,
              "title": "Expected Matches",
              "type": "integer"
            },
            "sheet": {
              "default": "",
              "title": "Sheet",
              "type": "string"
            },
            "cell": {
              "default": "",
              "description": "set_cell: Excel coordinate, e.g. B3",
              "title": "Cell",
              "type": "string"
            },
            "value": {
              "anyOf": [
                {
                  "type": "string"
                },
                {
                  "type": "integer"
                },
                {
                  "type": "number"
                },
                {
                  "type": "boolean"
                },
                {
                  "type": "null"
                }
              ],
              "default": null,
              "title": "Value"
            }
          },
          "required": [
            "kind"
          ],
          "title": "EditOperation",
          "type": "object"
        }
      },
      "additionalProperties": false,
      "properties": {
        "path": {
          "description": "Output or input path relative to the workspace",
          "minLength": 1,
          "title": "Path",
          "type": "string"
        },
        "source": {
          "description": "Existing source document; saved to path as a copy",
          "minLength": 1,
          "title": "Source",
          "type": "string"
        },
        "source_sha256": {
          "anyOf": [
            {
              "pattern": "^[a-f0-9]{64}$",
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Source Sha256"
        },
        "operations": {
          "items": {
            "$ref": "#/$defs/EditOperation"
          },
          "maxItems": 500,
          "minItems": 1,
          "title": "Operations",
          "type": "array"
        },
        "overwrite": {
          "default": false,
          "title": "Overwrite",
          "type": "boolean"
        }
      },
      "required": [
        "path",
        "source",
        "operations"
      ],
      "title": "EditDocumentParams",
      "type": "object"
    }
  }
];
