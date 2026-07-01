// // скругленный сектор но без суперэлипса
// uniform vec4  fillColor;
// uniform float inner_radius;
// uniform float outer_radius;
// uniform float angle;
// uniform float rotation;
// uniform float corner_radius; // Абсолютный радиус скругления
// // corner_exponent не используется в этой версии

// // Параметры текстуры
// uniform sampler2D iconTexture;
// uniform int iconID;
// uniform vec4 iconColor;
// uniform float iconSize;

// // --- Входы/Выходы ---
// in  vec2 uv;
// out vec4 fragColor;

// // --- Константы ---
// const float PI = 3.14159265359;
// const float TWO_PI = 6.28318530718;
// const int ATLAS_DIMENSIONS = 10;
// const float screen_pixel_estimate = 0.001;
// const float AA_WIDTH = screen_pixel_estimate * 1.5;

// // --- Функции ---
// vec4 getIconUVCoords(int id) {
//     float invDim = 1.0 / float(ATLAS_DIMENSIONS);
//     int actualID = id - 1;
//     if (actualID < 0 || id == 0) return vec4(0.0);
//     int row = actualID / ATLAS_DIMENSIONS;
//     int col = actualID % ATLAS_DIMENSIONS;
//     float x1 = float(col) * invDim;
//     float y1 = float(row) * invDim;
//     return vec4(x1, y1, x1 + invDim, y1 + invDim);
// }

// // Стандартная функция SDF для прямоугольника со скругленными углами
// // p: точка относительно центра прямоугольника
// // b: половины размеров прямоугольника (half_width, half_height)
// // r: радиус скругления углов
// // Возвращает расстояние до границы (отрицательное внутри)
// float sdRoundedBox(vec2 p, vec2 b, float r) {
//     // Расстояние до смещенных граней (+r)
//     vec2 q = abs(p) - b + r;
//     // length(max(q, 0.0)) : расстояние от внешних скругленных углов (если q.x>0 и q.y>0)
//     // min(max(q.x, q.y), 0.0) : отрицательное расстояние от ближайшей прямой грани (если точка внутри прямоугольника с скруглением)
//     return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
// }

// // Вспомогательная функция для вычисления разницы углов с учетом переноса через 0
// // Возвращает угол a относительно ref в диапазоне [-PI, PI]
// float angleDiff(float a, float ref) {
//     // Нормализуем углы в [0, TWO_PI] перед вычитанием для стабильности
//     float a_norm = mod(a + TWO_PI, TWO_PI);
//     float ref_norm = mod(ref + TWO_PI, TWO_PI);
//     float diff = a_norm - ref_norm;
//     // Приводим разницу к диапазону [-PI, PI]
//     if (diff > PI) diff -= TWO_PI;
//     if (diff <= -PI) diff += TWO_PI;
//     return diff;
// }


// // --- Основная функция ---
// void main()
// {
//     // --- 1. Базовые расчеты ---
//     float r = length(uv);
//     float theta = atan(uv.y, uv.x); // Результат в [-PI, PI]

//     // --- Ранний выход по радиусу (оптимизация) ---
//     if (r < inner_radius - corner_radius - AA_WIDTH || r > outer_radius + corner_radius + AA_WIDTH) {
//         discard;
//         return;
//     }

//     // --- 2. Параметры сектора ---
//     float halfAngle = angle * 0.5;
//     // rotation - центральный угол сегмента

//     // --- 3. Преобразование координат в локальную систему ---
//     // Ось Y' направлена радиально, ось X' - по касательной (против часовой)
//     float mid_radius = (inner_radius + outer_radius) * 0.5;
//     float local_y = r - mid_radius; // Радиальное смещение от центра

//     // Угловое смещение от центрального угла rotation в радианах
//     float local_theta_rad = angleDiff(theta, rotation); // Угол в [-PI, PI]

//     // Аппроксимация смещения по дуге (ось X')
//     // Используем r для большей точности на краях, чем mid_radius
//     float local_x = local_theta_rad * r;
//     vec2 local_p = vec2(local_x, local_y);

//     // --- 4. Определение параметров для sdRoundedBox ---
//     // Половина высоты "прямоугольника" (по радиусу)
//     float box_half_height = (outer_radius - inner_radius) * 0.5;
//     // Половина ширины "прямоугольника" (по дуге)
//     // Используем r для вычисления ширины дуги
//     float box_half_width = halfAngle * r;
//     vec2 box_half_dims = vec2(box_half_width, box_half_height);

//     // Ограничиваем corner_radius, чтобы он был не больше половины меньшей стороны
//     float max_possible_radius = min(box_half_width, box_half_height);
//     // Добавим небольшой допуск AA_WIDTH к максимальному радиусу,
//     // чтобы скругление корректно работало на границе AA
//     float effective_corner_radius = clamp(corner_radius, 0.0, max_possible_radius + AA_WIDTH);


