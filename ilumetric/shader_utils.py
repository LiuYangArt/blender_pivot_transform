"""утилиты для создания gpu.types.GPUShader из GLSL файлов

Совместимость с Blender 5:
в Blender 5+ встроенная функция blender_srgb_to_framebuffer_space больше
не доступна автоматически в шейдерах. Этот модуль всегда добавляет
локальную реализацию функции конвертации sRGB, чтобы один и тот же GLSL
корректно работал в Blender 4.x и 5+.
"""

from dataclasses import dataclass
from collections.abc import Sequence as SequenceABC
from functools import lru_cache
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

__all__ = [
    'get_shader',
    'get_compute_shader',
    'clear_shader_cache',
    'bind_uniform_block',
]


@dataclass(frozen=True)
class AttributeSpec:
    """описание одного входного атрибута вершины"""

    name: str
    gpu_type: str


@dataclass(frozen=True)
class VaryingSpec:
    """описание одного varyings между стадиями"""

    name: str
    gpu_type: str
    qualifier: str  # smooth | flat | no_perspective


@dataclass(frozen=True)
class SamplerSpec:
    """описание одного sampler'а"""

    name: str
    gpu_type: str


@dataclass(frozen=True)
class PushConstantSpec:
    """описание uniform-переменной, добавляемой через push_constant"""

    name: str
    gpu_type: str
    size: int = 0


@dataclass(frozen=True)
class FragmentOutputSpec:
    """описание выходной переменной фрагментного шейдера"""

    gpu_type: str
    name: str


@dataclass(frozen=True)
class UniformBufferSpec:
    """описание uniform buffer'а для UBO"""

    slot: int
    type_name: str
    instance_name: str


@dataclass
class GraphicsShaderBuildData:
    """готовый набор данных для GPUShaderCreateInfo"""

    vertex_src: str
    fragment_src: str
    attributes: List[AttributeSpec]
    varyings: List[VaryingSpec]
    samplers: List[SamplerSpec]
    push_constants: List[PushConstantSpec]
    fragment_output: FragmentOutputSpec
    use_world_clip: bool
    writes_frag_depth: bool
    uniform_buffers: List[UniformBufferSpec]
    typedef_source: str


# кеш шейдеров (ключ -> gpu.types.GPUShader)
_SHADER_CACHE: Dict[Tuple, object] = {}

# кеш UBO для шейдеров ((id(shader), block_name) -> GPUUniformBuf)
_UBO_CACHE: Dict[Tuple[int, str], object] = {}

_IO_DECL_RE = re.compile(
    r"""
    (?P<layout>layout\s*\(.*?\)\s*)?
    (?P<qualifiers>(?:(?:flat|smooth|noperspective|centroid|sample|patch|invariant)\s+)*)?
    (?P<direction>in|out)\s+
    (?P<glsl_type>\w+)\s+
    (?P<name>\w+)
    (?:\s*\[\s*\d+\s*\])?
    \s*;
    """,
    re.MULTILINE | re.VERBOSE,
)

_UNIFORM_DECL_RE = re.compile(
    r"uniform\s+(?P<glsl_type>\w+)\s+(?P<name>\w+)(?:\s*\[\s*(?P<size>\d+)\s*\])?\s*;",
    re.MULTILINE,
)

_INTERNAL_MACRO_PREFIXES = (
    '#include',
    'VERTEX_SHADER_CREATE_INFO',
    'FRAGMENT_SHADER_CREATE_INFO',
)

_GLSL_TO_GPU_TYPE = {
    'float': 'FLOAT',
    'vec2': 'VEC2',
    'vec3': 'VEC3',
    'vec4': 'VEC4',
    'int': 'INT',
    'ivec2': 'IVEC2',
    'ivec3': 'IVEC3',
    'ivec4': 'IVEC4',
    'uint': 'UINT',
    'uvec2': 'UVEC2',
    'uvec3': 'UVEC3',
    'uvec4': 'UVEC4',
    'mat3': 'MAT3',
    'mat4': 'MAT4',
    'bool': 'BOOL',
}

