# -*- coding: utf-8 -*-
"""Магазин предметов «Офисной Доты».

Чистые данные. Никаких импортов из office_dota.* — этот модуль обязан
импортироваться отдельно, в том числе инструментами балансировки и тестами.

Контракт: docs/ABILITY_SPEC.md
    §3 — единственный разрешённый набор `op`
    §5 — единственный разрешённый набор ключей в `stats`
    §7 — схема предмета

Дополнительно к §7 у каждого предмета есть поле `prototype` — предмет Dota 2,
который он воспроизводит. Это не украшение: узнаваемость — главное требование
к магазину. Игрок, знающий доту, обязан понять предмет по одной строке.

Соглашения этого модуля
-----------------------
* `tier`: 1 — базовый некрафтовый компонент и расходники,
          2 — средний (собирается или крупный компонент, ~1000–2500₿),
          3 — дорогой (~2500–4500₿),
          4 — поздняя игра (~4900₿+).
* `shop`: используются только "base" и "consumable". Значение "secret" схемой
  разрешено, но в игре не применяется: DESIGN.md §7 убирает курьера и делает
  покупку доступной откуда угодно, так что отдельная секретка потеряла смысл.
* Предмет без `components` продаётся целиком, у него `recipe_cost == 0`.
  Для собираемого предмета `cost == сумма cost компонентов + recipe_cost`.
  Повторяющийся ключ в `components` означает «нужно две штуки».
* Поля сверх §7, добавленные движком: `charges` (обязательно у расходников),
  `drop_on_death`, `target_types`, `blocked_by_damage` + `damage_block_sec`,
  `gain_charge_on_enemy_cast` + `max_charges` — накопление зарядов от чужих
  применений способностей рядом. Всё это проверяется в validate(); неизвестные
  поля запрещены, чтобы опечатка в данных не превращалась в молча отключённую
  механику.
* Баланс цен — дотовский (DESIGN.md §2, Turbo). Доход в Turbo примерно ×2,
  поэтому цены не резались: игроки просто доходят до предметов вдвое быстрее.
  Ориентир: тир 3 — с 8–10-й минуты, тир 4 — с 12–15-й. Раньше 10-й минуты
  тир-4 недостижим даже на идеальной линии.
"""

