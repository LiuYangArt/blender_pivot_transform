uniform float size;
uniform float dot_radius;
uniform vec4 dot_color;
uniform vec4 color;

out vec4 fragColor;

void main()
{
    // Базовая сетка
    vec2 grid_pos = gl_FragCoord.xy / size;

    // Смещение для нечетных строк (создает шестиугольный узор)
    float row_offset = floor(grid_pos.y) * 0.5;
    vec2 cell_pos = vec2(grid_pos.x + row_offset, grid_pos.y);

    // Находим позицию в ячейке
    vec2 cell_center = floor(cell_pos) + 0.5;

    // Смещаем центры ячеек обратно
    cell_center.x -= floor(cell_center.y) * 0.5;

    // Получаем позицию в экранных координатах
    vec2 center_screen = cell_center * size;

    // Расстояние до центра ячейки
    float dist = length(gl_FragCoord.xy - center_screen);

    // Рисуем точку если расстояние меньше радиуса
    if (dist < dot_radius) {
        fragColor = dot_color;
    } else {
        fragColor = color;
    }

    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}