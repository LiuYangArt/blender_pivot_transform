/* Шейдер для рисования пунктирных линий с произвольной толщиной.
 * Позволяет рисовать как сплошные линии, так и пунктир с одним или двумя цветами.
 */

#ifndef USE_GPU_SHADER_CREATE_INFO
uniform vec4 color;           // Основной цвет (RGBA)
uniform vec4 color2;          // Второй цвет (RGBA), используется если colors_len > 0

flat in vec2 stipple_start;   // Начальная точка линии в экранных координатах (не интерполируется)
in vec2 stipple_pos;          // Позиция текущего фрагмента (интерполируется)

uniform float dash_width;     // Полная длина одного сегмента (штрих + пробел)
uniform float udash_factor;   // Доля заполненной части штриха [0..1]
uniform int colors_len;       // >0, если разрешён второй цвет

out vec4 fragColor;
#else
/* В режиме CREATE_INFO параметры приходят из UBO */
flat in vec2 stipple_start;
in vec2 stipple_pos;
out vec4 fragColor;
#endif

void main()
{
    /* Расстояние вдоль линии от её начала до текущего фрагмента. */
    float dist_along = distance(stipple_pos, stipple_start);

#ifdef USE_GPU_SHADER_CREATE_INFO
    vec4 color = line_dash_params.color;
    vec4 color2 = line_dash_params.color2;
    float dash_width = line_dash_params.dash_width;
    float udash_factor = line_dash_params.udash_factor;
    int colors_len = line_dash_params.colors_len;
#endif

    /* Сплошная линия при udash_factor >= 1.0. */
    if (udash_factor >= 1.0) {
        fragColor = color;
    }
    else {
        /* Нормализованное положение внутри сегмента [0..1]. */
        float t = fract(dist_along / dash_width);

        if (t <= udash_factor) {
            /* Заполненная часть штриха. */
            fragColor = color;
        }
        else if (colors_len > 0) {
            /* Пробел, но указан второй цвет — рисуем им. */
            fragColor = color2;
        }
        else {
            /* Полностью пропускаем фрагмент. */
            discard;
        }
    }

    /* Перевод в цветовое пространство кадра Blender. */
    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}