ITEMS: dict[str, dict] = {

    # ======================================================================
    # ТИР 1 — РАСХОДНИКИ
    # ======================================================================

    # прототип: Clarity
    "energy_drink": {
        "key": "energy_drink",
        "name": "Банка энергетика",
        "prototype": "Clarity",
        "cost": 50,
        "components": [],
        "recipe_cost": 0,
        "shop": "consumable",
        "charges": 1,
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "unit_ally",
            "cast_range": 350,
            "cooldown": 0,
            "mana_cost": 0,
            "effects": [
                # break_on_damage: движок снимает модификатор при уроне от героя
                # (world._break_fragile_buffs). До него это было только обещанием в desc.
                {"op": "stat_buff", "stats": {"mana_regen": 8}, "duration": 25,
                 "target": "hit", "break_on_damage": True},
            ],
        },
        "desc": "Восстанавливает 200 маны за 25 секунд себе или союзнику. "
                "Выдыхается, если по вам прилетело от героя.",
        "tier": 1,
    },

    # прототип: Observer Ward
    "observer_ward": {
        "key": "observer_ward",
        "name": "Камера наблюдения",
        "prototype": "Observer Ward",
        "cost": 75,
        "components": [],
        "recipe_cost": 0,
        "shop": "consumable",
        "charges": 2,
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 0,
            "mana_cost": 0,
            "effects": [
                # Юнита-наблюдателя в движке нет и не будет (см. блок намеренных
                # отличий ниже), а summon с неизвестным ключом молча превращался
                # в обычного крипа ближнего боя рядом с кастером — content.creep_def
                # падает на _FALLBACK_CREEPS["melee_creep"]. Поэтому камера висит
                # на владельце и даёт то, ради чего вард и ставят, — обзор.
                # Истинного зрения здесь намеренно нет: это работа «Трекера
                # активности» (Dust), как Observer и Sentry разведены в доте.
                {"op": "stat_buff", "key": "observer_ward_vision",
                 "name": "Камера наблюдения",
                 "stats": {"vision_day": 700, "vision_night": 700},
                 "duration": 120, "target": "caster", "dispellable": False},
            ],
        },
        "desc": "Две минуты вы видите на 700 дальше обычного. Это не вард: "
                "камеру нельзя поставить в кустах и уйти — она висит на вас "
                "и уходит вместе с вами. Невидимок не показывает.",
        "tier": 1,
    },

    # прототип: Dust of Appearance
    "activity_tracker": {
        "key": "activity_tracker",
        "name": "Трекер активности",
        "prototype": "Dust of Appearance",
        "cost": 80,
        "components": [],
        "recipe_cost": 0,
        "shop": "consumable",
        "charges": 2,
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 20,
            "mana_cost": 0,
            "effects": [
                {"op": "true_sight", "duration": 12, "radius": 1050, "target": "caster"},
            ],
        },
        "desc": "12 секунд видно всех, кто выставил себе «невидимку», в радиусе 1050. "
                "Прямой ответ на «Не беспокоить»: статус статусом, а логи не врут.",
        "tier": 1,
    },

    # прототип: Smoke of Deceit
    "dnd_status": {
        "key": "dnd_status",
        "name": "Статус «Не беспокоить»",
        "prototype": "Smoke of Deceit",
        "cost": 100,
        "components": [],
        "recipe_cost": 0,
        "shop": "consumable",
        "charges": 1,
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 0,
            "mana_cost": 0,
            "effects": [
                {"op": "area", "radius": 1200, "filter": "ally", "max_targets": 0, "effects": [
                    {"op": "invisible", "duration": 45, "fade_delay": 0.5},
                    {"op": "stat_buff", "stats": {"move_speed_pct": 15}, "duration": 45, "target": "hit"},
                ]},
            ],
        },
        "desc": "Вы и союзники рядом пропадаете из всех чатов на 45 секунд: "
                "невидимость и +15% скорости. Слетает от атаки и рядом с чужой техникой.",
        "tier": 1,
    },

    # прототип: Town Portal Scroll
    "corporate_taxi": {
        "key": "corporate_taxi",
        "name": "Корпоративное такси",
        "prototype": "Town Portal Scroll",
        "cost": 100,
        "components": [],
        "recipe_cost": 0,
        "shop": "consumable",
        "charges": 1,
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "unit_ally",
            "cast_range": 0,
            "cooldown": 60,
            "mana_cost": 75,
            "effects": [
                {"op": "channel", "duration": 3, "interval": 3, "break_on_move": True, "on_tick": [
                    {"op": "blink", "max_dist": 0, "to": "target"},
                ]},
            ],
        },
        "desc": "Три секунды ждёте машину — и оказываетесь у любой своей постройки. "
                "Сдвинулись с места — заказ отменён.",
        "tier": 1,
    },

    # прототип: Healing Salve
    "coffee_mug": {
        "key": "coffee_mug",
        "name": "Кружка кофе",
        "prototype": "Healing Salve",
        "cost": 110,
        "components": [],
        "recipe_cost": 0,
        "shop": "consumable",
        "charges": 1,
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "unit_ally",
            "cast_range": 250,
            "cooldown": 0,
            "mana_cost": 0,
            "effects": [
                {"op": "stat_buff", "stats": {"hp_regen": 40}, "duration": 10,
                 "target": "hit", "break_on_damage": True},
            ],
        },
        "desc": "400 HP за 10 секунд. Если в процессе прилетело от героя — "
                "кофе остыл, эффект пропал.",
        "tier": 1,
    },

    # ======================================================================
    # ТИР 1 — БАЗОВЫЕ КОМПОНЕНТЫ
    # ======================================================================

    # прототип: Iron Branch
    "paperclip": {
        "key": "paperclip",
        "name": "Канцелярская скрепка",
        "prototype": "Iron Branch",
        "cost": 50,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"all_stats": 1},
        "passives": [],
        "active": None,
        "desc": "+1 ко всем атрибутам за 50₿. Из неё собирается половина магазина.",
        "tier": 1,
    },

    # прототип: Circlet
    "sticky_notes": {
        "key": "sticky_notes",
        "name": "Пачка стикеров",
        "prototype": "Circlet",
        "cost": 155,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"all_stats": 2},
        "passives": [],
        "active": None,
        "desc": "+2 ко всем атрибутам. Пока задача на стикере — она как бы под контролем.",
        "tier": 1,
    },

    # прототип: Ring of Regeneration
    "humidifier": {
        "key": "humidifier",
        "name": "Увлажнитель воздуха",
        "prototype": "Ring of Regeneration",
        "cost": 175,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"hp_regen": 2},
        "passives": [],
        "active": None,
        "desc": "+2 HP/с. В опенспейсе воздух суше, чем в Сахаре.",
        "tier": 1,
    },

    # прототип: Belt of Strength
    "back_support_belt": {
        "key": "back_support_belt",
        "name": "Ортопедический пояс",
        "prototype": "Belt of Strength",
        "cost": 450,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"str": 6},
        "passives": [],
        "active": None,
        "desc": "+6 к силе. Спина — главный рабочий инструмент офисного бойца.",
        "tier": 1,
    },

    # прототип: Gloves of Haste
    "hand_trainer": {
        "key": "hand_trainer",
        "name": "Кистевой эспандер",
        "prototype": "Gloves of Haste",
        "cost": 450,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"attack_speed": 15},
        "passives": [],
        "active": None,
        "desc": "+15 к скорости атаки. Кисть не устаёт — задачи закрываются чаще.",
        "tier": 1,
    },

    # прототип: Blades of Attack (обзор — офисный твист, в доте его у этого предмета нет)
    "second_monitor": {
        "key": "second_monitor",
        "name": "Второй монитор",
        "prototype": "Blades of Attack",
        "cost": 500,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"damage": 12, "vision_day": 150, "vision_night": 75},
        "passives": [],
        "active": None,
        "desc": "+12 к урону, +150 к дневному обзору и +75 к ночному. "
                "На одном мониторе работать невозможно, это все знают.",
        "tier": 1,
    },

    # прототип: Boots of Speed
    "sneakers": {
        "key": "sneakers",
        "name": "Кроссовки",
        "prototype": "Boots of Speed",
        "cost": 500,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"move_speed": 45},
        "passives": [],
        "active": None,
        "desc": "+45 к скорости передвижения. Дресс-код давно никто не читал.",
        "tier": 1,
    },

    # прототип: Chainmail
    "armored_case": {
        "key": "armored_case",
        "name": "Противоударный кейс",
        "prototype": "Chainmail",
        "cost": 550,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"armor": 5},
        "passives": [],
        "active": None,
        "desc": "+5 к броне. Ноутбук переживёт и падение, и совещание.",
        "tier": 1,
    },

    # прототип: Energy Booster
    "powerbank": {
        "key": "powerbank",
        "name": "Пауэрбанк",
        "prototype": "Energy Booster",
        "cost": 900,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"mana": 250},
        "passives": [],
        "active": None,
        "desc": "+250 к мане. Тяжёлый, но розетка всегда занята.",
        "tier": 1,
    },

    # ======================================================================
    # ТИР 2 — СРЕДНИЕ
    # ======================================================================

    # прототип: Magic Wand
    "desk_drawer": {
        "key": "desk_drawer",
        "name": "Ящик стола",
        "prototype": "Magic Wand",
        "cost": 445,
        "components": ["paperclip", "paperclip", "sticky_notes"],
        "recipe_cost": 190,
        "shop": "base",
        # Заряд за каждое вражеское применение способности в радиусе 1200
        # (world._charge_nearby_wands). Накопление работает и видно в интерфейсе,
        # но тратить заряды активкой движок пока не умеет — величины ниже
        # фиксированные, см. ENGINE_REQUESTS.
        "gain_charge_on_enemy_cast": True,
        "max_charges": 20,
        "stats": {"all_stats": 3},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 13,
            "mana_cost": 0,
            "effects": [
                {"op": "heal", "amount": 200, "target": "caster"},
                {"op": "restore_mana", "amount": 200, "pct": 0, "target": "caster"},
            ],
        },
        "desc": "В ящике стола есть всё: мгновенно 200 HP и 200 маны. "
                "Каждое вражеское заклинание рядом добавляет в ящик ещё одну "
                "мелочь — до 20 штук. Самая дешёвая кнопка «выжить» в игре.",
        "tier": 2,
    },

    # прототип: Staff of Wizardry
    "thick_manual": {
        "key": "thick_manual",
        "name": "Толстый справочник",
        "prototype": "Staff of Wizardry",
        "cost": 1000,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"int": 10},
        "passives": [],
        "active": None,
        "desc": "+10 к интеллекту. Никто его не читал, но на столе он выглядит солидно.",
        "tier": 2,
    },

    # прототип: Vitality Booster
    "gym_membership": {
        "key": "gym_membership",
        "name": "Абонемент в спортзал",
        "prototype": "Vitality Booster",
        "cost": 1100,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"hp": 250},
        "passives": [],
        "active": None,
        "desc": "+250 HP. Ходить не обязательно — здоровье прибавляет сам факт покупки.",
        "tier": 2,
    },

    # прототип: Power Treads
    "running_sneakers": {
        "key": "running_sneakers",
        "name": "Беговые кроссовки",
        "prototype": "Power Treads",
        "cost": 1400,
        "components": ["sneakers", "back_support_belt", "hand_trainer"],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"move_speed": 45, "attack_speed": 12, "str": 8},
        "passives": [],
        "active": None,
        "desc": "+45 скорости, +12 скорости атаки и +8 к силе. "
                "Настроены под выносливость: на переключение режима движок пока не способен.",
        "tier": 2,
    },

    # прототип: Ghost Scepter
    "sick_leave": {
        "key": "sick_leave",
        "name": "Больничный",
        "prototype": "Ghost Scepter",
        "cost": 1500,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"all_stats": 4},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 22,
            "mana_cost": 0,
            "effects": [
                # ghost делает всё сам, дублировать его данными нельзя:
                #   * F_ETHEREAL входит в маску CANNOT_ATTACK — явный disarm был дублем;
                #   * combat.ETHEREAL_MAGIC_AMP уже даёт ровно +40% магического урона,
                #     а magic_amp вешал сверх этого ещё и damage_taken_pct 40 на все типы.
                #     Вместе выходило ×1.96 по магии и +40% по чистому урону вместо +40%.
                {"op": "ghost", "duration": 4, "target": "caster"},
                {"op": "stat_buff", "stats": {"move_speed": 30}, "duration": 4, "target": "caster"},
            ],
        },
        "desc": "4 секунды вас физически нет в офисе: обычные атаки не проходят, "
                "но и вы не бьёте, а магия бьёт на 40% больнее.",
        "tier": 2,
    },

    # прототип: Hyperstone
    "mech_keyboard": {
        "key": "mech_keyboard",
        "name": "Механическая клавиатура",
        "prototype": "Hyperstone",
        "cost": 2000,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"attack_speed": 55},
        "passives": [],
        "active": None,
        "desc": "+55 к скорости атаки. Соседи по опенспейсу вас ненавидят, "
                "зато тикеты закрываются со скоростью пулемёта.",
        "tier": 2,
    },

    # прототип: Blade Mail
    "reply_all": {
        "key": "reply_all",
        "name": "Ответить всем",
        "prototype": "Blade Mail",
        "cost": 2100,
        "components": ["armored_case", "second_monitor"],
        "recipe_cost": 1050,
        "shop": "base",
        "stats": {"armor": 6, "damage": 22, "int": 10},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 25,
            "mana_cost": 25,
            "effects": [
                # damage_taken_pct -20 проверен: entities.damage_taken_mult = 1 + pct/100,
                # то есть ×0.8 на входящий урон любого типа.
                {"op": "stat_buff", "stats": {"damage_taken_pct": -20}, "duration": 4.5, "target": "caster"},
                # ВНИМАНИЕ: возврат урона сейчас не работает и включать его данными нельзя.
                # world.run_damage_reactions пропускает реакцию с пустым effects
                # (`if not inner: continue`), так что reflect_pct без вложенного damage —
                # мёртвая строка. Почему не чиню: см. ENGINE_REQUESTS, два активных
                # «Ответить всем» уходят в рекурсивный пинг-понг и роняют матч.
                {"op": "on_take_damage", "duration": 4.5, "reflect_pct": 100, "effects": []},
            ],
        },
        "desc": "4.5 секунды входящий урон слабее на 20%. Ответ отправителю пока "
                "висит в черновиках: возврат урона движок не проводит, "
                "поэтому предмет работает только как броня и кнопка на размен.",
        "tier": 2,
    },

    # прототип: Hand of Midas
    "corp_card": {
        "key": "corp_card",
        "name": "Корпоративная карта",
        "prototype": "Hand of Midas",
        "cost": 2200,
        "components": ["hand_trainer"],
        "recipe_cost": 1750,
        "shop": "base",
        "stats": {"attack_speed": 30},
        "passives": [],
        "active": {
            "targeting": "unit_enemy",
            "cast_range": 600,
            "cooldown": 90,
            "mana_cost": 0,
            "target_types": ["creep", "neutral"],
            "effects": [
                {"op": "execute", "hp_threshold": 10000,
                 "target_types": ["creep", "neutral"],
                 "on_kill": [
                     {"op": "grant_gold", "amount": 250, "target": "caster"},
                     # from_target_bounty: опыт кратен награде съеденного, как у Midas.
                     # Флат делал карту одинаковой на стажёре и на боссе леса;
                     # ctx.hit на этой ветке — как раз съеденный юнит.
                     {"op": "grant_xp", "from_target_bounty": 2.5, "target": "caster"},
                 ]},
            ],
        },
        "desc": "Списывает подрядчика со счёта: крип мгновенно исчезает, "
                "а вы получаете 250₿ и 2.5 его опыта. Чем жирнее подрядчик, "
                "тем выгоднее списание. В героя картой не ткнуть.",
        "tier": 2,
    },

    # прототип: Force Staff
    "deadline_kick": {
        "key": "deadline_kick",
        "name": "Пинок дедлайном",
        "prototype": "Force Staff",
        "cost": 2200,
        "components": ["thick_manual", "humidifier"],
        "recipe_cost": 1025,
        "shop": "base",
        "stats": {"int": 10, "hp_regen": 4},
        "passives": [],
        "active": {
            "targeting": "unit_any",
            "cast_range": 800,
            "cooldown": 18,
            "mana_cost": 100,
            "effects": [
                {"op": "push", "speed": 1000, "distance": 600, "target": "hit"},
            ],
        },
        "desc": "Двигает любого юнита на 600 туда, куда он смотрит. "
                "Работает и на союзника — «сроки горят, беги».",
        "tier": 2,
    },

    # прототип: Blink Dagger
    "vpn": {
        "key": "vpn",
        "name": "VPN",
        "prototype": "Blink Dagger",
        "cost": 2250,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {},
        "passives": [],
        "active": {
            "targeting": "point",
            "cast_range": 1200,
            "cooldown": 15,
            "mana_cost": 0,
            "blocked_by_damage": True,
            "damage_block_sec": 3.0,
            "effects": [
                {"op": "blink", "max_dist": 1200, "to": "point"},
            ],
        },
        "desc": "Мгновенный прыжок на 1200. После урона от вражеского героя "
                "соединение обрывается на 3 секунды.",
        "tier": 2,
    },

    # прототип: Mekansm
    "teambuilding": {
        "key": "teambuilding",
        "name": "Тимбилдинг",
        "prototype": "Mekansm",
        "cost": 2300,
        "components": ["armored_case", "humidifier", "sticky_notes"],
        "recipe_cost": 1420,
        "shop": "base",
        "stats": {"armor": 5, "hp_regen": 4, "all_stats": 2},
        "passives": [
            # key обязателен: без него abilities.auras() зовёт модификатор просто
            # "aura", и разные ауры затирают друг друга на одной цели.
            # unique/unique_rank: «Корпоратив» собирается из «Тимбилдинга», их ауры
            # не должны складываться — из группы остаётся сильнейшая.
            {"op": "aura", "key": "teambuilding_aura", "name": "Тимбилдинг",
             "radius": 1200, "filter": "ally", "stats": {"armor": 2, "hp_regen": 2},
             "unique": "team_support_aura", "unique_rank": 1},
        ],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 45,
            "mana_cost": 100,
            "effects": [
                {"op": "area", "radius": 750, "filter": "ally", "max_targets": 0, "effects": [
                    {"op": "heal", "amount": 275, "target": "hit"},
                    {"op": "stat_buff", "stats": {"armor": 3}, "duration": 25, "target": "hit"},
                ]},
            ],
        },
        "desc": "Аура +2 брони и +2 HP/с команде — не складывается ни со вторым "
                "тимбилдингом, ни с «Корпоративом». Активно: всем рядом 275 HP "
                "и +3 брони на 25 с. Верёвочный курс всё-таки работает.",
        "tier": 2,
    },

    # ======================================================================
    # ТИР 3 — ДОРОГИЕ
    # ======================================================================

    # прототип: Eul's Scepter of Divinity
    "sudden_call": {
        "key": "sudden_call",
        "name": "Внезапный созвон",
        "prototype": "Eul's Scepter of Divinity",
        "cost": 2725,
        "components": ["thick_manual", "powerbank"],
        "recipe_cost": 825,
        "shop": "base",
        "stats": {"int": 10, "mana": 250, "mana_regen": 4, "move_speed": 25},
        "passives": [],
        "active": {
            "targeting": "unit_any",
            "cast_range": 575,
            "cooldown": 23,
            "mana_cost": 150,
            "effects": [
                {"op": "purge", "strength": "basic", "target": "hit"},
                {"op": "cyclone", "duration": 2.5, "target": "hit", "on_land": [
                    {"op": "damage", "dtype": "magical", "amount": 100, "target": "hit"},
                ]},
            ],
        },
        "desc": "Затягивает юнита во внезапный созвон на 2.5 с: он неуязвим, "
                "но не может ничего — ни ходить, ни бить, ни кастовать. "
                "На выходе — 100 магического урона и лёгкое чувство бессмысленности.",
        "tier": 3,
    },

    # прототип: Desolator
    "public_reprimand": {
        "key": "public_reprimand",
        "name": "Публичный разнос",
        "prototype": "Desolator",
        "cost": 3500,
        "components": ["second_monitor", "second_monitor"],
        "recipe_cost": 2500,
        "shop": "base",
        "stats": {"damage": 50},
        "passives": [
            {"op": "proc_attack", "chance": 100, "effects": [
                {"op": "stat_buff", "stats": {"armor": -7}, "duration": 7, "target": "hit"},
            ]},
        ],
        "active": None,
        "desc": "+50 к урону. Каждая атака снимает с цели 7 брони на 7 секунд: "
                "после разноса при всех человек ещё долго беззащитен. Не складывается.",
        "tier": 3,
    },

    # прототип: Pipe of Insight (в основе — Hood of Defiance)
    "headphones": {
        "key": "headphones",
        "name": "Наушники с шумодавом",
        "prototype": "Pipe of Insight",
        "cost": 3600,
        "components": ["gym_membership", "humidifier", "sticky_notes"],
        "recipe_cost": 2170,
        "shop": "base",
        "stats": {"hp": 250, "hp_regen": 8, "magic_resist": 30},
        "passives": [
            # Другая группа: магсопр «Наушников» с бронёй тимбилдингов не конкурирует,
            # но свой key нужен, иначе модификатор снова назовётся "aura".
            {"op": "aura", "key": "headphones_aura", "name": "Наушники с шумодавом",
             "radius": 1200, "filter": "ally", "stats": {"magic_resist": 10}},
        ],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 60,
            "mana_cost": 100,
            "effects": [
                {"op": "area", "radius": 900, "filter": "ally", "max_targets": 0, "effects": [
                    {"op": "shield", "amount": 400, "duration": 12, "stype": "magical", "target": "hit"},
                ]},
            ],
        },
        "desc": "+30% сопротивления магии, аура +10% команде. Активно: барьер на 400 "
                "магического урона всем рядом. Опенспейс перестаёт существовать.",
        "tier": 3,
    },

    # прототип: Black King Bar
    "day_off": {
        "key": "day_off",
        "name": "Отгул",
        "prototype": "Black King Bar",
        "cost": 4050,
        "components": ["back_support_belt", "gym_membership", "second_monitor"],
        "recipe_cost": 2000,
        "shop": "base",
        "stats": {"str": 10, "damage": 24},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 70,
            "mana_cost": 0,
            "effects": [
                {"op": "purge", "strength": "strong", "target": "caster"},
                {"op": "magic_immune", "duration": 7},
            ],
        },
        "desc": "7 секунд вас просто нет: магия и контроль проходят мимо. "
                "Единственный предмет, который честно отменяет чужие планы на вас.",
        "tier": 3,
    },

    # прототип: Orchid Malevolence
    "blacklist": {
        "key": "blacklist",
        "name": "Чёрный список",
        "prototype": "Orchid Malevolence",
        "cost": 4125,
        "components": ["thick_manual", "thick_manual", "hand_trainer"],
        "recipe_cost": 1675,
        "shop": "base",
        "stats": {"int": 25, "attack_speed": 30, "mana_regen": 6},
        "passives": [],
        "active": {
            "targeting": "unit_enemy",
            "cast_range": 900,
            "cooldown": 18,
            "mana_cost": 100,
            "effects": [
                {"op": "silence", "duration": 5, "target": "hit"},
                {"op": "stat_buff", "stats": {"damage_taken_pct": 30}, "duration": 5, "target": "hit"},
            ],
        },
        "desc": "5 секунд цель не может кастовать и получает на 30% больше урона. "
                "Письма уходят, ответов нет, помощи не будет.",
        "tier": 3,
    },

    # прототип: Aghanim's Scepter
    "promotion": {
        "key": "promotion",
        "name": "Повышение",
        "prototype": "Aghanim's Scepter",
        "cost": 4200,
        "components": ["thick_manual", "gym_membership", "powerbank", "back_support_belt"],
        "recipe_cost": 750,
        "shop": "base",
        "stats": {
            "all_stats": 10, "hp": 175, "mana": 175,
            "spell_amp": 8, "cooldown_reduction": 10,
        },
        "passives": [],
        "active": None,
        "desc": "+10 ко всем атрибутам, +175 HP и маны, +8% к силе заклинаний "
                "и −10% к перезарядке. Ультимейт начинает работать по-взрослому.",
        "tier": 3,
    },

    # ======================================================================
    # ТИР 4 — ПОЗДНЯЯ ИГРА
    # ======================================================================

    # прототип: Guardian Greaves
    "corporate_party": {
        "key": "corporate_party",
        "name": "Корпоратив",
        "prototype": "Guardian Greaves",
        "cost": 4950,
        "components": ["teambuilding", "sneakers", "powerbank"],
        "recipe_cost": 1250,
        "shop": "base",
        "stats": {
            "armor": 5, "hp_regen": 6, "all_stats": 2,
            "move_speed": 45, "mana": 250,
        },
        "passives": [
            # Ранг выше, чем у «Тимбилдинга»: у носителя обоих (и у команды,
            # где есть и то и другое) остаётся только эта аура.
            {"op": "aura", "key": "corporate_party_aura", "name": "Корпоратив",
             "radius": 1200, "filter": "ally",
             "stats": {"armor": 3, "hp_regen": 3, "mana_regen": 2},
             "unique": "team_support_aura", "unique_rank": 2},
        ],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 40,
            "mana_cost": 0,
            "effects": [
                {"op": "area", "radius": 1200, "filter": "ally", "max_targets": 0, "effects": [
                    {"op": "heal", "amount": 350, "target": "hit"},
                    {"op": "restore_mana", "amount": 120, "pct": 0, "target": "hit"},
                    {"op": "purge", "strength": "basic", "target": "hit"},
                ]},
            ],
        },
        "desc": "Всей команде 350 HP, 120 маны и снятие дебаффов. Плюс аура брони, "
                "реген и кроссовки. Аура сильнее тимбилдинговой и заменяет её, "
                "а не складывается. После корпоратива команда как новая.",
        "tier": 4,
    },

    # прототип: Butterfly
    "flex_schedule": {
        "key": "flex_schedule",
        "name": "Гибкий график",
        "prototype": "Butterfly",
        "cost": 4975,
        "components": ["mech_keyboard", "hand_trainer", "second_monitor"],
        "recipe_cost": 2025,
        "shop": "base",
        "stats": {"agi": 35, "damage": 30, "attack_speed": 30, "evasion": 35},
        "passives": [],
        "active": {
            "targeting": "none",
            "cast_range": 0,
            "cooldown": 25,
            "mana_cost": 0,
            "effects": [
                {"op": "stat_buff", "stats": {"move_speed_pct": 35}, "duration": 2, "target": "caster"},
            ],
        },
        "desc": "35% атак по вам уходят в пустоту: вас просто нет на месте. "
                "Активно — +35% скорости на 2 с, «я на созвоне, перезвоню».",
        "tier": 4,
    },

    # прототип: Heart of Tarrasque
    "ergo_chair": {
        "key": "ergo_chair",
        "name": "Эргономичное кресло",
        "prototype": "Heart of Tarrasque",
        "cost": 5000,
        "components": ["gym_membership", "gym_membership", "back_support_belt"],
        "recipe_cost": 2350,
        "shop": "base",
        "stats": {"str": 45, "hp": 500, "hp_regen_pct": 1.6},
        "passives": [],
        "active": None,
        "desc": "+45 к силе, +500 HP и 1.6% максимального здоровья в секунду. "
                "Стоит как полугодовой бюджет отдела, но спина того стоит.",
        "tier": 4,
    },

    # прототип: Daedalus
    "stock_options": {
        "key": "stock_options",
        "name": "Опционы",
        "prototype": "Daedalus",
        "cost": 5150,
        "components": ["second_monitor", "second_monitor", "mech_keyboard"],
        "recipe_cost": 2150,
        "shop": "base",
        "stats": {"damage": 88},
        "passives": [
            {"op": "crit", "chance": 30, "mult": 2.4},
        ],
        "active": None,
        "desc": "+88 к урону и 30% шанс ударить на 240%. Обычно ничего, "
                "а иногда — сразу на квартиру.",
        "tier": 4,
    },

    # прототип: Divine Rapier
    "annual_bonus": {
        "key": "annual_bonus",
        "name": "Годовая премия",
        "prototype": "Divine Rapier",
        "cost": 5600,
        "components": [],
        "recipe_cost": 0,
        "shop": "base",
        "stats": {"damage": 350},
        "passives": [],
        "active": None,
        "drop_on_death": True,
        "desc": "+350 к урону. При смерти выпадает на пол, и поднять её может кто угодно — "
                "включая менеджмент. Покупается целиком, по частям премию не выдают.",
        "tier": 4,
    },
}


