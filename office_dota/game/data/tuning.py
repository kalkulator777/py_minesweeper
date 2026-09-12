# -*- coding: utf-8 -*-
"""Экономика, крипы, строения, лес и руны «Офисной Доты» — чистые данные.

Модуль сознательно не импортирует ничего из ``office_dota.*`` и вообще ничего,
кроме stdlib. Здесь только числа, несколько чистых функций-формул,
расчёт темпа ``ANALYSIS`` и самопроверка ``validate()``.

Источники требований:
  * ``docs/DESIGN.md`` §2 (матч 12–20 мин, 1–3 игрока в команде),
    §4 (динамическая экономика), §6 (офисная тема), §7 (границы).
  * ``docs/ABILITY_SPEC.md`` §6 (боевая модель Dota 2), §8.5 (Turbo:
    золото и опыт ≈ ×2, респавн ≈ ×0.5).

Как реализован Turbo-опыт (важно, чтобы не умножить дважды):
  ``XP_TABLE`` — это ПОРОГИ, УЖЕ УПОЛОВИНЕННЫЕ относительно Dota 2
  (10 540 XP до 25-го уровня вместо ~21 000). Награды за опыт (крипы, герои,
  Легаси) при этом оставлены на уровне обычной доты. Итог — тот же «опыт ×2»,
  но одной крутилкой: правишь пороги — правишь темп прокачки целиком.
  Золото, в отличие от опыта, умножено в самих наградах (баунти крипов ≈ ×1.6,
  пассив ×2.5, награда за героя ×2), потому что цены предметов — чужой модуль.

Единицы: расстояние — мировые юниты (как в gamemap), время — секунды,
урон — до брони/магсопра, ``magic_resist`` — доля (0.25 = 25%).
"""

# ==========================================================================
#  1. Уровни: опыт и респавн
# ==========================================================================

MAX_LEVEL = 25

# Накопительный опыт: XP_TABLE[i] — сколько всего нужно для уровня i+1.
# Шаг между уровнями — ровно половина доты (115→120, 185→180, ... 630).
XP_TABLE: list[int] = [
    0,      # 1
    120,    # 2
    300,    # 3
    540,    # 4
    830,    # 5
    1130,   # 6   <- первая ульта
    1490,   # 7
    1870,   # 8
    2260,   # 9
    2660,   # 10
    3080,   # 11
    3520,   # 12  <- вторая ульта
    3970,   # 13
    4430,   # 14
    4910,   # 15
    5410,   # 16
    5920,   # 17
    6440,   # 18  <- третья ульта, «пик» героя
    6980,   # 19
    7540,   # 20
    8110,   # 21
    8690,   # 22
    9290,   # 23
    9910,   # 24
    10540,  # 25
]

# Время возрождения по уровню героя, секунды. ≈ ×0.5 от доты.
# Смерть на 18-м уровне = 22 с — хватает, чтобы потерять базу, но не матч.
# ИНДЕКСАЦИЯ как у XP_TABLE: RESPAWN_TABLE[level - 1], 25 записей без фиктивного
# нуля в начале. Кто читает таблицу как RESPAWN_TABLE[level], получит сдвиг
# на уровень (герой 1-го уровня будет возрождаться 4 с вместо 3 с).
RESPAWN_TABLE: list[float] = [
    3.0, 4.0, 5.0, 6.0, 7.0,        # 1–5
    8.0, 9.0, 10.0, 11.0, 12.0,     # 6–10
    13.0, 14.0, 15.0, 16.0, 17.0,   # 11–15
    18.0, 20.0, 22.0, 24.0, 26.0,   # 16–20
    28.0, 30.0, 32.0, 34.0, 36.0,   # 21–25
]


def xp_to_level(total_xp: float) -> int:
    """Уровень героя по накопленному опыту. Чистая функция, 1..MAX_LEVEL."""
    lvl = 1
    for i, need in enumerate(XP_TABLE):
        if total_xp >= need:
            lvl = i + 1
        else:
            break
    return lvl


# ==========================================================================
#  2. Крипы
# ==========================================================================
# Статы — доталайк (чтобы не переучиваться), золото поднято под Turbo.
# magic_resist у линейных крипов 0.0 — как ``consts.CREEP_MAGIC_RESIST``.
# У Подрядчика 0.35: осадный крип не должен сноситься одним нюком,
# иначе осада линии ничего не стоит.

CREEPS: dict[str, dict] = {
    "melee_creep": {
        "name": "Стажёр",
        "hp": 550,
        "damage": [19, 23],
        "armor": 2.0,
        "magic_resist": 0.0,
        "attack_range": 100,
        "bat": 1.0,
        "move_speed": 325,
        "bounty_gold": [55, 65],
        "bounty_xp": 55,
        "vision": 750,
        "building_damage_mult": 1.0,
    },
    "ranged_creep": {
        "name": "Аналитик",
        "hp": 300,
        "damage": [22, 26],
        "armor": 0.0,
        "magic_resist": 0.0,
        "attack_range": 500,
        "bat": 1.0,
        "move_speed": 325,
        "bounty_gold": [80, 92],
        "bounty_xp": 70,
        "vision": 800,
        "building_damage_mult": 1.0,
    },
    "siege_creep": {
        "name": "Подрядчик",
        "hp": 875,
        "damage": [40, 44],
        "armor": 0.0,
        "magic_resist": 0.35,
        "attack_range": 690,
        "bat": 2.0,
        "move_speed": 325,
        "bounty_gold": [135, 155],
        "bounty_xp": 85,
        "vision": 700,
        "building_damage_mult": 2.5,   # ради него осадный и нужен
    },
    "super_melee": {
        "name": "Стажёр на удалёнке",      # мега-крип после падения Отдела найма
        "hp": 1100,
        "damage": [43, 49],
        "armor": 4.0,
        "magic_resist": 0.0,
        "attack_range": 100,
        "bat": 1.0,
        "move_speed": 340,
        "bounty_gold": [45, 55],           # меньше обычного: не кормим отстающих
        "bounty_xp": 50,
        "vision": 750,
        "building_damage_mult": 1.0,
    },
    "super_ranged": {
        "name": "Аналитик на удалёнке",
        "hp": 650,
        "damage": [42, 48],
        "armor": 2.0,
        "magic_resist": 0.0,
        "attack_range": 500,
        "bat": 1.0,
        "move_speed": 340,
        "bounty_gold": [60, 70],
        "bounty_xp": 60,
        "vision": 800,
        "building_damage_mult": 1.0,
    },
}

# Апгрейд крипов со временем. Формула аддитивная по шагам:
#   stat = base * (1 + pct * steps),  steps = min(t // interval, max_steps)
# В доте шаг 7.5 мин, в Turbo — 4 мин, иначе к 15-й минуте крипы не успевают
# стать угрозой и мега-крипы решают матч в одиночку.
CREEP_SCALING: dict = {
    "interval_sec": 240.0,
    "max_steps": 12,
    "hp_pct_per_step": 0.06,
    "damage_pct_per_step": 0.06,
    "armor_add_per_step": 0.5,
    "bounty_gold_pct_per_step": 0.04,
    "bounty_xp_pct_per_step": 0.03,
    "applies_to": ("melee_creep", "ranged_creep", "siege_creep",
                   "super_melee", "super_ranged"),
}


def creep_stats_at(key: str, match_time_sec: float) -> dict:
    """Статы крипа с учётом апгрейдов на минуте матча. Чистая функция."""
    base = CREEPS[key]
    if key not in CREEP_SCALING["applies_to"] or match_time_sec <= 0.0:
        steps = 0
    else:
        steps = int(min(match_time_sec // CREEP_SCALING["interval_sec"],
                        CREEP_SCALING["max_steps"]))
    hp_k = 1.0 + CREEP_SCALING["hp_pct_per_step"] * steps
    dmg_k = 1.0 + CREEP_SCALING["damage_pct_per_step"] * steps
    gold_k = 1.0 + CREEP_SCALING["bounty_gold_pct_per_step"] * steps
    xp_k = 1.0 + CREEP_SCALING["bounty_xp_pct_per_step"] * steps
    out = dict(base)
    out["hp"] = base["hp"] * hp_k
    out["damage"] = [base["damage"][0] * dmg_k, base["damage"][1] * dmg_k]
    out["armor"] = base["armor"] + CREEP_SCALING["armor_add_per_step"] * steps
    out["bounty_gold"] = [base["bounty_gold"][0] * gold_k,
                          base["bounty_gold"][1] * gold_k]
    out["bounty_xp"] = base["bounty_xp"] * xp_k
    out["upgrade_steps"] = steps
    return out


# ==========================================================================
#  3. Расписание волн
# ==========================================================================
# Turbo: волна каждые 25 с (дота — 30 с), первая в 0:20 (дота — 0:30).
# 2.4 волны в минуту — на этом числе построен весь расчёт в ANALYSIS.

