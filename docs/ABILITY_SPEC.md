# Спецификация примитивов движка

Это **контракт**. Любая способность героя, предмет или эффект должны выражаться
только через перечисленные ниже примитивы. Если нужного примитива нет — это отдельный
запрос на расширение движка, а не повод придумать свой.

Всё описывается python-словарями (они же сериализуются в JSON для клиента).

---

## 1. Определение способности

```python
{
  "key": "sysadmin_hook",              # уникальный ID, snake_case
  "name": "Патч-корд",                 # русское отображаемое имя
  "hotkey": "Q",                       # Q | W | E | R | D | F
  "desc": "Бросает патч-корд...",      # текст для тултипа
  "targeting": "point",                # см. §2
  "cast_range": 1000,                  # 0 = неограниченно / не применимо
  "cast_point": 0.3,                   # с, замах перед применением
  "cast_backswing": 0.5,               # с, анимация после
  "cooldown": [14, 12, 10, 8],         # по уровням способности
  "mana_cost": [110, 120, 130, 140],
  "max_level": 4,                      # 4 для обычных, 3 для ульты
  "level_req": [1, 3, 5, 7],           # мин. уровень героя для каждого уровня скилла
  "pierces_magic_immunity": false,
  "dispellable": true,
  "aoe_radius": 0,                     # для превью на клиенте, 0 = нет
  "effects": [ ... ]                   # см. §3
}
```

Ульты: `max_level: 3`, `level_req: [6, 12, 18]`.
Обычные: `max_level: 4`, `level_req: [1, 3, 5, 7]`.

## 2. Способы наведения (`targeting`)

| Значение | Смысл |
|---|---|
| `none` | Применяется мгновенно на себя/вокруг себя |
| `point` | Клик в точку карты |
| `unit_enemy` | Клик во вражеского юнита |
| `unit_ally` | Клик в союзного юнита |
| `unit_any` | Клик в любого юнита |
| `vector` | Точка старта + направление (два клика) |
| `toggle` | Вкл/выкл, тратит ману периодически |
| `passive` | Не применяется, работает всегда |
| `channel` | Канал: применяется и держится, прерывается движением/станом |

## 3. Эффекты (`effects`) — список операций

Каждая операция — словарь с `op`. Значения, зависящие от уровня скилла, —
списки длиной `max_level`. Скаляр = одинаково на всех уровнях.

### Урон и лечение
```python
{"op": "damage", "dtype": "magical", "amount": [100,175,250,325], "target": "hit"}
    # dtype: physical | magical | pure
    # target: hit | self | caster (см. §4)
{"op": "heal", "amount": [90,150,210,270], "target": "hit"}
{"op": "dot", "dtype": "magical", "dps": [30,45,60,75], "duration": 4, "interval": 0.5}
{"op": "execute", "hp_threshold": [250,325,400], "on_kill": [...]}   # добивание
{"op": "lifesteal_burst", "pct": 50}
```

### Контроль
```python
{"op": "stun",    "duration": [1.4,1.8,2.2,2.6]}
{"op": "slow",    "move_pct": [-20,-30,-40,-50], "attack_speed": [-20,-30,-40,-50], "duration": 4}
{"op": "silence", "duration": [3,4,5,6]}
{"op": "root",    "duration": [1.5,2,2.5,3]}      # нельзя двигаться, можно бить/кастовать
{"op": "disarm",  "duration": 3}                   # нельзя атаковать
{"op": "hex",     "duration": [1.5,2,2.5,3]}       # slow + silence + disarm + блок предметов
{"op": "taunt",   "duration": [2,2.5,3,3.5], "radius": 300}  # враги обязаны атаковать кастера
{"op": "purge",   "strength": "basic"}             # basic | strong
```

### Защита и баффы
```python
{"op": "shield", "amount": [80,130,180,230], "duration": 12, "stype": "all"}  # all|magical|physical
{"op": "invulnerable", "duration": [2,3,4,5]}
{"op": "magic_immune", "duration": [4,5,6]}
{"op": "invisible", "duration": 20, "fade_delay": 0.6}
{"op": "cheat_death", "duration": [4,5,6]}        # не может умереть, HP минимум 1
{"op": "stat_buff", "stats": {"armor": [2,4,6,8], "move_speed_pct": [8,12,16,20]}, "duration": 10}
```

### Перемещение
```python
{"op": "blink", "max_dist": 1200, "to": "point"}       # to: point | target | behind_target
{"op": "pull", "speed": 1450, "to": "caster"}          # тащит цель к кастеру
{"op": "push", "speed": 1000, "distance": 600}         # отталкивает
{"op": "leap", "distance": 500, "duration": 0.4}       # прыжок кастера
```

