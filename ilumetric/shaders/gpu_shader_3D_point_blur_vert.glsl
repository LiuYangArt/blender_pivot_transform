#ifndef USE_GPU_SHADER_CREATE_INFO
uniform mat4 ModelViewProjectionMatrix;
uniform float size;
uniform float blurAmount; // Параметр для контроля размытия
in vec3 pos;
out vec2 radii; // Упрощено до двух значений
#endif

void main()
{
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
    gl_PointSize = size;

    /* расчет радиуса в пикселях */
    float radius = 0.5 * size;

    /* внешний и внутренний радиусы для размытия */
    radii[0] = radius;
    radii[1] = radius * (1.0 - blurAmount); // Контроль размытия

    /* преобразование в единицы PointCoord */
    radii /= size;

#ifdef USE_WORLD_CLIP_PLANES
    world_clip_planes_calc_clip_distance((ModelMatrix * vec4(pos, 1.0)).xyz);
#endif
}