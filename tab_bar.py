# pyright: reportMissingImports=false
from datetime import datetime
from kitty.boss import get_boss
from kitty.fast_data_types import Screen, add_timer, get_options
from kitty.utils import color_as_int
from kitty.tab_bar import (
    DrawData,
    ExtraData,
    Formatter,
    TabBarData,
    as_rgb,
    draw_attributed_string,
    draw_title,
)

class Colors:
    def __init__(self, opts):
        self.opts = opts
        self.color_as_int = color_as_int

        # Standard terminal colors (0-15)
        self.black = as_rgb(color_as_int(opts.color0))
        self.red = as_rgb(color_as_int(opts.color1))
        self.green = as_rgb(color_as_int(opts.color2))
        self.yellow = as_rgb(color_as_int(opts.color3))
        self.blue = as_rgb(color_as_int(opts.color4))
        self.magenta = as_rgb(color_as_int(opts.color5))
        self.cyan = as_rgb(color_as_int(opts.color6))
        self.white = as_rgb(color_as_int(opts.color7))
        self.bright_black = as_rgb(color_as_int(opts.color8))
        self.bright_red = as_rgb(color_as_int(opts.color9))
        self.bright_green = as_rgb(color_as_int(opts.color10))
        self.bright_yellow = as_rgb(color_as_int(opts.color11))
        self.bright_blue = as_rgb(color_as_int(opts.color12))
        self.bright_magenta = as_rgb(color_as_int(opts.color13))
        self.bright_cyan = as_rgb(color_as_int(opts.color14))
        self.bright_white = as_rgb(color_as_int(opts.color15))

        # Aliases
        self.gray = self.bright_black

        # Custom component colors - define all of them here to be used nicely later on in this script
        # main icon color
        self.icon_fg = self.bright_black
        self.icon_bg = self.blue

        # battery cell related colors
        self.battery_bg = self.bright_white
        self.battery_text = self.bright_black
        self.battery_low = self.red
        self.battery_charging = self.cyan
        self.battery_full = self.green

        # clock and date colors
        self.clock_bg = self.magenta
        self.date_bg = self.green
        self.clock_color = self.bright_white
        self.date_color = self.bright_white


opts = get_options()
colors = Colors(opts)

# Define icons
class Icons:
    def __init__(self, colors):
        self.battery = {
            "unplugged": {
                10: "󰁺",
                20: "󰁻",
                30: "󰁼",
                40: "󰁽",
                50: "󰁾",
                60: "󰁿",
                70: "󰂀",
                80: "󰂁",
                90: "󰂂",
                100: "󰁹",
            },
            "plugged": {
                1: "󰂄",
            },
            "unplugged_colors": {
                15: colors.battery_low,
                16: colors.battery_text,
            },
            "plugged_colors": {
                15: colors.battery_low,
                16: colors.battery_charging,
                99: colors.battery_charging,
                100: colors.battery_full,
            }
        }
        self.shell_icon = "  "
        self.date_icon = ""
        self.time_icon = ""
        self.separator_symbol = ""
        self.soft_separator_symbol = ""

icons = Icons(colors)

RIGHT_MARGIN = 0
REFRESH_TIME = 1


def _draw_icon(screen: Screen, index: int) -> int:
    if index != 1:
        return 0
    fg, bg = screen.cursor.fg, screen.cursor.bg
    screen.cursor.fg = colors.icon_fg
    screen.cursor.bg = colors.icon_bg
    screen.draw(icons.shell_icon)
    screen.cursor.fg, screen.cursor.bg = colors.icon_bg, bg
    screen.draw("")
    screen.cursor.fg, screen.cursor.bg = fg, bg
    screen.cursor.x = len(icons.shell_icon)+1 # +1 because of the separator above
    return screen.cursor.x