# ==========================================================================
# Раскладка магазина для UI
# ==========================================================================
# Каждый предмет ровно в одной категории, порядок внутри категории — по цене.

SHOP_LAYOUT: dict = {
    "Расходники": [
        "energy_drink",
        "observer_ward",
        "activity_tracker",
        "dnd_status",
        "corporate_taxi",
        "coffee_mug",
    ],
    "Атрибуты": [
        "paperclip",
        "sticky_notes",
        "humidifier",
        "desk_drawer",
        "back_support_belt",
        "sneakers",
        "powerbank",
        "thick_manual",
        "gym_membership",
    ],
    "Броня": [
        "armored_case",
        "sick_leave",
        "reply_all",
        "teambuilding",
        "headphones",
        "day_off",
        "corporate_party",
        "ergo_chair",
    ],
    "Оружие": [
        "hand_trainer",
        "second_monitor",
        "running_sneakers",
        "mech_keyboard",
        "public_reprimand",
        "flex_schedule",
        "stock_options",
        "annual_bonus",
    ],
    "Артефакты": [
        "corp_card",
        "deadline_kick",
        "vpn",
        "sudden_call",
        "blacklist",
        "promotion",
    ],
}


# ==========================================================================
# Чего по-прежнему не хватает движку
# ==========================================================================
# Закрыто за прошлые круги: grant_gold/grant_xp (в том числе from_target_bounty),
# target_types, cyclone, ghost, restore_mana, true_sight, drop_on_death,
# reflect_pct + duration у on_take_damage, blocked_by_damage, break_on_damage,
# unique/unique_rank, gain_charge_on_enemy_cast — всё это уже используется выше.
# Семантика отрицательного damage_taken_pct подтверждена по коду:
# entities.damage_taken_mult = max(0, 1 + pct/100), то есть -20 даёт ×0.8.
# Осталось следующее. Каждый пункт сейчас обойдён, и обход виден игроку.

