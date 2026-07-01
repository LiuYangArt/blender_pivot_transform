uniform vec4 color;       // Основной цвет
uniform float edge_smooth; // Параметр сглаживания границы
in vec2 uv;               // Переданные координаты
out vec4 fragColor;

void main() {
    float dist = length(uv); // Расстояние от центра (0,0)
    // Сглаживаем край: при dist ~ 1 начинаем делать прозрачность
    float alpha = smoothstep(1.0 - edge_smooth, 1.0, dist);
    fragColor = vec4(color.rgb, color.a * (1.0 - alpha));
    // Преобразование в цветовое пространство Blender
    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}