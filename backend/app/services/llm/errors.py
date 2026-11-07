class LlmError(Exception):
    """Haiku の呼び出しの失敗の共通の親。"""


class LlmFormatError(LlmError):
    """出力の形が壊れていた（1回だけやり直す）。"""


class LlmRefusedError(LlmError):
    """安全のための拒否。やり直さない。"""


class LlmUnavailableError(LlmError):
    """通信・サーバーの失敗（SDK の自動やり直しの後）。その記事は次回に回す。"""


class BudgetExceededError(LlmError):
    """費用の上限に達する見込み。その回の Haiku 処理を止める。"""