WAVE_SCHEDULE: dict = {
    "first_wave_spawn_sec": 20.0,
    "interval_sec": 25.0,
    "lane_contact_delay_sec": 20.0,     # от спавна до встречи волн в центре линии
    "lanes": {"top": "Коридор", "mid": "Опенспейс", "bot": "Подвал"},
    "composition": {"melee_creep": 3, "ranged_creep": 1},
    "siege": {
        "unit": "siege_creep",
        "count": 1,
        "first_spawn_sec": 180.0,       # с 3:00 (дота — с 5:00)
        "every_n_waves": 3,
    },
    # Апгрейды состава после падения бараков. scope: lane | all_lanes.
    "upgrades": [
        {"trigger": "barracks_melee_destroyed", "scope": "lane",
         "replace": {"melee_creep": "super_melee"}},
        {"trigger": "barracks_ranged_destroyed", "scope": "lane",
         "replace": {"ranged_creep": "super_ranged"}},
        {"trigger": "all_barracks_destroyed", "scope": "all_lanes",
         "replace": {"melee_creep": "super_melee", "ranged_creep": "super_ranged"},
         "siege_every_n_waves": 2},     # мега-волна прёт осадой вдвое чаще
    ],
    "spawn_while_paused": False,
}


# ==========================================================================
#  4. Строения
# ==========================================================================
# Башня должна БИТЬ. Ориентир: герой 6-го уровня (~1200 HP, 2–3 брони)
# умирает под Кулером за 10 попаданий = 10 секунд. Ныряешь под башню —
# ныряешь на свои деньги.
#
# magic_resist строений = 0.0, как ``consts.BUILDING_MAGIC_RESIST``:
# строения защищены не сопротивлением, а правилом наведения
# (``BUILDING_RULES["abilities_can_target_buildings"]``), как в доте.
# damage/attack_range = 0 у неатакующих строений — это не «непроставленный
# стат», а признак «не стреляет».

BUILDINGS: dict[str, dict] = {
    "tower_t1": {
        "name": "Кулер",
        "hp": 1500, "damage": 130, "armor": 16.0, "magic_resist": 0.0,
        "attack_range": 700, "bat": 1.0,
        "bounty_team_gold": 120, "bounty_killer_gold": 240,
        "backdoor_protection": False,   # T1 берётся и сплитпушем, это нормально
        "hp_regen": 2.0,
    },
    "tower_t2": {
        "name": "Принтер",
        "hp": 2000, "damage": 150, "armor": 18.0, "magic_resist": 0.0,
        "attack_range": 700, "bat": 1.0,
        "bounty_team_gold": 150, "bounty_killer_gold": 280,
        "backdoor_protection": True,
        "hp_regen": 2.0,
    },
    "tower_t3": {
        "name": "Кофемашина",
        "hp": 2400, "damage": 170, "armor": 20.0, "magic_resist": 0.0,
        "attack_range": 700, "bat": 0.95,
        "bounty_team_gold": 180, "bounty_killer_gold": 320,
        "backdoor_protection": True,
        "hp_regen": 2.5,
    },
    "tower_t4": {
        "name": "Турникет",
        "hp": 2600, "damage": 180, "armor": 22.0, "magic_resist": 0.0,
        "attack_range": 700, "bat": 0.9,
        "bounty_team_gold": 100, "bounty_killer_gold": 120,
        "backdoor_protection": True,
        "hp_regen": 2.5,
    },
    "barracks_melee": {
        "name": "Отдел найма",
        "hp": 2000, "damage": 0, "armor": 8.0, "magic_resist": 0.0,
        "attack_range": 0, "bat": 1.0,
        "bounty_team_gold": 150, "bounty_killer_gold": 150,
        "backdoor_protection": True,
        "hp_regen": 3.0,
    },
    "barracks_ranged": {
        "name": "Отдел саппорта",
        "hp": 1300, "damage": 0, "armor": 6.0, "magic_resist": 0.0,
        "attack_range": 0, "bat": 1.0,
        "bounty_team_gold": 150, "bounty_killer_gold": 150,
        "backdoor_protection": True,
        "hp_regen": 3.0,
    },
    "ancient": {
        "name": "Трон",                 # «Прод-сервер» / «Совет директоров»
        "hp": 5000, "damage": 0, "armor": 15.0, "magic_resist": 0.0,
        "attack_range": 0, "bat": 1.0,
        "bounty_team_gold": 0, "bounty_killer_gold": 0,
        "backdoor_protection": True,
        "hp_regen": 4.0,
    },
    "fountain": {
        "name": "Кухня",
        "hp": 10000, "damage": 200, "armor": 100.0, "magic_resist": 0.0,
        "attack_range": 700, "bat": 0.4,
        "bounty_team_gold": 0, "bounty_killer_gold": 0,
        "backdoor_protection": True,
        "hp_regen": 10.0,
        "invulnerable": True,
        "aura": {"radius": 1100, "hp_regen_pct_per_sec": 0.06,
                 "mana_regen_pct_per_sec": 0.06},
    },
}

BUILDING_RULES: dict = {
    "abilities_can_target_buildings": False,   # как в доте: строения бьют атакой
    "aoe_damage_hits_buildings": False,
    "backdoor_damage_taken_pct": 0.25,         # под защитой строение почти не ломается
    "backdoor_regen_hp_per_sec": 25.0,
    "backdoor_active_while_lane_creeps_absent_sec": 5.0,
    "out_of_combat_regen_delay_sec": 15.0,
    "glyph_cooldown_sec": 180.0,               # дота 300 с, Turbo — быстрее
    "glyph_duration_sec": 6.0,
    "tower_deny_enabled": False,               # денаев в игре нет (DESIGN §7)
    "tower_attack_ramp_pct_per_hit": 0.0,
    "ancient_requires_t4_down": True,          # трон уязвим после падения турникетов
    "barracks_require_t3_down": True,
}


# ==========================================================================
#  5. Лес
# ==========================================================================
# Раскладка лагерей — в gamemap.CAMPS: на сторону 2×small, 2×medium,
# 1×large, 1×ancient плюс Легаси у реки. Ключи размеров совпадают.
# Лагерь должен стоить примерно как волна на линии, иначе в лес никто не пойдёт:
#   волна = 266 ₿ / 235 XP,  small 145/120, medium 230/200,
#   large 330/304, ancient 490/460.

JUNGLE: dict[str, dict] = {
    "small": {
        "name": "Уборщики",
        "respawn_sec": 45.0,
        "bounty_gold_total": [130, 160],
        "bounty_xp_total": 120,
        "variants": [
            {
                "name": "Уборщики",
                "units": [
                    {"key": "cleaner_lead", "name": "Старший уборщик", "count": 1,
                     "hp": 550, "damage": [14, 18], "armor": 1.0, "magic_resist": 0.0,
                     "attack_range": 100, "bat": 1.4, "move_speed": 300,
                     "bounty_gold": [60, 70], "bounty_xp": 50, "vision": 800},
                    {"key": "cleaner", "name": "Уборщик", "count": 2,
                     "hp": 300, "damage": [9, 13], "armor": 0.0, "magic_resist": 0.0,
                     "attack_range": 100, "bat": 1.4, "move_speed": 300,
                     "bounty_gold": [35, 45], "bounty_xp": 35, "vision": 800},
                ],
            },
        ],
    },
    "medium": {
        "name": "Бухгалтерия / Эйчары",
        "respawn_sec": 45.0,
        "bounty_gold_total": [210, 250],
        "bounty_xp_total": 200,
        "variants": [
            {
                "name": "Бухгалтерия",
                "units": [
                    {"key": "chief_accountant", "name": "Главбух", "count": 1,
                     "hp": 950, "damage": [20, 26], "armor": 2.0, "magic_resist": 0.15,
                     "attack_range": 500, "bat": 1.6, "move_speed": 290,
                     "bounty_gold": [110, 130], "bounty_xp": 100, "vision": 800},
                    {"key": "accountant", "name": "Бухгалтер", "count": 2,
                     "hp": 450, "damage": [14, 18], "armor": 1.0, "magic_resist": 0.0,
                     "attack_range": 500, "bat": 1.5, "move_speed": 290,
                     "bounty_gold": [50, 60], "bounty_xp": 50, "vision": 800},
                ],
            },
            {
                "name": "Эйчары",
                "units": [
                    {"key": "hr_lead", "name": "Старший эйчар", "count": 1,
                     "hp": 900, "damage": [22, 28], "armor": 2.0, "magic_resist": 0.25,
                     "attack_range": 400, "bat": 1.6, "move_speed": 300,
                     "bounty_gold": [115, 135], "bounty_xp": 105, "vision": 800},
                    {"key": "hr", "name": "Эйчар", "count": 2,
                     "hp": 420, "damage": [15, 19], "armor": 0.0, "magic_resist": 0.0,
                     "attack_range": 400, "bat": 1.5, "move_speed": 300,
                     "bounty_gold": [48, 58], "bounty_xp": 48, "vision": 800},
                ],
            },
        ],
    },
    "large": {
        "name": "Юристы",
        "respawn_sec": 45.0,
        "bounty_gold_total": [300, 360],
        "bounty_xp_total": 304,
        "variants": [
            {
                "name": "Юристы",
                "units": [
                    {"key": "law_partner", "name": "Партнёр", "count": 1,
                     "hp": 1400, "damage": [32, 40], "armor": 4.0, "magic_resist": 0.35,
                     "attack_range": 150, "bat": 1.5, "move_speed": 310,
                     "bounty_gold": [160, 190], "bounty_xp": 160, "vision": 800},
                    {"key": "lawyer", "name": "Юрист", "count": 2,
                     "hp": 700, "damage": [22, 28], "armor": 2.0, "magic_resist": 0.20,
                     "attack_range": 400, "bat": 1.5, "move_speed": 300,
                     "bounty_gold": [70, 85], "bounty_xp": 72, "vision": 800},
                ],
            },
        ],
    },
    "ancient": {
        "name": "Безопасники",
        "respawn_sec": 60.0,
        "bounty_gold_total": [450, 530],
        "bounty_xp_total": 460,
        "variants": [
            {
                "name": "Безопасники",
                "units": [
                    {"key": "security_chief", "name": "Начальник СБ", "count": 1,
                     "hp": 2200, "damage": [48, 58], "armor": 6.0, "magic_resist": 0.60,
                     "attack_range": 200, "bat": 1.6, "move_speed": 320,
                     "bounty_gold": [220, 260], "bounty_xp": 240, "vision": 900},
                    {"key": "security", "name": "Безопасник", "count": 2,
                     "hp": 1100, "damage": [30, 38], "armor": 4.0, "magic_resist": 0.60,
                     "attack_range": 150, "bat": 1.5, "move_speed": 310,
                     "bounty_gold": [115, 135], "bounty_xp": 110, "vision": 900},
                ],
            },
        ],
    },
    "roshan": {
        "name": "Легаси",
        "first_spawn_sec": 300.0,         # в матче на 15 минут Легаси — цель середины
        "respawn_sec": [240.0, 300.0],    # дота 8–11 мин, Turbo — вдвое меньше
        "bounty_gold_total": [300, 300],  # киллеру; команде — bounty_team_gold_each
        "bounty_xp_total": 400,
        "variants": [
            {
                "name": "Легаси",
                "units": [
                    {"key": "legacy", "name": "Легаси", "count": 1,
                     "hp": 3600, "damage": [90, 110], "armor": 14.0, "magic_resist": 0.55,
                     "attack_range": 150, "bat": 1.6, "move_speed": 320,
                     "bounty_gold": [300, 300], "bounty_xp": 400, "vision": 1800,
                     "bash_chance": 0.15, "bash_duration": 1.0,
                     "spell_block": True},
                ],
            },
        ],
        # Усиление со временем: считается от first_spawn_sec, аддитивно по минутам.
        "scaling": {
            "per_min_hp": 150.0,
            "per_min_damage": 6.0,
            "per_min_armor": 0.3,
            "max_minutes": 15.0,          # к 20:00 упирается в потолок
        },
        "bounty_team_gold_each": 150,
        "bounty_xp_each": 400,
        "drops": [
            {"key": "aegis", "name": "Бэкап", "from_kill": 1,
             "reincarnate_delay_sec": 4.0, "duration_sec": 240.0},
            {"key": "cheese", "name": "Печеньки", "from_kill": 3},
        ],
    },
}

