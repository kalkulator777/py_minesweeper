# -*- coding: utf-8 -*-
"""Ростер героев «Офисной Доты» — чистые данные, без движка.

Модуль намеренно не импортирует ничего из ``office_dota.*`` и вообще ничего,
кроме stdlib (а фактически — вообще ничего). Здесь только таблица ``HEROES``,
список пожеланий к движку ``ENGINE_REQUESTS`` и самопроверка ``validate()``.

Контракт — ``docs/ABILITY_SPEC.md``:
  §1 форма способности, §2 ``targeting``, §3 разрешённые ``op``,
  §4 ``target`` внутри операции, §5 разрешённые ключи ``stats``.

Баланс — Turbo (``docs/DESIGN.md`` §2, ``ABILITY_SPEC.md`` §8.5):
кулдауны ≈ ×0.7 от обычной Dota 2, урон ≈ ×1.15, матч 12–20 минут,
ориентир — уровни героя 1–18 (25-й уровень встречается редко).

Ростер (8 героев), обязательные архетипы покрыты:

  ключ           герой          прототип Dota 2   архетип
  -------------  -------------  ----------------  -----------------------------
  sysadmin       Сисадмин       Pudge             оффлейн-танк / инициатор
  senior         Сеньор         Juggernaut        керри поздней игры
  analyst        Аналитик       Zeus              мидер-нюкер
  hr             Эйчар          Lion              хард-саппорт с контролем
  scrum_master   Скрам-мастер   Dazzle            саппорт-лекарь
  security       Безопасник     Bounty Hunter     убийца / ганкер
  accountant     Бухгалтер      Leshrac           пушер
  junior         Джуниор        Phantom Lancer    необычная механика (иллюзии)

Одно осознанное отступление от «чистого» прототипа: у Сисадмина ``E`` —
это Berserker's Call от Axe, а не Flesh Heap. Связка «крюк + насмешка»
читается любым дотером мгновенно и даёт инициатору второй заход,
а офисное «Код-ревью» просилось в ростер само.
"""

# --- служебные множества для validate(); публичная структура тут одна: HEROES ---

_ALLOWED_OPS = frozenset({
    # урон и лечение
    "damage", "heal", "dot", "execute", "lifesteal_burst",
    # контроль
    "stun", "slow", "silence", "root", "disarm", "hex", "taunt", "purge",
    # защита и баффы
    "shield", "invulnerable", "magic_immune", "invisible", "cheat_death",
    "stat_buff",
    # перемещение
    "blink", "pull", "push", "leap",
    # формы доставки
    "projectile", "area", "aura", "channel", "delayed", "global",
    # пассивки и модификаторы атаки
    "passive_stats", "proc_attack", "crit", "bash", "evasion", "lifesteal",
    "cleave", "on_kill", "on_take_damage",
    # призыв
    "summon", "illusion",
    # добавлено движком после первого прохода ростера (см. ENGINE_REQUESTS)
    "chain", "true_sight", "mana_burn", "restore_mana", "grant_gold", "grant_xp",
    "cyclone", "ghost",
})

_ALLOWED_TARGETING = frozenset({
    "none", "point", "unit_enemy", "unit_ally", "unit_any",
    "vector", "toggle", "passive", "channel",
})

_ALLOWED_TARGET = frozenset({"hit", "caster", "allies_in_radius", "enemies_in_radius"})
_ALLOWED_DTYPE = frozenset({"physical", "magical", "pure"})
_ALLOWED_FILTER = frozenset({"enemy", "ally", "all", "creeps", "buildings", "enemy_all"})
_ALLOWED_STYPE = frozenset({"all", "magical", "physical"})
_ALLOWED_BLINK_TO = frozenset({"point", "target", "behind_target"})
_ALLOWED_PURGE = frozenset({"basic", "strong"})
_ALLOWED_PRIMARY = frozenset({"str", "agi", "int", "all"})
_ALLOWED_ATTACK_TYPE = frozenset({"melee", "ranged"})
_ALLOWED_HOTKEYS = ("Q", "W", "E", "R")

_ALLOWED_STATS = frozenset({
    "str", "agi", "int", "all_stats",
    "hp", "mana", "max_hp_pct", "max_mana_pct",
    "hp_regen", "mana_regen", "hp_regen_pct", "mana_regen_pct",
    "damage", "attack_speed", "attack_range", "bat_pct",
    "armor", "magic_resist", "status_resist", "evasion",
    "move_speed", "move_speed_pct",
    "spell_amp", "cooldown_reduction",
    "damage_taken_pct",
    "vision_day", "vision_night",
})

_ALLOWED_ROLES = frozenset({
    "safelane", "mid", "offlane", "support", "hard_support",
    "roamer", "pusher", "jungle",
})

# level_req жёстко задан спецификацией (§1)
_LEVEL_REQ_NORMAL = [1, 3, 5, 7]
_LEVEL_REQ_ULT = [6, 12, 18]

# Ключи, значение которых — список вложенных эффектов, а не список по уровням.
_EFFECT_LIST_KEYS = frozenset({
    "effects", "on_hit", "on_tick", "on_kill", "passives",
    "on_death_effects",      # метка платит, когда носитель умирает (Track)
})