_INT_LIKE_GPU_TYPES = {
    'INT',
    'IVEC2',
    'IVEC3',
    'IVEC4',
    'UINT',
    'UVEC2',
    'UVEC3',
    'UVEC4',
    'BOOL',
}

def _bool_to_int(value: Any) -> int:
    return 1 if bool(value) else 0


_UNIFORM_FIELD_TYPES: Dict[str, Tuple[str, int, Callable[[Any], Union[float, int]]]] = {
    'float': ('f', 1, float),
    'vec2': ('f', 2, float),
    'vec3': ('f', 3, float),
    'vec4': ('f', 4, float),
    'mat2': ('f', 4, float),
    'mat3': ('f', 9, float),
    'mat4': ('f', 16, float),
    'int': ('i', 1, int),
    'ivec2': ('i', 2, int),
    'ivec3': ('i', 3, int),
    'ivec4': ('i', 4, int),
    'uint': ('I', 1, int),
    'uvec2': ('I', 2, int),
    'uvec3': ('I', 3, int),
    'uvec4': ('I', 4, int),
    'bool': ('i', 1, _bool_to_int),
}

_GLSL_TO_GPU_SAMPLER_TYPE = {
    'sampler2D': 'FLOAT_2D',
    'isampler2D': 'INT_2D',
    'usampler2D': 'UINT_2D',
    'sampler3D': 'FLOAT_3D',
    'isampler3D': 'INT_3D',
    'usampler3D': 'UINT_3D',
    'samplerCube': 'FLOAT_CUBE',
    'isamplerCube': 'INT_CUBE',
    'usamplerCube': 'UINT_CUBE',
    'sampler2DArray': 'FLOAT_2D_ARRAY',
    'isampler2DArray': 'INT_2D_ARRAY',
    'usampler2DArray': 'UINT_2D_ARRAY',
    'sampler2DShadow': 'FLOAT_2D_SHADOW',
    'samplerCubeShadow': 'FLOAT_CUBE_SHADOW',
    'sampler2DArrayShadow': 'FLOAT_2D_ARRAY_SHADOW',
}

_BUILTIN_UNIFORMS: Dict[str, str] = {
    'ModelViewProjectionMatrix': 'MAT4',
    'ModelMatrix': 'MAT4',
    'ViewMatrix': 'MAT4',
    'ProjectionMatrix': 'MAT4',
    'NormalMatrix': 'MAT3',
    'ModelViewMatrix': 'MAT4',
    'ModelMatrixInverse': 'MAT4',
    'ViewMatrixInverse': 'MAT4',
    'ProjectionMatrixInverse': 'MAT4',
    'ViewProjectionMatrix': 'MAT4',
    'ObjectInfo': 'VEC4',
    'ClipPlane': 'VEC4',
}

_BUILTIN_UNIFORMS_RE = re.compile(
    r"\b(?:"
    + "|".join(map(re.escape, _BUILTIN_UNIFORMS.keys()))
    + r")\b"
)

_COLORSPACE_INCLUDE = """
// Blender 5+ (собственная реализация sRGB конвертации)
#ifndef blender_srgb_to_framebuffer_space
vec4 blender_srgb_to_framebuffer_space(vec4 color) {
    // линеаризация sRGB в линейное цветовое пространство
    vec3 linearRGB;
    float r = color.r;
    float g = color.g;
    float b = color.b;
    linearRGB.r = (r <= 0.04045) ? r / 12.92 : pow((r + 0.055) / 1.055, 2.4);
    linearRGB.g = (g <= 0.04045) ? g / 12.92 : pow((g + 0.055) / 1.055, 2.4);
    linearRGB.b = (b <= 0.04045) ? b / 12.92 : pow((b + 0.055) / 1.055, 2.4);
    return vec4(linearRGB, color.a);
}
#endif
"""

