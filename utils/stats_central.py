#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================
# ФАЙЛ: utils/stats_central.py
# ВЕРСИЯ: 1.0.0
# ОПИСАНИЕ: ЦЕНТРАЛИЗОВАННАЯ СТАТИСТИКА — единый источник правды
# ============================================

import logging
from typing import Optional, Dict, Any
from database import db, DatabaseError

logger = logging.getLogger(__name__)


async def get_full_user_stats(user_id: int) -> Optional[Dict[str, Any]]:
    """
    ЕДИНЫЙ ИСТОЧНИК СТАТИСТИКИ.
    Возвращает полную статистику пользователя: активность, XO, экономика, донат, ранг.
    """
    if user_id is None or db is None:
        return None
    
    try:
        stats = await db.get_user_stats(user_id)
        
        if not stats:
            await db.create_user(user_id)
            stats = await db.get_user_stats(user_id)
        
        if not stats:
            return None
        
        # Донат
        try:
            donor = await db._execute_with_retry(
                "SELECT total_donated, donor_rank FROM donors WHERE user_id = ?",
                (user_id,), fetch_one=True
            )
            if donor:
                stats['total_donated_rub'] = donor.get('total_donated', 0) or 0
                stats['donor_rank'] = donor.get('donor_rank', '💎 Поддерживающий')
        except Exception:
            stats['total_donated_rub'] = stats.get('total_donated_rub', 0) or 0
            stats['donor_rank'] = '💎 Поддерживающий'
        
        # Ранг
        try:
            rank = await db._execute_with_retry(
                "SELECT xp, level, rank_name, tier FROM user_ranks WHERE user_id = ?",
                (user_id,), fetch_one=True
            )
            if rank:
                stats['rank_xp'] = rank.get('xp', 0) or 0
                stats['rank_level'] = rank.get('level', 1) or 1
                stats['rank_name'] = rank.get('rank_name', 'Серебро V')
                stats['rank_tier'] = rank.get('tier', 'silver')
        except Exception:
            stats['rank_xp'] = 0
            stats['rank_level'] = 1
            stats['rank_name'] = 'Серебро V'
            stats['rank_tier'] = 'silver'
        
        # Имя пользователя для отображения
        stats['first_name'] = stats.get('first_name', 'Пользователь')
        stats['username'] = stats.get('username', '')
        
        # Гарантируем числовые значения
        numeric_keys = [
            'balance', 'messages_total', 'messages_today', 'messages_week',
            'messages_month', 'total_voice', 'total_stickers', 'total_photos',
            'total_videos', 'total_gifs', 'days_active', 'current_streak',
            'max_streak', 'games_played', 'wins', 'losses', 'draws',
            'wins_vs_bot', 'losses_vs_bot', 'max_win_streak',
            'total_earned', 'total_spent', 'daily_claims', 'daily_streak',
            'vip_level', 'total_donated_rub', 'total_donated_coins'
        ]
        for key in numeric_keys:
            stats[key] = stats.get(key, 0) or 0
        
        return stats
        
    except DatabaseError as e:
        logger.error(f"Database error getting stats for {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error getting stats for {user_id}: {e}")
        return None
