#ifndef USE_GPU_SHADER_CREATE_INFO
uniform vec4 color;
in vec2 radii;
out vec4 fragColor;
#endif

void main()
{
    float dist = length(gl_PointCoord - vec2(0.5));

    /* Плавный переход от центра к краю точки */
    if (dist > radii[0]) {
        discard; // За пределами внешнего радиуса
    }

    /* Вычисление прозрачности на основе расстояния */
    fragColor = color;

    if (dist > radii[1]) {
        /* Плавное уменьшение прозрачности в зоне размытия */
        float t = smoothstep(radii[0], radii[1], dist);
        fragColor.a *= t;
    }

    if (fragColor.a == 0.0) {
        discard;
    }

    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}