# typedef для UBO пунктирных линий
_LINE_DASH_UBO_TYPEDEF = """
struct LineDashParams {
    vec4 color;
    vec4 color2;
    vec2 viewport_size;
    float dash_width;
    float udash_factor;
    int colors_len;
    int _pad0;
    int _pad1;
    int _pad2;
};
"""

# маппинг (vert_name, frag_name) -> список UBO для этой пары шейдеров
_SHADER_UBO_OVERRIDES: Dict[Tuple[str, str], List[UniformBufferSpec]] = {
    ('gpu_shader_3D_line_dashed_uniform_color_vert', 'gpu_shader_2D_line_dashed_frag'): [
        UniformBufferSpec(
            slot=0,
            type_name='LineDashParams',
            instance_name='line_dash_params',
        ),
    ],
}


def clear_shader_cache() -> None:
    """очищает внутренний кеш созданных шейдеров и UBO"""

    _SHADER_CACHE.clear()
    _UBO_CACHE.clear()


@lru_cache()
def _shaders_dir() -> str:
    """возвращает абсолютный путь к папке `ilumetric/shaders`"""

    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'shaders')


def _read_glsl(name: str) -> str:
    """читает GLSL-файл по имени"""

    path = os.path.join(_shaders_dir(), f'{name}.glsl')
    with open(path, 'r', encoding='utf-8') as handle:
        return handle.read()


def _normalize_defines(
    defines: Optional[Union[Dict[str, Union[str, int]], Iterable[str]]],
) -> List[Tuple[str, str]]:
    """приводит define'ы к списку пар (name, value)"""

    if not defines:
        return []
    if isinstance(defines, dict):
        return [(str(name), str(value)) for name, value in defines.items()]
    return [(str(name), '1') for name in defines]


def _ensure_colorspace_include(fragment_src: str) -> str:
    """гарантирует наличие blender_srgb_to_framebuffer_space"""

    if '#ifndef blender_srgb_to_framebuffer_space' in fragment_src:
        return fragment_src
    if 'blender_srgb_to_framebuffer_space' in fragment_src:
        return _COLORSPACE_INCLUDE + fragment_src
    return fragment_src


def _detect_world_clip(vertex_src: str) -> bool:
    """проверяет наличие ClipPlane и необходимость USE_WORLD_CLIP_PLANES"""

    return bool(re.search(r"uniform\s+vec4\s+ClipPlane\s*;", vertex_src))


def _iter_io_decls(src: str) -> Iterable[Tuple[str, str, str, Tuple[str, ...]]]:
    """итерирует по объявлениям in/out"""

    for match in _IO_DECL_RE.finditer(src):
        qualifiers_str = match.group('qualifiers') or ''
        qualifiers = tuple(
            token.lower() for token in qualifiers_str.split() if token
        )
        yield (
            match.group('direction'),
            match.group('glsl_type'),
            match.group('name'),
            qualifiers,
        )


def _iter_uniform_decls(src: str) -> Iterable[Tuple[str, str, int]]:
    """итерирует по uniform-декларациям"""

    for match in _UNIFORM_DECL_RE.finditer(src):
        size = match.group('size')
        yield match.group('glsl_type'), match.group('name'), int(size or 0)


def _collect_attributes(vertex_src: str) -> List[AttributeSpec]:
    """возвращает описания vertex атрибутов"""

    attrs: List[AttributeSpec] = []
    seen: Set[str] = set()
    for direction, glsl_type, name, _ in _iter_io_decls(vertex_src):
        if direction != 'in' or name in seen:
            continue
        gpu_type = _GLSL_TO_GPU_TYPE.get(glsl_type)
        if not gpu_type:
            continue
        seen.add(name)
        attrs.append(AttributeSpec(name=name, gpu_type=gpu_type))
    return attrs