JUNGLE_RULES: dict = {
    "spawn_tick_sec": 15.0,        # лагерь проверяется на респавн раз в 15 с
    "stack_window_sec": 5.0,       # увёл нейтралов за это окно до тика — стак
    "max_stacks": 5,
    "block_radius": 700.0,         # герой/крип в радиусе блокирует спавн
    "neutrals_leash_range": 1200.0,
    "neutrals_return_heal_pct_per_sec": 0.20,
    "camps_per_side": {"small": 2, "medium": 1, "large": 1, "ancient": 1},
    "ancient_camp_magic_resist_note": "древние — 60% магсопра, нюком не снимаются",
}


def legacy_stats_at(match_time_sec: float) -> dict:
    """Статы Легаси (Roshan) на минуте матча. Чистая функция."""
    unit = dict(JUNGLE["roshan"]["variants"][0]["units"][0])
    sc = JUNGLE["roshan"]["scaling"]
    minutes = (match_time_sec - JUNGLE["roshan"]["first_spawn_sec"]) / 60.0
    minutes = max(0.0, min(minutes, sc["max_minutes"]))
    unit["hp"] = unit["hp"] + sc["per_min_hp"] * minutes
    unit["damage"] = [unit["damage"][0] + sc["per_min_damage"] * minutes,
                      unit["damage"][1] + sc["per_min_damage"] * minutes]
    unit["armor"] = unit["armor"] + sc["per_min_armor"] * minutes
    return unit


# ==========================================================================
#  6. Руны
# ==========================================================================
# Позиции — в gamemap: 2 точки силы на реке, 4 точки Премии.
# Turbo: руны силы с 3:00 (дота — с 6:00), интервал 2 мин у обоих типов.
# Водяных рун нет — в офисе нет воды, а механика лишняя.

RUNES: dict = {
    "power": {
        "name": "Руны силы",
        "first_spawn_sec": 180.0,
        "interval_sec": 120.0,
        "spots": 2,
        "max_on_map_per_spot": 1,
        "bottleable": True,
        "bottle_hold_sec": 120.0,
        "types": {
            "double_damage": {
                "name": "Переработка",
                "duration": 45.0,
                "effect": {"damage_mult": 2.0, "applies_to": "base_damage"},
                "desc": "Двойной базовый урон. Прототип: Double Damage.",
            },
            "haste": {
                "name": "Дедлайн",
                "duration": 22.0,
                "effect": {"move_speed_set": 550.0, "slow_immune": True},
                "desc": "Максимальная скорость, иммунитет к замедлениям. Haste.",
            },
            "regeneration": {
                "name": "Обед",
                "duration": 30.0,
                "effect": {"hp_regen_pct_per_sec": 0.06, "mana_regen_pct_per_sec": 0.06,
                           "break_on_damage_from_hero": True},
                "desc": "6% максимума HP и маны в секунду. Regeneration.",
            },
            "illusion": {
                "name": "Аутсорс",
                "duration": 75.0,
                "effect": {"illusion_count": 2, "dmg_out_pct": 35, "dmg_in_pct": 200},
                "desc": "Две иллюзии-подрядчика. Illusion.",
            },
            "invisibility": {
                "name": "Удалёнка",
                "duration": 45.0,
                "effect": {"invisible": True, "fade_delay": 2.0,
                           "break_on_attack_or_cast": True},
                "desc": "Невидимость. Invisibility.",
            },
            "arcane": {
                "name": "Флоу",
                "duration": 50.0,
                "effect": {"cooldown_reduction_pct": 30, "mana_cost_reduction_pct": 30},
                "desc": "−30% к кулдаунам и стоимости маны. Arcane.",
            },
        },
    },
    "bounty": {
        "name": "Премия",
        "first_spawn_sec": 0.0,
        "interval_sec": 120.0,
        "spots": 4,
        "max_on_map_per_spot": 1,
        "bottleable": False,
        # Ценность растёт с минутой матча: gold = base + per_min * минута.
        "gold_base": 80.0,
        "gold_per_min": 20.0,
        "xp_base": 40.0,
        "xp_per_min": 10.0,
        "team_share_pct": 0.0,     # премию забирает тот, кто подобрал (дота 7.33+)
        "desc": "Премия: золото и опыт, растут по ходу матча.",
    },
}


def bounty_rune_reward(match_time_sec: float) -> dict:
    """Золото и опыт с Премии на данной минуте. Чистая функция."""
    b = RUNES["bounty"]
    minutes = max(0.0, match_time_sec) / 60.0
    return {
        "gold": b["gold_base"] + b["gold_per_min"] * minutes,
        "xp": b["xp_base"] + b["xp_per_min"] * minutes,
    }


# ==========================================================================
#  7. Экономика
# ==========================================================================
# Пассив 2.5 ₿/с = 150 ₿/мин (дота — 100 ₿/мин), старт 800 ₿ — хватает
# на ботинки/расходники и один компонент.
# Награда за героя: (base + per_level * уровень) + шатдаун за серию.
#   Убить 10-й уровень = 120 + 180 = 300 ₿, 20-й = 480 ₿.
# Опыт за героя НЕ удваивается (пороги уже уполовинены): 60 + 12*уровень.

STREAK_BOUNTY_GOLD: list[int] = [
    0, 0, 0,        # серии 0–2 не считаются
    250,            # 3 убийства подряд
    400, 600, 800, 1000, 1200, 1400,
    1600,           # 10+ — потолок
]

