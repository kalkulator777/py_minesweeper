import tkinter as tk
import tkinter.messagebox
import random

# Окно
root = tk.Tk()
root.title("Python Minesweeper")

# Параметры игры
Rows = 7
# Rows = input('Кол-во ячеек по горизонтали')
Columns = 7
# Columns = input('Кол-во ячеек по вертикали')
Mines = 10
# Mines = input('Количество мин')

Cells = Rows * Columns - Mines
CellsOpened = 0

buttons = {}
mines = []

# Генерация кнопок
for x in range(0, Rows):
    for y in range(0, Columns):
        btn = tk.Button(root, text='', width=2, height=1, command=lambda x=x, y=y: on_click(x, y))
        btn.grid(row=x, column=y, sticky=tk.N+tk.W+tk.S+tk.E)
        buttons[(x, y)] = btn

# Генерация мин
while len(mines) < Mines:
    x, y = random.randint(0, Rows-1), random.randint(0, Columns-1)
    if (x, y) not in mines:
        mines.append((x, y))
        
# Нажатие на ячейку
def on_click(x, y):
    global Cells
    global CellsOpened
    CellsOpened += 1
    if (CellsOpened == Cells):
        game_win()
    else:
        # Нажатие на мину
        if (x, y) in mines:
            buttons[(x, y)].config(background='red')
            game_over()
        # Мины вокруг ячейки
        else:
            count = sum(1 for dx in [-1, 0, 1] for dy in [-1, 0, 1] if (x+dx, y+dy) in mines)
            buttons[(x, y)].config(background='white', text=str(count))
            buttons[(x, y)]['state'] = 'disabled'

def game_win():
    for (x, y) in buttons:
        buttons[(x, y)].config(background='green')
    for (x, y) in mines:
        buttons[(x, y)].config(background='red')
    for x, y in buttons:
        buttons[(x, y)]['state'] = 'disabled'
    tkinter.messagebox.showinfo(message='Вы выиграли!')
# Проигрыш
def game_over():
    for (x, y) in mines:
        buttons[(x, y)].config(background='red')
    for x, y in buttons:
        buttons[(x, y)]['state'] = 'disabled'
    tkinter.messagebox.showinfo(message="Вы проиграли!")

# Запуск главного цикла игры
root.mainloop()