def _decide_interp(qualifiers: Iterable[str], gpu_type: str) -> str:
    """подбирает qualifier для GPUStageInterfaceInfo"""

    lowered = {q.lower() for q in qualifiers}
    if 'flat' in lowered or gpu_type in _INT_LIKE_GPU_TYPES:
        return 'flat'
    if 'noperspective' in lowered or 'no_perspective' in lowered:
        return 'no_perspective'
    if 'smooth' in lowered:
        return 'smooth'
    return 'smooth'


def _collect_varyings(vertex_src: str, fragment_src: str) -> List[VaryingSpec]:
    """возвращает список varyings между стадиями"""

    registry: Dict[str, Tuple[str, Set[str]]] = {}

    def _store(src: str, expected_direction: str) -> None:
        for direction, glsl_type, name, qualifiers in _iter_io_decls(src):
            if direction != expected_direction:
                continue
            entry = registry.get(name)
            if entry is None:
                entry = (glsl_type, set())
                registry[name] = entry
            entry[1].update(qualifiers)

    _store(vertex_src, 'out')
    _store(fragment_src, 'in')

    varyings: List[VaryingSpec] = []
    for name, (glsl_type, qualifiers) in registry.items():
        gpu_type = _GLSL_TO_GPU_TYPE.get(glsl_type)
        if not gpu_type:
            continue
        qualifier = _decide_interp(qualifiers, gpu_type)
        varyings.append(VaryingSpec(name=name, gpu_type=gpu_type, qualifier=qualifier))
    return varyings


def _collect_samplers(*sources: str) -> List[SamplerSpec]:
    """возвращает список sampler-переменных"""

    specs: List[SamplerSpec] = []
    seen: Set[str] = set()
    for src in sources:
        for glsl_type, name, _ in _iter_uniform_decls(src):
            if name in seen:
                continue
            gpu_type = _GLSL_TO_GPU_SAMPLER_TYPE.get(glsl_type)
            if not gpu_type:
                continue
            seen.add(name)
            specs.append(SamplerSpec(name=name, gpu_type=gpu_type))
    return specs


def _detect_fragment_output(fragment_src: str) -> FragmentOutputSpec:
    """возвращает тип и имя выходного параметра фрагмента"""

    match = re.search(
        r"(?:layout\s*\(.*?\)\s*)?out\s+(?P<glsl_type>\w+)\s+(?P<name>\w+)",
        fragment_src,
    )
    if not match:
        return FragmentOutputSpec(gpu_type='VEC4', name='fragColor')
    gpu_type = _GLSL_TO_GPU_TYPE.get(match.group('glsl_type'), 'VEC4')
    return FragmentOutputSpec(gpu_type=gpu_type, name=match.group('name'))


def _collect_builtin_uniforms(vertex_src: str, fragment_src: str) -> List[PushConstantSpec]:
    """возвращает список встроенных uniform'ов, найденных в GLSL"""

    found: List[PushConstantSpec] = []
    seen: Set[str] = set()
    for src in (vertex_src, fragment_src):
        for match in _BUILTIN_UNIFORMS_RE.finditer(src):
            name = match.group(0)
            if name in seen:
                continue
            seen.add(name)
            found.append(PushConstantSpec(name=name, gpu_type=_BUILTIN_UNIFORMS[name]))
    return found


def _collect_push_constants(
    vertex_src: str,
    fragment_src: str,
    *,
    exclude: Set[str],
) -> List[PushConstantSpec]:
    """собирает пользовательские uniform'ы для push_constant"""

    specs: List[PushConstantSpec] = []
    seen: Set[str] = set()
    for src in (vertex_src, fragment_src):
        for glsl_type, name, size in _iter_uniform_decls(src):
            if name in exclude or name in seen:
                continue
            if glsl_type in _GLSL_TO_GPU_SAMPLER_TYPE:
                continue
            gpu_type = _GLSL_TO_GPU_TYPE.get(glsl_type)
            if not gpu_type:
                continue
            specs.append(PushConstantSpec(name=name, gpu_type=gpu_type, size=size))
            seen.add(name)
    return specs


