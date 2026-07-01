// uniform vec4  fillColor;
// uniform float width;
// uniform float height;
// uniform float corner_radius;  // Controls how rounded the corners are

// // Border parameters
// uniform vec4 borderColor;
// uniform float borderWidth;

// // Icon parameters
// // Texture used as a mask (black = transparent, white = opaque)
// uniform sampler2D iconTexture;
// uniform int iconID;
// uniform vec4 iconColor;
// uniform float iconSize;

// in  vec2 uv;
// out vec4 fragColor;

// const int ATLAS_DIMENSIONS = 4; // Texture atlas dimensions (10x10)

// // Calculate UV coordinates for icon in the atlas
// vec4 getIconUVCoords(int id) {
//     // Optimized - avoid division where possible
//     float invDim = 1.0 / float(ATLAS_DIMENSIONS);
//     int actualID = id - 1;
//     int row = actualID / ATLAS_DIMENSIONS;
//     int col = actualID % ATLAS_DIMENSIONS;

//     float x1 = float(col) * invDim;
//     float y1 = float(row) * invDim;

//     return vec4(x1, y1, x1 + invDim, y1 + invDim);
// }

// // Computes the superformula value for a normalized position
// float superFormula(vec2 pos, float n) {
//     return pow(abs(pos.x), n) + pow(abs(pos.y), n);
// }

// void main()
// {
//     // Use uv coordinates directly, as they are already centered at (0,0)
//     // for the equilateral triangle defined by your vertices
//     vec2 pos = uv;

//     // Get minimum dimension for proper scaling
//     float minDimension = min(width, height);

//     // Scale based on minimum dimension for consistent shape
//     pos /= minDimension * 0.5;

//     // Compute n parameter for the supercircle
//     // Map corner_radius from [0, 1] to a useful n value
//     // n = 2 is circle, higher values make it more rectangular
//     float n = mix(10.0, 2.0, corner_radius);

//     // Calculate distance using superellipse formula
//     float superValue = superFormula(pos, n);

//     // Define screen-space pixel size for AA (adjusted by shape size)
//     float pixelSize = 0.08 / minDimension;

//     // Distance from the exact edge (1.0 is exactly on edge)
//     float distFromEdge = abs(superValue - 1.0);

//     // Quick discard for efficiency (with safety margin)
//     if (superValue > 1.0 + 3.0 * pixelSize) {
//         discard;
//         return;
//     }

//     // Calculate main shape alpha
//     float shapeAlpha;
//     if (superValue <= 1.0) {
//         // Inside shape - fully opaque
//         shapeAlpha = 1.0;
//     } else {
//         // Outside shape but within AA region - apply smooth falloff
//         shapeAlpha = 1.0 - smoothstep(0.0, pixelSize, superValue - 1.0);
//     }

//     // If we're completely transparent, discard
//     if (shapeAlpha <= 0.0) {
//         discard;
//         return;
//     }

//     // Border calculations
//     float borderFactor = 0.0;

//     // Only process border if we have a border width
//     if (borderWidth > 0.0) {
//         // Scale border width relative to shape size
//         float scaledBorderWidth = borderWidth / minDimension;

//         // Calculate inner shape distance where border begins
//         float innerBorder = 1.0 - scaledBorderWidth * 2.0; // Scale for superformula

//         // Inside the shape and near the border region
//         if (superValue >= innerBorder && superValue <= 1.0) {
//             // Calculate distance from inner border
//             float borderDist = (superValue - innerBorder) / (1.0 - innerBorder);

//             // Apply smooth transition for the border
//             borderFactor = smoothstep(0.0, pixelSize / scaledBorderWidth, borderDist);
//         }

//         // For very thin borders, ensure they're visible at the edge
//         if (superValue > 1.0 - pixelSize && superValue < 1.0 + pixelSize) {
//             borderFactor = max(borderFactor, 1.0 - abs(superValue - 1.0) / pixelSize);
//         }
//     }