//     // --- 5. Вычисление SDF ---
//     float sd_final = sdRoundedBox(local_p, box_half_dims, effective_corner_radius);

//     // --- 6. Расчет покрытия (Coverage) на основе SDF ---
//     // Альфа = 1 внутри (sd < -AA), 0 снаружи (sd > AA)
//     float coverage = smoothstep(AA_WIDTH, -AA_WIDTH, sd_final);


//     // --- Окончательный выход, если точка вне фигуры ---
//      if (coverage <= 0.0) { // Используем 0.0, т.к. smoothstep дает точный 0
//          discard;
//          return;
//      }

//     // --- 7. Базовый цвет ---
//     vec4 baseColor = vec4(fillColor.rgb, fillColor.a * coverage);

//     // --- 8. Добавление ИКОНКИ ---
//     vec4 iconResultColor = vec4(0.0);
//     bool hasIcon = false;
//     if (iconID > 0) {
//         float segmentWidth = outer_radius - inner_radius;
//         float iconTargetSize = max(0.0, segmentWidth * iconSize);
//         float halfIconSize = iconTargetSize * 0.5;
//         vec2 segmentCenter = vec2(mid_radius * cos(rotation), mid_radius * sin(rotation));
//         vec2 iconLocalPos = uv - segmentCenter;

//         if (abs(iconLocalPos.x) <= halfIconSize + AA_WIDTH && abs(iconLocalPos.y) <= halfIconSize + AA_WIDTH) {
//              vec2 iconNormPos = iconLocalPos / max(halfIconSize, 0.0001);
//              vec4 iconUV = getIconUVCoords(iconID);
//              if (iconUV.z > iconUV.x) {
//                  vec2 texCoord = vec2(
//                      mix(iconUV.x, iconUV.z, (iconNormPos.x + 1.0) * 0.5),
//                      mix(iconUV.y, iconUV.w, (iconNormPos.y + 1.0) * 0.5)
//                  );
//                  if (texCoord.x >= iconUV.x && texCoord.x <= iconUV.z &&
//                      texCoord.y >= iconUV.y && texCoord.y <= iconUV.w)
//                  {
//                      float iconMask = texture(iconTexture, texCoord).r;
//                      iconResultColor = iconColor * iconMask;
//                      hasIcon = (iconResultColor.a > 0.01);
//                  }
//              }
//         }
//     }

//     // --- 9. Финальное смешивание и вывод ---
//     vec4 finalColor;
//     if (hasIcon) {
//         float iconAlpha = clamp(iconResultColor.a, 0.0, 1.0);
//         float baseAlpha = clamp(baseColor.a, 0.0, 1.0);
//         float combinedAlpha = iconAlpha + baseAlpha * (1.0 - iconAlpha);
//         vec3 combinedRGB = vec3(0.0);
//         if (combinedAlpha > 0.0001) {
//               combinedRGB = (iconResultColor.rgb * iconAlpha + baseColor.rgb * baseAlpha * (1.0 - iconAlpha)) / combinedAlpha;
//         }
//         finalColor = vec4(combinedRGB, combinedAlpha);
//     } else {
//         finalColor = baseColor;
//     }

//     fragColor = blender_srgb_to_framebuffer_space(finalColor);

//     // --- Отладка ---
//     // fragColor = vec4(vec3(coverage), 1.0);
//     // fragColor = vec4(vec3(0.5 + sd_final * 5.0), 1.0);
//     // fragColor = vec4(abs(local_p) / box_half_dims, 0.0 , 1.0);
// }





// TODO убрать старый код






// --- Uniforms ---
uniform vec4  fillColor;
uniform vec4  borderColor;
uniform float inner_radius;
uniform float outer_radius;
uniform float angle;
uniform float rotation;
uniform float corner_radius;
uniform float corner_exponent = 4.0; // Ожидаемые значения: 2.0, 4.0 или другие
uniform float borderWidth;

// Параметры текстуры
uniform sampler2D iconTexture;
uniform int iconID;
uniform vec4 iconColor;
uniform float iconSize;

// --- Входы/Выходы ---
in  vec2 uv;
out vec4 fragColor;

// --- Константы ---
const float PI = 3.14159265359;
const float TWO_PI = 6.28318530718;
const int ATLAS_DIMENSIONS = 10;
const float AA_WIDTH = 0.0015;
const float EPSILON = 1e-9; // Малая величина для избежания деления на ноль и log(0)