ENGINE_REQUESTS: list[str] = [
    "трата накопленных зарядов. Накопление заработало: gain_charge_on_enemy_cast "
    "и max_charges у «Ящика стола» (Magic Wand) реально наращивают счётчик "
    "(world._charge_nearby_wands), и он виден в интерфейсе. А списывать заряды "
    "умеет только ветка расходника в world.use_item (`if it.is_consumable`), "
    "которая вдобавок удаляет предмет на нуле — Magic Wand так вести себя не должен. "
    "Нужно одно из двух: поле у active вида spend_charges: N, либо масштабирование "
    "величин от числа зарядов (heal/restore_mana с per_charge). До этого активка "
    "остаётся фиксированной на 200 HP / 200 маны, а заряды — украшением.",

    "возвращённый урон не должен возвращаться обратно, и reflect_pct без вложенного "
    "damage вообще ничего не делает. Из-за второго «Ответить всем» (Blade Mail) "
    "сейчас не возвращает ни единицы урона: world.run_damage_reactions отбрасывает "
    "реакцию с пустым effects (`if not inner: continue`), а pct подставляется только "
    "в уже существующую операцию damage. Данными это чинится одной строкой внутри "
    "on_take_damage — {'op': 'damage', 'dtype': 'pure', 'amount': 0, 'target': 'hit'}, "
    "— но включать её нельзя, пока возврат не защищён от самого себя: у двух героев "
    "с активным «Ответить всем» отскок идёт по кругу, каждый раз ×0.8 (их же "
    "damage_taken_pct -20), нуля не достигает и обрывается только RecursionError. "
    "Нужен признак «этот урон не отражается» на стороне движка.",

    # Подтверждено координатором как «не будет» — оставлено, чтобы не забыть,
    # что эти предметы намеренно отличаются от прототипов.
    "stat_swap / toggle предметов: Power Treads («Беговые кроссовки») зафиксированы "
    "на str 8 и не переключают атрибут.",

    "юнита-наблюдателя не будет: призываемые варды в движок не заложены. "
    "«Камера наблюдения» поэтому не вард, а личный обзор на 2 минуты, и так "
    "и написана в desc, чтобы от неё не ждали дотовского Observer Ward. "
    "Побочно: summon с незнакомым unit молча спавнит крипа ближнего боя "
    "(content.creep_def падает на _FALLBACK_CREEPS) — именно это предмет и делал.",

    "убывающая длительность при повторном использовании: «Отгул» (BKB) держит "
    "фиксированные 7 с вместо дотовских 10→5.",

    "ultimate_upgrade: «Повышение» (Aghanim) не меняет ульту, а выдаёт "
    "spell_amp 8 + cooldown_reduction 10.",

    "отложенный накопленный урон: «Чёрный список» (Orchid) не взрывается в конце "
    "сайленса, а всё время держит damage_taken_pct 30.",
]