HEROES: dict[str, dict] = {

    # =====================================================================
    # 1. СИСАДМИН — Pudge — оффлейн-танк / инициатор
    # =====================================================================
    "sysadmin": {
        "key": "sysadmin",
        "name": "Сисадмин",
        "title": "Хранитель серверной",
        "archetype": "Инициатор/Танк",
        "prototype": "Pudge",
        "primary": "str",
        "attack_type": "melee",
        "attack_range": 150,
        "projectile_speed": 0,
        "bat": 1.7,
        "base_str": 27, "str_gain": 3.6,
        "base_agi": 14, "agi_gain": 1.5,
        "base_int": 14, "int_gain": 1.6,
        "base_damage": [29, 35],
        "base_armor": 2.0,
        "base_hp_regen": 0.75,
        "base_mana_regen": 0.9,
        "move_speed": 285,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 2,
        "roles": ["offlane", "support"],
        "lore": "Двадцать лет в серверной. Знает, что упало, ещё до алерта — и кто это уронил.",
        "abilities": [
            {   # прототип: Pudge — Meat Hook
                "key": "sysadmin_patch_cord",
                "name": "Патч-корд",
                "hotkey": "Q",
                "desc": "Швыряет в точку витую пару. Первый, кого зацепило, "
                        "получает чистый урон и едет к Сисадмину в серверную.",
                "targeting": "point",
                "cast_range": 1100,
                "cast_point": 0.3,
                "cast_backswing": 0.5,
                "cooldown": [10, 9, 8, 7],
                "mana_cost": [110, 120, 130, 140],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": True,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "projectile", "speed": 1650, "radius": 100, "pierce": False,
                     "max_dist": 1100, "on_hit": [
                         {"op": "damage", "dtype": "pure",
                          "amount": [110, 200, 290, 380], "target": "hit"},
                         {"op": "pull", "speed": 1650, "to": "caster"},
                     ]},
                ],
            },
            {   # прототип: Pudge — Rot
                "key": "sysadmin_server_heat",
                "name": "Духота в серверной",
                "hotkey": "W",
                "desc": "Включает всё разом: +45 °C и запах горячей пыли. "
                        "Каждую секунду жарит всех вокруг, включая самого Сисадмина, "
                        "и замедляет врагов. Пока включено — капает мана.",
                "targeting": "toggle",
                "toggle_interval": 1.0,
                "cast_range": 0,
                "cast_point": 0.0,
                "cast_backswing": 0.0,
                "cooldown": [0, 0, 0, 0],
                "mana_cost": [6, 9, 12, 15],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 255,
                "effects": [
                    {"op": "area", "radius": 255, "filter": "enemy", "max_targets": 0,
                     "effects": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [40, 70, 100, 130], "target": "hit"},
                         {"op": "slow",
                          "move_pct": [-14, -20, -26, -32],
                          "attack_speed": [0, 0, 0, 0], "duration": 1.1, "target": "hit"},
                     ]},
                    {"op": "damage", "dtype": "pure",
                     "amount": [20, 35, 50, 65], "target": "caster"},
                ],
            },
            {   # прототип: Axe — Berserker's Call (осознанная замена Flesh Heap)
                "key": "sysadmin_code_review",
                "name": "Код-ревью",
                "hotkey": "E",
                "desc": "Открывает ваш пулл-реквест на большом экране. "
                        "Все враги рядом обязаны смотреть только на Сисадмина, "
                        "а он на это время обрастает бронёй.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.3,
                "cast_backswing": 0.5,
                "cooldown": [12, 10, 9, 8],
                "mana_cost": [80, 90, 100, 110],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": True,
                "dispellable": False,
                "aoe_radius": 320,
                "effects": [
                    {"op": "taunt", "duration": [1.8, 2.3, 2.8, 3.3], "radius": 320},
                    {"op": "stat_buff", "stats": {"armor": [12, 14, 16, 18]},
                     "duration": [1.8, 2.3, 2.8, 3.3], "target": "caster"},
                ],
            },
            {   # прототип: Pudge — Dismember
                "key": "sysadmin_reboot",
                "name": "Внеплановая перезагрузка",
                "hotkey": "R",
                "desc": "Держит цель за шиворот и по одному гасит её сервисы. "
                        "Канал 3 с: чистый урон цели и лечение Сисадмину. "
                        "Сорвали канал — цель отпускает.",
                "targeting": "unit_enemy",
                "cast_range": 200,
                "cast_point": 0.3,
                "cast_backswing": 0.3,
                "cooldown": [21, 17, 14],
                "mana_cost": [100, 140, 180],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    # bound_to_channel: стан живёт ровно столько, сколько держится
                    # канал. Прервали — цель отпускает тем же тиком, а не стоит
                    # оглушённой все 3 с при выключенной способности.
                    {"op": "stun", "duration": [3.0, 3.0, 3.0], "target": "hit",
                     "bound_to_channel": True},
                    {"op": "channel", "duration": [3.0, 3.0, 3.0], "interval": 0.5,
                     "break_on_move": True, "on_tick": [
                         {"op": "damage", "dtype": "pure",
                          "amount": [35, 52, 69], "target": "hit"},
                         {"op": "heal", "amount": [22, 33, 44], "target": "caster"},
                     ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 2. СЕНЬОР — Juggernaut — керри поздней игры
    # =====================================================================
    "senior": {
        "key": "senior",
        "name": "Сеньор",
        "title": "Последний, кто уходит с работы",
        "archetype": "Керри/Боец",
        "prototype": "Juggernaut",
        "primary": "agi",
        "attack_type": "melee",
        "attack_range": 150,
        "projectile_speed": 0,
        "bat": 1.6,
        "base_str": 21, "str_gain": 2.4,
        "base_agi": 26, "agi_gain": 3.4,
        "base_int": 16, "int_gain": 1.6,
        "base_damage": [24, 32],
        "base_armor": 2.5,
        "base_hp_regen": 0.5,
        "base_mana_regen": 0.9,
        "move_speed": 305,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 1,
        "roles": ["safelane", "mid"],
        "lore": "Ничего не объясняет. Просто открывает ноутбук — и прод снова живой.",
        "abilities": [
            {   # прототип: Juggernaut — Blade Fury
                "key": "senior_incident_review",
                "name": "Разбор инцидента",
                "hotkey": "Q",
                "desc": "3 секунды крутится по опенспейсу и раздаёт всем вокруг. "
                        "Пока крутится — магия его не берёт.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.1,
                "cast_backswing": 0.3,
                "cooldown": [21, 18, 15, 13],
                "mana_cost": [100, 100, 100, 100],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 250,
                "effects": [
                    {"op": "magic_immune", "duration": 3.0},
                    {"op": "channel", "duration": 3.0, "interval": 0.5,
                     "break_on_move": False, "on_tick": [
                         {"op": "area", "radius": 250, "filter": "enemy", "max_targets": 0,
                          "effects": [
                              {"op": "damage", "dtype": "magical",
                               "amount": [46, 63, 80, 98], "target": "hit"},
                          ]},
                     ]},
                ],
            },
            {   # прототип: Juggernaut — Healing Ward
                "key": "senior_pair_programming",
                "name": "Парное программирование",
                "hotkey": "W",
                "desc": "Садится рядом и объясняет. Союзники вокруг сразу приходят "
                        "в себя и ещё 8 секунд регенерируют процент от максимума HP.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.2,
                "cast_backswing": 0.4,
                "cooldown": [40, 34, 28, 22],
                "mana_cost": [120, 120, 120, 120],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 600,
                "effects": [
                    {"op": "area", "radius": 600, "filter": "ally", "max_targets": 0,
                     "effects": [
                         {"op": "heal", "amount": [90, 140, 190, 240], "target": "hit"},
                         {"op": "stat_buff",
                          "stats": {"hp_regen_pct": [2.0, 2.6, 3.2, 3.8]},
                          "duration": 8.0, "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Juggernaut — Blade Dance
                "key": "senior_muscle_memory",
                "name": "Мышечная память",
                "hotkey": "E",
                "desc": "Пальцы помнят все хоткеи. Шанс нанести критический удар.",
                "targeting": "passive",
                "cast_range": 0,
                "cast_point": 0.0,
                "cast_backswing": 0.0,
                "cooldown": [0, 0, 0, 0],
                "mana_cost": [0, 0, 0, 0],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "crit", "chance": [17, 22, 27, 32],
                     "mult": [1.9, 2.0, 2.1, 2.2]},
                ],
            },
            {   # прототип: Juggernaut — Omnislash
                "key": "senior_friday_deploy",
                "name": "Залил в прод в пятницу",
                "hotkey": "R",
                "desc": "Прыгает в цель и несколько секунд правит всё подряд, "
                        "пока неуязвим. Ничего не объясняет, всё чинит.",
                "targeting": "unit_enemy",
                "cast_range": 400,
                "cast_point": 0.2,
                "cast_backswing": 0.5,
                "cooldown": [90, 75, 60],
                "mana_cost": [200, 275, 350],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 425,
                "effects": [
                    {"op": "blink", "max_dist": 400, "to": "target"},
                    {"op": "invulnerable", "duration": [3.0, 3.7, 4.4]},
                    {"op": "channel", "duration": [3.0, 3.7, 4.4], "interval": 0.4,
                     "break_on_move": False, "on_tick": [
                         {"op": "area", "radius": 425, "filter": "enemy", "max_targets": 1,
                          "effects": [
                              {"op": "blink", "max_dist": 425, "to": "target"},
                              {"op": "damage", "dtype": "physical",
                               "amount": [70, 100, 130], "target": "hit"},
                          ]},
                     ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 3. АНАЛИТИК — Zeus — мидер-нюкер
    # =====================================================================
    "analyst": {
        "key": "analyst",
        "name": "Аналитик",
        "title": "Всё уже в дашборде",
        "archetype": "Нюкер/Мидер",
        "prototype": "Zeus",
        "primary": "int",
        "attack_type": "ranged",
        "attack_range": 600,
        "projectile_speed": 1100,
        "bat": 1.7,
        "base_str": 20, "str_gain": 2.2,
        "base_agi": 11, "agi_gain": 1.2,
        "base_int": 25, "int_gain": 3.5,
        "base_damage": [22, 30],
        "base_armor": 0.5,
        "base_hp_regen": 0.25,
        "base_mana_regen": 1.0,
        "move_speed": 295,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 1,
        "roles": ["mid", "support"],
        "lore": "Не спорит. Открывает дашборд — и спорить становится не с чем.",
        "abilities": [
            {   # прототип: Zeus — Arc Lightning
                "key": "analyst_metrics_roast",
                "name": "Разнос по метрикам",
                "hotkey": "Q",
                "desc": "Дешёвый и быстрый разряд цифр. Перескакивает с одного "
                        "виноватого на следующего, слабея с каждым прыжком.",
                "targeting": "unit_enemy",
                "cast_range": 800,
                "cast_point": 0.15,
                "cast_backswing": 0.4,
                "cooldown": [1.5, 1.4, 1.3, 1.2],
                "mana_cost": [55, 60, 65, 70],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "chain", "jumps": [4, 5, 6, 7], "radius": 500, "decay": 0.85,
                     "delay": 0.2, "filter": "enemy", "effects": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [65, 90, 115, 140], "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Zeus — Lightning Bolt
                "key": "analyst_dashboard",
                "name": "Дашборд",
                "hotkey": "W",
                "desc": "Выкатывает цифру, от которой цель на мгновение столбенеет. "
                        "Заодно подсвечивает всех, кто прятался в этом квадрате.",
                "targeting": "unit_enemy",
                "cast_range": 750,
                "cast_point": 0.3,
                "cast_backswing": 0.5,
                "cooldown": [5.0, 4.6, 4.2, 3.8],
                "mana_cost": [100, 110, 120, 130],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "damage", "dtype": "magical",
                     "amount": [120, 185, 250, 315], "target": "hit"},
                    {"op": "stun", "duration": 0.4, "target": "hit"},
                    {"op": "true_sight", "duration": 5.0, "radius": 700, "target": "hit"},
                ],
            },
            {   # прототип: Zeus — Heavenly Jump
                "key": "analyst_chart_spike",
                "name": "Скачок на графике",
                "hotkey": "E",
                "desc": "Резко прыгает в точку. Все, кто оказался рядом с местом "
                        "приземления, получают урон и вязнут.",
                "targeting": "point",
                "cast_range": 500,
                "cast_point": 0.1,
                "cast_backswing": 0.3,
                "cooldown": [21, 18, 15, 12],
                "mana_cost": [90, 100, 110, 120],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 400,
                "effects": [
                    {"op": "leap", "distance": 500, "duration": 0.4},
                    {"op": "area", "radius": 400, "filter": "enemy", "max_targets": 0,
                     "effects": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [70, 110, 150, 190], "target": "hit"},
                         {"op": "slow",
                          "move_pct": [-25, -30, -35, -40],
                          "attack_speed": [-25, -30, -35, -40],
                          "duration": 2.5, "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Zeus — Thundergod's Wrath
                "key": "analyst_quarterly_report",
                "name": "Квартальный отчёт",
                "hotkey": "R",
                "desc": "Рассылает итоги квартала. Каждый враг на карте получает "
                        "магический урон — где бы он ни прятался.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.4,
                "cast_backswing": 0.6,
                "cooldown": [68, 60, 52],
                "mana_cost": [200, 300, 400],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "global", "filter": "enemy", "effects": [
                        {"op": "damage", "dtype": "magical",
                         "amount": [190, 290, 390], "target": "hit"},
                        {"op": "true_sight", "duration": 5.0, "radius": 600,
                         "target": "hit"},
                    ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 4. ЭЙЧАР — Lion — хард-саппорт с контролем
    # =====================================================================
    "hr": {
        "key": "hr",
        "name": "Эйчар",
        "title": "Отдел по работе с людьми",
        "archetype": "Хард-саппорт/Дизейблер",
        "prototype": "Lion",
        "primary": "int",
        "attack_type": "ranged",
        "attack_range": 600,
        "projectile_speed": 1200,
        "bat": 1.7,
        "base_str": 18, "str_gain": 2.2,
        "base_agi": 15, "agi_gain": 1.6,
        "base_int": 23, "int_gain": 3.0,
        "base_damage": [21, 29],
        "base_armor": 1.0,
        "base_hp_regen": 0.25,
        "base_mana_regen": 0.9,
        "move_speed": 290,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 2,
        "roles": ["hard_support", "roamer"],
        "lore": "«Есть минутка?» — последнее, что слышат в этой компании.",
        "abilities": [
            {   # прототип: Lion — Earth Spike
                "key": "hr_standup",
                "name": "Стендап",
                "hotkey": "Q",
                "desc": "Объявляет пятиминутку. Все на линии обязаны встать "
                        "и молча стоять. Пятиминутка, как обычно, не пятиминутка.",
                "targeting": "point",
                "cast_range": 600,
                "cast_point": 0.3,
                "cast_backswing": 0.6,
                "cooldown": [8, 7, 6, 5],
                "mana_cost": [100, 115, 130, 145],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 125,
                "effects": [
                    {"op": "projectile", "speed": 1600, "radius": 125, "pierce": True,
                     "max_dist": 600, "on_hit": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [70, 140, 210, 280], "target": "hit"},
                         {"op": "stun", "duration": [1.6, 1.8, 2.0, 2.2], "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Lion — Hex
                "key": "hr_interview",
                "name": "Собеседование",
                "hotkey": "W",
                "desc": "Зовёт цель «просто пообщаться». Цель превращается "
                        "в кандидата: ни ударить, ни скастовать, ни уйти.",
                "targeting": "unit_enemy",
                "cast_range": 550,
                "cast_point": 0.15,
                "cast_backswing": 0.5,
                "cooldown": [21, 17, 13, 9],
                "mana_cost": [110, 140, 170, 200],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "hex", "duration": [1.5, 2.0, 2.5, 3.0], "target": "hit"},
                ],
            },
            {   # прототип: Lion — Mana Drain
                "key": "hr_burnout",
                "name": "Выгорание",
                "hotkey": "E",
                "desc": "Тянет из цели последние силы: выжигает ману — тем больше, "
                        "чем умнее жертва, — превращает её в урон и переливает себе. "
                        "Цель при этом еле переставляет ноги.",
                "targeting": "channel",
                "cast_range": 600,
                "cast_point": 0.1,
                "cast_backswing": 0.3,
                "cooldown": [12, 10, 8, 6],
                "mana_cost": [0, 0, 0, 0],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "channel", "duration": 5.0, "interval": 0.5,
                     "break_on_move": True, "on_tick": [
                         {"op": "mana_burn", "per_int": [0.25, 0.4, 0.55, 0.7],
                          "damage_per_mana": 0.8, "target": "hit"},
                         {"op": "restore_mana", "amount": [10, 15, 20, 25], "pct": 0,
                          "target": "caster"},
                         {"op": "slow",
                          "move_pct": [-20, -20, -20, -20],
                          "attack_speed": [0, 0, 0, 0], "duration": 0.7, "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Lion — Finger of Death
                "key": "hr_dismissal",
                "name": "Увольнение",
                "hotkey": "R",
                "desc": "Подписывает приказ. Огромный магический урон, "
                        "а того, кто и так еле держался, увольняют сразу. "
                        "Выходное пособие оседает в бюджете отдела.",
                "targeting": "unit_enemy",
                "cast_range": 700,
                "cast_point": 0.3,
                "cast_backswing": 0.7,
                "cooldown": [56, 42, 28],
                "mana_cost": [200, 420, 650],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "damage", "dtype": "magical",
                     "amount": [690, 835, 980], "target": "hit"},
                    {"op": "execute", "hp_threshold": [125, 165, 200], "on_kill": [
                        {"op": "grant_gold", "amount": [150, 225, 300], "target": "caster"},
                    ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 5. СКРАМ-МАСТЕР — Dazzle — саппорт-лекарь
    # =====================================================================
    "scrum_master": {
        "key": "scrum_master",
        "name": "Скрам-мастер",
        "title": "Хранитель спринта",
        "archetype": "Саппорт/Лекарь",
        "prototype": "Dazzle",
        "primary": "int",
        "attack_type": "ranged",
        "attack_range": 550,
        "projectile_speed": 900,
        "bat": 1.7,
        "base_str": 20, "str_gain": 2.4,
        "base_agi": 20, "agi_gain": 2.0,
        "base_int": 23, "int_gain": 2.9,
        "base_damage": [20, 28],
        "base_armor": 1.5,
        "base_hp_regen": 0.5,
        "base_mana_regen": 0.9,
        "move_speed": 300,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 2,
        "roles": ["support", "hard_support"],
        "lore": "Не даёт спринту умереть. Иногда — буквально.",
        "abilities": [
            {   # прототип: Dazzle — Shadow Wave
                "key": "sm_retro",
                "name": "Ретроспектива",
                "hotkey": "Q",
                "desc": "Проговаривает, что пошло не так. Волна скачет по союзникам "
                        "и лечит каждого, а врагам рядом с ними прилетает столько же урона.",
                "targeting": "unit_ally",
                "cast_range": 600,
                "cast_point": 0.2,
                "cast_backswing": 0.4,
                "cooldown": [7, 6, 5, 4],
                "mana_cost": [90, 105, 120, 135],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 600,
                "effects": [
                    # decay 1.0 — осознанно, а не «чтобы не разбираться»:
                    # 1) у Shadow Wave в доте затухания нет, волна лечит всех
                    #    одинаково — прототип требует ровно этого (§8.4);
                    # 2) движок масштабирует только amount/dps верхнего уровня,
                    #    а урон тут лежит во вложенном area — при decay < 1
                    #    хил бы затухал, а урон нет, и обещание «лечит ровно
                    #    столько, сколько бьёт» развалилось бы.
                    {"op": "chain", "jumps": [3, 4, 5, 6], "radius": 500, "decay": 1.0,
                     "delay": 0.15, "filter": "ally", "effects": [
                         {"op": "heal", "amount": [100, 155, 210, 265], "target": "hit"},
                         {"op": "area", "radius": 225, "filter": "enemy", "max_targets": 0,
                          "effects": [
                              {"op": "damage", "dtype": "magical",
                               "amount": [100, 155, 210, 265], "target": "hit"},
                          ]},
                     ]},
                ],
            },
            {   # прототип: Dazzle — Shallow Grave
                "key": "sm_sprint_extension",
                "name": "Продление спринта",
                "hotkey": "W",
                "desc": "Спринт не провален, он продлён. Союзник не может умереть — "
                        "HP не опускается ниже единицы.",
                "targeting": "unit_ally",
                "cast_range": 750,
                "cast_point": 0.1,
                "cast_backswing": 0.3,
                "cooldown": [42, 35, 28, 21],
                "mana_cost": [140, 140, 140, 140],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": True,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "cheat_death", "duration": [4.0, 4.5, 5.0, 5.5], "target": "hit"},
                ],
            },
            {   # прототип: Dazzle — Poison Touch
                "key": "sm_toxic_thread",
                "name": "Токсичный тред",
                "hotkey": "E",
                "desc": "Добавляет цель в тред на сорок сообщений. "
                        "Долгий урон и вязкое замедление.",
                "targeting": "unit_enemy",
                "cast_range": 700,
                "cast_point": 0.25,
                "cast_backswing": 0.5,
                "cooldown": [10, 9, 8, 7],
                "mana_cost": [90, 100, 110, 120],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "dot", "dtype": "magical", "dps": [16, 24, 32, 40],
                     "duration": [5, 6, 7, 8], "interval": 1.0, "target": "hit"},
                    {"op": "slow",
                     "move_pct": [-14, -18, -22, -26],
                     "attack_speed": [0, 0, 0, 0],
                     "duration": [5, 6, 7, 8], "target": "hit"},
                ],
            },
            {   # прототип: Dazzle — Bad Juju + Weave
                "key": "sm_agile",
                "name": "Гибкие методологии",
                "hotkey": "R",
                "desc": "Перекраивает процесс под себя: у союзников резко "
                        "сокращаются откаты и растёт броня, у врагов броня осыпается.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.3,
                "cast_backswing": 0.5,
                "cooldown": [60, 50, 40],
                "mana_cost": [150, 200, 250],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 900,
                "effects": [
                    {"op": "area", "radius": 900, "filter": "ally", "max_targets": 0,
                     "effects": [
                         {"op": "stat_buff",
                          "stats": {"cooldown_reduction": [20, 30, 40],
                                    "armor": [3, 5, 7]},
                          "duration": [14, 16, 18], "target": "hit"},
                     ]},
                    {"op": "area", "radius": 900, "filter": "enemy", "max_targets": 0,
                     "effects": [
                         {"op": "stat_buff", "stats": {"armor": [-5, -7, -9]},
                          "duration": [14, 16, 18], "target": "hit"},
                     ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 6. БЕЗОПАСНИК — Bounty Hunter — убийца / ганкер
    # =====================================================================
    "security": {
        "key": "security",
        "name": "Безопасник",
        "title": "Отдел информационной безопасности",
        "archetype": "Убийца/Ганкер",
        "prototype": "Bounty Hunter",
        "primary": "agi",
        "attack_type": "melee",
        "attack_range": 150,
        "projectile_speed": 0,
        "bat": 1.7,
        "base_str": 21, "str_gain": 2.6,
        "base_agi": 22, "agi_gain": 3.0,
        "base_int": 20, "int_gain": 2.0,
        "base_damage": [24, 32],
        "base_armor": 2.0,
        "base_hp_regen": 0.5,
        "base_mana_regen": 0.9,
        "move_speed": 315,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 2,
        "roles": ["roamer", "offlane", "support"],
        "lore": "Видел твою переписку. Всю. И историю браузера тоже.",
        "abilities": [
            {   # прототип: Bounty Hunter — Shuriken Toss
                "key": "sec_policy_shuriken",
                "name": "Политика безопасности",
                "hotkey": "Q",
                "desc": "Метает в цель регламент на сорока листах. "
                        "Углы у регламента острые.",
                "targeting": "unit_enemy",
                "cast_range": 700,
                "cast_point": 0.3,
                "cast_backswing": 0.4,
                "cooldown": [8, 7, 6, 5],
                "mana_cost": [80, 90, 100, 110],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "projectile", "speed": 1500, "radius": 100, "pierce": False,
                     "max_dist": 900, "on_hit": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [145, 225, 305, 385], "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Bounty Hunter — Jinada
                "key": "sec_snap_audit",
                "name": "Внезапный аудит",
                "hotkey": "W",
                "desc": "Раз в несколько секунд следующий удар — это проверка "
                        "без предупреждения: дополнительный урон, цель надолго "
                        "теряет темп, а часть её бюджета уходит «на нужды отдела».",
                "targeting": "passive",
                "cast_range": 0,
                "cast_point": 0.0,
                "cast_backswing": 0.0,
                # откат самой проверки — он же cooldown прока ниже
                "cooldown": [10, 8, 6, 4],
                "mana_cost": [0, 0, 0, 0],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    # cooldown у прока обязателен: без него chance 100 срабатывал
                    # КАЖДЫМ ударом — отсюда и бесконечная кража бюджета.
                    # Кулдаун — Jinada'шный 10/8/6/4 с.
                    {"op": "proc_attack", "key": "sec_jinada",
                     "chance": [100, 100, 100, 100], "cooldown": [10, 8, 6, 4],
                     "effects": [
                         {"op": "damage", "dtype": "physical",
                          "amount": [60, 100, 140, 180], "target": "hit"},
                         {"op": "slow",
                          "move_pct": [-25, -35, -45, -55],
                          "attack_speed": [-25, -35, -45, -55],
                          "duration": 2.5, "target": "hit"},
                         {"op": "grant_gold", "amount": [10, 18, 26, 34],
                          "target": "caster"},
                     ]},
                ],
            },
            {   # прототип: Bounty Hunter — Shadow Walk
                "key": "sec_remote_access",
                "name": "Удалённый доступ",
                "hotkey": "E",
                "desc": "Заходит по VPN и пропадает с радаров: невидимость "
                        "и прибавка к скорости. Первый удар из невидимости больно бьёт.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.2,
                "cast_backswing": 0.3,
                "cooldown": [14, 12, 10, 8],
                "mana_cost": [50, 50, 50, 50],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "invisible", "duration": [15, 20, 25, 30], "fade_delay": 0.3},
                    {"op": "stat_buff",
                     "stats": {"move_speed_pct": [10, 15, 20, 25]},
                     "duration": [15, 20, 25, 30], "target": "caster"},
                    # Бонус должен бить только первым ударом из невидимости,
                    # а условия «пока невидим» у прока нет (см. ENGINE_REQUESTS).
                    # Ближайшее, что даёт движок, — кулдаун прока по откату самой
                    # способности: один усиленный удар за один заход по VPN.
                    {"op": "proc_attack", "key": "sec_backstab",
                     "chance": [100, 100, 100, 100], "cooldown": [14, 12, 10, 8],
                     "effects": [
                         {"op": "damage", "dtype": "physical",
                          "amount": [60, 110, 160, 210], "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Bounty Hunter — Track
                "key": "sec_probation",
                "name": "Испытательный срок",
                "hotkey": "R",
                "desc": "Ставит цель на карандаш: она получает больше урона "
                        "от всех источников и больше нигде не спрячется, "
                        "команда Безопасника разгоняется. Когда помеченного "
                        "закрывают — премия Безопаснику и всему отделу рядом, "
                        "кто бы ни довёл дело до конца.",
                "targeting": "unit_enemy",
                "cast_range": 1000,
                "cast_point": 0.1,
                "cast_backswing": 0.3,
                "cooldown": [14, 10, 6],
                "mana_cost": [50, 75, 100],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": True,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    # Премия висит на самой метке: on_death_effects срабатывают,
                    # когда помеченный умирает от ЧЬЕЙ УГОДНО руки. on_kill платил
                    # только за собственные килы Безопасника, то есть отдел не
                    # получал ничего — ради этого Track и ставят.
                    # Суммы — скалярами: движок исполняет on_death_effects с
                    # level=1, и списки по уровням молча схлопнулись бы в первый
                    # элемент (см. ENGINE_REQUESTS).
                    {"op": "stat_buff", "key": "sec_probation_mark",
                     "name": "Испытательный срок", "dispellable": False,
                     "stats": {"damage_taken_pct": [12, 16, 20]},
                     "duration": [30, 30, 30], "target": "hit",
                     "on_death_effects": [
                         # личная премия — приходит, даже если Безопасник на
                         # другом конце карты
                         {"op": "grant_gold", "amount": 180, "target": "caster"},
                         # доля отделу: всем союзникам в 1200 от места закрытия
                         # (в том числе самому Безопаснику, если он рядом)
                         {"op": "area", "radius": 1200, "filter": "ally",
                          "max_targets": 0, "effects": [
                              {"op": "grant_gold", "amount": 120, "target": "hit"},
                          ]},
                     ]},
                    {"op": "true_sight", "duration": [30, 30, 30], "radius": 900,
                     "target": "hit"},
                    {"op": "area", "radius": 1200, "filter": "ally", "max_targets": 0,
                     "effects": [
                         {"op": "stat_buff", "key": "sec_probation_haste",
                          "name": "Под наблюдением",
                          "stats": {"move_speed_pct": [12, 16, 20]},
                          "duration": [30, 30, 30], "target": "hit"},
                     ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 7. БУХГАЛТЕР — Leshrac — пушер
    # =====================================================================
    "accountant": {
        "key": "accountant",
        "name": "Бухгалтер",
        "title": "Закрывает квартал вашими нервами",
        "archetype": "Пушер/Нюкер",
        "prototype": "Leshrac",
        "primary": "int",
        "attack_type": "ranged",
        "attack_range": 575,
        "projectile_speed": 1000,
        "bat": 1.7,
        "base_str": 22, "str_gain": 2.6,
        "base_agi": 16, "agi_gain": 1.8,
        "base_int": 24, "int_gain": 3.2,
        "base_damage": [22, 30],
        "base_armor": 1.0,
        "base_hp_regen": 0.5,
        "base_mana_regen": 0.9,
        "move_speed": 320,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 2,
        "roles": ["mid", "offlane", "pusher"],
        "lore": "Считает не деньги, а то, сколько вы им должны. Всегда больше, чем кажется.",
        "abilities": [
            {   # прототип: Leshrac — Split Earth
                "key": "acc_snap_inspection",
                "name": "Внеплановая проверка",
                "hotkey": "Q",
                "desc": "Через полсекунды в указанной точке разверзается аудит. "
                        "Всех, кто там стоял, подбрасывает и оглушает.",
                "targeting": "point",
                "cast_range": 800,
                "cast_point": 0.4,
                "cast_backswing": 0.5,
                "cooldown": [8, 7, 6, 5],
                "mana_cost": [100, 115, 130, 145],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 250,
                "effects": [
                    {"op": "delayed", "delay": 0.5, "effects": [
                        {"op": "area", "radius": [200, 225, 250, 275], "filter": "enemy",
                         "max_targets": 0, "effects": [
                             {"op": "damage", "dtype": "magical",
                              "amount": [115, 170, 230, 290], "target": "hit"},
                             {"op": "stun", "duration": [1.2, 1.5, 1.8, 2.1],
                              "target": "hit"},
                         ]},
                    ]},
                ],
            },
            {   # прототип: Leshrac — Diabolic Edict
                "key": "acc_penalties",
                "name": "Штрафные санкции",
                "hotkey": "W",
                "desc": "Восемь секунд вокруг Бухгалтера хлопают штрафы. "
                        "Бьют по одному случайному врагу рядом — чем меньше "
                        "целей, тем больнее каждой. Достаётся и кулеру с принтером: "
                        "линия сносится сама собой.",
                "targeting": "none",
                "cast_range": 0,
                "cast_point": 0.3,
                "cast_backswing": 0.4,
                "cooldown": [17, 15, 13, 11],
                "mana_cost": [95, 110, 125, 140],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 500,
                "effects": [
                    {"op": "channel", "duration": 8.0, "interval": 0.4,
                     "break_on_move": False, "on_tick": [
                         {"op": "area", "radius": 500, "filter": "enemy", "max_targets": 1,
                          "effects": [
                              {"op": "damage", "dtype": "magical",
                               "amount": [22, 32, 42, 52], "target": "hit"},
                          ]},
                         {"op": "area", "radius": 500, "filter": "buildings",
                          "max_targets": 1, "effects": [
                              {"op": "damage", "dtype": "magical",
                               "amount": [11, 16, 21, 26], "target": "hit"},
                          ]},
                     ]},
                ],
            },
            {   # прототип: Leshrac — Lightning Storm
                "key": "acc_payment_cascade",
                "name": "Каскад платежей",
                "hotkey": "E",
                "desc": "Один платёж тянет за собой следующий, тот — ещё один. "
                        "Каждого задетого на секунду вбивает в пол.",
                "targeting": "unit_enemy",
                "cast_range": 800,
                "cast_point": 0.3,
                "cast_backswing": 0.4,
                "cooldown": [5.0, 4.5, 4.0, 3.5],
                "mana_cost": [90, 100, 110, 120],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "chain", "jumps": [4, 5, 6, 7], "radius": 500, "decay": 0.9,
                     "delay": 0.25, "filter": "enemy", "effects": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [85, 130, 175, 220], "target": "hit"},
                         {"op": "slow",
                          "move_pct": [-75, -75, -75, -75],
                          "attack_speed": [-75, -75, -75, -75],
                          "duration": 0.6, "target": "hit"},
                     ]},
                ],
            },
            {   # прототип: Leshrac — Pulse Nova
                "key": "acc_late_fee",
                "name": "Начисление пени",
                "hotkey": "R",
                "desc": "Пеня капает каждую секунду на всех, кто рядом. "
                        "Пока включено — жрёт ману. Пока включено — рядом не стоят.",
                "targeting": "toggle",
                "toggle_interval": 1.0,
                "cast_range": 0,
                "cast_point": 0.0,
                "cast_backswing": 0.0,
                "cooldown": [0, 0, 0],
                "mana_cost": [20, 28, 36],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 500,
                "effects": [
                    {"op": "area", "radius": 500, "filter": "enemy", "max_targets": 0,
                     "effects": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [75, 110, 145], "target": "hit"},
                     ]},
                ],
            },
        ],
    },

    # =====================================================================
    # 8. ДЖУНИОР — Phantom Lancer — необычная механика (иллюзии)
    # =====================================================================
    "junior": {
        "key": "junior",
        "name": "Джуниор",
        "title": "Копипастит и размножается",
        "archetype": "Керри/Иллюзионист",
        "prototype": "Phantom Lancer",
        "primary": "agi",
        "attack_type": "melee",
        "attack_range": 150,
        "projectile_speed": 0,
        "bat": 1.7,
        "base_str": 19, "str_gain": 2.2,
        "base_agi": 25, "agi_gain": 3.2,
        "base_int": 20, "int_gain": 1.8,
        "base_damage": [22, 30],
        "base_armor": 2.0,
        "base_hp_regen": 0.25,
        "base_mana_regen": 0.9,
        "move_speed": 290,
        "vision_day": 1800, "vision_night": 800,
        "difficulty": 3,
        "roles": ["safelane", "mid"],
        "lore": "Взял одну задачу. Теперь их сорок, и все выглядят как он.",
        "abilities": [
            {   # прототип: Phantom Lancer — Spirit Lance
                "key": "jun_copypaste",
                "name": "Копипаста",
                "hotkey": "Q",
                "desc": "Кидает в цель чужой кусок кода со Stack Overflow: "
                        "урон, замедление и рядом появляется ещё один Джуниор.",
                "targeting": "unit_enemy",
                "cast_range": 600,
                "cast_point": 0.4,
                "cast_backswing": 0.4,
                "cooldown": [7, 6, 5, 4],
                "mana_cost": [110, 120, 130, 140],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "projectile", "speed": 1100, "radius": 100, "pierce": False,
                     "max_dist": 800, "on_hit": [
                         {"op": "damage", "dtype": "magical",
                          "amount": [115, 175, 230, 290], "target": "hit"},
                         {"op": "slow",
                          "move_pct": [-20, -20, -20, -20],
                          "attack_speed": [0, 0, 0, 0],
                          "duration": [3.25, 3.5, 3.75, 4.0], "target": "hit"},
                     ]},
                    {"op": "illusion", "count": [1, 1, 1, 1], "duration": 8.0,
                     "dmg_out_pct": [20, 26, 32, 38], "dmg_in_pct": [320, 300, 280, 260]},
                ],
            },
            {   # прототип: Phantom Lancer — Doppelganger
                "key": "jun_outsource",
                "name": "Аутсорс",
                "hotkey": "W",
                "desc": "На секунду пропадает («я на созвоне») и выныривает "
                        "в другой точке вместе со свежей партией подрядчиков.",
                "targeting": "point",
                "cast_range": 550,
                "cast_point": 0.1,
                "cast_backswing": 0.3,
                "cooldown": [18, 15, 13, 10],
                "mana_cost": [100, 100, 100, 100],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": True,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "invulnerable", "duration": 1.0},
                    {"op": "blink", "max_dist": 550, "to": "point"},
                    {"op": "illusion", "count": [1, 1, 2, 2], "duration": 8.0,
                     "dmg_out_pct": [20, 26, 32, 38], "dmg_in_pct": [320, 300, 280, 260]},
                ],
            },
            {   # прототип: Phantom Lancer — Phantom Rush
                "key": "jun_task_rush",
                "name": "Рывок к задаче",
                "hotkey": "E",
                "desc": "Увидел задачу — рванул к ней, не дочитав описание. "
                        "Рывок к цели и короткое окно ярости.",
                "targeting": "unit_enemy",
                # дальность рывка растёт с уровнем (движок читает cast_range
                # по уровням той же lv(), что и остальные величины)
                "cast_range": [400, 550, 700, 850],
                "cast_point": 0.0,
                "cast_backswing": 0.2,
                "cooldown": [9, 7, 5, 3],
                "mana_cost": [40, 40, 40, 40],
                "max_level": 4,
                "level_req": [1, 3, 5, 7],
                "pierces_magic_immunity": False,
                "dispellable": True,
                "aoe_radius": 0,
                "effects": [
                    {"op": "blink", "max_dist": [400, 550, 700, 850], "to": "target"},
                    {"op": "stat_buff",
                     "stats": {"attack_speed": [40, 60, 80, 100],
                               "damage": [20, 35, 50, 65]},
                     "duration": 4.0, "target": "caster"},
                ],
            },
            {   # прототип: Phantom Lancer — Juxtapose
                "key": "jun_task_flood",
                "name": "Наплодил задач",
                "hotkey": "R",
                "desc": "Каждый его удар порождает ещё одного Джуниора. "
                        "И тот тоже что-то делает. И тот тоже.",
                "targeting": "passive",
                "cast_range": 0,
                "cast_point": 0.0,
                "cast_backswing": 0.0,
                "cooldown": [0, 0, 0],
                "mana_cost": [0, 0, 0],
                "max_level": 3,
                "level_req": [6, 12, 18],
                "pierces_magic_immunity": False,
                "dispellable": False,
                "aoe_radius": 0,
                "effects": [
                    {"op": "proc_attack", "chance": [30, 35, 40], "effects": [
                        {"op": "illusion", "count": [1, 1, 1], "duration": 8.0,
                         "dmg_out_pct": [20, 26, 32], "dmg_in_pct": [350, 320, 290]},
                    ]},
                ],
            },
        ],
    },
}


# =========================================================================
# Чего ещё не хватает в ABILITY_SPEC.md §3.
# Первый проход закрыл chain, тик у toggle, filter 'buildings', лимит
# иллюзий, true_sight, mana_burn/restore_mana, grant_gold.
# Второй проход закрыл ещё четыре пункта, и ростер под них уже переписан:
#   * bound_to_channel у контроля — «Внеплановая перезагрузка» больше не
#     оставляет цель в стане при сорванном канале;
#   * cooldown у proc_attack — «Внезапный аудит» и «Удалённый доступ»
#     перестали срабатывать каждым ударом (проверка на это добавлена
#     в validate(), чтобы баг не вернулся молча);
#   * on_death_effects у stat_buff — «Испытательный срок» платит премию
#     отделу, когда помеченного закрыл кто угодно;
#   * cast_range по уровням — «Рывок к задаче» снова растёт с уровнем.
# Подтверждены и сняты с вопросов: blink to 'target' изнутри area
# («Залил в прод в пятницу» собран правильно) и сигнатура grant_gold/grant_xp.
# Ниже — то, что осталось, и два пункта, вылезших уже на новых примитивах.
# =========================================================================

ENGINE_REQUESTS: list[str] = [
    "условие у прока — из старого пункта про proc_attack осталась половина. "
    "Кулдаун вы дали, кража бюджета вылечена, но «Удалённый доступ» "
    "(Shadow Walk) по смыслу бьёт бонусом ТОЛЬКО первым ударом из "
    "невидимости, а proc висит на герое постоянно, пока прокачан скилл. "
    "Сейчас это подпёрто кулдауном прока, равным откату самой способности "
    "(14/12/10/8), — то есть бонус приходит и без невидимости, просто редко. "
    "Прошу {'op':'proc_attack','requires_state':'invisible'} или общий "
    "'requires_modifier': '<key>'. Заодно: поле once_per_target у прока "
    "разбирается (abilities.attack_procs), но в цикле атаки (world, "
    "'for proc in attack_procs') не проверяется — сейчас это тихий no-op, "
    "поэтому я на него не опирался.",

    "уровень способности у on_death_effects — новый пункт, вылез сразу "
    "после того, как «Испытательный срок» переехал на метку. Движок "
    "исполняет эффекты метки с level=1 (world._run_death_marks строит "
    "EffectContext(..., 1, ...)), поэтому список по уровням молча "
    "схлопнулся бы в первый элемент. Пришлось записать премию скалярами "
    "(180 лично Безопаснику + 120 каждому союзнику в 1200 от трупа), то "
    "есть она не растёт с уровнем ульты. Достаточно сохранить уровень в "
    "данных модификатора и передавать его в контекст — тогда вернём "
    "[200,300,400] и отдельную шкалу для команды.",

    "decay у chain не доходит до вложенных эффектов — второй новый пункт. "
    "abilities._scaled умножает только amount/dps/heal ВЕРХНЕГО уровня "
    "каждого эффекта и не спускается в 'effects' вложенного area. "
    "У «Ретроспективы» (Shadow Wave) хил лежит на верхнем уровне, а урон "
    "по врагам — во вложенном area, так что при decay < 1 хил затухал бы, "
    "а урон нет, и обещание «лечит ровно столько, сколько бьёт» "
    "развалилось бы. Поэтому decay там 1.0 — и это ещё и правильный "
    "прототип: у Shadow Wave в доте затухания нет. Затухание с вложенными "
    "формами доставки нужно либо сделать рекурсивным, либо честно написать "
    "в §3, что оно только для плоских эффектов.",

    "урон в процентах от HP — {'op':'damage','pct_of':'max_hp'|'current_hp'}. "
    "Нужен, чтобы нюкеры не выключались к 15-й минуте, когда у всех по 2500 HP. "
    "Особенно после того, как я по вашей просьбе срезал Аналитика: сейчас его "
    "поздняя игра держится только на предметах.",

    "каталог юнитов для summon — «Парное программирование» задумывалось как "
    "Healing Ward: юнит, который стоит, лечит и которого можно убить. Op summon "
    "есть, но нет описания, где живут статы юнита 'healing_ward'. Сейчас это "
    "разовый area-хил + hp_regen_pct, то есть убиваемой варды у Сеньора нет.",
]


# =========================================================================
# Самопроверка
# =========================================================================

def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _check_level_list(value, max_level: int, where: str) -> None:
    assert isinstance(value, list), (
        f"{where}: ожидался список по уровням способности, получено {value!r}")
    assert len(value) == max_level, (
        f"{where}: длина списка {len(value)}, а max_level={max_level}; "
        f"значение {value!r}")
    for i, item in enumerate(value):
        assert _is_num(item), (
            f"{where}[{i}]: ожидалось число, получено {item!r}")


def _check_stats(stats, max_level: int, where: str) -> None:
    assert isinstance(stats, dict), f"{where}: stats обязан быть словарём, получено {stats!r}"
    assert stats, f"{where}: пустой stats — так нельзя"
    for stat_key, stat_val in stats.items():
        assert stat_key in _ALLOWED_STATS, (
            f"{where}: характеристика '{stat_key}' отсутствует в ABILITY_SPEC.md §5")
        if isinstance(stat_val, list):
            _check_level_list(stat_val, max_level, f"{where}.stats['{stat_key}']")
        else:
            assert _is_num(stat_val), (
                f"{where}.stats['{stat_key}']: ожидалось число или список, "
                f"получено {stat_val!r}")


def _level_value(value, i: int):
    """Значение поля на i-м уровне: список — по индексу, скаляр — как есть."""
    if isinstance(value, (list, tuple)):
        return value[min(i, len(value) - 1)]
    return value


def _check_proc_cooldown(eff: dict, max_level: int, where: str) -> None:
    """proc_attack со стопроцентным шансом обязан иметь кулдаун прока.

    Ровно этот баг ломал Безопасника: «Внезапный аудит» с chance 100 и без
    cooldown срабатывал КАЖДЫМ ударом — по 34 золота и -55% к темпу с каждой
    атаки, около 270 украденного бюджета за 12 секунд непрерывного боя.
    Молча такое больше не проезжает.
    """
    chance = eff.get("chance", 100)
    cooldown = eff.get("cooldown", 0)
    for i in range(max_level):
        c = _level_value(chance, i)
        assert _is_num(c) and 0 < c <= 100, (
            f"{where}: chance на уровне {i + 1} = {c!r}, "
            f"допустим шанс в процентах 0 < chance <= 100")
        cd = _level_value(cooldown, i)
        assert _is_num(cd) and cd >= 0, (
            f"{where}: cooldown на уровне {i + 1} = {cd!r}, "
            f"ожидалось неотрицательное число")
        assert not (c >= 100 and cd <= 0), (
            f"{where}: на уровне {i + 1} шанс {c}% и нет кулдауна прока — "
            f"такой proc_attack срабатывает каждым ударом (так Безопасник и "
            f"крал бюджет). Задай 'cooldown' — число или список по уровням, — "
            f"либо опусти шанс ниже 100")


def _check_effects(effects, max_level: int, where: str) -> None:
    assert isinstance(effects, list), (
        f"{where}: список эффектов обязан быть list, получено {type(effects).__name__}")
    for idx, eff in enumerate(effects):
        at = f"{where}[{idx}]"
        assert isinstance(eff, dict), f"{at}: эффект обязан быть словарём, получено {eff!r}"
        op = eff.get("op")
        assert op is not None, f"{at}: у эффекта нет поля 'op'"
        assert op in _ALLOWED_OPS, (
            f"{at}: op='{op}' нет в разрешённом наборе ABILITY_SPEC.md §3. "
            f"Выдумывать op запрещено (§8.2)")
        at = f"{at}(op={op})"

        # --- перечислимые поля --------------------------------------------
        if "dtype" in eff:
            assert eff["dtype"] in _ALLOWED_DTYPE, (
                f"{at}: dtype='{eff['dtype']}' не входит в {sorted(_ALLOWED_DTYPE)}")
        if "filter" in eff:
            assert eff["filter"] in _ALLOWED_FILTER, (
                f"{at}: filter='{eff['filter']}' не входит в {sorted(_ALLOWED_FILTER)}")
        if "target" in eff:
            assert eff["target"] in _ALLOWED_TARGET, (
                f"{at}: target='{eff['target']}' не входит в {sorted(_ALLOWED_TARGET)} "
                f"(ABILITY_SPEC.md §4)")
        if "stype" in eff:
            assert eff["stype"] in _ALLOWED_STYPE, (
                f"{at}: stype='{eff['stype']}' не входит в {sorted(_ALLOWED_STYPE)}")
        if op == "blink":
            assert eff.get("to") in _ALLOWED_BLINK_TO, (
                f"{at}: to='{eff.get('to')}' не входит в {sorted(_ALLOWED_BLINK_TO)}")
        if op == "pull":
            assert eff.get("to") == "caster", (
                f"{at}: pull умеет тащить только к кастеру, получено to={eff.get('to')!r}")
        if op == "purge":
            assert eff.get("strength") in _ALLOWED_PURGE, (
                f"{at}: strength='{eff.get('strength')}' не входит в {sorted(_ALLOWED_PURGE)}")
        if op == "proc_attack":
            _check_proc_cooldown(eff, max_level, at)

        # --- значения -----------------------------------------------------
        for field, value in eff.items():
            if field == "op":
                continue
            if field in _EFFECT_LIST_KEYS:
                _check_effects(value, max_level, f"{at}.{field}")
                continue
            if field == "stats":
                _check_stats(value, max_level, at)
                continue
            if isinstance(value, list):
                _check_level_list(value, max_level, f"{at}.{field}")
            else:
                assert _is_num(value) or isinstance(value, (str, bool)), (
                    f"{at}.{field}: недопустимый тип значения {type(value).__name__}")


_REQUIRED_HERO_FIELDS = (
    "key", "name", "title", "archetype", "prototype", "primary", "attack_type",
    "attack_range", "projectile_speed", "bat", "base_str", "str_gain",
    "base_agi", "agi_gain", "base_int", "int_gain", "base_damage", "base_armor",
    "base_hp_regen", "base_mana_regen", "move_speed", "vision_day",
    "vision_night", "difficulty", "roles", "lore", "abilities",
)

_REQUIRED_ABILITY_FIELDS = (
    "key", "name", "hotkey", "desc", "targeting", "cast_range", "cast_point",
    "cast_backswing", "cooldown", "mana_cost", "max_level", "level_req",
    "pierces_magic_immunity", "dispellable", "aoe_radius", "effects",
)


def validate() -> bool:
    """Проверяет ростер на соответствие docs/ABILITY_SPEC.md.

    Поднимает AssertionError с внятным текстом при первой же проблеме.
    Возвращает True, если всё в порядке.
    """
    assert isinstance(HEROES, dict) and HEROES, "HEROES пуст или не словарь"

    seen_ability_keys: dict[str, str] = {}

    for hero_key, hero in HEROES.items():
        h = f"герой '{hero_key}'"
        assert isinstance(hero, dict), f"{h}: значение обязано быть словарём"

        for field in _REQUIRED_HERO_FIELDS:
            assert field in hero, f"{h}: отсутствует обязательное поле '{field}'"

        assert hero["key"] == hero_key, (
            f"{h}: поле key='{hero['key']}' не совпадает с ключом словаря '{hero_key}'")
        assert hero_key == hero_key.lower() and " " not in hero_key, (
            f"{h}: ключ героя обязан быть snake_case")
        assert hero["primary"] in _ALLOWED_PRIMARY, (
            f"{h}: primary='{hero['primary']}' не входит в {sorted(_ALLOWED_PRIMARY)}")
        assert hero["attack_type"] in _ALLOWED_ATTACK_TYPE, (
            f"{h}: attack_type='{hero['attack_type']}' не входит в "
            f"{sorted(_ALLOWED_ATTACK_TYPE)}")
        if hero["attack_type"] == "melee":
            assert hero["projectile_speed"] == 0, (
                f"{h}: у melee-героя projectile_speed обязан быть 0, "
                f"получено {hero['projectile_speed']}")
        else:
            assert hero["projectile_speed"] > 0, (
                f"{h}: у ranged-героя projectile_speed обязан быть > 0")
        assert isinstance(hero["prototype"], str) and hero["prototype"], (
            f"{h}: не указан prototype — герой Dota 2, чей паттерн воспроизводится")
        assert 1 <= hero["difficulty"] <= 3, (
            f"{h}: difficulty={hero['difficulty']}, допустимо 1..3")
        assert isinstance(hero["base_damage"], list) and len(hero["base_damage"]) == 2, (
            f"{h}: base_damage обязан быть [min, max]")
        assert hero["base_damage"][0] <= hero["base_damage"][1], (
            f"{h}: base_damage min > max: {hero['base_damage']}")
        assert isinstance(hero["roles"], list) and hero["roles"], (
            f"{h}: roles обязан быть непустым списком")
        for role in hero["roles"]:
            assert role in _ALLOWED_ROLES, (
                f"{h}: роль '{role}' неизвестна, допустимо {sorted(_ALLOWED_ROLES)}")
        assert 100 <= hero["move_speed"] <= 550, (
            f"{h}: move_speed={hero['move_speed']} вне разумных границ движка 100..550")

        abilities = hero["abilities"]
        assert isinstance(abilities, list) and len(abilities) == 4, (
            f"{h}: ожидалось ровно 4 способности, найдено "
            f"{len(abilities) if isinstance(abilities, list) else '?'}")

        hotkeys: list[str] = []
        for ability in abilities:
            assert isinstance(ability, dict), f"{h}: способность обязана быть словарём"
            for field in _REQUIRED_ABILITY_FIELDS:
                assert field in ability, (
                    f"{h}: способность '{ability.get('key', '?')}' — "
                    f"отсутствует обязательное поле '{field}'")

            a = f"{h}, способность '{ability['key']}'"

            assert ability["key"] not in seen_ability_keys, (
                f"{a}: ключ способности уже занят героем "
                f"'{seen_ability_keys[ability['key']]}' — ключи обязаны быть уникальны")
            seen_ability_keys[ability["key"]] = hero_key

            hotkey = ability["hotkey"]
            assert hotkey in _ALLOWED_HOTKEYS, (
                f"{a}: hotkey='{hotkey}', ожидался один из {list(_ALLOWED_HOTKEYS)}")
            assert hotkey not in hotkeys, (
                f"{a}: hotkey '{hotkey}' уже занят другой способностью этого героя")
            hotkeys.append(hotkey)

            assert ability["targeting"] in _ALLOWED_TARGETING, (
                f"{a}: targeting='{ability['targeting']}' не входит в "
                f"{sorted(_ALLOWED_TARGETING)} (ABILITY_SPEC.md §2)")

            max_level = ability["max_level"]
            assert max_level in (3, 4), (
                f"{a}: max_level={max_level}, допустимо 4 (обычная) или 3 (ульта)")
            is_ult = max_level == 3
            assert (hotkey == "R") == is_ult, (
                f"{a}: ульта обязана висеть на R и иметь max_level=3; "
                f"здесь hotkey='{hotkey}', max_level={max_level}")

            expected_req = _LEVEL_REQ_ULT if is_ult else _LEVEL_REQ_NORMAL
            assert ability["level_req"] == expected_req, (
                f"{a}: level_req={ability['level_req']}, спецификация требует "
                f"{expected_req}")

            for field in ("cooldown", "mana_cost"):
                _check_level_list(ability[field], max_level, f"{a}.{field}")
                for value in ability[field]:
                    assert value >= 0, f"{a}.{field}: отрицательное значение {value}"

            # cast_range умеет расти с уровнем: движок читает его той же
            # функцией по уровням, что и остальные величины.
            if isinstance(ability["cast_range"], list):
                _check_level_list(ability["cast_range"], max_level, f"{a}.cast_range")
                for value in ability["cast_range"]:
                    assert value >= 0, (
                        f"{a}.cast_range: отрицательное значение {value}")
            else:
                assert _is_num(ability["cast_range"]) and ability["cast_range"] >= 0, (
                    f"{a}.cast_range: ожидалось неотрицательное число или "
                    f"список по уровням, получено {ability['cast_range']!r}")

            for field in ("cast_point", "cast_backswing", "aoe_radius"):
                assert _is_num(ability[field]) and ability[field] >= 0, (
                    f"{a}.{field}: ожидалось неотрицательное число, "
                    f"получено {ability[field]!r}")

            for field in ("pierces_magic_immunity", "dispellable"):
                assert isinstance(ability[field], bool), (
                    f"{a}.{field}: ожидался bool, получено {ability[field]!r}")

            if ability["targeting"] == "toggle":
                assert "toggle_interval" in ability, (
                    f"{a}: у toggle-способности обязано быть поле 'toggle_interval' — "
                    f"как часто применяются её эффекты")
                interval = ability["toggle_interval"]
                assert _is_num(interval) and interval > 0, (
                    f"{a}.toggle_interval: ожидалось положительное число, "
                    f"получено {interval!r}")
                assert any(cost > 0 for cost in ability["mana_cost"]), (
                    f"{a}: toggle без расхода маны за тик выключить нечем — "
                    f"он бесплатен навсегда; задай mana_cost > 0")
            else:
                assert "toggle_interval" not in ability, (
                    f"{a}: 'toggle_interval' имеет смысл только при targeting='toggle'")

            assert ability["effects"], f"{a}: пустой список effects"
            _check_effects(ability["effects"], max_level, f"{a}.effects")

        assert set(hotkeys) == set(_ALLOWED_HOTKEYS), (
            f"{h}: хоткеи {hotkeys}, а нужен полный набор {list(_ALLOWED_HOTKEYS)}")

    return True


if __name__ == "__main__":  # pragma: no cover
    validate()
    print(f"{len(HEROES)} героев OK")
