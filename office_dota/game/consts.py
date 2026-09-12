"""Константы движка: тик, команды, типы урона, флаги состояний.

Здесь только то, что определяет поведение движка. Игровой баланс (статы крипов,
цены предметов, таблица опыта) живёт в office_dota/game/data/ и меняется без
правки движка.
"""
from __future__ import annotations

# --- Темп симуляции -------------------------------------------------------
TICK_RATE = 20                     # тиков симуляции в секунду
TICK_DT = 1.0 / TICK_RATE          # 0.05 с — фиксированный шаг
SNAPSHOT_RATE = 20                 # снапшотов клиенту в секунду (= каждый тик; в LAN трафик не жмём)
SNAPSHOT_EVERY_N_TICKS = max(1, round(TICK_RATE / SNAPSHOT_RATE))
CLIENT_INTERP_DELAY = 0.10         # с, буфер интерполяции на клиенте

# --- Команды --------------------------------------------------------------
TEAM_DEV = 0                       # «Разработка», зелёные, база в левом нижнем углу
TEAM_MGMT = 1                      # «Менеджмент», красные, база в правом верхнем
TEAM_NEUTRAL = 2                   # лес, Легаси
TEAMS = (TEAM_DEV, TEAM_MGMT)

TEAM_NAMES = {
    TEAM_DEV: "Разработка",
    TEAM_MGMT: "Менеджмент",
    TEAM_NEUTRAL: "Нейтралы",
}
TEAM_COLORS = {
    TEAM_DEV: "#3fbf6f",
    TEAM_MGMT: "#d94c4c",
    TEAM_NEUTRAL: "#b0a080",
}


def enemy_of(team: int) -> int:
    return TEAM_MGMT if team == TEAM_DEV else TEAM_DEV


# --- Типы урона -----------------------------------------------------------
DMG_PHYSICAL = "physical"
DMG_MAGICAL = "magical"
DMG_PURE = "pure"
DAMAGE_TYPES = (DMG_PHYSICAL, DMG_MAGICAL, DMG_PURE)

# Откуда пришёл урон — влияет на то, что можно заблокировать
SRC_ATTACK = "attack"              # обычная атака
SRC_ABILITY = "ability"            # способность героя
SRC_ITEM = "item"
SRC_DOT = "dot"                    # периодический урон
SRC_TOWER = "tower"

# --- Боевая модель (Dota 2, чтобы не переучиваться) ------------------------
ARMOR_K = 0.06                     # коэффициент формулы брони
BASE_MAGIC_RESIST = 0.25           # 25% базового магсопра у героев
CREEP_MAGIC_RESIST = 0.0
BUILDING_MAGIC_RESIST = 0.0

HP_PER_STR = 22.0
HP_REGEN_PER_STR = 0.1
ARMOR_PER_AGI = 1.0 / 6.0          # 1 броня за 6 ловкости
ATTACK_SPEED_PER_AGI = 1.0
MANA_PER_INT = 12.0
MANA_REGEN_PER_INT = 0.05
SPELL_AMP_PER_INT = 0.001          # +0.1% за очко интеллекта
UNIVERSAL_DAMAGE_PER_STAT = 0.7    # универсальные герои: урон за очко каждого атрибута

MIN_ATTACK_SPEED = 20              # IAS зажат в эти границы
MAX_ATTACK_SPEED = 700
DEFAULT_BAT = 1.7                  # базовое время атаки

# --- Флаги состояний ------------------------------------------------------
# Битовая маска: состояний много и проверяются они каждый тик на каждом юните.
F_STUNNED = 1 << 0                 # не двигается, не атакует, не кастует
F_SILENCED = 1 << 1                # не кастует способности
F_ROOTED = 1 << 2                  # не двигается, но бьёт и кастует
F_DISARMED = 1 << 3                # не атакует
F_HEXED = 1 << 4                   # slow + silence + disarm + блок предметов
F_TAUNTED = 1 << 5                 # обязан атаковать источник насмешки
F_INVULNERABLE = 1 << 6            # не получает урона вообще
F_MAGIC_IMMUNE = 1 << 7            # игнорирует магический урон и большинство контроля
F_INVISIBLE = 1 << 8               # невидим для врага без детекта
F_BROKEN = 1 << 9                  # пассивки отключены
F_MUTED = 1 << 10                  # не использует предметы
F_CHEAT_DEATH = 1 << 11            # не может умереть, HP не падает ниже 1
F_TRUESIGHT = 1 << 12              # видит невидимых рядом
F_CHANNELING = 1 << 13             # держит канал, прерывается контролем
F_ETHEREAL = 1 << 14               # не получает физ. урон, получает больше магического