### Формы доставки (обёртки над эффектами)
```python
{"op": "projectile", "speed": 1450, "radius": 100, "pierce": false,
 "max_dist": 1100, "on_hit": [ ...вложенные эффекты... ]}

{"op": "area", "radius": [300,350,400,450], "filter": "enemy",   # enemy|ally|all|creeps
 "max_targets": 0, "effects": [ ... ]}

{"op": "aura", "radius": 900, "filter": "ally", "stats": {...}}  # постоянная, для passive

{"op": "channel", "duration": [3,4,5], "interval": 0.5,
 "break_on_move": true, "on_tick": [ ... ]}

{"op": "delayed", "delay": 1.2, "effects": [ ... ]}   # отложенное срабатывание
{"op": "global", "filter": "enemy", "effects": [...]} # по всей карте (для ультов уровня Зевса)
```

### Пассивки и модификаторы атаки
```python
{"op": "passive_stats", "stats": {"damage": [10,20,30,40], "hp": [0,0,0,0]}}
{"op": "proc_attack", "chance": [15,20,25,30], "effects": [...]}   # шанс при атаке
{"op": "crit", "chance": [20,25,30,35], "mult": [1.8,2.0,2.2,2.4]}
{"op": "bash", "chance": [10,12,14,16], "duration": 1.2}
{"op": "evasion", "pct": [10,15,20,25]}
{"op": "lifesteal", "pct": [10,15,20,25]}
{"op": "cleave", "pct": [25,35,45,55], "radius": 300}
{"op": "on_kill", "effects": [...]}                   # триггер при убийстве
{"op": "on_take_damage", "effects": [...]}            # триггер при получении урона
```

### Призыв
```python
{"op": "summon", "unit": "intern", "count": [1,2,3,4], "duration": 40}
{"op": "illusion", "count": [1,1,2,2], "duration": 20, "dmg_out_pct": 40, "dmg_in_pct": 200}
```

## 4. Цели эффекта (`target` внутри операции)

| Значение | Смысл |
|---|---|
| `hit` | То, во что попали (цель каста, жертва снаряда, юнит в области) |
| `caster` | Сам кастер |
| `allies_in_radius` | Союзники в `radius` от точки применения |
| `enemies_in_radius` | Враги в `radius` |

По умолчанию — `hit`.

## 5. Характеристики, на которые можно влиять

Валидные ключи в `stats` (для `stat_buff`, `passive_stats`, `aura`, предметов):

```
str, agi, int, all_stats
hp, mana, max_hp_pct, max_mana_pct
hp_regen, mana_regen, hp_regen_pct, mana_regen_pct
damage, attack_speed, attack_range, bat_pct
armor, magic_resist, status_resist, evasion
move_speed, move_speed_pct
spell_amp, cooldown_reduction
damage_taken_pct        # положительное = получает больше урона (усиление входящего)
vision_day, vision_night
```

## 6. Боевая модель (как в Dota 2 — не переучиваться)

- **Броня:** `снижение = 0.06*A / (1 + 0.06*|A|)`; отрицательная броня усиливает урон
- **Магсопр:** базово 25%, источники складываются мультипликативно:
  `итог = 1 - Π(1 - r_i)`
- **Чистый урон** игнорирует и броню, и магсопр (но не блокируется маг. иммунитетом, если не указано)
- **Скорость атаки:** `IAS = 100 + agi + бонусы`, зажата в `[20, 700]`;
  `время_атаки = BAT / (IAS/100)`, BAT обычно 1.7
- **Атрибуты:** 1 str = +22 HP и +0.1 HP/с · 1 agi = +0.167 брони и +1 к скорости атаки ·
  1 int = +12 маны, +0.05 маны/с и +0.1% усиления заклинаний
- Основной атрибут даёт **+1 к урону** за очко. Универсальные герои — +0.7 за очко каждого.
- **Сопротивление статусу** сокращает длительность контроля мультипликативно

## 7. Определение предмета

```python
{
  "key": "vpn",
  "name": "VPN",
  "cost": 2250,                        # итоговая цена (для рецептов — сумма)
  "components": ["boots", "recipe_vpn"],  # [] для базового предмета
  "recipe_cost": 0,
  "shop": "base",                      # base | secret | consumable
  "stats": {"move_speed": 45},         # пассивные характеристики
  "passives": [ ...effects... ],       # пассивные эффекты (proc, aura, evasion...)
  "active": {                          # null, если предмета нет активки
     "targeting": "point", "cast_range": 1200,
     "cooldown": 15, "mana_cost": 0,
     "effects": [ ... ]
  },
  "desc": "Телепортирует на 1200...",
  "tier": 2                            # 1 базовый, 2 средний, 3 дорогой, 4 поздний
}
```

## 8. Правила, обязательные к соблюдению

1. Любое число, зависящее от уровня, — **список** длиной `max_level`. Никаких формул в данных.
2. Никаких новых `op`. Нужен новый — обоснуй отдельно, не выдумывай молча.
3. Все имена, описания и тултипы — **на русском**. Ключи — английский snake_case.
4. Каждая способность обязана быть узнаваемым аналогом чего-то из Dota 2.
   В комментарии к способности указывай прототип: `# прототип: Pudge — Meat Hook`.
5. Числа балансим под **Turbo**: золото и опыт примерно ×2, респавн ×0.5 от обычной доты.
