# MIGRATION: Phase-1 - Fehlerklassen

class LangGraphError(Exception):
    pass

class ToolError(LangGraphError):
    pass