ECONOMY: dict = {
    "starting_gold": 800,
    "passive_gold_per_sec": 2.5,
    "passive_gold_start_sec": 0.0,
    "gold_symbol": "₿",
    "gold_name": "Бюджет",

    # Опыт делится между героями в радиусе (как в доте).
    "xp_share_radius": 1300.0,
    "xp_split_among_heroes": True,
    "assist_gold_share": 0.45,          # доля награды каждому ассистенту
    "assist_xp_share": 0.60,
    "assist_radius": 1300.0,

    "hero_kill": {
        "base_gold": 120.0,
        "gold_per_level": 18.0,
        "xp_base": 60.0,
        "xp_per_level": 12.0,
        "streak_bounty_gold": STREAK_BOUNTY_GOLD,
        "streak_starts_at": 3,
        "first_blood_bonus_gold": 200.0,
        "shutdown_to_killer_only": True,
    },

    "death": {
        "gold_loss_base": 20.0,
        "gold_loss_per_level": 8.0,      # 18-й уровень = 164 ₿
        "gold_loss_cap": 400.0,
        "loses_reliable_gold_first": False,
        "no_loss_before_sec": 60.0,      # первую минуту смерть не штрафуем
    },

    "buyback": {
        # cost = base + level_sq_factor * lvl^2 + time_factor * t_sec
        # 18-й уровень на 12:00 = 100 + 486 + 360 = 946 ₿
        "base": 100.0,
        "level_sq_factor": 1.5,
        "time_factor": 0.5,
        "cooldown_sec": 240.0,           # дота 480 с
        "respawn_delay_sec": 0.0,        # мгновенно
        "gold_penalty_pct_after": 0.0,
    },

    # Доставка покупки вне базы — consts.DELIVERY_TIME (12 с), тут не дублируем.
    "sell_back_pct": 0.5,
    "sell_back_window_sec": 10.0,

    # На что действуют динамические множители (DESIGN §4).
    "dynamic_applies_to": {
        # Гандикап за численность применяется ТОЛЬКО к золоту.
        # Опыт и так концентрируется: в команде из одного героя его не с кем
        # делить, поэтому одиночка получает втрое больше опыта на человека
        # уже без всяких множителей. Замер на восьми минутах 1 против 3:
        # с гандикапом по опыту одиночка выходил на 25 уровень против 8,
        # без него — 16 против 10, что и есть задуманное «тяжело, но не
        # безнадёжно».
        "creep_gold": True,
        "creep_xp": False,
        "neutral_gold": True,
        "neutral_xp": False,
        "rune_gold": True,
        "hero_kill_gold": True,
        "hero_kill_xp": False,
        "building_gold": False,
        "passive_gold": False,
    },
}


def hero_kill_gold(victim_level: int, victim_streak: int = 0,
                   first_blood: bool = False) -> float:
    """Золото киллеру за убийство героя. Чистая функция."""
    hk = ECONOMY["hero_kill"]
    lvl = max(1, min(int(victim_level), MAX_LEVEL))
    gold = hk["base_gold"] + hk["gold_per_level"] * lvl
    streak = max(0, int(victim_streak))
    table = hk["streak_bounty_gold"]
    gold += table[min(streak, len(table) - 1)]
    if first_blood:
        gold += hk["first_blood_bonus_gold"]
    return gold


def hero_kill_xp(victim_level: int) -> float:
    """Опыт за убийство героя (до дележа между участниками). Чистая функция."""
    hk = ECONOMY["hero_kill"]
    lvl = max(1, min(int(victim_level), MAX_LEVEL))
    return hk["xp_base"] + hk["xp_per_level"] * lvl


def death_gold_penalty(level: int, match_time_sec: float = 999.0) -> float:
    """Сколько золота теряет герой при смерти. Чистая функция."""
    d = ECONOMY["death"]
    if match_time_sec < d["no_loss_before_sec"]:
        return 0.0
    lvl = max(1, min(int(level), MAX_LEVEL))
    return min(d["gold_loss_base"] + d["gold_loss_per_level"] * lvl,
               d["gold_loss_cap"])


def buyback_cost(level: int, match_time_sec: float) -> float:
    """Стоимость выкупа. Чистая функция."""
    b = ECONOMY["buyback"]
    lvl = max(1, min(int(level), MAX_LEVEL))
    return (b["base"] + b["level_sq_factor"] * lvl * lvl
            + b["time_factor"] * max(0.0, match_time_sec))


# ==========================================================================
#  8. Динамическая экономика (DESIGN §4) — ключевая часть
# ==========================================================================
# Обе крутилки выключаются одним флагом DYNAMIC_ECONOMY_ENABLED.
#
# Эффективная сила команды считается снаружи и подаётся числом:
#     own_power = сумма HUMAN_POWER за каждого живого игрока-человека
#               + BOT_POWER за каждого героя под ботом
# Отдельной функции для этого намеренно нет — это одна строка sum() в движке,
# а данные не должны знать, как устроен список игроков.

HUMAN_POWER = 1.0
BOT_POWER = 0.6
DYNAMIC_ECONOMY_ENABLED = True
UNDERDOG_MULT_CAP = 2.2

_TEAM_INCOME_EXPONENT = 0.75      # DESIGN §4а: N**0.75 / N
_UNDERDOG_EXPONENT = 0.65         # DESIGN §4б: (enemy/own)**0.65


def team_income_multiplier(team_size: int) -> float:
    """Множитель дохода НА ГЕРОЯ от численности команды (DESIGN §4а).

    Суммарный доход команды растёт как N**0.75, поэтому каждому достаётся
    N**0.75 / N. Третий игрок приносит команде меньше, чем второй.

        N=1 -> 1.000   N=2 -> 0.841   N=3 -> 0.760   N=5 -> 0.669

    Граничные случаи: team_size <= 1 (в том числе 0 и отрицательные числа
    из битой статистики) даёт 1.0 — делить не на что и незачем.
    """
    if not DYNAMIC_ECONOMY_ENABLED:
        return 1.0
    n = int(team_size)
    if n <= 1:
        return 1.0
    return float(n) ** _TEAM_INCOME_EXPONENT / float(n)


def underdog_multiplier(own_power: float, enemy_power: float) -> float:
    """Множитель золота и опыта отстающей по силе команде (DESIGN §4б).

        clamp((enemy_power / own_power) ** 0.65, 1.0, UNDERDOG_MULT_CAP)

    Ведущая команда не штрафуется: множитель никогда не меньше 1.0.

    Граничные случаи (деления на ноль быть не должно):
      * own_power <= 0 и enemy_power <= 0 — героев нет ни у кого -> 1.0;
      * own_power <= 0, враг есть — получать некому, отдаём потолок;
      * enemy_power <= 0 — сравнивать не с кем -> 1.0.
    """
    if not DYNAMIC_ECONOMY_ENABLED:
        return 1.0
    own = float(own_power)
    enemy = float(enemy_power)
    if own <= 0.0:
        return 1.0 if enemy <= 0.0 else UNDERDOG_MULT_CAP
    if enemy <= 0.0:
        return 1.0
    mult = (enemy / own) ** _UNDERDOG_EXPONENT
    if mult < 1.0:
        return 1.0
    if mult > UNDERDOG_MULT_CAP:
        return UNDERDOG_MULT_CAP
    return mult


# ==========================================================================
#  9. Модель темпа — то, на чём держится ANALYSIS
# ==========================================================================
# Все допущения вынесены сюда числами, чтобы их можно было оспорить,
# а не спрятаны в тексте.

PACING_MODEL: dict = {
    "lane_contact_min": 40.0 / 60.0,      # первая волна на линии
    "gold_at_contact": 900.0,             # 800 старт + 2.5 ₿/с * 40 с
    # (от, до, XP/мин, ₿/мин) — вывод каждой строки см. в ANALYSIS
    "phases": [
        {"from_min": 40.0 / 60.0, "to_min": 4.0, "xp_per_min": 451.0, "gold_per_min": 597.0},
        {"from_min": 4.0, "to_min": 9.0, "xp_per_min": 660.0, "gold_per_min": 937.0},
        {"from_min": 9.0, "to_min": 30.0, "xp_per_min": 820.0, "gold_per_min": 1100.0},
    ],
    # Накопленные траты к моменту покупки (ожидаемые цены — их держит items.py)
    "spend_marks": {
        "boots": 1300.0,    # 800 старт-кит + 500 ботинки
        "t2": 3600.0,       # + предмет 2-го тира ~2300
        "t3": 7800.0,       # + предмет 3-го тира ~4200
        "t4": 13800.0,      # + предмет 4-го тира ~6000
    },
    "assumed_item_cost": {"tier1_boots": 500, "tier2": 2300, "tier3": 4200, "tier4": 6000},
}

# Ожидаемые результаты модели (минуты). validate() сверяет с расчётом.
PACING_TARGETS: dict = {
    "level_6_min": 3.17,
    "level_12_min": 7.06,
    "level_18_min": 11.00,
    "level_25_min": 16.00,
    "boots_min": 1.34,
    "t2_min": 4.76,
    "t3_min": 9.20,
    "t4_min": 14.66,
}

MATCH_LENGTH_TARGET_MIN = (12.0, 20.0)


def _crossing_times(targets: dict[str, float], start_min: float,
                    start_value: float, rate_key: str) -> dict[str, float]:
    """Когда накопительная величина пересечёт каждый порог. Чистая функция."""
    out: dict[str, float] = {}
    pending = dict(targets)
    t = start_min
    value = start_value
    for ph in PACING_MODEL["phases"]:
        t0 = max(t, ph["from_min"])
        t1 = ph["to_min"]
        if t1 <= t0:
            continue
        rate = ph[rate_key]
        value_end = value + rate * (t1 - t0)
        for name in [k for k, v in pending.items() if v <= value_end]:
            out[name] = t0 + max(0.0, pending[name] - value) / rate
            del pending[name]
        value = value_end
        t = t1
    return out


def estimate_pacing() -> dict[str, float]:
    """Расчётные тайминги уровней и предметов, минуты. Чистая функция."""
    xp_marks = {
        "level_6_min": float(XP_TABLE[5]),
        "level_12_min": float(XP_TABLE[11]),
        "level_18_min": float(XP_TABLE[17]),
        "level_25_min": float(XP_TABLE[24]),
    }
    res = _crossing_times(xp_marks, PACING_MODEL["lane_contact_min"], 0.0, "xp_per_min")
    gold_marks = {f"{k}_min": v for k, v in PACING_MODEL["spend_marks"].items()}
    res.update(_crossing_times(gold_marks, PACING_MODEL["lane_contact_min"],
                               PACING_MODEL["gold_at_contact"], "gold_per_min"))
    return res