//     // Mix fill and border colors
//     vec4 resultColor = mix(fillColor, borderColor, borderFactor);

//     // Apply icon if specified
//     bool hasIcon = false;
//     vec4 iconResult = vec4(0.0);

//     if (iconID > 0) {
//         // Position icon at the center (0,0) of the triangle
//         vec2 localPos = uv;

//         // Calculate icon size based on minimum dimension
//         float scaledIconSize = (minDimension * 0.5) * iconSize;

//         // Check if we're inside the icon area
//         if (abs(localPos.x) <= scaledIconSize && abs(localPos.y) <= scaledIconSize) {
//             // Normalize icon coordinates
//             vec2 iconPos = localPos / scaledIconSize;

//             // Get UV coordinates for the icon in the atlas
//             vec4 iconUV = getIconUVCoords(iconID);

//             // Transform to texture coordinates
//             vec2 texCoord = vec2(
//                 mix(iconUV.x, iconUV.z, (iconPos.x + 1.0) * 0.5),
//                 mix(iconUV.y, iconUV.w, (iconPos.y + 1.0) * 0.5)
//             );

//             // Sample texture and calculate blend factor
//             vec4 texSample = texture(iconTexture, texCoord);

//             // Optimized luminance calculation for RGB
//             float blendFactor = dot(texSample.rgb, vec3(0.299, 0.587, 0.114));

//             // Mix colors only if there's some texture influence
//             if (blendFactor > 0.0) {
//                 hasIcon = true;
//                 iconResult = mix(vec4(0.0), iconColor, blendFactor);
//             }
//         }
//     }

//     // Apply alpha from anti-aliasing to button color
//     resultColor.a *= shapeAlpha;

//     // Overlay icon on top, preserving button transparency
//     if (hasIcon) {
//         // Correct icon overlay maintaining transparency
//         float finalAlpha = iconResult.a + resultColor.a * (1.0 - iconResult.a);
//         resultColor.rgb = (iconResult.rgb * iconResult.a + resultColor.rgb * resultColor.a * (1.0 - iconResult.a)) / max(finalAlpha, 0.0001);
//         resultColor.a = finalAlpha;
//     }

//     // Apply resulting color with color space conversion
//     fragColor = blender_srgb_to_framebuffer_space(resultColor);
// }





// --- Uniforms ---
uniform vec4  fillColor;
uniform float width;
uniform float height;
// Теперь corner_radius [0, 1] контролирует геометрический радиус скругления
uniform float corner_radius;

// Border parameters (SDF style)
uniform vec4 borderColor;
uniform float borderWidth; // Border width in world/pixel units

// Icon parameters
uniform sampler2D iconTexture;
uniform int iconID;
uniform vec4 iconColor;
uniform float iconSize; // Relative size (0 to 1 of shape radius)

// --- Дополнительные параметры для формы угла ---
// Вы можете сделать это uniform'ом, если хотите менять динамически
// 2.0 = круглые углы, 4.0 = "squircle", > 4.0 = более квадратные углы
const float corner_exponent = 4.0; // Фиксируем для squircle-подобных углов

// --- In/Out ---
in  vec2 uv; // Should be world-space coordinates centered at the shape's origin
out vec4 fragColor;

// --- Constants ---
const float PI = 3.14159265359;
const float TWO_PI = 6.28318530718;
const int ATLAS_DIMENSIONS = 4; // Texture atlas dimensions (e.g., 4x4)
const float AA_WIDTH = 1.0; // Anti-aliasing width in screen pixels (adjust as needed)
const float EPSILON = 1e-6; // Small value for safe math

// --- Functions ---