# ==========================================================================
# Валидация
# ==========================================================================

# §3 ABILITY_SPEC.md + операции, добавленные движком по прошлому ENGINE_REQUESTS.
_ALLOWED_OPS = frozenset({
    "damage", "heal", "dot", "execute", "lifesteal_burst",
    "stun", "slow", "silence", "root", "disarm", "hex", "taunt", "purge",
    "shield", "invulnerable", "magic_immune", "invisible", "cheat_death", "stat_buff",
    "blink", "pull", "push", "leap",
    "projectile", "area", "aura", "channel", "delayed", "global",
    "passive_stats", "proc_attack", "crit", "bash", "evasion", "lifesteal",
    "cleave", "on_kill", "on_take_damage",
    "summon", "illusion",
    # расширение движка
    "chain", "restore_mana", "mana_burn", "grant_gold", "grant_xp",
    "true_sight", "ghost", "cyclone",
})

# §5 ABILITY_SPEC.md — полный список характеристик, на которые можно влиять.
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

_ALLOWED_SHOPS = frozenset({"base", "secret", "consumable"})
_ALLOWED_TARGETING = frozenset({
    "none", "point", "unit_enemy", "unit_ally", "unit_any",
    "vector", "toggle", "passive", "channel",
})
_ALLOWED_TARGETS = frozenset({"hit", "caster", "allies_in_radius", "enemies_in_radius"})
# "enemy" больше не задевает строения — для них есть "buildings" и "enemy_all".
_ALLOWED_FILTERS = frozenset({"enemy", "ally", "all", "creeps", "buildings", "enemy_all"})
_ALLOWED_TARGET_TYPES = frozenset({"creep", "neutral", "hero", "tower", "barracks"})

