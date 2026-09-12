import random
import time

# screen -S games_bot -d -m python3 /home/bot-user/games_bot/games_bot.py
from games_bot_config import DB_CONFIG, API_TOKEN, BOT_SETTINGS
from bot_messages import get_translation, get_time_translation, monthNames
global context_user_data


# Размеры игрового поля
ROWS = 10
COLS = 10

DELAY = 0.4

# Возможные элементы 🥥🍇🍈🍋🥭🍎🍏🍐🫐🌽🥑🫒🥥 '🔲' # 🔲🔳🔘 💢💥💥💭💢 🟦⬜◼◻◾◽▪💠
ELEMENTS = ['🍏', '🍊', '🍇', '🍓', '🍒', '🍉', '🍍', '🍌']
EMPTY = '🟦'
AVALIABLE = '🟩'
SHIP = '🔳'
BUILDING_SHIP = '🔲'
NEARBYE_AREA = '🟧'

def create_board_sea_fight():
    return [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]

def add_ship_check_avaliability(x, y):
    global context_user_data
    board = context_user_data['board']
    print("add_ship_check_avaliability context_user_data['selected']", context_user_data['selected'])
    print("len(context_user_data['selected']) ", len(context_user_data['selected']))
    if board[x][y] == EMPTY or board[x][y] == AVALIABLE:
        if len(context_user_data['selected']) == 0:
            all_is_clear = True
            for x1 in range(3):
                for y1 in range(3):
                    x2 = x - 1 + x1
                    y2 = y - 1 + y1
                    if x2 >= 0 and x2 < ROWS and y2 >= 0 and y2 < COLS:
                        if board[x2][y2] == SHIP:
                            all_is_clear = False
            return all_is_clear

        if len(context_user_data['selected']) > 0:
            if board[x][y] == AVALIABLE:
                x1 = context_user_data['selected'][0][0]
                x2 = context_user_data['selected'][-1][0]
                y1 = context_user_data['selected'][0][1]
                y2 = context_user_data['selected'][-1][1]
                if (abs(x1 - x) + abs(y1 - y) == 1) or (abs(x2 - x) + abs(y2 - y) == 1):  # Проверка, что элементы соседние
                    return True

    return False

def add_ship_check_is_all_done(length):
    global context_user_data
    if length == 1:
        return True
    if len(context_user_data['selected']) == length:
        return True
    return False

def add_ship():
    global context_user_data
    for sel in context_user_data['selected']:
        x, y = sel
        context_user_data['board'][x][y] = SHIP

def check_direction(direction, x, y, length):
    global context_user_data
    board = context_user_data['board']

    ret = False
    if direction == 'x+':
        for i in range(length):
            if y + i < COLS:
                if board[x][y + i] != SHIP:
                    if y + i + 1 >= COLS:
                        ret = True
                    elif board[x][y + i + 1] != SHIP:
                        ret = True
                    else:
                        ret = False
            else:
                ret = False
    elif direction == 'x-':
        for i in range(length):
            if y - i >= 0:
                if board[x][y - i] != SHIP:
                    if y - i - 1 < 0:
                        ret = True
                    elif board[x][y - i - 1] != SHIP:
                        ret = True
                    else:
                        ret = False
            else:
                ret = False
    elif direction == 'y+':
        for i in range(length):
            if x + i < ROWS:
                if board[x + i][y] != SHIP:
                    if x + i + 1 >= ROWS:
                        ret = True
                    elif board[x + i + 1][y] != SHIP:
                        ret = True
                    else:
                        ret = False
            else:
                ret = False
    elif direction == 'y-':
        for i in range(length):
            if x - i >= 0:
                if board[x - i][y] != SHIP:
                    if x - i - 1 < 0:
                        ret = True
                    elif board[x - i - 1][y] != SHIP:
                        ret = True
                    else:
                        ret = False
            else:
                ret = False
    return ret

def fill_nearbye(board):
    for x in range(ROWS):
        for y in range(COLS):
            if board[x][y] == SHIP:
                for dx in range(-1, 2):
                    for dy in range(-1, 2):
                        if 0 <= x + dx < COLS and 0 <= y + dy < COLS:
                            if board[x + dx][y + dy] == EMPTY:
                                board[x + dx][y + dy] = NEARBYE_AREA
    return board

def add_ship_show_available_continuation(x, y, length):
    global context_user_data
    board = context_user_data['board']
    if length == 1:
        return
    else:
        board = fill_nearbye(board)
        direction = 'all'
        if len(context_user_data['selected']) > 1:
            x1 = context_user_data['selected'][0][0]
            x2 = context_user_data['selected'][-1][0]
            y1 = context_user_data['selected'][0][1]
            y2 = context_user_data['selected'][-1][1]
            if x1 == x2:
                direction = 'x'
            else:
                direction = 'y'
        else:
            x1 = x2 = x
            y1 = y2 = y

            # fill
        for i in range(-length + 1, length):
            if 0 <= x + i < ROWS:
                if board[x + i][y] == EMPTY:
                    board[x + i][y] = AVALIABLE
            if 0 <= y + i < COLS:
                if board[x][y + i] == EMPTY:
                    board[x][y + i] = AVALIABLE
        # check length
        count_x = 0
        count_y = 0
        for i in range(-length + 1, length):
            if 0 <= x + i < ROWS:
                if board[x + i][y] == AVALIABLE or board[x + i][y] == BUILDING_SHIP:
                    count_x += 1
            if 0 <= y + i < COLS:
                if board[x][y + i] == AVALIABLE or board[x][y + i] == BUILDING_SHIP:
                    count_y += 1
        # erasing not liquid directions
        for i in range(-length + 1, length):
            if 0 <= x + i < ROWS:
                if board[x + i][y] == AVALIABLE and (direction == 'x' or count_x < length):
                    board[x + i][y] = EMPTY
            if 0 <= y + i < COLS:
                if board[x][y + i] == AVALIABLE and (direction == 'y' or count_y < length):
                    board[x][y + i] = EMPTY
        # erasing much then needed length
        rest_length = length - len(context_user_data['selected'])
        for i in range(-length + 1, length):
            if 0 <= x + i < ROWS:
                if (board[x + i][y] == AVALIABLE and (x + i < min(x1, x2) - rest_length or x + i > max(x1, x2) + rest_length) ):
                    board[x + i][y] = EMPTY
            if 0 <= y + i < COLS:
                if (board[x][y + i] == AVALIABLE and (y + i < min(y1, y2) - rest_length or y + i > max(y1, y2) + rest_length) ):
                    board[x][y + i] = EMPTY

    clean_board(NEARBYE_AREA)
    context_user_data['board'] = board

