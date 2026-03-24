"""
Утилиты для NEXUS бота.
lock не импортируется здесь — импортируйте его напрямую из utils.lock.
"""

from .antispam import (
    is_spam,
    is_rate_limited,
    is_temp_banned,
    add_temp_ban,
    add_warning,
    reset_warnings,
    get_warnings,
    should_mute,
    contains_forbidden_words,
    contains_links,
    contains_phone,
    get_spam_stats,
    cleanup_old_data,
    get_rate_limit_info
)

from .filters import (
    contains_bad_words,
    censor_text,
    BAD_WORDS
)

from .logger import (
    log_info,
    log_success,
    log_error,
    log_warning,
    log_attack,
    log_admin,
    log_game,
    log_economy,
    log_user,
    measure_time,
    get_logs_summary,
    Logger
)
