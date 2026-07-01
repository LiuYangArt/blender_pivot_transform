uniform vec4 color;
uniform vec3 light;

in vec3 normal;

out vec4 fragColor;

void main()
{
    fragColor = color;
    fragColor.xyz *= clamp(dot(normalize(normal), light), 0.2, 1.0);
    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}