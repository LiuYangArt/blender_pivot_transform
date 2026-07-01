uniform mat4 ModelViewProjectionMatrix;
#ifdef USE_WORLD_CLIP_PLANES
uniform mat4 ModelMatrix;

#endif

uniform float lineTh;

vec4 outPos;
vec4 posGen;

in vec3 pos;
in vec3 nor;

void main()
{
    outPos = ModelViewProjectionMatrix * vec4(pos+(nor*lineTh), 1.0);
    gl_Position = outPos;

#ifdef USE_WORLD_CLIP_PLANES
    world_clip_planes_calc_clip_distance((ModelMatrix * vec4(pos, 1.0)).xyz);
#endif
}