# ==========================================================================
#  10. Расчёт
# ==========================================================================

ANALYSIS = """\
=== РАСЧЁТ ТЕМПА: офисная дота, Turbo, матч 12-20 минут ===

0. ДОПУЩЕНИЯ (всё в PACING_MODEL, спорить с ними — правя числа там)
   - Волна: 3 Стажёра + 1 Аналитик, интервал 25 с  =>  2.4 волны/мин.
   - Волна спавнится в 0:20, встречается на линии в 0:40. Отсчёт — от 0:40.
   - Подрядчик (осадный) — каждая 3-я волна с 3:00, т.е. 0.8 осадного/мин.
   - Реализация ластхитов: 70% на линии (денаев нет, добивать легко), 85% после 4:00.
   - Утилизация опыта: 80% на линии, 85% дальше (ходьба, смерти, закупка).
   - Каждый герой стоит на своей линии: команд по 1-3 игрока, линий три.
   - Апгрейд крипов: +4% золота и +3% опыта каждые 4 минуты (к 8:00 это x1.08 / x1.06).

1. ДОХОД ПО ФАЗАМ

   Фаза A, линия (0:40 - 4:00)
     опыт  = (3*55 + 70) = 235 XP/волна * 2.4 = 564 XP/мин * 0.80 = 451 XP/мин
     золото= (3*60 + 86) = 266 B/волна  * 2.4 = 638 B/мин  * 0.70 = 447
             + пассив 2.5 B/с * 60 = 150                          = 597 B/мин

   Фаза B, линия + лес + ганки (4:00 - 9:00)
     волна с осадным в среднем: XP 235 + 85/3 = 263, золото 266 + 145/3 = 314
     апгрейд крипов: XP 263*1.06 = 279, золото 314*1.04 = 327
     опыт  = 279 * 2.4 = 670 * 0.85 = 570 + убийства/лагеря ~90   = 660 XP/мин
     золото= 327 * 2.4 = 785 * 0.85 = 667 + пассив 150
             + башни и убийства ~120                              = 937 B/мин

   Фаза C, объекты и драки 3x3 (9:00+)
     опыт  = 820 XP/мин  (линия та же, сверху Легаси 400 XP и убийства героев:
             убить 15-й уровень = 60 + 12*15 = 240 XP, в драке 2-3 таких)
     золото= 1100 B/мин  (башни: Принтер 150 команде + 280 киллеру,
             Кофемашина 180/320, Легаси 300 киллеру + 150 каждому)

2. УРОВНИ (пороги XP_TABLE уже уполовинены относительно доты)

   Уровень 6 = 1130 XP:
     1130 / 451 = 2.50 мин линии  ->  0:40 + 2:30 = 3:10
   Уровень 12 = 3520 XP:
     к 4:00 накоплено 451 * 3.33 = 1503
     (3520 - 1503) / 660 = 3.06 мин  ->  4:00 + 3:04 = 7:04
   Уровень 18 = 6440 XP:
     к 9:00 накоплено 1503 + 660*5 = 4803
     (6440 - 4803) / 820 = 2.00 мин  ->  9:00 + 2:00 = 11:00
   Уровень 25 = 10540 XP:
     (10540 - 4803) / 820 = 7.00 мин  ->  16:00 (только в затяжных матчах)

   Читается так: Q-W-E набраны к 3-й минуте, ульта на 3:10, второй уровень
   ульты к 7:00, третий к 11:00. Пик героя совпадает с фазой хай-граунда.

3. ЗОЛОТО НА ПРЕДМЕТЫ
   Цены держит items.py; здесь взяты ориентиры тиров из ABILITY_SPEC §7:
   T1 ботинки ~500, T2 ~2300, T3 ~4200, T4 ~6000. Старт-кит 800 тратится в 0:00.

   К 0:40 на руках: 800 + 2.5*40 = 900 B
   Ботинки (нужно потратить 1300):
     (1300 - 900) / 597 = 0.67 мин  ->  1:20
   Первый крупный предмет, T2 (накопленных трат 3600):
     к 4:00 заработано 900 + 597*3.33 = 2890
     (3600 - 2890) / 937 = 0.76 мин  ->  4:45
   Предмет T3 (трат 7800):
     к 9:00 заработано 2890 + 937*5 = 7575
     (7800 - 7575) / 1100 = 0.20 мин ->  9:12
   Предмет T4 (трат 13800):
     к 12:00 заработано 7575 + 1100*3 = 10875
     (13800 - 10875) / 1100 = 2.66 мин -> 14:40

   Итого к 15-й минуте у кора: ботинки + T2 + T3 + T4 = четыре слота.
   Это ровно тот момент, когда матч и должен заканчиваться.

4. ПРОВЕРКА ДЛИНЫ МАТЧА (иначе всё выше — бумага)
   Броня: снижение = 0.06*A / (1 + 0.06*A).
   Герой 12-го уровня с одним T2: ~110 урона, BAT 1.7, IAS ~160 -> 0.94 атаки/с
   -> ~103 DPS. Волна крипов: 3*21 + 24 = 87 DPS.

   Кулер T1 (1500 HP, 16 брони -> проходит 51%):
     двое героев 7-го уровня (~70 DPS каждый) + волна 87 = 227 * 0.51 = 116 DPS
     1500 / 116 = 13 с чистого битья. С учётом того, что башня отстреливает
     волну и бьёт в ответ 130 за удар, первый Кулер падает на 5:00-6:30.
   Принтер T2 (2000 HP, 18 брони -> 48%):
     трое по 103 DPS + волна 87 = 397 * 0.48 = 191 -> 10 с -> 8:00-9:30.
   Кофемашина T3 (2400 HP, 20 брони -> 45%):
     397 * 0.45 = 181 -> 13 с -> 11:00-12:30, к этому моменту у всех ульта 3.
   Трон (5000 HP, 15 брони -> 53%):
     трое 18-го уровня с тремя предметами (~200 DPS) + мега-волна 150
     = 750 * 0.53 = 397 -> 13 с.

   Складываем: линия до первого Кулера ~5 минут, размен башен T1/T2 3-4 минуты,
   первая выигранная драка 3-на-3 после 11:00 конвертируется в T3 + бараки + трон
   за 1.5-2 минуты. ТИПИЧНЫЙ МАТЧ: 14-16 минут. Быстрый (ранний вайп) - 12.
   Затяжной (два выкупа и Бэкап) - 19-20. Попадает в целевой коридор.

5. ЧТО Я МЕНЯЛ, ЧТОБЫ ПОПАСТЬ В КОРИДОР (числа отвергнутых заходов — посчитанные)

   Заход 1: интервал волны 20 с, опыт крипов как в доте (62/76/88).
     волна 262 XP * 3.0 = 786 * 0.80 = 629 XP/мин -> уровень 6 на 2:28,
     к 4:00 накоплено 2095, фаза B даёт 876 XP/мин -> уровень 18 на 8:58.
     Пик героя на 9-й минуте при матче на 12-20: третий уровень ульты приходит
     раньше, чем команда вообще успевает собраться на пуш, и матч схлопывается
     к 11-13 минутам, не дожив до предметов 4-го тира. Отвергнуто.
     Правка: интервал 25 с, опыт крипов 55/70/85 (-11%) -> уровень 18 на 11:00.

   Заход 2: пассив 3.5 B/с (остальное как в финале).
     к 0:40 на руках 940, фаза A 657 B/мин, фаза B 997 B/мин
     -> T3 на 8:41 вместо 9:12, T4 на 13:55 вместо 14:40.
     Предмет 3-го тира оказывался РАНЬШЕ третьего уровня ульты (11:00) —
     драки на 9-10-й минуте решал магазин, а не прокачка. Плюс пассив — это
     доход за ничегонеделание, а у нас люди уходят на созвон и герой остаётся
     под ботом (DESIGN §3): чем жирнее пассив, тем выгоднее не играть.
     Отвергнуто, пассив опущен до 2.5 B/с.

   Числа выше — третий заход, он и записан в модуль.

6. ДИНАМИЧЕСКАЯ ЭКОНОМИКА: 3 человека против 1 человека
   team_income_multiplier(3) = 3**0.75 / 3 = 2.2795 / 3 = 0.760
   team_income_multiplier(1) = 1.0
   underdog_multiplier(1.0, 3.0) = (3/1)**0.65 = 2.04  (потолок 2.2 не задет)

   Фаза A: соло получает 597 * 1.0 * 2.04 = 1218 B/мин,
           каждый из тройки 597 * 0.760 * 1.0 = 454 B/мин.
   По командам: 1218 против 1362 — численный перевес остался преимуществом,
   но перестал быть автопобедой: их кор фармит вдвое медленнее соло-героя.

   3 человека против 1 бота: own=0.6, enemy=3.0 -> (5.0)**0.65 = 2.85 -> потолок 2.2.
   Потолок нужен: без него бот на 3v1 получал бы x2.85 и превращался в монстра,
   которого ведёт ИИ — это не весело ни одной из сторон.

   ОСТОРОЖНО: underdog по умолчанию множит и опыт тоже (ECONOMY
   ["dynamic_applies_to"]["creep_xp"]). Соло против троих выходит на 18-й
   уровень примерно к 7:00 вместо 11:00. Если на плейтесте это будет читаться
   как «гандикап играет за меня», первым делом выключать надо именно XP-флаги,
   а не трогать экспоненту.
"""


