/* Вершинный шейдер для рисования пунктирных 3D-линий.
 * Поддерживает любую толщину и 1–2 равномерных цвета.
 * Пунктир вычисляется в экранном пространстве.
 */

#ifndef USE_GPU_SHADER_CREATE_INFO
uniform mat4 ModelViewProjectionMatrix;

/* Размер вьюпорта в пикселях (передаётся из Python). */
uniform vec2 viewport_size;

#ifdef USE_WORLD_CLIP_PLANES
uniform mat4 ModelMatrix;
#endif

in vec3 pos;

/* Координаты начала линии и текущей точки в экранном пространстве. */
flat out vec2 stipple_start; // одно значение на примитив (не интерполируется)
out vec2 stipple_pos;        // интерполируемая позиция текущей вершины
#else
/* В режиме CREATE_INFO параметры приходят из UBO */
flat out vec2 stipple_start;
out vec2 stipple_pos;
#endif

void main()
{
    vec4 pos_4d = vec4(pos, 1.0);
    gl_Position = ModelViewProjectionMatrix * pos_4d;

    /* Проецируем координаты вершины в пространство экрана и масштабируем до пикселей. */
#ifdef USE_GPU_SHADER_CREATE_INFO
    stipple_pos = line_dash_params.viewport_size * 0.5 * (gl_Position.xy / gl_Position.w);
#else
    stipple_pos = viewport_size * 0.5 * (gl_Position.xy / gl_Position.w);
#endif
    stipple_start = stipple_pos; // значение из первой вершины из-за flat

#ifdef USE_WORLD_CLIP_PLANES
    world_clip_planes_calc_clip_distance((ModelMatrix * pos_4d).xyz);
#endif
}
