uniform vec4 color;         // Основной цвет
uniform float edge_smooth;    // Параметр сглаживания краёв
uniform float inner_radius;   // Радиус внутренней окружности (начало кольца)
in vec2 uv;                 // Переданные координаты
out vec4 fragColor;

void main() {
    float dist = length(uv); // Расстояние от центра (0,0)

    // Сглаживание внутреннего края: значение 0 до inner_radius и 1 после inner_radius + edge_smooth
    float inner = smoothstep(inner_radius, inner_radius + edge_smooth, dist);
    // Сглаживание внешнего края: значение 1 до (1.0 - edge_smooth) и 0 после 1.0
    float outer = smoothstep(1.0 - edge_smooth, 1.0, dist);

    // Маска кольца: внутри кольца альфа=1, на границах плавное затухание до 0
    float mask = inner * (1.0 - outer);

    fragColor = vec4(color.rgb, color.a * mask);
    // Преобразование в цветовое пространство Blender
    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}