# Комбинации для быстрых проверок
CANNOT_MOVE = F_STUNNED | F_ROOTED | F_HEXED | F_CHANNELING
CANNOT_ATTACK = F_STUNNED | F_DISARMED | F_HEXED | F_CHANNELING | F_ETHEREAL
CANNOT_CAST = F_STUNNED | F_SILENCED | F_HEXED
CANNOT_USE_ITEMS = F_STUNNED | F_HEXED | F_MUTED
IS_DISABLED = F_STUNNED | F_HEXED

# Контроль, который снимается магическим иммунитетом
BLOCKED_BY_MAGIC_IMMUNITY = F_STUNNED | F_SILENCED | F_ROOTED | F_HEXED | F_TAUNTED

# --- Типы сущностей -------------------------------------------------------
E_HERO = "hero"
E_CREEP = "creep"
E_NEUTRAL = "neutral"
E_TOWER = "tower"
E_BARRACKS = "barracks"
E_ANCIENT = "ancient"
E_FOUNTAIN = "fountain"
E_PROJECTILE = "projectile"
E_WARD = "ward"
E_RUNE = "rune"
E_SUMMON = "summon"
E_ILLUSION = "illusion"
E_EFFECT = "effect"                # чисто визуальная сущность

BUILDING_TYPES = frozenset({E_TOWER, E_BARRACKS, E_ANCIENT, E_FOUNTAIN})
ATTACKABLE_TYPES = frozenset({
    E_HERO, E_CREEP, E_NEUTRAL, E_TOWER, E_BARRACKS,
    E_ANCIENT, E_WARD, E_SUMMON, E_ILLUSION,
})

# --- Приказы юниту --------------------------------------------------------
ORDER_NONE = "none"
ORDER_MOVE = "move"
ORDER_ATTACK_UNIT = "attack_unit"
ORDER_ATTACK_MOVE = "attack_move"
ORDER_HOLD = "hold"
ORDER_STOP = "stop"
ORDER_CAST = "cast"
ORDER_FOLLOW = "follow"

# --- Фазы матча -----------------------------------------------------------
PHASE_LOBBY = "lobby"              # сбор игроков, выбор героев
PHASE_PREGAME = "pregame"          # герои выбраны, обратный отсчёт до первой волны
PHASE_RUNNING = "running"
PHASE_PAUSED = "paused"
PHASE_FINISHED = "finished"

# --- Пауза ----------------------------------------------------------------
PAUSE_REASON_MANUAL = "manual"          # кто-то нажал паузу
PAUSE_REASON_DISCONNECT = "disconnect"  # игрок отвалился, ждём
PAUSE_REASON_PREGAME = "pregame"
UNPAUSE_COUNTDOWN = 3.0            # с, обратный отсчёт перед снятием паузы
DISCONNECT_GRACE = 5.0             # с, не паузим при мгновенном реконнекте (F5)

# --- Туман войны ----------------------------------------------------------
FOW_CELL = 128                     # сторона клетки сетки видимости, в юнитах мира
FOW_UPDATE_EVERY_N_TICKS = 2       # пересчёт видимости не каждый тик — дорого

# --- Прочее ---------------------------------------------------------------
DAY_NIGHT_PERIOD = 240.0           # с, полный цикл (в Turbo вдвое быстрее доты)
ATTACK_RANGE_BUFFER = 40.0         # допуск дальности атаки, чтобы не «дёргались»
TURN_RATE_DEFAULT = 7.0            # рад/с, скорость разворота юнита
MAX_MOVE_SPEED = 550.0
MIN_MOVE_SPEED = 100.0
ITEM_SLOTS = 6
BACKPACK_SLOTS = 3
DELIVERY_TIME = 12.0               # с, доставка покупки вне базы (курьера как юнита нет)