def _build_uniform_regex(names: Sequence[str]) -> Optional[re.Pattern[str]]:
    """возвращает регулярку для uniform-деклараций заданных имён"""

    if not names:
        return None
    joined = '|'.join(map(re.escape, names))
    return re.compile(
        rf"uniform\s+\w+\s+(?:{joined})(?:\s*\[\s*\d+\s*\])?\s*;",
    )


def _build_io_regex(names: Sequence[str], *, directions: Sequence[str]) -> Optional[re.Pattern[str]]:
    """возвращает регулярку для in/out объявлений"""

    if not names:
        return None
    joined_names = '|'.join(map(re.escape, names))
    joined_dirs = '|'.join(directions)
    qualifier = r"(?:flat|smooth|noperspective|centroid|sample|patch|invariant)\s+"
    layout = r"(?:layout\s*\(.*?\)\s*)?"
    return re.compile(
        rf"{layout}(?:{qualifier})*"
        rf"(?:{joined_dirs})\s+\w+\s+(?:{joined_names})(?:\s*\[\s*\d+\s*\])?\s*;",
    )


def _build_fragment_out_regex(name: str) -> re.Pattern[str]:
    """возвращает регулярку для строки с out переменной"""

    layout = r"(?:layout\s*\(.*?\)\s*)?"
    return re.compile(rf"{layout}out\s+\w+\s+{re.escape(name)}(?:\s*\[\s*\d+\s*\])?\s*;")


def _strip_decls(
    src: str,
    *,
    attr_names: Sequence[str] = (),
    varying_names: Sequence[str] = (),
    sampler_names: Sequence[str] = (),
    push_names: Sequence[str] = (),
    frag_out_name: Optional[str] = None,
) -> str:
    """удаляет декларации ресурсов, описанных через GPUShaderCreateInfo"""

    if not src:
        return src

    attr_re = _build_io_regex(attr_names, directions=('in',))
    varying_re = _build_io_regex(varying_names, directions=('in', 'out'))
    sampler_re = _build_uniform_regex(sampler_names)
    push_re = _build_uniform_regex(push_names)
    frag_out_re = _build_fragment_out_regex(frag_out_name) if frag_out_name else None
    removal_patterns = tuple(
        pattern
        for pattern in (attr_re, varying_re, sampler_re, push_re, frag_out_re)
        if pattern is not None
    )

    kept: List[str] = []
    for line in src.splitlines():
        code_part = line.split('//', 1)[0].strip()
        if not code_part:
            kept.append(line)
            continue
        if code_part.startswith(_INTERNAL_MACRO_PREFIXES):
            continue
        if any(pattern.fullmatch(code_part) for pattern in removal_patterns):
            continue
        kept.append(line)
    return "\n".join(kept)


def _prepend_prolog(src: str, *, use_world_clip: bool) -> str:
    """вставляет #define USE_GPU_SHADER_CREATE_INFO и USE_WORLD_CLIP_PLANES"""

    lines: List[str] = []
    if 'USE_GPU_SHADER_CREATE_INFO' not in src:
        lines.append('#define USE_GPU_SHADER_CREATE_INFO')
    if use_world_clip and 'USE_WORLD_CLIP_PLANES' not in src:
        lines.append('#define USE_WORLD_CLIP_PLANES')
    if not lines:
        return src
    return "\n".join(lines) + "\n" + src


def _apply_define(info: object, name: str, value: Optional[str] = None) -> None:
    """безопасно добавляет define к GPUShaderCreateInfo"""

    try:
        if value is None:
            info.define(name)
        else:
            info.define(name, value)
    except Exception:
        pass