# Ключи, под которыми у операций-обёрток лежат вложенные эффекты.
_NESTED_EFFECT_KEYS = ("effects", "on_hit", "on_tick", "on_kill", "on_land")

_REQUIRED_FIELDS = (
    "key", "name", "prototype", "cost", "components", "recipe_cost",
    "shop", "stats", "passives", "active", "desc", "tier",
)
# Опечатка в имени поля = молча отключённая механика, поэтому белый список.
_KNOWN_ITEM_FIELDS = frozenset(_REQUIRED_FIELDS) | {
    "charges", "drop_on_death", "target_types",
    "blocked_by_damage", "damage_block_sec",
    "gain_charge_on_enemy_cast", "max_charges",
}
_KNOWN_ACTIVE_FIELDS = frozenset({
    "targeting", "cast_range", "cooldown", "mana_cost", "effects",
    "target_types", "blocked_by_damage", "damage_block_sec",
})

_SHOP_CATEGORIES = ("Расходники", "Атрибуты", "Броня", "Оружие", "Артефакты")

# Выше этого порога execute перестаёт быть добиванием и становится «убить кого угодно».
_EXECUTE_SAFE_THRESHOLD = 1500


def _check_stats(stats, where, problems):
    """Все ключи в stats обязаны быть из §5."""
    if not isinstance(stats, dict):
        problems.append(f"{where}: stats должен быть dict, а не {type(stats).__name__}")
        return
    for stat_key, value in stats.items():
        if stat_key not in _ALLOWED_STATS:
            problems.append(
                f"{where}: характеристика {stat_key!r} отсутствует в ABILITY_SPEC.md §5. "
                f"Разрешены: {', '.join(sorted(_ALLOWED_STATS))}"
            )
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            problems.append(f"{where}: значение {stat_key!r} должно быть числом, получено {value!r}")


def _check_target_types(value, where, problems):
    """target_types — непустой список из известных типов юнитов."""
    if not isinstance(value, list) or not value:
        problems.append(f"{where}: target_types должен быть непустым списком, получено {value!r}")
        return
    unknown = sorted(set(value) - _ALLOWED_TARGET_TYPES)
    if unknown:
        problems.append(
            f"{where}: неизвестные target_types {unknown}, "
            f"разрешены {sorted(_ALLOWED_TARGET_TYPES)}"
        )


def _max_number(value):
    """Число или список чисел по уровням (§8.1) -> максимум."""
    if isinstance(value, list):
        numbers = [v for v in value if isinstance(v, (int, float))]
        return max(numbers) if numbers else 0
    return value if isinstance(value, (int, float)) else 0


