"""
Tool schemas for FlowChat MCP tools
"""

from typing import Dict, Any


class ToolSchema:
    """Base class for tool schemas"""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        category: str = "read"
    ):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.category = category

    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP tool format"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema
        }