def _build_graphics_data(
    vertex_src: str,
    fragment_src: str,
    *,
    vert_name: str = '',
    frag_name: str = '',
) -> GraphicsShaderBuildData:
    """формирует все данные для GPUShaderCreateInfo"""

    use_world_clip = _detect_world_clip(vertex_src)
    attributes = _collect_attributes(vertex_src)
    varyings = _collect_varyings(vertex_src, fragment_src)
    samplers = _collect_samplers(vertex_src, fragment_src)
    fragment_output = _detect_fragment_output(fragment_src)
    builtin_uniforms = _collect_builtin_uniforms(vertex_src, fragment_src)
    sampler_names = [spec.name for spec in samplers]
    builtin_names = {spec.name for spec in builtin_uniforms}

    # проверяем, нужен ли UBO для этой пары шейдеров
    shader_key = (vert_name, frag_name)
    ubo_specs = list(_SHADER_UBO_OVERRIDES.get(shader_key, []))

    # если есть UBO override, собираем имена полей структуры для исключения
    ubo_field_names: Set[str] = set()
    typedef_source = ''
    if ubo_specs:
        # для линий это struct LineDashParams { vec4 color; vec4 color2; ... }
        typedef_source = _LINE_DASH_UBO_TYPEDEF
        # извлекаем имена полей из typedef
        # (простой парсинг: ищем строки вида "type name;")
        for line in typedef_source.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith('//') and stripped != '}' and stripped != 'struct LineDashParams {':
                tokens = stripped.rstrip(';').split()
                if len(tokens) >= 2 and not tokens[1].startswith('_'):
                    ubo_field_names.add(tokens[1])

    push_constants = _collect_push_constants(
        vertex_src,
        fragment_src,
        exclude=builtin_names | set(sampler_names) | ubo_field_names,
    )
    all_push = builtin_uniforms + push_constants
    uniform_names = [spec.name for spec in all_push]

    # добавляем имена UBO-полей к списку uniform'ов для вычистки из GLSL
    all_uniform_names = uniform_names + list(ubo_field_names)

    vertex_clean = _strip_decls(
        vertex_src,
        attr_names=[spec.name for spec in attributes],
        varying_names=[spec.name for spec in varyings],
        sampler_names=sampler_names,
        push_names=all_uniform_names,
        frag_out_name=fragment_output.name,
    )
    fragment_clean = _strip_decls(
        fragment_src,
        attr_names=(),
        varying_names=[spec.name for spec in varyings],
        sampler_names=sampler_names,
        push_names=all_uniform_names,
        frag_out_name=fragment_output.name,
    )

    vertex_final = _prepend_prolog(vertex_clean, use_world_clip=use_world_clip)
    fragment_final = _prepend_prolog(fragment_clean, use_world_clip=use_world_clip)

    writes_frag_depth = 'gl_FragDepth' in fragment_final

    return GraphicsShaderBuildData(
        vertex_src=vertex_final,
        fragment_src=fragment_final,
        attributes=attributes,
        varyings=varyings,
        samplers=samplers,
        push_constants=all_push,
        fragment_output=fragment_output,
        use_world_clip=use_world_clip,
        writes_frag_depth=writes_frag_depth,
        uniform_buffers=ubo_specs,
        typedef_source=typedef_source,
    )