// Calculate UV coordinates for icon in the atlas
vec4 getIconUVCoords(int id) {
    float invDim = 1.0 / float(ATLAS_DIMENSIONS);
    int actualID = id - 1;
    if (actualID < 0 || id == 0) return vec4(0.0); // Handle invalid ID
    int row = actualID / ATLAS_DIMENSIONS;
    int col = actualID % ATLAS_DIMENSIONS;
    float x1 = float(col) * invDim;
    float y1 = float(row) * invDim;
    return vec4(x1, y1, x1 + invDim, y1 + invDim);
}

// --- SDF Functions (скопированы из первого шейдера) ---

// Общая Lp норма - используется как fallback
float LpNormGeneral(vec2 v, float p) {
    if (p <= 0.0) return max(abs(v.x), abs(v.y)); // L-infinity
    vec2 vt = abs(v);
    // Используем max с EPSILON для стабильности pow при нулевых значениях
    float px = pow(max(vt.x, EPSILON), p);
    float py = pow(max(vt.y, EPSILON), p);
    // Используем max с EPSILON для стабильности 1/p при p->0
    float invP = (p > EPSILON) ? 1.0 / p : 0.0;
    return pow(px + py, invP);
}

// SDF функция с оптимизацией для exponent = 2 и 4
// p: точка в локальных координатах прямоугольника
// b: половина размеров прямоугольника (vec2)
// r: радиус скругления
// exponent: показатель степени для формы угла (2=круг, 4=squircle)
float sdRoundedSuperellipseBoxOptimized(vec2 p, vec2 b, float r, float exponent) {
    vec2 q = abs(p) - b + r; // Смещение к центру угловой кривой
    vec2 q_safe = max(q, 0.0); // Координаты для расчета нормы угла (только в квадранте угла)

    float cornerDist;

    // ОПТИМИЗАЦИЯ: Частные случаи для exponent
    if (abs(exponent - 2.0) < 0.01) { // Экспонента == 2 (Круглые углы)
        cornerDist = length(q_safe);
    } else if (abs(exponent - 4.0) < 0.01) { // Экспонента == 4 (Squircle углы)
        // Быстрое возведение в 4 степень
        vec2 q2 = q_safe * q_safe;
        vec2 q4 = q2 * q2;
        // Быстрый корень 4-й степени (sqrt(sqrt))
        // Добавим EPSILON для стабильности при нуле
        cornerDist = sqrt(sqrt(q4.x + q4.y + EPSILON));
    } else { // Общий случай (медленнее)
        cornerDist = LpNormGeneral(q_safe, exponent);
    }

    // distance = расстояние до центра скругления + расстояние вдоль края - радиус
    float edgeDist = min(max(q.x, q.y), 0.0); // Расстояние до ближайшего края (<= 0)
    return cornerDist + edgeDist - r;
}


