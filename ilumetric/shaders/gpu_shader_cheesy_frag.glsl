uniform float size;
uniform float hole_radius;
uniform vec4 hole_color;
uniform vec4 color;

out vec4 fragColor;

// Простая функция для псевдослучайных чисел
float random(vec2 co) {
    return fract(sin(dot(co.xy, vec2(12.9898, 78.233))) * 43758.5453);
}

void main()
{
    // Инициализируем фрагмент цветом сыра
    fragColor = color;

    // Текущая позиция
    vec2 pos = gl_FragCoord.xy;

    // Проверяем ячейки вокруг текущей позиции
    // Это позволит дыркам объединяться на границах ячеек
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            // Находим базовую ячейку
            vec2 grid_pos = pos / size;
            vec2 cell_id = floor(grid_pos) + vec2(x, y);
            vec2 cell_center = cell_id + 0.5;

            // Добавляем случайное смещение к центру
            float rand_x = random(cell_id) * 0.8 - 0.4;
            float rand_y = random(cell_id + vec2(1.0, 1.0)) * 0.8 - 0.4;
            cell_center += vec2(rand_x, rand_y);

            // Позиция в экранных координатах
            vec2 center_screen = cell_center * size;

            // Расстояние до центра
            float dist = length(pos - center_screen);

            // Случайный радиус дырки
            float rand_size = random(cell_id + vec2(0.5, 0.5));
            float actual_radius = hole_radius * (0.4 + 0.6 * rand_size);

            // Решаем, будет ли дырка (примерно 60% шанс)
            float make_hole = step(0.4, random(cell_id + vec2(2.0, 3.0)));

            // Если эта точка внутри дырки, устанавливаем цвет дырки
            if (dist < actual_radius && make_hole > 0.5) {
                fragColor = hole_color;
            }
        }
    }

    // Если доступна функция коррекции цвета, используем её
    // Если нет - просто закомментируйте эту строку
    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}