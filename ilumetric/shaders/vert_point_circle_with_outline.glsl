#ifndef USE_GPU_SHADER_CREATE_INFO
uniform mat4 ModelViewProjectionMatrix;
uniform float size;
uniform float outlineWidth;
uniform vec4 color;
in vec3 pos;
out vec4 radii;
#endif

void main()
{
    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);
    gl_PointSize = size;

    /* calculate concentric radii in pixels */
    float radius = 0.5 * size;

    /* start at the outside and progress toward the center */
    radii[0] = radius;
    radii[1] = radius - 1.0;
    radii[2] = radius - outlineWidth;
    radii[3] = radius - outlineWidth - 1.0;

    /* convert to PointCoord units */
    radii /= size;


    #ifdef USE_WORLD_CLIP_PLANES
    world_clip_planes_calc_clip_distance((ModelMatrix * vec4(pos, 1.0)).xyz);
#endif
}