// --- Функции ---
vec4 getIconUVCoords(int id) {
    float invDim = 1.0 / float(ATLAS_DIMENSIONS);
    int actualID = id - 1;
    if (actualID < 0 || id == 0) return vec4(0.0);
    int row = actualID / ATLAS_DIMENSIONS;
    int col = actualID % ATLAS_DIMENSIONS;
    float x1 = float(col) * invDim;
    float y1 = float(row) * invDim;
    return vec4(x1, y1, x1 + invDim, y1 + invDim);
}


float angleDiff(float a, float ref) {
    float diff = mod(a - ref + PI, TWO_PI) - PI; // Более короткий вариант
    return diff;
}

// Общая Lp норма - используется как fallback
float LpNormGeneral(vec2 v, float p) {
    if (p <= 0.0) return max(abs(v.x), abs(v.y));
    vec2 vt = abs(v);
    float px = pow(max(vt.x, EPSILON), p);
    float py = pow(max(vt.y, EPSILON), p);
    float invP = (p > EPSILON) ? 1.0 / p : 0.0;
    return pow(px + py, invP);
}

// SDF функция с оптимизацией для exponent = 2 и 4
float sdRoundedSuperellipseBoxOptimized(vec2 p, vec2 b, float r, float exponent) {
    vec2 q = abs(p) - b + r;
    vec2 q_safe = max(q, 0.0); // Координаты для расчета нормы угла

    float cornerDist;

    // ОПТИМИЗАЦИЯ: Частные случаи для exponent
    if (abs(exponent - 2.0) < 0.01) { // Экспонента == 2 (Круг)
        cornerDist = length(q_safe);
    } else if (abs(exponent - 4.0) < 0.01) { // Экспонента == 4 (Squircle)
        // Быстрое возведение в 4 степень
        vec2 q2 = q_safe * q_safe;
        vec2 q4 = q2 * q2;
        // Быстрый корень 4-й степени (sqrt(sqrt))
        cornerDist = sqrt(sqrt(q4.x + q4.y));
    } else { // Общий случай (медленнее)
        cornerDist = LpNormGeneral(q_safe, exponent);
    }

    float edgeDist = min(max(q.x, q.y), 0.0);
    return cornerDist + edgeDist - r;
}


