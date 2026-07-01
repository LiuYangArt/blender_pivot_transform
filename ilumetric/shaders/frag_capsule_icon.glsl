uniform vec4  fillColor;
uniform float width;
uniform float height;
uniform float corner_radius;  // В диапазоне [0, 1]. 1 – максимальное скругление относительно min(width,height)

// Border parameters
uniform vec4 borderColor;
uniform float borderWidth;

// Icon parameters
// Texture used as a mask (black = transparent, white = opaque)
uniform sampler2D iconTexture;
uniform int iconID;
uniform vec4 iconColor;
uniform float iconSize;

in  vec2 uv;
out vec4 fragColor;

const int ATLAS_DIMENSIONS = 10; // Texture atlas dimensions (10x10)

// Calculate UV coordinates for icon in the atlas
vec4 getIconUVCoords(int id) {
    float invDim = 1.0 / float(ATLAS_DIMENSIONS);
    int actualID = id - 1;
    int row = actualID / ATLAS_DIMENSIONS;
    int col = actualID % ATLAS_DIMENSIONS;

    float x1 = float(col) * invDim;
    float y1 = float(row) * invDim;

    return vec4(x1, y1, x1 + invDim, y1 + invDim);
}

void main()
{
    // Используем uv как координаты относительно центра фигуры
    vec2 pos = uv;

    // Вычисляем минимальную размерность и определяем равномерный радиус скругления
    float minDimension = min(width, height);
    // Радиус скругления задаётся как доля от половины минимальной размерности
    float r = corner_radius * 0.5 * minDimension;

    // Полуразмеры прямоугольника
    vec2 rectSize = vec2(width, height) * 0.5;

    // Определяем размер пикселя для сглаживания (чем меньше фигура, тем заметнее артефакты)
    float pixelSize = 0.015 / minDimension;

    // Вычисляем signed distance field (SDF) для закруглённого прямоугольника
    vec2 d = abs(pos) - (rectSize - vec2(r));
    float sdf = length(max(d, vec2(0.0))) + min(max(d.x, d.y), 0.0) - r;

    // Быстрое отбрасывание: если точка далеко за границей фигуры, прекращаем обработку
    if(sdf > 3.0 * pixelSize) {
        discard;
        return;
    }

    // Вычисляем альфа-канал по сглаженному краю фигуры
    float shapeAlpha = 1.0 - smoothstep(-pixelSize, pixelSize, sdf);

    // Расчёт границы: если borderWidth > 0, определяем внутреннее SDF, смещённое на ширину границы
    float borderFactor = 0.0;
    if (borderWidth > 0.0) {
        // Если прибавить borderWidth к SDF, то получим SDF внутренней области (без границы)
        float innerAlpha = 1.0 - smoothstep(-pixelSize, pixelSize, sdf + borderWidth);
        // Граница – это разница между полной фигурой и внутренней областью
        borderFactor = shapeAlpha - innerAlpha;
    }

    // Смешиваем цвета заливки и границы.
    // Если граница есть, смешиваем в пропорции, иначе остаётся fillColor.
    vec4 resultColor = mix(fillColor, borderColor, borderFactor / max(shapeAlpha, 0.0001));
    resultColor.a *= shapeAlpha;

    // Обработка иконки (логика без изменений)
    bool hasIcon = false;
    vec4 iconResult = vec4(0.0);

    if (iconID > 0) {
        // Центрируем иконку по uv
        vec2 localPos = uv;
        float scaledIconSize = (minDimension * 0.5) * iconSize;
        if (abs(localPos.x) <= scaledIconSize && abs(localPos.y) <= scaledIconSize) {
            vec2 iconPos = localPos / scaledIconSize;
            vec4 iconUV = getIconUVCoords(iconID);
            vec2 texCoord = vec2(
                mix(iconUV.x, iconUV.z, (iconPos.x + 1.0) * 0.5),
                mix(iconUV.y, iconUV.w, (iconPos.y + 1.0) * 0.5)
            );
            vec4 texSample = texture(iconTexture, texCoord);
            float blendFactor = dot(texSample.rgb, vec3(0.299, 0.587, 0.114));
            if (blendFactor > 0.0) {
                hasIcon = true;
                iconResult = mix(vec4(0.0), iconColor, blendFactor);
            }
        }
    }

    // Накладываем иконку, сохраняя прозрачность кнопки
    if (hasIcon) {
        float finalAlpha = iconResult.a + resultColor.a * (1.0 - iconResult.a);
        resultColor.rgb = (iconResult.rgb * iconResult.a + resultColor.rgb * resultColor.a * (1.0 - iconResult.a)) / max(finalAlpha, 0.0001);
        resultColor.a = finalAlpha;
    }

    // Преобразуем итоговый цвет в цветовое пространство фреймбуфера
    fragColor = blender_srgb_to_framebuffer_space(resultColor);
}