def _check_effects(effects, where, problems):
    """Рекурсивно: op из §3, stats из §5, target из §4, filter и target_types."""
    if not isinstance(effects, list):
        problems.append(f"{where}: ожидался список эффектов, получено {type(effects).__name__}")
        return

    # Дубль в одном списке: эфирная форма входит в маску «не может атаковать»
    # (consts.CANNOT_ATTACK содержит F_ETHEREAL), так что disarm рядом с ghost —
    # лишняя строка. Она переживёт любую правку ghost и начнёт врать в тултипе.
    ops_here = [e.get("op") for e in effects if isinstance(e, dict)]
    if "ghost" in ops_here and "disarm" in ops_here:
        problems.append(
            f"{where}: ghost и disarm в одном списке эффектов — дубль. "
            f"Эфирная форма сама запрещает атаковать, отдельный disarm "
            f"ничего не добавляет."
        )

    for i, eff in enumerate(effects):
        sub = f"{where}[{i}]"
        if not isinstance(eff, dict):
            problems.append(f"{sub}: эффект должен быть dict, получено {type(eff).__name__}")
            continue
        op = eff.get("op")
        if op is None:
            problems.append(f"{sub}: у эффекта нет ключа 'op'")
            continue
        if op not in _ALLOWED_OPS:
            problems.append(
                f"{sub}: op={op!r} не поддерживается движком "
                f"(правило ABILITY_SPEC.md §8.2 — новые op выдумывать нельзя)"
            )
        if "stats" in eff:
            _check_stats(eff["stats"], f"{sub}(op={op})", problems)
        target = eff.get("target")
        if target is not None and target not in _ALLOWED_TARGETS:
            problems.append(
                f"{sub}: target={target!r} отсутствует в ABILITY_SPEC.md §4 "
                f"(разрешены: {', '.join(sorted(_ALLOWED_TARGETS))})"
            )
        if "filter" in eff and eff["filter"] not in _ALLOWED_FILTERS:
            problems.append(
                f"{sub}: filter={eff['filter']!r}, разрешены {sorted(_ALLOWED_FILTERS)}"
            )
        if "target_types" in eff:
            _check_target_types(eff["target_types"], sub, problems)

        # Уникальность: из группы обязан оставаться сильнейший, а «сильнейший»
        # определяется только рангом. Без unique_rank движок берёт 1 для всех
        # участников группы, и выживает не сильный эффект, а наложенный первым.
        if "unique" in eff or "unique_rank" in eff:
            group = eff.get("unique")
            if not isinstance(group, str) or not group:
                problems.append(
                    f"{sub}: unique_rank={eff.get('unique_rank')!r} без непустого "
                    f"имени группы unique ничего не делает"
                )
            elif "unique_rank" not in eff:
                problems.append(
                    f"{sub}: группа unique={group!r} задана без unique_rank. "
                    f"Движок возьмёт ранг 1 всем участникам группы, и останется "
                    f"не сильнейший эффект, а тот, что лёг первым"
                )
            elif not isinstance(eff["unique_rank"], (int, float)) or \
                    isinstance(eff["unique_rank"], bool):
                problems.append(
                    f"{sub}: unique_rank={eff['unique_rank']!r} должен быть числом"
                )

        # Ауре нужен свой key: без него abilities.auras() зовёт модификатор
        # просто "aura", и две разные ауры затирают друг друга на одной цели.
        if op == "aura" and not eff.get("key"):
            problems.append(
                f"{sub}: у ауры нет key — движок назовёт модификатор 'aura', "
                f"и любая другая аура затрёт эту на той же цели"
            )

        # ghost уже усиливает магию ровно на 40% (combat.ETHEREAL_MAGIC_AMP).
        if op == "ghost" and eff.get("magic_amp"):
            problems.append(
                f"{sub}: ghost с magic_amp={eff['magic_amp']!r} — двойной счёт. "
                f"Эфирная форма усиливает магию сама, а magic_amp вешает сверх "
                f"этого damage_taken_pct на все типы урона, включая чистый"
            )

        # Защита от бага «execute убивает героя одним нажатием».
        if op == "execute":
            threshold = _max_number(eff.get("hp_threshold"))
            types = eff.get("target_types")
            if threshold > _EXECUTE_SAFE_THRESHOLD:
                if not types:
                    problems.append(
                        f"{sub}: execute с hp_threshold={threshold} убьёт кого угодно, "
                        f"включая героя. Такому порогу обязателен target_types "
                        f"без 'hero' (например ['creep', 'neutral'])."
                    )
                elif "hero" in types:
                    problems.append(
                        f"{sub}: execute с hp_threshold={threshold} и 'hero' в target_types — "
                        f"это мгновенное убийство любого героя."
                    )

        if op == "on_take_damage":
            if "duration" not in eff:
                problems.append(
                    f"{sub}: у on_take_damage нет duration — движок подставит своё значение, "
                    f"и предмет будет работать не так, как написано в desc"
                )
            reflect = eff.get("reflect_pct")
            if reflect is not None and not (0 <= reflect <= 100):
                problems.append(f"{sub}: reflect_pct={reflect!r}, ожидалось 0..100")
            if not reflect and not eff.get("effects"):
                problems.append(
                    f"{sub}: on_take_damage без reflect_pct и без effects ничего не делает"
                )
            # На самом деле пустого effects мало и при reflect_pct: движок только
            # подставляет процент в уже описанную операцию damage, а реакцию
            # с пустым списком отбрасывает целиком (run_damage_reactions).
            # Жёсткой проверкой это пока не сделано осознанно: «Ответить всем»
            # намеренно оставлен выключенным до защиты возврата от самого себя,
            # см. ENGINE_REQUESTS.

        for nested_key in _NESTED_EFFECT_KEYS:
            if nested_key in eff:
                _check_effects(eff[nested_key], f"{sub}.{nested_key}", problems)


def _check_schema(key, item, problems):
    """Поля предмета по §7 + расширения движка + базовая типизация."""
    for field in _REQUIRED_FIELDS:
        if field not in item:
            problems.append(f"{key}: нет обязательного поля {field!r} (ABILITY_SPEC.md §7)")
    unknown = sorted(set(item) - _KNOWN_ITEM_FIELDS)
    if unknown:
        problems.append(
            f"{key}: неизвестные поля {unknown} — опечатка молча отключит механику. "
            f"Разрешены: {sorted(_KNOWN_ITEM_FIELDS)}"
        )
    if item.get("key") != key:
        problems.append(f"{key}: поле 'key' == {item.get('key')!r}, а ключ словаря — {key!r}")
    if key != key.lower() or " " in key or "-" in key:
        problems.append(f"{key}: ключ обязан быть snake_case в нижнем регистре")
    shop = item.get("shop")
    if shop not in _ALLOWED_SHOPS:
        problems.append(f"{key}: shop={shop!r}, разрешено только {sorted(_ALLOWED_SHOPS)}")
    if item.get("tier") not in (1, 2, 3, 4):
        problems.append(f"{key}: tier={item.get('tier')!r}, ожидалось 1..4")
    if not item.get("name"):
        problems.append(f"{key}: пустое имя")
    if not item.get("desc"):
        problems.append(f"{key}: пустое описание")
    if not item.get("prototype"):
        problems.append(f"{key}: не указан prototype — предмет Dota 2, который он воспроизводит")

    _check_charges(key, item, problems)

    if "drop_on_death" in item and not isinstance(item["drop_on_death"], bool):
        problems.append(f"{key}: drop_on_death={item['drop_on_death']!r}, ожидался bool")
    if "target_types" in item:
        _check_target_types(item["target_types"], key, problems)
    _check_damage_block(item, key, problems)

    _check_stats(item.get("stats", {}), f"{key}.stats", problems)
    _check_effects(item.get("passives", []), f"{key}.passives", problems)

    active = item.get("active")
    if active is not None:
        if not isinstance(active, dict):
            problems.append(f"{key}.active: ожидался dict или None, получено {type(active).__name__}")
        else:
            unknown = sorted(set(active) - _KNOWN_ACTIVE_FIELDS)
            if unknown:
                problems.append(f"{key}.active: неизвестные поля {unknown}")
            targeting = active.get("targeting")
            if targeting not in _ALLOWED_TARGETING:
                problems.append(
                    f"{key}.active: targeting={targeting!r} отсутствует в ABILITY_SPEC.md §2"
                )
            for field in ("cooldown", "mana_cost"):
                if field not in active:
                    problems.append(f"{key}.active: нет поля {field!r}")
            if "target_types" in active:
                _check_target_types(active["target_types"], f"{key}.active", problems)
            _check_damage_block(active, f"{key}.active", problems)
            _check_effects(active.get("effects", []), f"{key}.active.effects", problems)
            if not active.get("effects"):
                problems.append(f"{key}.active: активка без эффектов — тогда должно быть None")


def _check_charges(key, item, problems):
    """Заряды: разовые у расходника и накопительные у копилок.

    Оба накопительных поля движок читает со значениями по умолчанию
    (world._charge_nearby_wands берёт max_charges=20, если поля нет), поэтому
    потолок обязан стоять в данных, а не подразумеваться.
    """
    shop = item.get("shop")
    charges = item.get("charges")
    gains = item.get("gain_charge_on_enemy_cast")
    cap = item.get("max_charges")

    if gains is not None and not isinstance(gains, bool):
        problems.append(f"{key}: gain_charge_on_enemy_cast={gains!r}, ожидался bool")
    if gains and not (isinstance(cap, int) and not isinstance(cap, bool) and cap >= 1):
        problems.append(
            f"{key}: gain_charge_on_enemy_cast=True требует max_charges >= 1, "
            f"получено {cap!r}. Без него потолок зарядов задаёт движок (20), "
            f"а не данные, и правка баланса пройдёт мимо предмета."
        )
    if cap is not None and not gains:
        problems.append(
            f"{key}: max_charges={cap!r} без gain_charge_on_enemy_cast=True — "
            f"копить заряды нечем, поле ничего не ограничивает"
        )

    if shop == "consumable":
        if not isinstance(charges, int) or isinstance(charges, bool) or charges < 1:
            problems.append(
                f"{key}: расходнику нужен charges >= 1 (сколько применений в покупке), "
                f"получено {charges!r}"
            )
        return

    if charges is None:
        return
    if not gains:
        problems.append(
            f"{key}: charges={charges!r} у не-расходника, который ничего не копит. "
            f"Списывать заряды движок умеет только веткой расходника в use_item, "
            f"и она же удаляет предмет на нуле — см. ENGINE_REQUESTS"
        )
    elif not isinstance(charges, int) or isinstance(charges, bool) or charges < 0:
        problems.append(
            f"{key}: стартовый charges={charges!r}, ожидалось неотрицательное целое"
        )
    elif isinstance(cap, int) and charges > cap:
        problems.append(
            f"{key}: стартовый charges={charges} больше max_charges={cap}"
        )