// --- Основная функция ---
void main()
{
    // --- 1. Базовые расчеты ---
    float r = length(uv);
    // Оптимизация: Вычисляем r*r один раз, если нужен только он, но нам нужен r
    float theta = atan(uv.y, uv.x);

    // --- Ранний выход по радиусу ---
    // Оставим как есть, sqrt здесь оправдан для раннего выхода
    if (r < inner_radius - corner_radius - AA_WIDTH || r > outer_radius + corner_radius + AA_WIDTH) {
         discard;
         return;
    }

    // --- 2. Параметры сектора ---
    float halfAngle = angle * 0.5;

    // --- 3. Преобразование координат в локальную систему ---
    float mid_radius = (inner_radius + outer_radius) * 0.5;
    float local_y = r - mid_radius;
    float local_theta_rad = angleDiff(theta, rotation);
    float local_x = local_theta_rad * r;
    vec2 local_p = vec2(local_x, local_y);

    // --- 4. Определение параметров для SDF ---
    float box_half_height = (outer_radius - inner_radius) * 0.5;
    // Оптимизация: Можно вычислить halfAngle*r до clamp'а, если r не сильно меняется? Нет, оставим.
    float box_half_width = halfAngle * r;
    vec2 box_half_dims = vec2(box_half_width, box_half_height);

    // Ограничение corner_radius
    // Оптимизация: вычислять max_possible_radius только если corner_radius > 0 ? Незначительно.
    float max_possible_radius = min(box_half_width, box_half_height);
    float effective_corner_radius = clamp(corner_radius, 0.0, max_possible_radius + AA_WIDTH);

    // --- 5. Вычисление SDF с ОПТИМИЗИРОВАННОЙ функцией ---
    float sd_outer = sdRoundedSuperellipseBoxOptimized(local_p, box_half_dims, effective_corner_radius, corner_exponent);

    // --- 6. Расчет покрытия (Coverage) для ВНЕШНЕЙ формы ---
    float coverage_outer = smoothstep(AA_WIDTH, -AA_WIDTH, sd_outer);

    // --- Окончательный выход ---
     if (coverage_outer <= 0.0) {
         discard;
         return;
     }

    // --- 7. Расчет покрытия для ВНУТРЕННЕЙ области (ЗАЛИВКИ) ---
    float coverage_fill = 0.0;
    // ОПТИМИЗАЦИЯ: вынести if (borderWidth > 0.0) как можно выше? Не даст выигрыша здесь.
    // Условие на uniform'е - ветка выполняется одинаково для всех пикселей.
    if (borderWidth > 0.0) {
        float sd_fill_boundary = sd_outer + borderWidth;
        coverage_fill = smoothstep(AA_WIDTH, -AA_WIDTH, sd_fill_boundary);
        // clamp здесь не обязателен, smoothstep уже возвращает [0,1]
        // coverage_fill = clamp(coverage_fill, 0.0, 1.0);
    } else {
        coverage_fill = coverage_outer; // Покрытие заливки = общему покрытию
    }

    // --- 8. Определение базового цвета ---
    // ОПТИМИЗАЦИЯ: mix - быстрая операция
    vec4 mixed_color = mix(borderColor, fillColor, coverage_fill);
    vec4 baseColor = vec4(mixed_color.rgb, mixed_color.a * coverage_outer);


    // --- 9. Добавление ИКОНКИ ---
    // ОПТИМИЗАЦИЯ: Условие if(iconID > 0) на uniform'е - очень эффективно.
    vec4 iconResultColor = vec4(0.0);
    bool hasIcon = false;
    if (iconID > 0) {
        // Вычисления внутри этой ветки выполняются только когда есть иконка
        float segmentWidth = outer_radius - inner_radius; // Переменная нужна? Да, для iconTargetSize
        float iconTargetSize = max(0.0, segmentWidth * iconSize);
        float halfIconSize = iconTargetSize * 0.5;
        // ОПТИМИЗАЦИЯ: Вычислить segmentCenter только если iconID > 0 ? Уже сделано.
        vec2 segmentCenter = vec2(mid_radius * cos(rotation), mid_radius * sin(rotation)); // cos/sin здесь неизбежны
        vec2 iconLocalPos = uv - segmentCenter;

        // ОПТИМИЗАЦИЯ: Проверка if(abs...) может вызвать расхождение, но часто приемлемо.
        if (abs(iconLocalPos.x) <= halfIconSize + AA_WIDTH && abs(iconLocalPos.y) <= halfIconSize + AA_WIDTH) {
             // Деление может быть не самым дешевым, но нужно
             vec2 iconNormPos = iconLocalPos / max(halfIconSize, EPSILON); // Защита от деления на ноль
             vec4 iconUV = getIconUVCoords(iconID); // Дешево
             if (iconUV.z > iconUV.x) { // Дешево
                 vec2 texCoord = vec2(
                     mix(iconUV.x, iconUV.z, (iconNormPos.x + 1.0) * 0.5),
                     mix(iconUV.y, iconUV.w, (iconNormPos.y + 1.0) * 0.5)
                 ); // mix дешево
                 // Проверка if(texCoord...) - небольшое расхождение возможно
                 if (texCoord.x >= iconUV.x && texCoord.x <= iconUV.z &&
                     texCoord.y >= iconUV.y && texCoord.y <= iconUV.w)
                 {
                     // ОПТИМИЗАЦИЯ: texture() - основная стоимость здесь. Неизбежно.
                     float iconMask = texture(iconTexture, texCoord).r;
                     iconResultColor = iconColor * iconMask; // Дешево
                     hasIcon = (iconResultColor.a > 0.01); // Дешево
                 }
             }
        }
    }

    // --- 10. Финальное смешивание и вывод ---
    // ОПТИМИЗАЦИЯ: Ветка if(hasIcon) может вызывать расхождение.
    // Альтернатива без if:
    // float hasIconF = float(hasIcon);
    // float finalCombinedAlpha = mix(baseColor.a, iconAlpha + baseColor.a * (1.0 - iconAlpha), hasIconF);
    // vec3 finalCombinedRGB = mix(baseColor.rgb, (iconResultColor.rgb * iconAlpha + baseColor.rgb * baseColor.a * (1.0 - iconAlpha)) / max(finalCombinedAlpha, EPSILON), hasIconF);
    // finalColor = vec4(finalCombinedRGB, finalCombinedAlpha);
    // Оставляем if для читаемости, современные компиляторы могут его хорошо обработать.
    vec4 finalColor;
    if (hasIcon) {
        float iconAlpha = clamp(iconResultColor.a, 0.0, 1.0); // clamp дешевый
        float baseAlpha = baseColor.a; // Уже содержит clamp неявно из smoothstep
        float combinedAlpha = iconAlpha + baseAlpha * (1.0 - iconAlpha);
        vec3 combinedRGB = vec3(0.0);
         // Деление может быть не самым дешевым
        if (combinedAlpha > EPSILON) {
              combinedRGB = (iconResultColor.rgb * iconAlpha + baseColor.rgb * baseAlpha * (1.0 - iconAlpha)) / combinedAlpha;
        }
        finalColor = vec4(combinedRGB, combinedAlpha);
    } else {
        finalColor = baseColor;
    }

    fragColor = blender_srgb_to_framebuffer_space(finalColor);
}