def clean_board(goal = AVALIABLE):
    global context_user_data
    board = context_user_data['board']
    for x in range(ROWS):
        for y in range(COLS):
            if board[x][y] == goal:
                board[x][y] = EMPTY
    context_user_data['board'] = board

def print_board_sea_fight(board = None):
    global context_user_data, old_context_user_data
    if board is None:
        board = context_user_data['board']
    print('==== 0  1  2   3  4  5  6  7   8  9 =====')


    col = 0
    for line in board:
        row = f"{col} |"
        for symb in line:
            row += f" {symb}"
        print(row)
        col += 1


def blinking_sea_fight(x, y):
    global context_user_data
    context_user_data['board']

    item = context_user_data['board'][x][y]
    for i in range(3):
        context_user_data['board'][x][y] = BUILDING_SHIP # 🔲🔳🔘 💢💥💥💭💢
        print_board_sea_fight()
        context_user_data['board'][x][y] = item
        time.sleep(DELAY)
        print_board_sea_fight()
        time.sleep(DELAY)

def animate_matches_deletion_sea_fight(matches):
    global context_user_data

    saved_items = []
    for match in matches:
        saved_items.append(context_user_data['board'][match[0]][match[1]])

    for i in range(3):
        for match in matches:
            x = match[0]
            y = match[1]
            context_user_data['board'][x][y] = '💥' # 🔲🔳🔘 💢💥💥💭💢
        print_board_sea_fight(True)
        m = 0
        for match in matches:
            x = match[0]
            y = match[1]
            context_user_data['board'][x][y] = saved_items[m]
            m += 1
        time.sleep(DELAY)
        print_board_sea_fight(True)
        time.sleep(DELAY)


def button_sea_fight(x, y, length = 0):
    global context_user_data

    board = context_user_data['board']
    if len(context_user_data['selected']) > 0 and [x, y] in context_user_data['selected']:
        print(f"selection ({x} {y})")
        # Проверка, что элементы крайние
        x1 = context_user_data['selected'][0][0]
        y1 = context_user_data['selected'][0][1]
        x2 = context_user_data['selected'][-1][0]
        y2 = context_user_data['selected'][-1][1]
        clean_board()
        if abs(x1 - x) + abs(y1 - y) == 0:
            del context_user_data['selected'][0]
            context_user_data['board'][x][y] = EMPTY
            if len(context_user_data['selected']) > 0:
                add_ship_show_available_continuation(x2, y2, length)
        elif abs(x2 - x) + abs(y2 - y) == 0:
            del context_user_data['selected'][-1]
            context_user_data['board'][x][y] = EMPTY
            if len(context_user_data['selected']) > 0:
                add_ship_show_available_continuation(x1, y1, length)
        print_board_sea_fight()
    elif add_ship_check_avaliability(x, y):
        clean_board()
        context_user_data['selected'].append([x, y])
        # print(context_user_data['selected'])
        add_ship_show_available_continuation(x, y, length)
        if add_ship_check_is_all_done(length):
            blinking_sea_fight(x, y)
            add_ship()
            context_user_data['selected'] = []
            print_board_sea_fight()
            return True
        else:
            blinking_sea_fight(x,y)
            context_user_data['board'][x][y] = BUILDING_SHIP
    else:
        print("==== not enought free space =====")
    print_board_sea_fight()

    return False

def test():
    global context_user_data
    context_user_data = {}

    context_user_data['score'] = 0
    context_user_data['selected'] = []
    context_user_data['board'] = create_board_sea_fight()
    context_user_data['ships'] = [
        {'length': 3, 'x': -1, 'y': -1},
        {'length': 2, 'x': -1, 'y': -1},
        {'length': 1, 'x': -1, 'y': -1},
        {'length': 3, 'x': -1, 'y': -1},
        {'length': 4, 'x': -1, 'y': -1},
    ]


    print_board_sea_fight()
    s = None
    for ship in context_user_data['ships']:
        ship_img = ""
        for _ in range(ship['length']):
            ship_img += BUILDING_SHIP
        while s != ' ':
            s = input()
            x, y = s.split(' ')
            x = int(x)
            y = int(y)

            print(f"Adding {ship_img}")
            r = button_sea_fight(x, y, ship['length'])
            if r:
                break


if __name__ == '__main__':
    test()