def _create_graphics_info(
    data: GraphicsShaderBuildData,
    *,
    defines: Optional[List[Tuple[str, str]]] = None,
    depth_write: Optional[str] = None,
) -> object:
    """создаёт GPUShaderCreateInfo на основе подготовленных данных"""

    from gpu.types import GPUShaderCreateInfo, GPUStageInterfaceInfo

    info = GPUShaderCreateInfo()

    # typedef для UBO (если нужен)
    if data.typedef_source:
        info.typedef_source(data.typedef_source)

    for idx, attr in enumerate(data.attributes):
        info.vertex_in(idx, attr.gpu_type, attr.name)

    if data.varyings:
        iface = GPUStageInterfaceInfo("iface_auto")
        for varying in data.varyings:
            getattr(iface, varying.qualifier)(varying.gpu_type, varying.name)
        info.vertex_out(iface)

    info.fragment_out(0, data.fragment_output.gpu_type, data.fragment_output.name)

    for bind, sampler in enumerate(data.samplers):
        info.sampler(bind, sampler.gpu_type, sampler.name)

    # uniform buffers (UBO)
    for ubo in data.uniform_buffers:
        info.uniform_buf(ubo.slot, ubo.type_name, ubo.instance_name)

    for push in data.push_constants:
        info.push_constant(push.gpu_type, push.name, push.size)

    for name, value in defines or []:
        _apply_define(info, name, value)

    if depth_write:
        info.depth_write(depth_write)
    elif data.writes_frag_depth:
        info.depth_write('ANY')

    info.vertex_source(data.vertex_src)
    info.fragment_source(data.fragment_src)

    if data.use_world_clip:
        _apply_define(info, 'USE_WORLD_CLIP_PLANES')

    return info


def get_shader(
    vert_name: str,
    frag_name: str,
    *,
    defines: Optional[Union[Dict[str, Union[str, int]], Iterable[str]]] = None,
    depth_write: Optional[str] = None,
) -> object:
    """создаёт gpu.types.GPUShader из пары GLSL файлов"""

    normalized_defines = _normalize_defines(defines)
    cache_key = (
        'graphics',
        vert_name,
        frag_name,
        tuple(normalized_defines),
        depth_write or '',
    )
    cached = _SHADER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    import gpu

    vertex_src = _read_glsl(vert_name)
    fragment_src = _ensure_colorspace_include(_read_glsl(frag_name))

    build = _build_graphics_data(
        vertex_src,
        fragment_src,
        vert_name=vert_name,
        frag_name=frag_name,
    )
    info = _create_graphics_info(build, defines=normalized_defines, depth_write=depth_write)

    shader = gpu.shader.create_from_info(info)
    _SHADER_CACHE[cache_key] = shader
    return shader


def get_compute_shader(
    comp_name: str,
    *,
    defines: Optional[Union[Dict[str, Union[str, int]], Iterable[str]]] = None,
    local_group_size: Tuple[int, int, int] = (8, 8, 1),
) -> object:
    """создаёт gpu.types.GPUShader для compute-шейдера"""

    normalized_defines = _normalize_defines(defines)
    cache_key = (
        'compute',
        comp_name,
        tuple(normalized_defines),
        local_group_size,
    )
    cached = _SHADER_CACHE.get(cache_key)
    if cached is not None:
        return cached

    import gpu
    from gpu.types import GPUShaderCreateInfo

    comp_src = _read_glsl(comp_name)

    info = GPUShaderCreateInfo()
    info.local_group_size(*local_group_size)

    for name, value in normalized_defines:
        _apply_define(info, name, value)

    info.compute_source(comp_src)

    shader = gpu.shader.create_from_info(info)
    _SHADER_CACHE[cache_key] = shader
    return shader


