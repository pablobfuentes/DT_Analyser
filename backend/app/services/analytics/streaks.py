"""Win/loss streak analytics."""

from __future__ import annotations

from app.utils.analytics import TradeOutcome


def compute_streaks(outcomes: list[TradeOutcome]) -> dict:
    """
    outcomes in chronological order (exit_time asc).
    BREAKEVEN breaks both streaks.
    """
    if not outcomes:
        return {
            "longest_win": 0,
            "longest_loss": 0,
            "current_type": None,
            "current_count": 0,
        }

    longest_win = 0
    longest_loss = 0
    win_run = 0
    loss_run = 0

    for o in outcomes:
        if o == "WIN":
            win_run += 1
            loss_run = 0
            longest_win = max(longest_win, win_run)
        elif o == "LOSS":
            loss_run += 1
            win_run = 0
            longest_loss = max(longest_loss, loss_run)
        else:
            win_run = 0
            loss_run = 0

    # Current streak from end
    current_type: str | None = None
    current_count = 0
    for o in reversed(outcomes):
        if o == "BREAKEVEN":
            current_type = "BE"
            current_count = 0
            break
        if current_type is None:
            current_type = o
            current_count = 1
        elif o == current_type:
            current_count += 1
        else:
            break

    return {
        "longest_win": longest_win,
        "longest_loss": longest_loss,
        "current_type": current_type,
        "current_count": current_count,
    }
