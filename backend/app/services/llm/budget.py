"""費用の上限（月・1回）の管理。呼ぶ前に見込みを予約し、呼んだ後に実費で精算する。

並列で呼んでも上限を超える量は、最大で「同時数 × 1回の見込み」に収まる。
DB は触らない（記録は呼び出し側が1件ずつ行う）。
"""

from app.services.llm.errors import BudgetExceededError


class Budget:
    def __init__(self, *, run_limit_usd: float, month_limit_usd: float, month_spent_usd: float):
        self._run_limit = run_limit_usd
        self._month_limit = month_limit_usd
        self._month_at_start = month_spent_usd
        self.run_spent = 0.0  # 精算済みの実費（この回）
        self._reserved = 0.0  # 予約中の見込み

    def reserve(self, estimate_usd: float) -> None:
        if self.run_spent + self._reserved + estimate_usd > self._run_limit:
            raise BudgetExceededError(f"1回の上限 ${self._run_limit:.2f} に達する見込み")
        month_total = self._month_at_start + self.run_spent + self._reserved + estimate_usd
        if month_total > self._month_limit:
            raise BudgetExceededError(f"月の上限 ${self._month_limit:.2f} に達する見込み")
        self._reserved += estimate_usd

    def settle(self, estimate_usd: float, actual_usd: float) -> None:
        """予約を外し、実費を足す。呼び出しが失敗したときは actual_usd = 0 で呼ぶ。"""
        self._reserved = max(0.0, self._reserved - estimate_usd)
        self.run_spent += actual_usd
