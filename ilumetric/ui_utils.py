__all__ = [
    'is_dark_color_wcag',
    'is_dark_color',
    'draw_line_separator',
]

# цвет
def is_dark_color_wcag(color):
    r, g, b = color
    # Расчет яркости по стандартной формуле WCAG (та же, что и раньше)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    # Рассчитываем контраст с белым и черным цветом
    white_contrast = (1.0 + 0.05) / (luminance + 0.05)
    black_contrast = (luminance + 0.05) / (0.05)
    # Если контраст с белым больше, значит фон темный
    return white_contrast > black_contrast


def is_dark_color(color):
    r, g, b = color
    # Расчет яркости с учетом разной чувствительности глаза к цветам
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    # Установка порога немного ниже 0.5 для лучшего восприятия
    return luminance < 0.5


def draw_line_separator(layout):
    import bpy
    if bpy.app.version >= (4,2,0):
        return layout.separator(type='LINE')
    else:
        return layout.separator()