// --- Main ---
void main()
{
    // --- 1. Shape Parameters ---
    vec2 half_dims = vec2(width * 0.5, height * 0.5);

    // Преобразуем corner_radius [0, 1] в эффективный геометрический радиус скругления 'r'
    // Максимальный возможный радиус - половина меньшей стороны
    float max_possible_radius = min(half_dims.x, half_dims.y);
    // Отображаем [0, 1] в [0, max_possible_radius]
    float effective_corner_radius = clamp(corner_radius * max_possible_radius, 0.0, max_possible_radius);

    // Используем константу corner_exponent (задана выше как 4.0)

    // --- 2. Calculate SDF ---
    // Используем SDF для скруглённого прямоугольника/суперэллипса
    float sd = sdRoundedSuperellipseBoxOptimized(uv, half_dims, effective_corner_radius, corner_exponent);

    // --- 3. Calculate Outer Coverage (Shape + Border) ---
    // Адаптивная ширина AA на основе градиента SDF (может дать более четкие края)
    //float aa = AA_WIDTH * length(vec2(dFdx(sd), dFdy(sd))); // Вариант с dFdx/dFdy
    // Простой вариант с фиксированной шириной AA в мировых координатах
    // Нужно подобрать подходящее значение AA_WIDTH, возможно, не 1.0, а что-то меньшее,
    // зависящее от масштаба ваших координат uv. Начните с малого (0.01?) и увеличивайте.
    // Или используйте размер пикселя: AA_WIDTH / min(width, height) ?
    float aa = AA_WIDTH * ( isinf(dFdx(sd)) || isinf(dFdy(sd)) ? 0.01 : length(vec2(dFdx(sd), dFdy(sd))) ); // Более безопасный расчет AA
    // Если dFdx/dFdy не работают или дают плохие результаты, вернитесь к фиксированному значению:
    // float aa = 0.5; // Подберите это значение экспериментально!

    float coverage_outer = smoothstep(aa, -aa, sd);

    // --- 4. Early discard if fully transparent ---
    if (coverage_outer <= 0.0) {
        discard;
        return;
    }

    // --- 5. Calculate Fill Coverage ---
    float coverage_fill = 0.0;
    if (borderWidth > 0.0) {
        // sd_fill_boundary представляет внутренний край обводки
        float sd_fill_boundary = sd + borderWidth;
        coverage_fill = smoothstep(aa, -aa, sd_fill_boundary);
    } else {
        coverage_fill = coverage_outer; // Нет обводки
    }
    coverage_fill = min(coverage_fill, coverage_outer); // Убедимся, что заливка не выходит за пределы

    // --- 6. Determine Base Color (Fill + Border) ---
    vec4 mixed_color = mix(borderColor, fillColor, coverage_fill);
    vec4 baseColor = vec4(mixed_color.rgb, mixed_color.a * coverage_outer);


    // --- 7. Add Icon ---
    vec4 iconResultColor = vec4(0.0);
    bool hasIcon = false;

    if (iconID > 0 && iconSize > 0.0) {
        float min_half_dim = min(half_dims.x, half_dims.y);
        // Используем эффективный радиус формы для масштаба иконки, чтобы она вписывалась
        // Учитываем и радиус скругления
        float effective_radius = min_half_dim;
        float iconTargetSize = max(0.0, effective_radius * 2.0 * iconSize);
        float halfIconSize = iconTargetSize * 0.5;

        vec2 iconLocalPos = uv;

        if (abs(iconLocalPos.x) <= halfIconSize + aa && abs(iconLocalPos.y) <= halfIconSize + aa) {
            vec2 iconNormPos = iconLocalPos / max(halfIconSize, EPSILON);

            if (max(abs(iconNormPos.x), abs(iconNormPos.y)) <= 1.0 + (aa / max(halfIconSize, EPSILON))) {
                vec4 iconUV = getIconUVCoords(iconID);
                if (iconUV.z > iconUV.x && iconUV.w > iconUV.y) {
                    vec2 texCoord = vec2(
                        mix(iconUV.x, iconUV.z, (iconNormPos.x + 1.0) * 0.5),
                        mix(iconUV.y, iconUV.w, (iconNormPos.y + 1.0) * 0.5)
                    );
                    float iconMask = texture(iconTexture, texCoord).r;
                    iconResultColor = iconColor * iconMask;
                    hasIcon = (iconResultColor.a > 0.01);
                }
            }
        }
    }

    // --- 8. Final Blending (Icon over Base Shape) ---
    vec4 finalColor;
    if (hasIcon) {
        float iconAlpha = clamp(iconResultColor.a, 0.0, 1.0);
        float baseAlpha = baseColor.a;
        float combinedAlpha = iconAlpha + baseAlpha * (1.0 - iconAlpha);
        vec3 combinedRGB = vec3(0.0);
        if (combinedAlpha > EPSILON) {
             combinedRGB = (iconResultColor.rgb * iconAlpha + baseColor.rgb * baseAlpha * (1.0 - iconAlpha)) / combinedAlpha;
        }
        finalColor = vec4(combinedRGB, combinedAlpha);
    } else {
        finalColor = baseColor;
    }

    // --- 9. Output ---
    fragColor = blender_srgb_to_framebuffer_space(finalColor); // Если нужно

}