# ==========================================================================
#  11. Самопроверка
# ==========================================================================

_REQUIRED_CREEP_FIELDS = ("hp", "damage", "armor", "magic_resist", "attack_range",
                          "bat", "move_speed", "bounty_gold", "bounty_xp", "vision")
_REQUIRED_BUILDING_FIELDS = ("hp", "damage", "armor", "magic_resist", "attack_range",
                             "bat", "bounty_team_gold", "bounty_killer_gold",
                             "backdoor_protection", "hp_regen")
_REQUIRED_UNIT_FIELDS = ("hp", "damage", "armor", "magic_resist", "attack_range",
                         "bat", "move_speed", "bounty_gold", "bounty_xp", "vision")


def _check_range_pair(pair, what: str, allow_zero: bool = False) -> None:
    assert isinstance(pair, (list, tuple)) and len(pair) == 2, \
        f"{what}: ожидалась пара [min, max], получено {pair!r}"
    lo, hi = pair
    assert lo <= hi, f"{what}: min ({lo}) больше max ({hi})"
    if not allow_zero:
        assert lo > 0, f"{what}: min должен быть > 0, получено {lo}"


def validate() -> None:
    """Проверяет внутреннюю согласованность модуля. AssertionError с текстом."""

    # --- уровни ---------------------------------------------------------
    assert MAX_LEVEL == 25, f"MAX_LEVEL должен быть 25, а не {MAX_LEVEL}"
    assert len(XP_TABLE) == MAX_LEVEL, \
        f"XP_TABLE: {len(XP_TABLE)} записей вместо {MAX_LEVEL}"
    assert XP_TABLE[0] == 0, f"XP_TABLE[0] (1-й уровень) должен быть 0, а не {XP_TABLE[0]}"
    for i in range(1, MAX_LEVEL):
        assert XP_TABLE[i] > XP_TABLE[i - 1], (
            f"XP_TABLE не монотонна: уровень {i + 1} требует {XP_TABLE[i]} XP, "
            f"а уровень {i} — {XP_TABLE[i - 1]}")
    for i in range(2, MAX_LEVEL):
        step_prev = XP_TABLE[i - 1] - XP_TABLE[i - 2]
        step = XP_TABLE[i] - XP_TABLE[i - 1]
        assert step >= step_prev, (
            f"XP_TABLE: шаг до уровня {i + 1} ({step}) меньше шага до "
            f"уровня {i} ({step_prev}) — кривая опыта должна быть выпуклой")

    assert len(RESPAWN_TABLE) == MAX_LEVEL, \
        f"RESPAWN_TABLE: {len(RESPAWN_TABLE)} записей вместо {MAX_LEVEL}"
    for i in range(MAX_LEVEL):
        assert RESPAWN_TABLE[i] > 0, \
            f"RESPAWN_TABLE[{i}]: время возрождения должно быть > 0"
        if i:
            assert RESPAWN_TABLE[i] > RESPAWN_TABLE[i - 1], (
                f"RESPAWN_TABLE не монотонна: уровень {i + 1} возрождается за "
                f"{RESPAWN_TABLE[i]} с, а уровень {i} — за {RESPAWN_TABLE[i - 1]} с")
    assert RESPAWN_TABLE[-1] <= 60.0, (
        f"RESPAWN_TABLE: {RESPAWN_TABLE[-1]} с на 25-м уровне — это дота, "
        f"а не Turbo; в матче на 15 минут одна смерть не должна стоить матча")
    assert xp_to_level(0) == 1 and xp_to_level(XP_TABLE[5]) == 6 \
        and xp_to_level(10 ** 9) == MAX_LEVEL, "xp_to_level считает неверно"

    # --- крипы ----------------------------------------------------------
    for key in ("melee_creep", "ranged_creep", "siege_creep",
                "super_melee", "super_ranged"):
        assert key in CREEPS, f"CREEPS: нет обязательного крипа {key!r}"
    for key, c in CREEPS.items():
        for f in _REQUIRED_CREEP_FIELDS:
            assert f in c, f"CREEPS[{key!r}]: нет поля {f!r}"
        assert c["hp"] > 0, f"CREEPS[{key!r}]: hp должен быть > 0"
        _check_range_pair(c["damage"], f"CREEPS[{key!r}].damage")
        _check_range_pair(c["bounty_gold"], f"CREEPS[{key!r}].bounty_gold")
        assert c["armor"] >= 0, f"CREEPS[{key!r}]: armor не может быть отрицательной"
        assert 0.0 <= c["magic_resist"] < 1.0, \
            f"CREEPS[{key!r}]: magic_resist вне [0, 1): {c['magic_resist']}"
        assert c["attack_range"] > 0, f"CREEPS[{key!r}]: attack_range должен быть > 0"
        assert c["bat"] > 0, f"CREEPS[{key!r}]: bat должен быть > 0"
        assert 100 <= c["move_speed"] <= 550, \
            f"CREEPS[{key!r}]: move_speed {c['move_speed']} вне [100, 550] (consts)"
        assert c["bounty_xp"] > 0, f"CREEPS[{key!r}]: bounty_xp должен быть > 0"
        assert c["vision"] > 0, f"CREEPS[{key!r}]: vision должен быть > 0"

    assert CREEPS["siege_creep"]["building_damage_mult"] > 1.0, \
        "Подрядчик обязан бить строения больнее обычного крипа, иначе он бессмыслен"
    assert CREEPS["super_melee"]["hp"] > CREEPS["melee_creep"]["hp"], \
        "super_melee должен быть крепче обычного Стажёра"
    assert CREEPS["super_ranged"]["hp"] > CREEPS["ranged_creep"]["hp"], \
        "super_ranged должен быть крепче обычного Аналитика"
    assert CREEPS["super_melee"]["bounty_gold"][1] < CREEPS["melee_creep"]["bounty_gold"][1], \
        "мега-крипы не должны кормить проигрывающую команду сильнее обычных"

    assert CREEP_SCALING["interval_sec"] > 0 and CREEP_SCALING["max_steps"] > 0, \
        "CREEP_SCALING: интервал и число шагов должны быть > 0"
    early = creep_stats_at("melee_creep", 0.0)
    late = creep_stats_at("melee_creep", 12 * 60.0)
    assert late["hp"] > early["hp"] and late["damage"][0] > early["damage"][0], \
        "CREEP_SCALING: крипы не усиливаются со временем"
    assert creep_stats_at("melee_creep", 10 ** 6)["upgrade_steps"] == CREEP_SCALING["max_steps"], \
        "CREEP_SCALING: не работает потолок max_steps"

    # --- волны ----------------------------------------------------------
    ws = WAVE_SCHEDULE
    assert ws["interval_sec"] > 0, "WAVE_SCHEDULE: интервал волн должен быть > 0"
    assert ws["interval_sec"] < 30.0, (
        f"WAVE_SCHEDULE: интервал {ws['interval_sec']} с — это не Turbo "
        f"(в доте 30 с, здесь должно быть меньше)")
    assert ws["first_wave_spawn_sec"] > 0, "WAVE_SCHEDULE: первая волна не в 0:00"
    assert sum(ws["composition"].values()) >= 3, "WAVE_SCHEDULE: волна слишком мелкая"
    for unit in ws["composition"]:
        assert unit in CREEPS, f"WAVE_SCHEDULE: неизвестный крип {unit!r}"
    assert ws["siege"]["unit"] in CREEPS, "WAVE_SCHEDULE: неизвестный осадный крип"
    assert ws["siege"]["every_n_waves"] >= 1, "WAVE_SCHEDULE: осадный чаще каждой волны"
    for up in ws["upgrades"]:
        for src, dst in up["replace"].items():
            assert src in CREEPS and dst in CREEPS, \
                f"WAVE_SCHEDULE.upgrades: неизвестная замена {src!r} -> {dst!r}"

    # --- строения -------------------------------------------------------
    for key in ("tower_t1", "tower_t2", "tower_t3", "tower_t4",
                "barracks_melee", "barracks_ranged", "ancient", "fountain"):
        assert key in BUILDINGS, f"BUILDINGS: нет обязательного строения {key!r}"
    for key, b in BUILDINGS.items():
        for f in _REQUIRED_BUILDING_FIELDS:
            assert f in b, f"BUILDINGS[{key!r}]: нет поля {f!r}"
        assert b["hp"] > 0, f"BUILDINGS[{key!r}]: hp должен быть > 0"
        assert b["armor"] >= 0, f"BUILDINGS[{key!r}]: armor не может быть отрицательной"
        assert 0.0 <= b["magic_resist"] < 1.0, \
            f"BUILDINGS[{key!r}]: magic_resist вне [0, 1)"
        assert b["damage"] >= 0, f"BUILDINGS[{key!r}]: damage не может быть < 0"
        assert b["attack_range"] >= 0, f"BUILDINGS[{key!r}]: attack_range не может быть < 0"
        assert b["bat"] > 0, f"BUILDINGS[{key!r}]: bat должен быть > 0"
        assert b["bounty_team_gold"] >= 0 and b["bounty_killer_gold"] >= 0, \
            f"BUILDINGS[{key!r}]: награда не может быть отрицательной"
        assert isinstance(b["backdoor_protection"], bool), \
            f"BUILDINGS[{key!r}]: backdoor_protection должен быть bool"
        assert b["hp_regen"] >= 0, f"BUILDINGS[{key!r}]: hp_regen не может быть < 0"
        # стреляет — значит стреляет: либо и урон, и дальность, либо ни того ни другого
        assert (b["damage"] > 0) == (b["attack_range"] > 0), (
            f"BUILDINGS[{key!r}]: урон {b['damage']} и дальность {b['attack_range']} "
            f"противоречат друг другу")

    towers = ("tower_t1", "tower_t2", "tower_t3", "tower_t4")
    for t in towers:
        b = BUILDINGS[t]
        # «агро на башне — смерть»: герой 6-го уровня (~1200 HP, 2 брони)
        # должен умирать не дольше чем за 12 попаданий
        dmg_after_armor = b["damage"] * (1.0 - 0.06 * 2.0 / (1.0 + 0.06 * 2.0))
        hits = 1200.0 / dmg_after_armor
        assert hits <= 12.0, (
            f"BUILDINGS[{t!r}]: {b['damage']} урона — это {hits:.1f} попаданий "
            f"по герою 6-го уровня. Башня должна бить больно, максимум 12")
        assert b["attack_range"] >= 700, \
            f"BUILDINGS[{t!r}]: дальность башни меньше 700 — под неё будут заходить безнаказанно"
    for a, b in zip(towers, towers[1:]):
        assert BUILDINGS[b]["damage"] >= BUILDINGS[a]["damage"], \
            f"BUILDINGS: {b} бьёт слабее, чем {a} — тиры должны расти"
        assert BUILDINGS[b]["hp"] >= BUILDINGS[a]["hp"], \
            f"BUILDINGS: у {b} меньше HP, чем у {a} — тиры должны расти"
    assert BUILDINGS["ancient"]["hp"] > BUILDINGS["tower_t4"]["hp"], \
        "BUILDINGS: Трон должен быть крепче Турникета"
    assert BUILDINGS["fountain"].get("invulnerable") is True, \
        "BUILDINGS: Кухня (фонтан) обязана быть неуязвимой"
    assert not BUILDINGS["tower_t1"]["backdoor_protection"], \
        "BUILDINGS: у Кулера (T1) не должно быть защиты от бэкдора"
    for key in ("tower_t2", "tower_t3", "tower_t4", "barracks_melee",
                "barracks_ranged", "ancient"):
        assert BUILDINGS[key]["backdoor_protection"], \
            f"BUILDINGS[{key!r}]: должна быть защита от бэкдора"

    # --- лес ------------------------------------------------------------
    for key in ("small", "medium", "large", "ancient", "roshan"):
        assert key in JUNGLE, f"JUNGLE: нет лагеря {key!r}"
    prev_gold = 0.0
    for key in ("small", "medium", "large", "ancient"):
        camp = JUNGLE[key]
        assert camp["respawn_sec"] > 0, f"JUNGLE[{key!r}]: respawn_sec должен быть > 0"
        assert camp["variants"], f"JUNGLE[{key!r}]: нет ни одного состава"
        total_gold = 0.0
        total_xp = 0.0
        for var in camp["variants"]:
            g = 0.0
            x = 0.0
            assert var["units"], f"JUNGLE[{key!r}]/{var['name']}: пустой состав"
            for u in var["units"]:
                for f in _REQUIRED_UNIT_FIELDS:
                    assert f in u, f"JUNGLE[{key!r}]/{u.get('key')}: нет поля {f!r}"
                assert u["count"] >= 1, f"JUNGLE[{key!r}]/{u['key']}: count < 1"
                assert u["hp"] > 0 and u["vision"] > 0 and u["bat"] > 0, \
                    f"JUNGLE[{key!r}]/{u['key']}: hp/vision/bat должны быть > 0"
                assert u["armor"] >= 0, f"JUNGLE[{key!r}]/{u['key']}: armor < 0"
                assert 0.0 <= u["magic_resist"] < 1.0, \
                    f"JUNGLE[{key!r}]/{u['key']}: magic_resist вне [0, 1)"
                assert u["attack_range"] > 0 and u["move_speed"] > 0, \
                    f"JUNGLE[{key!r}]/{u['key']}: attack_range/move_speed должны быть > 0"
                _check_range_pair(u["damage"], f"JUNGLE[{key!r}]/{u['key']}.damage")
                _check_range_pair(u["bounty_gold"], f"JUNGLE[{key!r}]/{u['key']}.bounty_gold")
                assert u["bounty_xp"] > 0, f"JUNGLE[{key!r}]/{u['key']}: bounty_xp <= 0"
                g += sum(u["bounty_gold"]) / 2.0 * u["count"]
                x += u["bounty_xp"] * u["count"]
            lo, hi = camp["bounty_gold_total"]
            assert lo <= g <= hi, (
                f"JUNGLE[{key!r}]/{var['name']}: сумма золота юнитов {g:.0f} "
                f"не попадает в заявленное bounty_gold_total {camp['bounty_gold_total']}")
            total_gold = max(total_gold, g)
            total_xp = max(total_xp, x)
        assert total_gold > prev_gold, (
            f"JUNGLE: лагерь {key!r} даёт {total_gold:.0f} золота — не больше, "
            f"чем предыдущий по размеру ({prev_gold:.0f})")
        prev_gold = total_gold
        assert total_xp > 0

    wave_gold = sum(CREEPS[u]["bounty_gold"][1] * n
                    for u, n in WAVE_SCHEDULE["composition"].items())
    assert JUNGLE["small"]["bounty_gold_total"][1] <= wave_gold, \
        "JUNGLE: мелкий лагерь не должен быть выгоднее целой волны на линии"
    assert JUNGLE["large"]["bounty_gold_total"][0] > wave_gold * 0.9, \
        "JUNGLE: большой лагерь слишком дёшев, в лес никто не пойдёт"

    rosh = JUNGLE["roshan"]
    assert rosh["first_spawn_sec"] > 0, "JUNGLE: Легаси не должен быть доступен с 0:00"
    assert rosh["first_spawn_sec"] <= 0.5 * MATCH_LENGTH_TARGET_MIN[0] * 60.0, (
        f"JUNGLE: Легаси появляется на {rosh['first_spawn_sec'] / 60:.1f}-й минуте — "
        f"в матче на {MATCH_LENGTH_TARGET_MIN[0]:.0f}-{MATCH_LENGTH_TARGET_MIN[1]:.0f} "
        f"минут его просто не успеют убить")
    _check_range_pair(rosh["respawn_sec"], "JUNGLE['roshan'].respawn_sec")
    r_early = legacy_stats_at(rosh["first_spawn_sec"])
    r_late = legacy_stats_at(rosh["first_spawn_sec"] + 600.0)
    assert r_late["hp"] > r_early["hp"], "JUNGLE: Легаси не усиливается со временем"
    assert r_late["damage"][0] > r_early["damage"][0], \
        "JUNGLE: урон Легаси не растёт со временем"
    assert legacy_stats_at(0.0)["hp"] == r_early["hp"], \
        "legacy_stats_at: до первого спавна статы не должны отличаться от базовых"
    assert any(d["key"] == "aegis" for d in rosh["drops"]), \
        "JUNGLE: с Легаси обязан падать Бэкап (аегис)"
    assert JUNGLE["ancient"]["variants"][0]["units"][0]["magic_resist"] >= 0.5, \
        "JUNGLE: древние (Безопасники) должны иметь высокий магсопр"
    assert JUNGLE_RULES["spawn_tick_sec"] > JUNGLE_RULES["stack_window_sec"] > 0, \
        "JUNGLE_RULES: окно стака должно быть меньше тика респавна и больше нуля"

    # --- руны -----------------------------------------------------------
    for rune_key in ("double_damage", "haste", "regeneration", "illusion",
                     "invisibility", "arcane"):
        assert rune_key in RUNES["power"]["types"], \
            f"RUNES: нет руны силы {rune_key!r}"
        r = RUNES["power"]["types"][rune_key]
        assert r["duration"] > 0, f"RUNES[{rune_key!r}]: длительность должна быть > 0"
        assert r.get("name"), f"RUNES[{rune_key!r}]: нет русского имени"
    assert RUNES["power"]["first_spawn_sec"] > 0, "RUNES: руны силы с 0:00 — это не дота"
    assert RUNES["power"]["interval_sec"] > 0 and RUNES["bounty"]["interval_sec"] > 0, \
        "RUNES: интервал спавна должен быть > 0"
    assert RUNES["power"]["spots"] >= 2 and RUNES["bounty"]["spots"] >= 2, \
        "RUNES: точек спавна слишком мало"
    assert RUNES["bounty"]["name"] == "Премия", "RUNES: руна награды называется «Премия»"
    b0 = bounty_rune_reward(0.0)["gold"]
    b10 = bounty_rune_reward(600.0)["gold"]
    assert b10 > b0 > 0, "RUNES: Премия должна дорожать со временем"
    assert b10 < CREEPS["melee_creep"]["bounty_gold"][0] * 6, (
        f"RUNES: Премия на 10-й минуте даёт {b10:.0f} золота — это больше волны, "
        f"руна не должна заменять фарм")

    # --- экономика ------------------------------------------------------
    assert ECONOMY["starting_gold"] > 0, "ECONOMY: стартовое золото должно быть > 0"
    assert ECONOMY["passive_gold_per_sec"] > 0, "ECONOMY: пассивный доход должен быть > 0"
    assert ECONOMY["passive_gold_per_sec"] * 60.0 >= 100.0, (
        "ECONOMY: пассив меньше 100 ₿/мин — это ниже обычной доты, а у нас Turbo")
    assert 0.0 < ECONOMY["assist_gold_share"] <= 1.0, \
        "ECONOMY: доля ассиста вне (0, 1]"
    assert hero_kill_gold(1) > 0, "ECONOMY: убийство героя 1-го уровня ничего не даёт"
    assert hero_kill_gold(25) > hero_kill_gold(5), \
        "ECONOMY: награда за героя должна расти с уровнем жертвы"
    assert hero_kill_gold(10, victim_streak=5) > hero_kill_gold(10), \
        "ECONOMY: за серию убийств должна быть добавка (шатдаун)"
    assert hero_kill_gold(10, victim_streak=99) == hero_kill_gold(10, victim_streak=10), \
        "ECONOMY: шатдаун должен упираться в потолок таблицы, а не расти бесконечно"
    assert hero_kill_xp(25) > hero_kill_xp(1) > 0, \
        "ECONOMY: опыт за героя должен расти с уровнем"
    assert hero_kill_xp(18) < XP_TABLE[17] - XP_TABLE[16], (
        "ECONOMY: одно убийство героя даёт больше уровня — так ганк решает матч")
    for i in range(1, len(STREAK_BOUNTY_GOLD)):
        assert STREAK_BOUNTY_GOLD[i] >= STREAK_BOUNTY_GOLD[i - 1], \
            "ECONOMY: таблица серий немонотонна"
    assert death_gold_penalty(18, 0.0) == 0.0, \
        "ECONOMY: в первую минуту смерть не должна штрафовать золотом"
    assert 0 < death_gold_penalty(18) <= ECONOMY["death"]["gold_loss_cap"], \
        "ECONOMY: штраф за смерть вне разумных границ"
    assert death_gold_penalty(25) >= death_gold_penalty(5), \
        "ECONOMY: штраф за смерть должен расти с уровнем"
    bb_early = buyback_cost(6, 180.0)
    bb_late = buyback_cost(20, 900.0)
    assert 0 < bb_early < bb_late, \
        "ECONOMY: выкуп должен дорожать с уровнем и временем матча"
    assert bb_late < 2500.0, (
        f"ECONOMY: выкуп на 15-й минуте стоит {bb_late:.0f} ₿ — в Turbo это "
        f"недостижимо, механика выкупа окажется мёртвой")
    assert ECONOMY["buyback"]["cooldown_sec"] < MATCH_LENGTH_TARGET_MIN[1] * 60.0, \
        "ECONOMY: кулдаун выкупа длиннее матча — это тот же мёртвый выкуп"

    # --- динамическая экономика (граничные случаи) ----------------------
    assert DYNAMIC_ECONOMY_ENABLED is True, \
        "DYNAMIC_ECONOMY_ENABLED выключен — проверки ниже написаны для включённого"
    assert HUMAN_POWER == 1.0 and BOT_POWER == 0.6, \
        "HUMAN_POWER/BOT_POWER должны быть 1.0 и 0.6 (DESIGN §4)"
    assert 0 < BOT_POWER < HUMAN_POWER, "Бот должен считаться слабее человека"
    assert UNDERDOG_MULT_CAP == 2.2, "UNDERDOG_MULT_CAP должен быть 2.2 (DESIGN §4)"

    assert team_income_multiplier(0) == 1.0, \
        "team_income_multiplier(0): пустая команда не должна ломать экономику (ждём 1.0)"
    assert team_income_multiplier(-3) == 1.0, \
        "team_income_multiplier(-3): мусорный вход должен давать 1.0, а не исключение"
    assert team_income_multiplier(1) == 1.0, \
        "team_income_multiplier(1): соло-герой не штрафуется"
    assert abs(team_income_multiplier(2) - 0.8409) < 0.001, \
        f"team_income_multiplier(2) = {team_income_multiplier(2):.4f}, ждали 0.8409"
    assert abs(team_income_multiplier(3) - 0.7598) < 0.001, \
        f"team_income_multiplier(3) = {team_income_multiplier(3):.4f}, ждали 0.7598"
    prev = 1.0
    for n in range(1, 8):
        cur = team_income_multiplier(n)
        assert 0.0 < cur <= 1.0, f"team_income_multiplier({n}) = {cur} вне (0, 1]"
        assert cur <= prev, (
            f"team_income_multiplier немонотонна: N={n} даёт {cur:.4f}, "
            f"а N={n - 1} давало {prev:.4f}")
        prev = cur
    # суммарный доход команды всё-таки растёт с численностью
    for n in range(1, 7):
        assert n * team_income_multiplier(n) < (n + 1) * team_income_multiplier(n + 1), \
            "Суммарный доход команды должен расти с численностью, пусть и сублинейно"

    assert underdog_multiplier(1.0, 1.0) == 1.0, \
        "underdog_multiplier: при равной силе множитель обязан быть ровно 1.0"
    assert underdog_multiplier(3.0, 1.0) == 1.0, \
        "underdog_multiplier: ведущую команду не штрафуем (ждём 1.0)"
    assert underdog_multiplier(0.0, 0.0) == 1.0, \
        "underdog_multiplier(0, 0): героев нет ни у кого — ждём 1.0, а не деление на ноль"
    assert underdog_multiplier(0.0, 3.0) == UNDERDOG_MULT_CAP, \
        "underdog_multiplier(0, 3): деления на ноль быть не должно, ждём потолок"
    assert underdog_multiplier(1.0, 0.0) == 1.0, \
        "underdog_multiplier(1, 0): сравнивать не с кем — ждём 1.0"
    assert underdog_multiplier(-1.0, 3.0) == UNDERDOG_MULT_CAP, \
        "underdog_multiplier: отрицательная сила не должна ломать формулу"
    assert abs(underdog_multiplier(1.0, 3.0) - 2.042) < 0.01, (
        f"underdog_multiplier(1, 3) = {underdog_multiplier(1.0, 3.0):.3f}, "
        f"ждали (3)**0.65 = 2.042")
    assert underdog_multiplier(BOT_POWER, 3.0 * HUMAN_POWER) == UNDERDOG_MULT_CAP, \
        "underdog_multiplier: 3 человека против одного бота должны упереться в потолок"
    for own in (0.6, 1.0, 1.6, 2.0, 3.0):
        for enemy in (0.0, 0.6, 1.0, 3.0, 30.0):
            m = underdog_multiplier(own, enemy)
            assert 1.0 <= m <= UNDERDOG_MULT_CAP, (
                f"underdog_multiplier({own}, {enemy}) = {m} вышел за "
                f"[1.0, {UNDERDOG_MULT_CAP}]")

    # --- темп: расчёт из ANALYSIS должен сходиться -----------------------
    pace = estimate_pacing()
    for name, expected in PACING_TARGETS.items():
        assert name in pace, f"estimate_pacing(): не посчитан {name}"
        assert abs(pace[name] - expected) < 0.1, (
            f"Темп разъехался с ANALYSIS: {name} = {pace[name]:.2f} мин, "
            f"а в расчёте записано {expected:.2f} мин")
    lo, hi = MATCH_LENGTH_TARGET_MIN
    assert pace["level_18_min"] < hi * 0.6, (
        f"Уровень 18 приходит на {pace['level_18_min']:.1f}-й минуте — слишком поздно "
        f"для матча на {lo:.0f}-{hi:.0f} минут, третий уровень ульты не успеет сыграть")
    assert pace["level_18_min"] > lo * 0.6, (
        f"Уровень 18 на {pace['level_18_min']:.1f}-й минуте — слишком рано, "
        f"прокачка обесценится")
    assert lo <= pace["level_25_min"] <= hi, (
        f"25-й уровень на {pace['level_25_min']:.1f}-й минуте — он должен быть "
        f"редкой наградой за затяжной матч, т.е. внутри [{lo:.0f}, {hi:.0f}]")
    assert pace["t2_min"] < 6.0, (
        f"Первый крупный предмет на {pace['t2_min']:.1f}-й минуте — для Turbo это долго")
    assert pace["t3_min"] < pace["t4_min"] <= hi, (
        f"Предмет 4-го тира на {pace['t4_min']:.1f}-й минуте не попадает в матч")
    assert pace["boots_min"] < 2.0, "Ботинки должны покупаться на первых минутах"

    assert isinstance(ANALYSIS, str) and len(ANALYSIS) > 1000, \
        "ANALYSIS: расчёт должен быть расчётом, а не заглушкой"


if __name__ == "__main__":
    validate()
    print(ANALYSIS)