def _draw_left_status(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_title_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    if screen.cursor.x >= screen.columns - right_status_length:
        return screen.cursor.x
    tab_bg = screen.cursor.bg
    tab_fg = screen.cursor.fg
    default_bg = as_rgb(int(draw_data.default_bg))
    if extra_data.next_tab:
        next_tab_bg = as_rgb(draw_data.tab_bg(extra_data.next_tab))
        needs_soft_separator = next_tab_bg == tab_bg
    else:
        next_tab_bg = default_bg
        needs_soft_separator = False
    if screen.cursor.x <= len(icons.shell_icon):
        screen.cursor.x = len(icons.shell_icon)
    screen.draw(" ")
    screen.cursor.bg = tab_bg
    draw_title(draw_data, screen, tab, index)
    if not needs_soft_separator:
        screen.draw(" ")
        screen.cursor.fg = tab_bg
        screen.cursor.bg = next_tab_bg
        screen.draw(icons.separator_symbol)
    else:
        prev_fg = screen.cursor.fg
        if tab_bg == tab_fg:
            screen.cursor.fg = default_bg
        elif tab_bg != default_bg:
            c1 = draw_data.inactive_bg.contrast(draw_data.default_bg)
            c2 = draw_data.inactive_bg.contrast(draw_data.inactive_fg)
            if c1 < c2:
                screen.cursor.fg = default_bg
        screen.draw(" " + icons.soft_separator_symbol)
        screen.cursor.fg = prev_fg
    end = screen.cursor.x
    return end


def _draw_right_status(screen: Screen, is_last: bool, cells: list) -> int:
    if not is_last:
        return 0
    draw_attributed_string(Formatter.reset, screen)
    screen.cursor.x = screen.columns - right_status_length
    screen.cursor.fg = 0
    # draw the sep first
    for bg_color, color, status in cells:
        sep = ""
        if "%" not in status:
            sep = " " + sep
        screen.cursor.fg = bg_color
        screen.draw(f"{sep}")
        screen.cursor.bg = bg_color
        screen.cursor.fg = color
        screen.draw(status)
    screen.cursor.bg = 0
    return screen.cursor.x


def _redraw_tab_bar(_):
    tm = get_boss().active_tab_manager
    if tm is not None:
        tm.mark_tab_bar_dirty()


def get_battery_cells() -> list:
    try:
        with open("/sys/class/power_supply/BAT0/status", "r") as f:
            status = f.read()
        with open("/sys/class/power_supply/BAT0/capacity", "r") as f:
            percent = int(f.read())

        def pick_by_threshold(table: dict[int, int], pct: int) -> int:
            # choose the largest key that is still ≤ pct
            keys = sorted(table)
            for k in reversed(keys):
                if pct >= k:
                    return table[k]
            return table[keys[0]]          # pct is below the smallest threshold

        if status == "Discharging\n":
            icon_color = pick_by_threshold(icons.battery["unplugged_colors"], percent)
            icon = pick_by_threshold(icons.battery["unplugged"], percent)
        elif status == "Not charging\n":
            icon_color = pick_by_threshold(icons.battery["unplugged_colors"], percent)
            icon = icons.battery["plugged"][1]
        else:
            icon_color = pick_by_threshold(icons.battery["plugged_colors"], percent)
            icon = icons.battery["plugged"][1]

        bg_color = colors.battery_bg
        icon_cell = (bg_color, icon_color, icon)
        percent_cell = (bg_color, colors.battery_text, f"{percent}%")

        return [icon_cell, percent_cell]
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Got error in battery cell: {e}")
        return []


timer_id = None
right_status_length = -1

def draw_tab(
    draw_data: DrawData,
    screen: Screen,
    tab: TabBarData,
    before: int,
    max_title_length: int,
    index: int,
    is_last: bool,
    extra_data: ExtraData,
) -> int:
    global timer_id
    global right_status_length
    if timer_id is None:
        timer_id = add_timer(_redraw_tab_bar, REFRESH_TIME, True)
    clock = datetime.now().strftime(f"{icons.time_icon} %H:%M:%S")
    date = datetime.now().strftime(f"{icons.date_icon} %d.%m.%Y")
    cells = get_battery_cells()
    cells.append((colors.clock_bg, colors.clock_color, clock))
    cells.append((colors.date_bg, colors.date_color, date))
    right_status_length = RIGHT_MARGIN
    for _, _, status in cells:
        # 2-wide separator for every cell except the % one which is battery
        sep_len = 1 if "%" in status else 2
        right_status_length += len(status) + sep_len

    _draw_icon(screen, index)
    _draw_left_status(
        draw_data,
        screen,
        tab,
        before,
        max_title_length,
        index,
        is_last,
        extra_data,
    )
    _draw_right_status(
        screen,
        is_last,
        cells,
    )
    return screen.cursor.x