def _check_damage_block(holder, where, problems):
    """blocked_by_damage и damage_block_sec идут только парой."""
    blocked = holder.get("blocked_by_damage")
    seconds = holder.get("damage_block_sec")
    if blocked is not None and not isinstance(blocked, bool):
        problems.append(f"{where}: blocked_by_damage={blocked!r}, ожидался bool")
    if blocked and (not isinstance(seconds, (int, float)) or seconds <= 0):
        problems.append(
            f"{where}: blocked_by_damage=True требует damage_block_sec > 0, получено {seconds!r}"
        )
    if seconds is not None and not blocked:
        problems.append(
            f"{where}: damage_block_sec={seconds!r} без blocked_by_damage=True ничего не делает"
        )


def _check_recipe_math(key, item, problems):
    """Компоненты существуют, арифметика цены сходится."""
    components = item.get("components", [])
    if not isinstance(components, list):
        problems.append(f"{key}: components должен быть списком")
        return
    missing = [c for c in components if c not in ITEMS]
    if missing:
        problems.append(
            f"{key}: в components ссылки на несуществующие предметы: {', '.join(sorted(set(missing)))}"
        )
        return
    if key in components:
        problems.append(f"{key}: предмет указан в собственных components")
        return

    cost = item.get("cost")
    recipe_cost = item.get("recipe_cost", 0)
    if not isinstance(cost, int) or cost < 0:
        problems.append(f"{key}: cost={cost!r}, ожидалось неотрицательное целое")
        return
    if not isinstance(recipe_cost, int) or recipe_cost < 0:
        problems.append(f"{key}: recipe_cost={recipe_cost!r}, ожидалось неотрицательное целое")
        return

    if not components:
        if recipe_cost != 0:
            problems.append(
                f"{key}: предмет без components продаётся целиком, "
                f"recipe_cost обязан быть 0, а он {recipe_cost}"
            )
        return

    parts = sum(ITEMS[c]["cost"] for c in components)
    if cost != parts + recipe_cost:
        breakdown = " + ".join(f"{c}({ITEMS[c]['cost']})" for c in components)
        problems.append(
            f"{key}: cost={cost}, а по рецепту {breakdown} + рецепт({recipe_cost}) "
            f"= {parts + recipe_cost}. Расхождение {cost - parts - recipe_cost}."
        )


def _check_no_cycles(problems):
    """Обход в глубину по графу рецептов: ни один предмет не собирается из себя."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {key: WHITE for key in ITEMS}

    def walk(key, stack):
        color[key] = GREY
        for comp in ITEMS[key].get("components", []):
            if comp not in ITEMS:
                continue  # уже отловлено в _check_recipe_math
            if color[comp] == GREY:
                loop = " -> ".join(stack[stack.index(comp):] + [comp]) if comp in stack \
                    else f"{key} -> {comp}"
                problems.append(f"цикл в рецептах: {loop}")
            elif color[comp] == WHITE:
                walk(comp, stack + [comp])
        color[key] = BLACK

    for key in ITEMS:
        if color[key] == WHITE:
            walk(key, [key])


def _check_shop_layout(problems):
    """Все категории на месте, все ключи существуют, каждый предмет ровно раз."""
    if not isinstance(SHOP_LAYOUT, dict):
        problems.append("SHOP_LAYOUT должен быть dict")
        return

    expected = set(_SHOP_CATEGORIES)
    actual = set(SHOP_LAYOUT)
    if actual != expected:
        if expected - actual:
            problems.append(f"SHOP_LAYOUT: нет категорий {sorted(expected - actual)}")
        if actual - expected:
            problems.append(
                f"SHOP_LAYOUT: лишние категории {sorted(actual - expected)}, "
                f"ожидались только {sorted(expected)}"
            )

    seen: dict[str, list[str]] = {}
    for category, keys in SHOP_LAYOUT.items():
        if not isinstance(keys, list):
            problems.append(f"SHOP_LAYOUT[{category!r}]: ожидался список ключей")
            continue
        for key in keys:
            if key not in ITEMS:
                problems.append(f"SHOP_LAYOUT[{category!r}]: предмета {key!r} нет в ITEMS")
                continue
            seen.setdefault(key, []).append(category)

    for key, categories in sorted(seen.items()):
        if len(categories) > 1:
            problems.append(
                f"{key}: попал сразу в несколько категорий SHOP_LAYOUT: {categories}"
            )

    forgotten = sorted(set(ITEMS) - set(seen))
    if forgotten:
        problems.append(
            f"SHOP_LAYOUT: предметы не попали ни в одну категорию "
            f"(игрок их не увидит): {', '.join(forgotten)}"
        )

    # Расходники и только они лежат в consumable-магазине.
    for key in SHOP_LAYOUT.get("Расходники", []):
        if key in ITEMS and ITEMS[key]["shop"] != "consumable":
            problems.append(
                f"{key}: лежит в категории «Расходники», но shop={ITEMS[key]['shop']!r}"
            )
    for key, item in ITEMS.items():
        if item.get("shop") == "consumable" and key not in SHOP_LAYOUT.get("Расходники", []):
            problems.append(f"{key}: shop='consumable', но лежит не в категории «Расходники»")


def validate() -> None:
    """Проверяет целостность магазина. Кидает AssertionError со списком проблем."""
    problems: list[str] = []

    if not ITEMS:
        raise AssertionError("ITEMS пуст — магазина нет")

    for key, item in ITEMS.items():
        if not isinstance(item, dict):
            problems.append(f"{key}: предмет должен быть dict, получено {type(item).__name__}")
            continue
        _check_schema(key, item, problems)
        _check_recipe_math(key, item, problems)

    _check_no_cycles(problems)
    _check_shop_layout(problems)

    if problems:
        raise AssertionError(
            "items.py не проходит проверку по docs/ABILITY_SPEC.md — "
            f"{len(problems)} проблем(ы):\n  - " + "\n  - ".join(problems)
        )


if __name__ == "__main__":
    validate()
    by_tier: dict[int, int] = {}
    for _item in ITEMS.values():
        by_tier[_item["tier"]] = by_tier.get(_item["tier"], 0) + 1
    print(f"{len(ITEMS)} предметов OK")
    for _tier in sorted(by_tier):
        print(f"  тир {_tier}: {by_tier[_tier]}")
