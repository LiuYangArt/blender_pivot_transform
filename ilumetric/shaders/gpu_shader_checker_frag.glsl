uniform float size;
uniform vec4 color;
uniform vec4 color2;

out vec4 fragColor;

void main()
{
    vec2 phase = mod(gl_FragCoord.xy, (size * 2));
    if ((phase.x > size && phase.y < size) || (phase.x < size && phase.y > size)) {
    fragColor = color;
    }
    else {
    fragColor = color2;
    }
    fragColor = blender_srgb_to_framebuffer_space(fragColor);
}