def bind_uniform_block(
    shader: object,
    *,
    block_name: str,
    payload: Optional[Union[bytes, bytearray, memoryview]] = None,
    fields: Optional[Sequence[Union[Tuple[str, Any], Dict[str, Any]]]] = None,
) -> None:
    """привязывает UBO к uniform-блоку шейдера и при необходимости упаковывает данные

    Args:
        shader: gpu.types.GPUShader созданный через get_shader/get_compute_shader
        block_name: имя uniform-блока в GLSL
        payload: готовый набор байт, если вы уже собрали данные самостоятельно
        fields: последовательность описаний полей, если удобнее передать структуры,
            а не байты. Каждый элемент — tuple или dict с ключами:
            • type: GLSL-тип ('float', 'vec4', 'int', 'mat4', ...). Регистр не важен
            • value: скаляр или последовательность длиной как у типа
            • fill (необязательно): чем заполнить недостающие компоненты, если value
              короче нужной длины. Например, {'type': 'vec4', 'value': (r, g, b), 'fill': 1.0}
            • Для паддинга используйте {'type': 'pad', 'value': 12}, чтобы добавить 12 пустых байт.

            Алгоритм просто идёт по списку сверху вниз, поэтому порядок элементов должен
            полностью повторять layout шейдера (std140/std430 выравнивание нужно соблюдать вручную).

    Raises:
        ValueError: если не переданы payload/fields или описание типа некорректно
    """
    from gpu.types import GPUUniformBuf
    import struct

    if payload is not None and fields is not None:
        raise ValueError("нужно передать либо payload, либо fields, но не оба сразу")
    if payload is None and not fields:
        raise ValueError("не переданы данные для UBO")

    def _is_sequence(value: Any) -> bool:
        return isinstance(value, SequenceABC) and not isinstance(value, (str, bytes, bytearray))

    def _normalize_field_spec(spec: Union[Tuple[str, Any], Dict[str, Any]]) -> Tuple[str, Any, Optional[Any]]:
        if isinstance(spec, dict):
            type_name = spec.get('type')
            value = spec.get('value')
            fill = spec.get('fill')
        else:
            if len(spec) != 2:
                raise ValueError(f"tuple field spec должен состоять из (type, value), получено: {spec!r}")
            type_name, value = spec
            fill = None
        if not type_name:
            raise ValueError("field spec должен содержать тип")
        return str(type_name).lower(), value, fill

    def _pack_fields(field_specs: Sequence[Union[Tuple[str, Any], Dict[str, Any]]]) -> bytes:
        fmt_parts: List[str] = []
        packed_values: List[Union[float, int]] = []

        for spec in field_specs:
            type_name, value, fill = _normalize_field_spec(spec)
            if type_name in {'pad', 'padding'}:
                pad_size = int(value)
                if pad_size <= 0:
                    raise ValueError("padding должен быть положительным числом байт")
                fmt_parts.append(f'{pad_size}x')
                continue

            type_info = _UNIFORM_FIELD_TYPES.get(type_name)
            if type_info is None:
                raise ValueError(f"неизвестный GLSL-тип '{type_name}'")

            fmt_char, component_count, caster = type_info

            if component_count == 1 and not _is_sequence(value):
                components = (value,)
            else:
                if not _is_sequence(value):
                    raise ValueError(f"значение для {type_name} должно быть последовательностью длиной {component_count}")
                components = tuple(value)

            if len(components) > component_count:
                raise ValueError(f"{type_name} ожидает {component_count} компонентов, получено {len(components)}")
            if len(components) < component_count:
                if fill is None:
                    raise ValueError(
                        f"{type_name} ожидает {component_count} компонентов, получено {len(components)}. "
                        "Либо добавьте недостающие значения, либо укажите ключ fill."
                    )
                missing = component_count - len(components)
                components = components + tuple(fill for _ in range(missing))

            fmt_parts.append(f'{component_count}{fmt_char}')
            packed_values.extend(caster(component) for component in components)

        fmt = '<' + ''.join(fmt_parts)
        return struct.pack(fmt, *packed_values)

    if payload is None:
        payload_bytes = _pack_fields(fields or ())
    elif isinstance(payload, memoryview):
        payload_bytes = payload.tobytes()
    elif isinstance(payload, (bytes, bytearray)):
        payload_bytes = bytes(payload)
    else:
        payload_bytes = bytes(payload)

    cache_key = (id(shader), block_name)
    ubo = _UBO_CACHE.get(cache_key)
    if ubo is None:
        ubo = GPUUniformBuf(payload_bytes)
        _UBO_CACHE[cache_key] = ubo
    else:
        ubo.update(payload_bytes)

    shader.bind()
    shader.uniform_block(block_name, ubo)



